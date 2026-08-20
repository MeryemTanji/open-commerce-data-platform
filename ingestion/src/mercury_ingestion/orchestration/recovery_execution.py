"""Mercury's recovery execution layer (ADR-010 Phase 3B).

Phase 3A's ``RecoveryPlanner`` is pure and side-effect-free: given
evidence, it decides *what* should happen next for one logical source
delivery, but never performs I/O. This module is the layer that
actually *does* what Phase 3A decided, and durably records that it did
so:

- ``RecoveryAction.SKIP`` -> no physical work, no replay-state event.
- ``RecoveryAction.INGEST_AND_LOAD`` -> a connector is run (source
  validation, record counting, and immutable GCS Raw landing via the
  existing ``BaseConnector``/``StorageManager`` contract), and on
  success the landed artifact is loaded into BigQuery Raw via the
  existing ``BigQueryRawLoader``. Every stage transition is durably
  recorded via ``ReplayStateStore``, exactly as ``HistoricalReplayRunner``
  already does for ordinary daily replay.
- ``RecoveryAction.LOAD_ONLY`` -> the caller-supplied, already-validated
  GCS Raw artifact is loaded into BigQuery Raw directly -- no connector
  runs, no new GCS write happens -- with the warehouse stage transition
  durably recorded.
- ``RecoveryAction.RECONCILE`` / ``RecoveryAction.MANUAL_REVIEW`` ->
  physical state is ambiguous or inconsistent; this module performs no
  physical work and appends no replay-state event for either, reporting
  ``BLOCKED`` exactly as Phase 3A already decided. Reconciling that
  ambiguity is Phase 3C, which this module does not implement.

This module reimplements no lifecycle logic of its own: ``BaseConnector``
still owns ingestion/landing, ``BigQueryRawLoader`` still owns warehouse
loading, ``ReplayStateStore`` still owns state persistence, and
connector resolution goes through the single shared
``connector_builder.build_connector()`` -- also used by
``HistoricalReplayRunner`` -- so there is exactly one connector map in
the codebase.

Per ADR-011, no raw exception text ever reaches a persisted or returned
value here. A connector failure's message is already a safe, Mercury-
authored string by the time it reaches this module (``BaseConnector``
itself never emits ``str(exc)``); a warehouse-load, source-provider, or
replay-state-persistence failure is converted into a fresh
``OperationalError``/safe orchestration message here, exactly as
``HistoricalReplayRunner`` already does for the same kinds of failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Iterable
from uuid import uuid4

from mercury_ingestion.common.metadata import IngestionStatus
from mercury_ingestion.common.operational_errors import OperationalError, OperationalErrorCategory
from mercury_ingestion.common.storage import StorageManager
from mercury_ingestion.connectors.base import ConnectorRunResult
from mercury_ingestion.orchestration.connector_builder import build_connector
from mercury_ingestion.orchestration.recovery import RecoveryAction, RecoveryPlan, RecoveryPlanItem
from mercury_ingestion.orchestration.replay import DAILY_SOURCE_OBJECTS
from mercury_ingestion.orchestration.state import (
    ReplayStage,
    ReplayStateRecord,
    ReplayStateStore,
    is_date_complete,
)
from mercury_ingestion.sources.base import SourceDelivery, SourceDeliveryProvider
from mercury_ingestion.warehouse.bigquery_loader import BigQueryLoadResult, BigQueryRawLoader


def _require_non_blank(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


def _require_date(value: object, field_name: str) -> None:
    if not isinstance(value, date):
        raise TypeError(f"{field_name} must be a datetime.date")


def _now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class RecoveryExecutionOutcome(str, Enum):
    """What actually happened when a RecoveryPlanItem was executed.

    - ``SUCCEEDED``: the action's physical work completed -- warehouse
      data is now present for this source/date.
    - ``FAILED``: physical work was attempted (ingestion and/or
      warehouse loading) but did not complete successfully.
    - ``SKIPPED``: the ``SKIP`` action -- no physical work was ever
      attempted, because the source was already logically complete.
    - ``BLOCKED``: the ``RECONCILE``/``MANUAL_REVIEW`` action -- no
      physical work was attempted, because the ambiguity/inconsistency
      must be resolved by a human or by Phase 3C before any automated
      action is safe.
    """

    SKIPPED = "skipped"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ValidatedRawArtifact:
    """An already-validated, reusable GCS Raw artifact for one source/date.

    Phase 3B does not itself inspect, list, or download GCS -- this type
    is the explicit, caller-supplied evidence that such validation has
    already happened, exactly mirroring how
    ``RecoveryEvidence.valid_gcs_raw`` is also caller-supplied rather
    than independently verified by ``RecoveryPlanner``. Supplying one
    only makes sense for a ``LOAD_ONLY`` item; ``RecoveryExecutor``
    never uses it to skip landing during ``INGEST_AND_LOAD``.
    """

    source_object: str
    delivery_date: date
    gcs_uri: str

    def __post_init__(self) -> None:
        _require_non_blank(self.source_object, "source_object")
        _require_date(self.delivery_date, "delivery_date")
        _require_non_blank(self.gcs_uri, "gcs_uri")
        if not self.gcs_uri.startswith("gs://"):
            raise ValueError(f"gcs_uri must start with 'gs://': {self.gcs_uri!r}")


@dataclass(frozen=True, slots=True)
class RecoveryItemExecutionResult:
    """The outcome of executing one ``RecoveryPlanItem``.

    Contains structural execution facts only -- ``ingestion_result``/
    ``warehouse_result`` reuse Mercury's existing result types rather
    than introducing a second, generic free-text error/display surface.
    Any durable failure description belongs in
    ``ReplayStateRecord.error_message`` (already ADR-011-safe), not
    here.
    """

    source_object: str
    planned_action: RecoveryAction
    outcome: RecoveryExecutionOutcome
    ingestion_result: ConnectorRunResult | None = None
    warehouse_result: BigQueryLoadResult | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.source_object, "source_object")
        if not isinstance(self.planned_action, RecoveryAction):
            raise TypeError("planned_action must be a RecoveryAction")
        if not isinstance(self.outcome, RecoveryExecutionOutcome):
            raise TypeError("outcome must be a RecoveryExecutionOutcome")
        if self.ingestion_result is not None and not isinstance(self.ingestion_result, ConnectorRunResult):
            raise TypeError("ingestion_result must be a ConnectorRunResult or None")
        if self.warehouse_result is not None and not isinstance(self.warehouse_result, BigQueryLoadResult):
            raise TypeError("warehouse_result must be a BigQueryLoadResult or None")

        if self.planned_action is RecoveryAction.SKIP:
            self._require(self.outcome is RecoveryExecutionOutcome.SKIPPED, "SKIP must have outcome=SKIPPED")
            self._require_no_results("SKIP")

        elif self.planned_action in (RecoveryAction.RECONCILE, RecoveryAction.MANUAL_REVIEW):
            self._require(
                self.outcome is RecoveryExecutionOutcome.BLOCKED,
                f"{self.planned_action.value} must have outcome=BLOCKED",
            )
            self._require_no_results(self.planned_action.value)

        elif self.planned_action is RecoveryAction.LOAD_ONLY:
            self._require(self.ingestion_result is None, "LOAD_ONLY must never carry an ingestion_result")
            if self.outcome is RecoveryExecutionOutcome.SUCCEEDED:
                self._require(self.warehouse_result is not None, "LOAD_ONLY SUCCEEDED requires a warehouse_result")
            elif self.outcome is RecoveryExecutionOutcome.FAILED:
                self._require(self.warehouse_result is None, "LOAD_ONLY FAILED must not carry a warehouse_result")
            else:
                raise ValueError("LOAD_ONLY outcome must be SUCCEEDED or FAILED")

        elif self.planned_action is RecoveryAction.INGEST_AND_LOAD:
            if self.outcome is RecoveryExecutionOutcome.SUCCEEDED:
                self._require(
                    self.ingestion_result is not None and self.ingestion_result.metadata.status is IngestionStatus.SUCCESS,
                    "INGEST_AND_LOAD SUCCEEDED requires a successful ingestion_result",
                )
                self._require(self.warehouse_result is not None, "INGEST_AND_LOAD SUCCEEDED requires a warehouse_result")
            elif self.outcome is RecoveryExecutionOutcome.FAILED:
                self._require(self.ingestion_result is not None, "INGEST_AND_LOAD FAILED requires an ingestion_result")
                self._require(self.warehouse_result is None, "INGEST_AND_LOAD FAILED must not carry a warehouse_result")
            else:
                raise ValueError("INGEST_AND_LOAD outcome must be SUCCEEDED or FAILED")

    def _require(self, condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(message)

    def _require_no_results(self, action_label: str) -> None:
        if self.ingestion_result is not None or self.warehouse_result is not None:
            raise ValueError(
                f"{action_label} means no physical work was performed; "
                "ingestion_result and warehouse_result must both be None"
            )


@dataclass(frozen=True, slots=True)
class RecoveryExecutionResult:
    """The full set of per-source execution outcomes for one recovery run.

    ``date_complete`` is always re-derived from durable replay state
    (via ``get_completed_for_date()`` + ``is_date_complete()``) after
    every plan item has been processed -- never from this run's own
    execution outcomes. This preserves the ADR-010 Phase 2 monotonic-
    completion invariant: a source that already succeeded in an earlier
    run remains logically complete even if this recovery attempt's own
    work for a *different* sibling source failed.
    """

    delivery_date: date
    run_id: str
    items: tuple[RecoveryItemExecutionResult, ...]
    date_complete: bool

    def __post_init__(self) -> None:
        _require_date(self.delivery_date, "delivery_date")
        _require_non_blank(self.run_id, "run_id")
        if not isinstance(self.items, tuple):
            raise TypeError("items must be a tuple")
        for item in self.items:
            if not isinstance(item, RecoveryItemExecutionResult):
                raise TypeError("every item in items must be a RecoveryItemExecutionResult")
        if not isinstance(self.date_complete, bool):
            raise TypeError("date_complete must be a bool")

        source_objects = [item.source_object for item in self.items]
        duplicates = {obj for obj in source_objects if source_objects.count(obj) > 1}
        if duplicates:
            raise ValueError(f"duplicate source_object entries in execution result: {', '.join(sorted(duplicates))}")

    @property
    def succeeded(self) -> tuple[RecoveryItemExecutionResult, ...]:
        return tuple(item for item in self.items if item.outcome is RecoveryExecutionOutcome.SUCCEEDED)

    @property
    def failed(self) -> tuple[RecoveryItemExecutionResult, ...]:
        return tuple(item for item in self.items if item.outcome is RecoveryExecutionOutcome.FAILED)

    @property
    def skipped(self) -> tuple[RecoveryItemExecutionResult, ...]:
        return tuple(item for item in self.items if item.outcome is RecoveryExecutionOutcome.SKIPPED)

    @property
    def blocked(self) -> tuple[RecoveryItemExecutionResult, ...]:
        return tuple(item for item in self.items if item.outcome is RecoveryExecutionOutcome.BLOCKED)


class RecoveryExecutionError(Exception):
    """Raised when recovery execution cannot proceed safely.

    Covers control-plane failures (a replay-state append failing) and
    orchestration-level failures (the source provider itself failing to
    produce a batch) -- never ordinary per-source ingestion/warehouse
    failures, which are represented as a ``FAILED``
    ``RecoveryItemExecutionResult`` instead and do not raise.

    The message is always Mercury-authored and display-safe -- it never
    embeds ``str(exc)``, ``repr(exc)``, or ``exc.args``. The original
    exception remains available via normal Python exception chaining
    (``raise ... from exc``) for transient debugging only.
    """

    def __init__(self, message: str, *, delivery_date: date, source_object: str | None = None) -> None:
        super().__init__(message)
        self.delivery_date = delivery_date
        self.source_object = source_object


class RecoveryExecutor:
    """Executes a ``RecoveryPlan`` against real infrastructure, durably.

    Unlike ``RecoveryPlanner`` (pure, no I/O), this class performs
    actual physical work and durably records it: it reuses the existing
    ``SourceDeliveryProvider`` (to obtain the day's deliveries),
    ``connector_builder.build_connector()`` + ``BaseConnector``
    (ingestion + immutable GCS Raw landing), ``BigQueryRawLoader``
    (warehouse loading), and ``ReplayStateStore`` (durable state) --
    exactly the same components ``HistoricalReplayRunner`` already uses
    for ordinary daily replay, with none of their lifecycle logic
    reimplemented here.

    Dependencies are injected, matching ``HistoricalReplayRunner``'s own
    constructor style: this class never creates a GCS/BigQuery client,
    a source provider, or a replay-state store itself, and never
    hard-codes a concrete backend (e.g. ``BigQueryReplayStateStore``) --
    only the generic ``ReplayStateStore``/``SourceDeliveryProvider``
    abstractions are depended on.
    """

    def __init__(
        self,
        source_provider: SourceDeliveryProvider,
        storage_manager: StorageManager,
        bigquery_loader: BigQueryRawLoader,
        replay_state_store: ReplayStateStore,
    ) -> None:
        if not isinstance(source_provider, SourceDeliveryProvider):
            raise TypeError("source_provider must be a SourceDeliveryProvider")
        if not isinstance(storage_manager, StorageManager):
            raise TypeError("storage_manager must be a StorageManager")
        if not isinstance(bigquery_loader, BigQueryRawLoader):
            raise TypeError("bigquery_loader must be a BigQueryRawLoader")
        if not isinstance(replay_state_store, ReplayStateStore):
            raise TypeError("replay_state_store must be a ReplayStateStore")

        self.source_provider = source_provider
        self.storage_manager = storage_manager
        self.bigquery_loader = bigquery_loader
        self.replay_state_store = replay_state_store

    def execute_plan(
        self, plan: RecoveryPlan, validated_raw_artifacts: Iterable[ValidatedRawArtifact] = ()
    ) -> RecoveryExecutionResult:
        """Validate, then execute, every item in a plan.

        The full request is validated before any physical work,
        source-provider call, or replay-state append occurs -- a
        malformed request (wrong artifact date, duplicate artifact
        source, a missing or extra artifact relative to the plan's
        ``LOAD_ONLY`` items) raises ``ValueError`` immediately, with
        zero side effects.

        Exactly one ``run_id`` is generated for this invocation and
        shared by every replay-state event it produces. The source
        provider is called at most once, and only if the plan contains
        at least one ``INGEST_AND_LOAD`` item.
        """
        if not isinstance(plan, RecoveryPlan):
            raise TypeError("plan must be a RecoveryPlan")

        artifacts_by_source = self._validate_request(plan, tuple(validated_raw_artifacts))

        ingest_items = [item for item in plan.items if item.action is RecoveryAction.INGEST_AND_LOAD]
        if ingest_items:
            deliveries_by_source, ingestion_date = self._fetch_deliveries(plan.delivery_date, ingest_items)
        else:
            deliveries_by_source, ingestion_date = {}, plan.delivery_date

        run_id = str(uuid4())
        results: list[RecoveryItemExecutionResult] = []
        for item in plan.items:
            if item.action is RecoveryAction.SKIP:
                results.append(self._skip(item))
            elif item.action in (RecoveryAction.RECONCILE, RecoveryAction.MANUAL_REVIEW):
                results.append(self._blocked(item))
            elif item.action is RecoveryAction.LOAD_ONLY:
                results.append(
                    self._execute_load_only(item, plan.delivery_date, run_id, artifacts_by_source[item.source_object])
                )
            else:
                results.append(
                    self._execute_ingest_and_load(
                        item, plan.delivery_date, ingestion_date, run_id, deliveries_by_source[item.source_object]
                    )
                )

        completed_records = self.replay_state_store.get_completed_for_date(plan.delivery_date)
        date_complete = is_date_complete(completed_records, DAILY_SOURCE_OBJECTS)

        return RecoveryExecutionResult(
            delivery_date=plan.delivery_date, run_id=run_id, items=tuple(results), date_complete=date_complete
        )

    @staticmethod
    def _validate_request(
        plan: RecoveryPlan, artifacts: tuple[ValidatedRawArtifact, ...]
    ) -> dict[str, ValidatedRawArtifact]:
        """Validate the full execution request before any side effects.

        Enforces, in order: no duplicate artifact ``source_object``
        entries; every artifact's ``delivery_date`` matches the plan's;
        every ``LOAD_ONLY`` item has exactly one matching artifact; and
        no artifact is supplied for a non-``LOAD_ONLY`` source.
        """
        artifact_source_objects = [artifact.source_object for artifact in artifacts]
        duplicates = {obj for obj in artifact_source_objects if artifact_source_objects.count(obj) > 1}
        if duplicates:
            raise ValueError(f"duplicate validated_raw_artifacts source_object entries: {', '.join(sorted(duplicates))}")

        for artifact in artifacts:
            if artifact.delivery_date != plan.delivery_date:
                raise ValueError(
                    f"validated_raw_artifacts entry for source_object={artifact.source_object!r} has "
                    f"delivery_date {artifact.delivery_date.isoformat()}, which does not match "
                    f"plan.delivery_date {plan.delivery_date.isoformat()}"
                )

        artifacts_by_source = {artifact.source_object: artifact for artifact in artifacts}
        load_only_source_objects = {item.source_object for item in plan.items if item.action is RecoveryAction.LOAD_ONLY}

        missing = load_only_source_objects - artifacts_by_source.keys()
        if missing:
            raise ValueError(f"LOAD_ONLY plan items missing a validated_raw_artifact: {', '.join(sorted(missing))}")

        extra = artifacts_by_source.keys() - load_only_source_objects
        if extra:
            raise ValueError(f"validated_raw_artifacts supplied for non-LOAD_ONLY sources: {', '.join(sorted(extra))}")

        return artifacts_by_source

    def _fetch_deliveries(
        self, delivery_date: date, ingest_items: list[RecoveryPlanItem]
    ) -> tuple[dict[str, SourceDelivery], date]:
        """Fetch the day's source batch exactly once, for INGEST_AND_LOAD items only.

        Every required source_object must resolve to exactly one
        ``SourceDelivery`` in the fetched batch: zero matches raises
        (missing), and two or more matches also raises (ambiguous --
        never silently resolved by picking one). Unrelated extra
        sources in the batch that are not required by this plan are
        ignored, not rejected. This validation happens before any
        replay-state append, connector creation, storage work, or
        BigQuery work for the affected sources.

        Also returns the effective ingestion date for this batch:
        ``batch.ingestion_date`` if the provider supplied one, else
        ``delivery_date`` as the sensible default. This method only
        *consumes* whatever the provider returned -- it never derives a
        provider-specific timing offset (e.g. Mercury's Olist "+1 day"
        historical-simulation convention) itself.

        A source-provider failure never produces a fake source-level
        result -- it raises ``RecoveryExecutionError`` immediately, with
        no per-item work (and thus no replay-state events) having
        started yet.
        """
        try:
            batch = self.source_provider.get_daily_delivery(delivery_date)
        except Exception as exc:  # noqa: BLE001 - converted into a safe orchestration error below
            raise RecoveryExecutionError(
                f"failed to obtain source delivery batch for {delivery_date.isoformat()}",
                delivery_date=delivery_date,
            ) from exc

        ingestion_date = batch.ingestion_date if batch.ingestion_date is not None else delivery_date

        needed = {item.source_object for item in ingest_items}
        matches_by_source: dict[str, list[SourceDelivery]] = {source_object: [] for source_object in needed}
        for delivery in batch.deliveries:
            if delivery.source_object in matches_by_source:
                matches_by_source[delivery.source_object].append(delivery)

        missing = sorted(source_object for source_object, matches in matches_by_source.items() if len(matches) == 0)
        if missing:
            raise RecoveryExecutionError(
                f"source delivery batch for {delivery_date.isoformat()} is missing required source_object(s): "
                f"{', '.join(missing)}",
                delivery_date=delivery_date,
            )

        duplicated = sorted(source_object for source_object, matches in matches_by_source.items() if len(matches) > 1)
        if duplicated:
            raise RecoveryExecutionError(
                f"source delivery batch for {delivery_date.isoformat()} contains duplicate SourceDelivery "
                f"entries for required source_object(s): {', '.join(duplicated)}",
                delivery_date=delivery_date,
            )

        return {source_object: matches[0] for source_object, matches in matches_by_source.items()}, ingestion_date

    @staticmethod
    def _skip(item: RecoveryPlanItem) -> RecoveryItemExecutionResult:
        return RecoveryItemExecutionResult(
            source_object=item.source_object,
            planned_action=RecoveryAction.SKIP,
            outcome=RecoveryExecutionOutcome.SKIPPED,
        )

    @staticmethod
    def _blocked(item: RecoveryPlanItem) -> RecoveryItemExecutionResult:
        return RecoveryItemExecutionResult(
            source_object=item.source_object,
            planned_action=item.action,
            outcome=RecoveryExecutionOutcome.BLOCKED,
        )

    def _execute_load_only(
        self, item: RecoveryPlanItem, delivery_date: date, run_id: str, artifact: ValidatedRawArtifact
    ) -> RecoveryItemExecutionResult:
        source_object = item.source_object
        started_at = _now()

        self._append_state(
            ReplayStateRecord.running(
                run_id=run_id,
                event_id=str(uuid4()),
                delivery_date=delivery_date,
                source_object=source_object,
                stage=ReplayStage.WAREHOUSE,
                started_at=started_at,
                recorded_at=_now(),
            ),
            delivery_date=delivery_date,
            source_object=source_object,
        )

        try:
            warehouse_result = self.bigquery_loader.load(
                source_object=source_object, gcs_uri=artifact.gcs_uri, partition_date=delivery_date
            )
        except Exception:  # noqa: BLE001 - converted into a safe OperationalError below
            completion_time = _now()
            operational_error = OperationalError(
                category=OperationalErrorCategory.WAREHOUSE_LOAD_FAILED,
                component="RecoveryExecutor",
                operation="load_only",
                safe_message="Warehouse load failed during recovery",
            )
            self._append_state(
                ReplayStateRecord.failed(
                    run_id=run_id,
                    event_id=str(uuid4()),
                    delivery_date=delivery_date,
                    source_object=source_object,
                    stage=ReplayStage.WAREHOUSE,
                    started_at=started_at,
                    completed_at=completion_time,
                    recorded_at=completion_time,
                    error_message=operational_error.to_safe_string(),
                ),
                delivery_date=delivery_date,
                source_object=source_object,
            )
            return RecoveryItemExecutionResult(
                source_object=source_object,
                planned_action=RecoveryAction.LOAD_ONLY,
                outcome=RecoveryExecutionOutcome.FAILED,
            )

        completion_time = _now()
        self._append_state(
            ReplayStateRecord.success(
                run_id=run_id,
                event_id=str(uuid4()),
                delivery_date=delivery_date,
                source_object=source_object,
                started_at=started_at,
                completed_at=completion_time,
                recorded_at=completion_time,
            ),
            delivery_date=delivery_date,
            source_object=source_object,
        )
        return RecoveryItemExecutionResult(
            source_object=source_object,
            planned_action=RecoveryAction.LOAD_ONLY,
            outcome=RecoveryExecutionOutcome.SUCCEEDED,
            warehouse_result=warehouse_result,
        )

    def _execute_ingest_and_load(
        self, item: RecoveryPlanItem, delivery_date: date, ingestion_date: date, run_id: str, delivery: SourceDelivery
    ) -> RecoveryItemExecutionResult:
        source_object = item.source_object
        started_at = _now()

        self._append_state(
            ReplayStateRecord.running(
                run_id=run_id,
                event_id=str(uuid4()),
                delivery_date=delivery_date,
                source_object=source_object,
                stage=ReplayStage.INGESTION,
                started_at=started_at,
                recorded_at=_now(),
            ),
            delivery_date=delivery_date,
            source_object=source_object,
        )

        connector = build_connector(delivery, self.storage_manager)
        connector_result = connector.run(ingestion_date=ingestion_date)

        if connector_result.metadata.status is not IngestionStatus.SUCCESS:
            # BaseConnector.run() never emits raw exception text -- this
            # is already a safe, Mercury-authored OperationalError string.
            completion_time = _now()
            self._append_state(
                ReplayStateRecord.failed(
                    run_id=run_id,
                    event_id=str(uuid4()),
                    delivery_date=delivery_date,
                    source_object=source_object,
                    stage=ReplayStage.INGESTION,
                    started_at=started_at,
                    completed_at=completion_time,
                    recorded_at=completion_time,
                    error_message=connector_result.metadata.error_message,
                ),
                delivery_date=delivery_date,
                source_object=source_object,
            )
            return RecoveryItemExecutionResult(
                source_object=source_object,
                planned_action=RecoveryAction.INGEST_AND_LOAD,
                outcome=RecoveryExecutionOutcome.FAILED,
                ingestion_result=connector_result,
            )

        self._append_state(
            ReplayStateRecord.running(
                run_id=run_id,
                event_id=str(uuid4()),
                delivery_date=delivery_date,
                source_object=source_object,
                stage=ReplayStage.WAREHOUSE,
                started_at=started_at,
                recorded_at=_now(),
            ),
            delivery_date=delivery_date,
            source_object=source_object,
        )

        try:
            warehouse_result = self.bigquery_loader.load(
                source_object=connector_result.metadata.source_object,
                gcs_uri=connector_result.metadata.landing_path,
                partition_date=delivery_date,
            )
        except Exception:  # noqa: BLE001 - converted into a safe OperationalError below
            completion_time = _now()
            operational_error = OperationalError(
                category=OperationalErrorCategory.WAREHOUSE_LOAD_FAILED,
                component="RecoveryExecutor",
                operation="ingest_and_load",
                safe_message="Warehouse load failed during recovery",
            )
            self._append_state(
                ReplayStateRecord.failed(
                    run_id=run_id,
                    event_id=str(uuid4()),
                    delivery_date=delivery_date,
                    source_object=source_object,
                    stage=ReplayStage.WAREHOUSE,
                    started_at=started_at,
                    completed_at=completion_time,
                    recorded_at=completion_time,
                    error_message=operational_error.to_safe_string(),
                ),
                delivery_date=delivery_date,
                source_object=source_object,
            )
            return RecoveryItemExecutionResult(
                source_object=source_object,
                planned_action=RecoveryAction.INGEST_AND_LOAD,
                outcome=RecoveryExecutionOutcome.FAILED,
                ingestion_result=connector_result,
            )

        completion_time = _now()
        self._append_state(
            ReplayStateRecord.success(
                run_id=run_id,
                event_id=str(uuid4()),
                delivery_date=delivery_date,
                source_object=source_object,
                started_at=started_at,
                completed_at=completion_time,
                recorded_at=completion_time,
            ),
            delivery_date=delivery_date,
            source_object=source_object,
        )
        return RecoveryItemExecutionResult(
            source_object=source_object,
            planned_action=RecoveryAction.INGEST_AND_LOAD,
            outcome=RecoveryExecutionOutcome.SUCCEEDED,
            ingestion_result=connector_result,
            warehouse_result=warehouse_result,
        )

    def _append_state(self, record: ReplayStateRecord, *, delivery_date: date, source_object: str) -> None:
        """Persist one replay-state event, failing execution clearly if that fails.

        Operational replay state is part of the control plane, not a
        best-effort side channel: if persistence fails, execution does
        not continue to the current physical operation or any later
        sibling source. Neither GCS nor BigQuery is rolled back in that
        case -- any artifact already written remains exactly as it is.
        """
        try:
            self.replay_state_store.append(record)
        except Exception as exc:  # noqa: BLE001 - converted into a safe orchestration error below
            raise RecoveryExecutionError(
                f"failed to persist replay state (stage={record.stage.value}, status={record.status.value}) "
                f"for source_object={source_object!r} on {delivery_date.isoformat()}",
                delivery_date=delivery_date,
                source_object=source_object,
            ) from exc