"""Mercury's recovery planning domain model (ADR-010 Phase 3A).

This module answers a third question that ``state.py`` deliberately does
not: given everything Mercury currently knows about one logical source
delivery, *what should happen next*? It is a pure decision policy --
given evidence, it produces a deterministic ``RecoveryAction`` and never
performs I/O, never calls GCS or BigQuery, and never mutates anything.
It has no knowledge of Olist simulation, connectors, GCS/BigQuery
clients, or ``HistoricalReplayRunner`` execution mechanics.

Recovery planning considers four categories of evidence for one
``(delivery_date, source_object)``:

1. logical completion (has this source ever reached
   ``SUCCESS | WAREHOUSE``? -- monotonic, per ``state.py``);
2. the latest replay attempt (diagnostic context only; it must never
   override logical completion or physical-state evidence);
3. whether a *validated* reusable GCS Raw artifact exists;
4. whether BigQuery Raw data exists for this source/date.

Phase 3A only plans. It does not execute ``INGEST_AND_LOAD`` or
``LOAD_ONLY``, does not validate GCS/BigQuery physical state itself
(that validation is assumed to have already happened before evidence
reaches this module), does not reconcile, and does not append any
``ReplayStateRecord`` events. Those are Phase 3B/3C.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Iterable

from mercury_ingestion.orchestration.state import ReplayStateRecord


def _require_non_blank(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


def _require_bool(value: object, field_name: str) -> None:
    # bool is a subclass of int, so an explicit isinstance(bool) check is
    # required here -- a truthy/falsy check alone would silently accept
    # e.g. 1/0 as if they were True/False.
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")


class RecoveryAction(str, Enum):
    """The action Mercury should take next for one logical source delivery.

    - ``SKIP``: the source has already logically completed; there is
      nothing to do.
    - ``INGEST_AND_LOAD``: no logical completion and no reusable Raw
      artifact exists anywhere -- a full ingestion + warehouse attempt
      is required.
    - ``LOAD_ONLY``: a valid, reusable GCS Raw artifact already exists
      but BigQuery Raw does not -- only the warehouse step is needed.
    - ``RECONCILE``: both GCS Raw and BigQuery Raw appear to exist but
      logical completion was never recorded -- this is a genuine
      ambiguity Mercury must not silently resolve by assuming success.
    - ``MANUAL_REVIEW``: BigQuery Raw exists without a valid GCS Raw
      artifact -- inconsistent with Mercury's expected data path
      (GCS always precedes BigQuery) and must not be guessed away.
    """

    SKIP = "skip"
    INGEST_AND_LOAD = "ingest_and_load"
    LOAD_ONLY = "load_only"
    RECONCILE = "reconcile"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True, slots=True)
class RecoveryEvidence:
    """Everything the planner is given about one logical source delivery.

    ``logical_completion`` is supplied explicitly rather than inferred
    from ``latest_attempt`` here -- the caller is expected to have
    already derived it correctly (e.g. via
    ``is_date_complete``-style logic over
    ``ReplayStateStore.get_completed_for_date()``), since re-deriving
    monotonic completion from a single attempt record would be exactly
    the Phase 2 bug this architecture already fixed once.

    ``valid_gcs_raw`` means a GCS artifact has already been validated as
    safe to reuse by some future physical-state inspector -- it is not
    merely "an object happens to exist at that path". Phase 3A does not
    define how that validation happens; it only consumes the boolean
    result.

    ``latest_attempt`` is optional diagnostic context (e.g. to explain
    *why* a source needs recovery). It is never consulted by the
    decision logic itself -- only ``logical_completion``,
    ``valid_gcs_raw``, and ``bigquery_raw_present`` determine the
    action.
    """

    delivery_date: date
    source_object: str
    logical_completion: bool
    valid_gcs_raw: bool
    bigquery_raw_present: bool
    latest_attempt: ReplayStateRecord | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.delivery_date, date):
            raise TypeError("delivery_date must be a datetime.date")
        _require_non_blank(self.source_object, "source_object")
        _require_bool(self.logical_completion, "logical_completion")
        _require_bool(self.valid_gcs_raw, "valid_gcs_raw")
        _require_bool(self.bigquery_raw_present, "bigquery_raw_present")

        if self.latest_attempt is not None:
            if not isinstance(self.latest_attempt, ReplayStateRecord):
                raise TypeError("latest_attempt must be a ReplayStateRecord or None")
            if self.latest_attempt.delivery_date != self.delivery_date:
                raise ValueError("latest_attempt.delivery_date does not match this evidence's delivery_date")
            if self.latest_attempt.source_object != self.source_object:
                raise ValueError("latest_attempt.source_object does not match this evidence's source_object")


@dataclass(frozen=True, slots=True)
class RecoveryPlanItem:
    """One source's recovery decision, with the evidence and reasoning behind it."""

    source_object: str
    action: RecoveryAction
    reason: str
    evidence: RecoveryEvidence

    def __post_init__(self) -> None:
        _require_non_blank(self.source_object, "source_object")
        if not isinstance(self.action, RecoveryAction):
            raise TypeError("action must be a RecoveryAction")
        _require_non_blank(self.reason, "reason")
        if not isinstance(self.evidence, RecoveryEvidence):
            raise TypeError("evidence must be a RecoveryEvidence")
        if self.source_object != self.evidence.source_object:
            raise ValueError("source_object does not match evidence.source_object")


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    """The full set of per-source recovery decisions for one business date.

    An empty ``items`` tuple is deliberately allowed: unlike
    ``SourceDeliveryBatch`` (which represents an actual delivery that
    must contain something to be meaningful), a ``RecoveryPlan``
    represents a decision over whatever sources the caller chose to
    evaluate -- including, legitimately, none (e.g. a caller that
    already filtered out sources it isn't concerned with). Membership
    against Mercury's expected daily source set is a separate,
    orchestration-level concern, not something this generic planner
    enforces.
    """

    delivery_date: date
    items: tuple[RecoveryPlanItem, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.delivery_date, date):
            raise TypeError("delivery_date must be a datetime.date")
        if not isinstance(self.items, tuple):
            raise TypeError("items must be a tuple")
        for item in self.items:
            if not isinstance(item, RecoveryPlanItem):
                raise TypeError("every item in items must be a RecoveryPlanItem")
            if item.evidence.delivery_date != self.delivery_date:
                raise ValueError(
                    f"item for source_object={item.source_object!r} has evidence.delivery_date "
                    f"{item.evidence.delivery_date.isoformat()}, which does not match this plan's "
                    f"delivery_date {self.delivery_date.isoformat()}"
                )

        source_objects = [item.source_object for item in self.items]
        duplicates = {obj for obj in source_objects if source_objects.count(obj) > 1}
        if duplicates:
            raise ValueError(f"duplicate source_object entries in plan: {', '.join(sorted(duplicates))}")

    @property
    def needs_execution(self) -> tuple[RecoveryPlanItem, ...]:
        """Items whose action requires doing new ingestion/warehouse work."""
        return tuple(
            item for item in self.items if item.action in (RecoveryAction.INGEST_AND_LOAD, RecoveryAction.LOAD_ONLY)
        )

    @property
    def requires_reconciliation(self) -> tuple[RecoveryPlanItem, ...]:
        """Items where physical state is ambiguous and needs reconciliation."""
        return tuple(item for item in self.items if item.action is RecoveryAction.RECONCILE)

    @property
    def requires_manual_review(self) -> tuple[RecoveryPlanItem, ...]:
        """Items in an inconsistent state that must not be guessed away."""
        return tuple(item for item in self.items if item.action is RecoveryAction.MANUAL_REVIEW)

    @property
    def skipped(self) -> tuple[RecoveryPlanItem, ...]:
        """Items that are already logically complete and need nothing."""
        return tuple(item for item in self.items if item.action is RecoveryAction.SKIP)


