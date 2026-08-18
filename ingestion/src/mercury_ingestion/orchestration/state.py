"""Mercury's generic historical-replay state model (ADR-010).

This module owns the append-only replay-state domain model persisted and
queried by ``HistoricalReplayRunner``. It is deliberately independent of
any persistence technology: no BigQuery, no GCS, no connectors, no
source simulation, and no Google Cloud client of any kind. A concrete
store (e.g. ``BigQueryReplayStateStore``) implements the
``ReplayStateStore`` contract defined here against a specific backend.

Replay state is append-only: each state transition for one
``(delivery_date, source_object)`` is persisted as its own event rather
than overwriting a single mutable row. The latest event for a given
``(delivery_date, source_object)`` represents the latest known ATTEMPT
state -- distinct from logical completion, which is monotonic once a
``SUCCESS | WAREHOUSE`` event has ever been recorded (see
``ReplayStateStore`` for the full distinction). Earlier events remain
visible for auditability. This module records and queries that state
only -- it implements no retry, resume, or recovery behavior. That is
Phase 3 of ADR-010.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class ReplayStatus(str, Enum):
    """Lifecycle status of a single persisted replay-state event.

    Absence of any state for a ``(delivery_date, source_object)`` pair
    represents work that has not been attempted -- there is
    deliberately no ``NOT_RUN`` value. Date-level completeness is
    derived from the latest events, not stored as its own status.
    """

    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ReplayStage(str, Enum):
    """Orchestration stage a replay-state event belongs to.

    Corresponds exactly to the stage boundaries already established by
    ``HistoricalReplayRunner`` (ADR-009): source delivery, ingestion,
    and warehouse loading.
    """

    SOURCE_DELIVERY = "source_delivery"
    INGESTION = "ingestion"
    WAREHOUSE = "warehouse"


def _require_non_blank(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


def _require_aware(value: datetime, field_name: str) -> None:
    """A datetime is timezone-aware only if it carries real UTC offset info."""
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ReplayStateRecord:
    """One append-only state event for one source object on one delivery date.

    Three distinct identities are in play:

    - ``run_id`` identifies one top-level replay invocation/attempt
      (e.g. one ``run_range()`` call, or one standalone ``run_day()``
      call) -- every event written during that invocation shares it.
    - ``event_id`` uniquely identifies this individual persisted
      transition, since multiple events (e.g. a ``RUNNING`` event
      followed by a ``SUCCESS`` event, possibly across different
      ``run_id``s on a later retry) legitimately share the same
      ``(delivery_date, source_object)``.
    - ``(delivery_date, source_object)`` remains the logical execution
      identity -- the pair a caller queries by, independent of how many
      attempts or events exist for it.

    All datetimes must be timezone-aware. This record represents state
    explicitly supplied by its caller -- it never generates its own
    timestamps or its own ``run_id``/``event_id``.

    ``status=SUCCESS`` always means end-to-end replay completion through
    the warehouse stage, per ADR-010's definition of source-level
    success (source delivery -> connector validation -> GCS Raw landing
    -> BigQuery Raw load -> SUCCESS). Accordingly, ``SUCCESS`` is only
    valid paired with ``stage=WAREHOUSE`` -- ``RUNNING`` and ``FAILED``
    remain valid at any of the three stages, since observing an
    in-progress or failed attempt at ``SOURCE_DELIVERY`` or
    ``INGESTION`` is exactly the kind of intermediate visibility this
    event model exists to preserve.
    """

    run_id: str
    event_id: str
    delivery_date: date
    source_object: str
    status: ReplayStatus
    stage: ReplayStage
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None
    recorded_at: datetime

    def __post_init__(self) -> None:
        _require_non_blank(self.run_id, "run_id")
        _require_non_blank(self.event_id, "event_id")

        if not isinstance(self.delivery_date, date):
            raise TypeError("delivery_date must be a datetime.date")

        _require_non_blank(self.source_object, "source_object")

        if not isinstance(self.status, ReplayStatus):
            raise TypeError("status must be a ReplayStatus")
        if not isinstance(self.stage, ReplayStage):
            raise TypeError("stage must be a ReplayStage")

        _require_aware(self.started_at, "started_at")
        _require_aware(self.recorded_at, "recorded_at")

        if self.completed_at is not None:
            _require_aware(self.completed_at, "completed_at")
            if self.completed_at < self.started_at:
                raise ValueError("completed_at cannot be earlier than started_at")

        if self.error_message is not None:
            _require_non_blank(self.error_message, "error_message")

        if self.status is ReplayStatus.RUNNING:
            if self.completed_at is not None:
                raise ValueError("RUNNING records must not have completed_at")
            if self.error_message is not None:
                raise ValueError("RUNNING records must not have error_message")
        elif self.status is ReplayStatus.SUCCESS:
            if self.stage is not ReplayStage.WAREHOUSE:
                raise ValueError(
                    "SUCCESS records must have stage=WAREHOUSE; SUCCESS represents end-to-end "
                    f"replay completion, not stage='{self.stage.value}'"
                )
            if self.completed_at is None:
                raise ValueError("SUCCESS records must have completed_at")
            if self.error_message is not None:
                raise ValueError("SUCCESS records must not have error_message")
        elif self.status is ReplayStatus.FAILED:
            if self.completed_at is None:
                raise ValueError("FAILED records must have completed_at")
            # error_message may be None or a non-blank string -- some
            # upstream/provider exceptions genuinely carry no useful
            # message, and fabricating one would misrepresent the event.

    @classmethod
    def running(
        cls,
        *,
        run_id: str,
        event_id: str,
        delivery_date: date,
        source_object: str,
        stage: ReplayStage,
        started_at: datetime,
        recorded_at: datetime,
    ) -> "ReplayStateRecord":
        """Build a RUNNING event. Timestamps and run_id must be supplied explicitly."""
        return cls(
            run_id=run_id,
            event_id=event_id,
            delivery_date=delivery_date,
            source_object=source_object,
            status=ReplayStatus.RUNNING,
            stage=stage,
            started_at=started_at,
            completed_at=None,
            error_message=None,
            recorded_at=recorded_at,
        )

    @classmethod
    def success(
        cls,
        *,
        run_id: str,
        event_id: str,
        delivery_date: date,
        source_object: str,
        started_at: datetime,
        completed_at: datetime,
        recorded_at: datetime,
    ) -> "ReplayStateRecord":
        """Build a SUCCESS event. Always stage=WAREHOUSE -- SUCCESS means
        end-to-end replay completion, so there is no stage to choose.
        Timestamps and run_id must be supplied explicitly.
        """
        return cls(
            run_id=run_id,
            event_id=event_id,
            delivery_date=delivery_date,
            source_object=source_object,
            status=ReplayStatus.SUCCESS,
            stage=ReplayStage.WAREHOUSE,
            started_at=started_at,
            completed_at=completed_at,
            error_message=None,
            recorded_at=recorded_at,
        )

    @classmethod
    def failed(
        cls,
        *,
        run_id: str,
        event_id: str,
        delivery_date: date,
        source_object: str,
        stage: ReplayStage,
        started_at: datetime,
        completed_at: datetime,
        recorded_at: datetime,
        error_message: str | None = None,
    ) -> "ReplayStateRecord":
        """Build a FAILED event. Timestamps and run_id must be supplied explicitly."""
        return cls(
            run_id=run_id,
            event_id=event_id,
            delivery_date=delivery_date,
            source_object=source_object,
            status=ReplayStatus.FAILED,
            stage=stage,
            started_at=started_at,
            completed_at=completed_at,
            error_message=error_message,
            recorded_at=recorded_at,
        )


class ReplayStateStore(ABC):
    """Persistence contract for append-only replay-state events.

    Deliberately narrow and free of any backend-specific concept (no
    ``table_id``, ``dataset_id``, SQL, or ``project_id`` appears here) --
    those belong entirely to concrete implementations.

    Two distinct questions are answered by different methods here, and
    must not be conflated:

    - **Latest attempt** (``get_latest``/``get_latest_for_date``): what
      happened most recently when this logical source was attempted?
      This can regress -- a later ``FAILED`` attempt is a perfectly
      valid "latest" event even if an earlier attempt succeeded.
    - **Logical completion** (``get_completed_for_date``): has this
      logical source delivery successfully completed through BigQuery
      Raw at least once? This is monotonic -- once a
      ``(delivery_date, source_object)`` reaches ``SUCCESS | WAREHOUSE``,
      it remains logically complete regardless of what any later replay
      attempt records, because Mercury has no destructive invalidation
      mechanism that could actually undo that success (the GCS artifact
      and BigQuery partition it produced are immutable and untouched by
      a later failed attempt).
    """

    @abstractmethod
    def append(self, record: ReplayStateRecord) -> None:
        """Persist one new state event. Never updates or deletes prior events."""

    @abstractmethod
    def get_history(self, delivery_date: date, source_object: str) -> tuple[ReplayStateRecord, ...]:
        """Return every event for this (delivery_date, source_object), oldest first."""

    @abstractmethod
    def get_latest(self, delivery_date: date, source_object: str) -> ReplayStateRecord | None:
        """Return the most recently recorded ATTEMPT event for this pair, or None.

        This reflects the latest attempt, not necessarily the latest
        success -- a ``FAILED`` event recorded after an earlier
        ``SUCCESS`` is correctly returned here. Use
        ``get_completed_for_date`` to ask about logical completion
        instead.
        """

    @abstractmethod
    def get_latest_for_date(self, delivery_date: date) -> tuple[ReplayStateRecord, ...]:
        """Return the latest ATTEMPT event per source_object present on this date.

        Same latest-attempt semantics as ``get_latest`` -- see that
        method's docstring.
        """

    @abstractmethod
    def get_completed_for_date(self, delivery_date: date) -> tuple[ReplayStateRecord, ...]:
        """Return the logical completion record per source_object for this date.

        A ``source_object`` appears in the result if and only if it has
        *ever* produced a ``SUCCESS | WAREHOUSE`` event for this
        ``delivery_date`` -- across every replay attempt/``run_id``, not
        just the most recent one. When a source has multiple successful
        attempts, its most recently recorded ``SUCCESS`` event is
        returned. A source with no successful event at all (never
        attempted, still running, or every attempt failed) is absent
        from the result entirely, even if it has a more recent
        ``FAILED`` or ``RUNNING`` event. Results are ordered
        deterministically by ``source_object``.

        This is the completion-monotonic counterpart to
        ``get_latest_for_date``: a later failed replay attempt never
        removes a source from this result once it has succeeded.
        """


def is_date_complete(records: tuple[ReplayStateRecord, ...], expected_source_objects: frozenset[str]) -> bool:
    """Derive whether a delivery date is fully, successfully replayed.

    ``records`` should normally be the logical completion record per
    source object for a single date (as returned by
    ``ReplayStateStore.get_completed_for_date()``) so that an earlier
    success is not erased by a later failed attempt -- this function
    does not itself reduce a full event history or a latest-attempt
    result down to completion state; it only checks the records it is
    given. A date is complete only if the actual source object set
    exactly matches ``expected_source_objects`` and every one of those
    records has status ``SUCCESS``. Because ``ReplayStateRecord``'s own
    invariant guarantees ``SUCCESS`` implies ``stage=WAREHOUSE``,
    checking ``status`` alone is sufficient here; there is no need to
    separately re-check ``stage``. Date-level completion is always
    derived this way; it is never itself persisted as a stored state.

    Records spanning more than one ``delivery_date`` are malformed
    input -- a violation of this function's own contract, not a
    legitimate "incomplete" answer -- and raise ``ValueError`` rather
    than returning ``False``.
    """
    if not isinstance(records, tuple):
        raise TypeError("records must be a tuple")
    for record in records:
        if not isinstance(record, ReplayStateRecord):
            raise TypeError("every item in records must be a ReplayStateRecord")

    if not isinstance(expected_source_objects, frozenset):
        raise TypeError("expected_source_objects must be a frozenset")
    if not expected_source_objects:
        raise ValueError("expected_source_objects cannot be empty")
    for source_object in expected_source_objects:
        _require_non_blank(source_object, "expected_source_objects entry")

    delivery_dates = {record.delivery_date for record in records}
    if len(delivery_dates) > 1:
        raise ValueError(
            f"records must all share one delivery_date; found multiple: "
            f"{', '.join(sorted(d.isoformat() for d in delivery_dates))}"
        )

    source_objects = [record.source_object for record in records]
    duplicates = {obj for obj in source_objects if source_objects.count(obj) > 1}
    if duplicates:
        raise ValueError(
            f"duplicate source_object values in records: {', '.join(sorted(duplicates))}"
        )

    if set(source_objects) != expected_source_objects:
        return False

    return all(record.status is ReplayStatus.SUCCESS for record in records)