class RecoveryPlanner:
    """Deterministic, side-effect-free recovery decision policy.

    Given evidence, ``decide()``/``plan()`` always produce the same
    action for the same input -- there is no hidden state, no clock
    access, and no randomness. Nothing here reads from or writes to any
    external system.
    """

    def decide(self, evidence: RecoveryEvidence) -> RecoveryPlanItem:
        """Decide the recovery action for one logical source delivery.

        Logical completion always wins first: once ``evidence.logical_completion``
        is ``True``, the action is unconditionally ``SKIP`` -- a later
        ``FAILED``/``RUNNING`` attempt recorded in ``evidence.latest_attempt``
        never changes this, because that field is never inspected by
        this method at all.
        """
        action, reason = self._decide_action(evidence)
        return RecoveryPlanItem(source_object=evidence.source_object, action=action, reason=reason, evidence=evidence)

    def plan(self, delivery_date: date, evidence: Iterable[RecoveryEvidence]) -> RecoveryPlan:
        """Build a full-date recovery plan from evidence for its sources.

        Orders the resulting plan by ``source_object`` (ascending),
        regardless of the order ``evidence`` was supplied in -- the
        planner owns this determinism itself rather than trusting the
        caller to already iterate in a stable order. Two calls given the
        same evidence in different input orders always produce
        identically ordered plans. Alphabetical ``source_object``
        ordering is used deliberately instead of any Mercury/Olist-
        specific source sequence, since this module has no knowledge of
        (and must not gain knowledge of) concepts like
        ``DAILY_SOURCE_OBJECTS`` -- it stays generic and
        backend-independent.
        """
        ordered_evidence = sorted(evidence, key=lambda item: item.source_object)
        items = tuple(self.decide(item) for item in ordered_evidence)
        return RecoveryPlan(delivery_date=delivery_date, items=items)

    @staticmethod
    def _decide_action(evidence: RecoveryEvidence) -> tuple[RecoveryAction, str]:
        """The decision table itself -- deliberately only three inputs.

        ``evidence.latest_attempt`` is intentionally absent from this
        function's logic: including it would risk exactly the kind of
        latest-attempt-overrides-completion regression ADR-010 Phase 2
        already had to fix once.
        """
        if evidence.logical_completion:
            return RecoveryAction.SKIP, "source has already logically completed (SUCCESS|WAREHOUSE recorded)"

        gcs = evidence.valid_gcs_raw
        bigquery = evidence.bigquery_raw_present

        if not gcs and not bigquery:
            return (
                RecoveryAction.INGEST_AND_LOAD,
                "no logical completion and no reusable Raw artifact exists in GCS or BigQuery",
            )
        if gcs and not bigquery:
            return (
                RecoveryAction.LOAD_ONLY,
                "a valid, reusable GCS Raw artifact exists but BigQuery Raw does not -- only warehouse loading is needed",
            )
        if gcs and bigquery:
            return (
                RecoveryAction.RECONCILE,
                "GCS Raw and BigQuery Raw both appear to exist without recorded logical completion -- ambiguous, must not assume success",
            )
        # not gcs and bigquery
        return (
            RecoveryAction.MANUAL_REVIEW,
            "BigQuery Raw exists without a valid GCS Raw artifact, which is inconsistent with Mercury's expected data path",
        )