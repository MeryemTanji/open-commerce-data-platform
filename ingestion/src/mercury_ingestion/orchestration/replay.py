"""Mercury's historical replay orchestration layer (ADR-009 / ADR-010).

``HistoricalReplayRunner`` coordinates existing, independently-proven
components -- a ``SourceDeliveryProvider``, Mercury's concrete
connectors, the existing ``IngestionRunner``, a ``StorageManager``,
``BigQueryRawLoader``, and a ``ReplayStateStore`` -- into a single
historical-replay workflow. It reimplements none of their internal
behavior: no CSV parsing, no Olist temporal selection, no source schema
validation, no checksum computation, no GCS object-naming or upload
mechanics, no BigQuery schemas, partition decorators, or
write-disposition rules, no BigQuery client creation, and no
replay-state persistence mechanics. Those all remain exactly where they
already live.

This module is distinct from ``mercury_ingestion.runner``, whose
``IngestionRunner`` executes a batch of connectors and stays exactly as
it is -- ``HistoricalReplayRunner`` sits one level above it, adding
source delivery, per-source replay-state tracking, and warehouse
loading around individual connector runs.

Per ADR-010's final daily execution model, a business date is one
completeness boundary containing several *independent* source
deliveries. Within one date, Mercury attempts all safe work: every
expected source's ingestion is attempted regardless of earlier
failures, and every successfully-ingested source is then attempted in
the warehouse phase regardless of earlier warehouse failures. A source
failing does not stop its siblings. Only once all safe work for the
date has been attempted does Mercury derive whether the date is
complete; an incomplete date stops the historical range from
progressing to later dates. ``run_initial_load()`` remains out of scope
for replay-state tracking -- ADR-010's immediate scope is historical
incremental (daily) replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from mercury_ingestion.common.metadata import IngestionStatus
from mercury_ingestion.common.storage import StorageManager
from mercury_ingestion.connectors.base import BaseConnector, ConnectorRunResult
from mercury_ingestion.connectors.customers import CustomerConnector
from mercury_ingestion.connectors.geolocations import GeolocationConnector
from mercury_ingestion.connectors.order_items import OrderItemsConnector
from mercury_ingestion.connectors.orders import OrdersConnector
from mercury_ingestion.connectors.payments import PaymentsConnector
from mercury_ingestion.connectors.products import ProductsConnector
from mercury_ingestion.connectors.reviews import ReviewsConnector
from mercury_ingestion.connectors.sellers import SellersConnector
from mercury_ingestion.orchestration.state import (
    ReplayStage,
    ReplayStateRecord,
    ReplayStateStore,
    is_date_complete,
)
from mercury_ingestion.runner import IngestionRunner, RunnerResult, RunnerStatus
from mercury_ingestion.sources.base import SourceDelivery, SourceDeliveryBatch, SourceDeliveryProvider
from mercury_ingestion.warehouse.bigquery_loader import BigQueryLoadResult, BigQueryRawLoader

# Maps each stable Mercury source_object to its existing concrete
# connector class. Deliberately explicit rather than derived, so the
# mapping stays reviewable and never silently drifts from the actual
# connector set.
CONNECTOR_MAP: dict[str, type[BaseConnector]] = {
    "customers": CustomerConnector,
    "orders": OrdersConnector,
    "order_items": OrderItemsConnector,
    "products": ProductsConnector,
    "sellers": SellersConnector,
    "payments": PaymentsConnector,
    "reviews": ReviewsConnector,
    "geolocations": GeolocationConnector,
}

# Expected source membership for each replay stage. Declared explicitly
# here rather than imported from mercury_ingestion.simulation.olist, so
# orchestration stays independent of Olist-simulation internals -- a
# future non-simulated SourceDeliveryProvider (e.g. a REST-backed one)
# has no reason to depend on simulator constants, and this runner
# shouldn't either. The values happen to match the simulator's own
# classification because both describe the same real-world source set,
# not because one derives from the other.
INITIAL_SOURCE_OBJECTS: frozenset[str] = frozenset({"customers", "products", "sellers", "geolocations"})
DAILY_SOURCE_OBJECTS: frozenset[str] = frozenset({"orders", "order_items", "payments", "reviews"})


def _now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _require_date(value: object, field_name: str) -> None:
    if not isinstance(value, date):
        raise TypeError(f"{field_name} must be a datetime.date")


class HistoricalReplayError(Exception):
    """Raised when a stage of historical replay fails for a given day.

    Carries orchestration context (which delivery date, which stage,
    and -- for source-level failures -- which source object) without
    hiding the underlying cause, which remains available via normal
    exception chaining (``raise ... from exc``). When a date turns out
    incomplete after all safe work has already been attempted,
    ``partial_day_result`` carries whatever ``HistoricalReplayDayResult``
    was already assembled, so a caller can still inspect which sources
    actually succeeded rather than losing that information merely
    because the date as a whole did not complete.
    """

    def __init__(
        self,
        message: str,
        *,
        delivery_date: date,
        stage: str,
        source_object: str | None = None,
        partial_day_result: "HistoricalReplayDayResult | None" = None,
    ) -> None:
        super().__init__(message)
        self.delivery_date = delivery_date
        self.stage = stage
        self.source_object = source_object
        self.partial_day_result = partial_day_result


@dataclass(frozen=True, slots=True)
class HistoricalReplayInitialResult:
    """Outcome of a single ``run_initial_load()`` call."""

    ingestion_date: date
    source_batch: SourceDeliveryBatch
    ingestion_result: RunnerResult
    warehouse_results: tuple[BigQueryLoadResult, ...]

    def __post_init__(self) -> None:
        _require_date(self.ingestion_date, "ingestion_date")
        if not isinstance(self.source_batch, SourceDeliveryBatch):
            raise TypeError("source_batch must be a SourceDeliveryBatch")
        if not isinstance(self.ingestion_result, RunnerResult):
            raise TypeError("ingestion_result must be a RunnerResult")
        if not isinstance(self.warehouse_results, tuple):
            raise TypeError("warehouse_results must be a tuple")


@dataclass(frozen=True, slots=True)
class HistoricalReplayDayResult:
    """Outcome of a single date's replay -- successful only if the date is complete.

    ``ingestion_result.results`` contains every attempted source's
    individual ``ConnectorRunResult`` (one per expected source, in
    delivery order), even those that failed -- Phase 2's per-source
    execution never discards a connector's own result. ``warehouse_results``
    contains one ``BigQueryLoadResult`` per source whose warehouse load
    actually succeeded, which may be fewer than the full expected set on
    an incomplete date. When ``run_day()``/``run_range()`` raise because a
    date turned out incomplete, the ``HistoricalReplayDayResult`` already
    assembled up to that point is attached to the raised
    ``HistoricalReplayError`` as ``partial_day_result``, so this
    information is never silently discarded.
    """

    delivery_date: date
    source_batch: SourceDeliveryBatch
    ingestion_result: RunnerResult
    warehouse_results: tuple[BigQueryLoadResult, ...]

    def __post_init__(self) -> None:
        _require_date(self.delivery_date, "delivery_date")
        if not isinstance(self.source_batch, SourceDeliveryBatch):
            raise TypeError("source_batch must be a SourceDeliveryBatch")
        if not isinstance(self.ingestion_result, RunnerResult):
            raise TypeError("ingestion_result must be a RunnerResult")
        if not isinstance(self.warehouse_results, tuple):
            raise TypeError("warehouse_results must be a tuple")


@dataclass(frozen=True, slots=True)
class HistoricalReplayRangeResult:
    """Outcome of a single ``run_range()`` call, covering only completed days."""

    start_date: date
    end_date: date
    day_results: tuple[HistoricalReplayDayResult, ...]

    def __post_init__(self) -> None:
        _require_date(self.start_date, "start_date")
        _require_date(self.end_date, "end_date")
        if not isinstance(self.day_results, tuple):
            raise TypeError("day_results must be a tuple")


@dataclass(frozen=True, slots=True)
class _SourceIngestionOutcome:
    """Internal carrier passed from the ingestion phase to the warehouse phase.

    Not part of the public API -- purely a way to hand each source's
    connector result and execution-start time from
    ``_run_ingestion_phase`` to ``_run_warehouse_phase`` without
    recomputing or losing either.
    """

    source_object: str
    source_started_at: datetime
    connector_result: ConnectorRunResult
    ingestion_succeeded: bool


def _derive_ingestion_status(connector_results: tuple[ConnectorRunResult, ...]) -> RunnerStatus:
    """Derive the RunnerStatus this set of connector results represents.

    Mirrors ``IngestionRunner``'s own status-derivation rule (success if
    zero failed, failed if all failed, partial failure otherwise), but is
    computed locally from already-executed ``ConnectorRunResult`` values
    rather than by importing ``IngestionRunner``'s private helper --
    Phase 2 runs each connector individually (one at a time, so a
    per-source RUNNING state can be recorded immediately before each
    attempt) rather than as a single ``IngestionRunner`` batch, so no
    single ``IngestionRunner`` call ever sees the full four-connector set
    to derive this status itself.
    """
    if not connector_results:
        raise ValueError("connector_results cannot be empty")
    failed_count = sum(1 for result in connector_results if result.metadata.status is IngestionStatus.FAILED)
    if failed_count == 0:
        return RunnerStatus.SUCCESS
    if failed_count == len(connector_results):
        return RunnerStatus.FAILED
    return RunnerStatus.PARTIAL_FAILURE


class HistoricalReplayRunner:
    """Coordinates source delivery, per-source replay-state tracking,
    ingestion, and warehouse loading.

    Dependencies are injected rather than constructed internally: this
    class never creates a GCP client, a storage manager, a source
    provider, or a replay-state store itself. It accepts the
    ``StorageManager`` abstraction (not a hard-coded
    ``GCSStorageManager``) and the generic ``ReplayStateStore``
    abstraction (not a hard-coded ``BigQueryReplayStateStore``), so any
    conforming implementation -- local, cloud, or in-memory for tests --
    can be used. ``BigQueryRawLoader`` remains solely responsible for
    validating that a landing path is a ``gs://`` URI, which this class
    does not duplicate. Resource initialization (e.g.
    ``BigQueryReplayStateStore.ensure_resources()``) is the caller's
    responsibility before constructing this runner, not this runner's.

    ``replay_state_store`` is a required constructor dependency, exactly
    like ``storage_manager`` and ``bigquery_loader`` -- it is not made
    optional. Incremental historical replay (``run_day()``/``run_range()``)
    is not allowed to silently run without durable state tracking, and
    making the dependency uniformly required keeps the constructor's
    contract simple and avoids ``Optional``-handling branches inside
    ``run_day()``/``run_range()``. ``run_initial_load()`` simply does not
    use it -- callers who only ever call ``run_initial_load()`` still
    construct one (the ADR-010 usage example shows the state store
    always being constructed before the runner), which is a minor
    constructor-time inconvenience rather than a real cost.
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

    def run_initial_load(self, ingestion_date: date) -> HistoricalReplayInitialResult:
        """Run the master/reference sources through ingestion and warehouse loading.

        ``ingestion_date`` is explicit -- the connectors and
        ``BigQueryRawLoader`` both require a platform ingestion date even
        though the resulting BigQuery tables are unpartitioned; this
        runner never manufactures one internally.

        Out of scope for ADR-010 replay-state tracking: no
        ``ReplayStateRecord`` events are written for initial/master-
        reference loads, and ``self.replay_state_store`` is not touched
        by this method at all. ADR-010's immediate scope is historical
        incremental (daily) replay; the reference workflow remains the
        simpler ADR-009 all-or-nothing batch behavior.
        """
        _require_date(ingestion_date, "ingestion_date")

        source_batch = self.source_provider.get_initial_delivery()
        self._validate_batch_membership(source_batch, INITIAL_SOURCE_OBJECTS, ingestion_date)
        ingestion_result = self._run_ingestion_batch(
            source_batch, ingestion_date, ingestion_date, stage="initial ingestion"
        )
        warehouse_results = self._load_warehouse_batch(ingestion_result, ingestion_date)

        return HistoricalReplayInitialResult(
            ingestion_date=ingestion_date,
            source_batch=source_batch,
            ingestion_result=ingestion_result,
            warehouse_results=warehouse_results,
        )

    def generate_range(self, start_date: date, end_date: date) -> tuple[SourceDeliveryBatch, ...]:
        """Generate/retrieve daily source deliveries only -- no ingestion, no warehouse.

        This keeps historical source generation independently executable
        from cloud ingestion and warehouse replay, per ADR-009.
        """
        self._validate_range(start_date, end_date)
        return tuple(self.source_provider.get_daily_delivery(day) for day in self._iter_dates(start_date, end_date))

    def run_day(self, delivery_date: date) -> HistoricalReplayDayResult:
        """Run one complete transactional day and generate a fresh run_id for it.

        Public callers never supply or manage ``run_id`` -- it is
        generated here and shared by every replay-state event this
        invocation writes.
        """
        _require_date(delivery_date, "delivery_date")
        run_id = str(uuid4())
        return self._run_day(delivery_date, run_id)

    def run_range(self, start_date: date, end_date: date) -> HistoricalReplayRangeResult:
        """Run each day in the inclusive range in order, stopping after the first incomplete date.

        Exactly one ``run_id`` is generated for the entire invocation and
        shared by every replay-state event written across every
        attempted date -- not one per date. Within each date, Mercury
        attempts all safe work (every expected source's ingestion, then
        every successfully-ingested source's warehouse load) regardless
        of individual source failures; only once a date's safe work is
        exhausted and found incomplete does the range stop, and later
        dates are never attempted. Version 1 has no continue-on-error
        mode, retries, or resume/checkpointing.
        """
        self._validate_range(start_date, end_date)
        run_id = str(uuid4())

        day_results: list[HistoricalReplayDayResult] = []
        for day in self._iter_dates(start_date, end_date):
            day_results.append(self._run_day(day, run_id))  # raises + stops on incomplete date

        return HistoricalReplayRangeResult(start_date=start_date, end_date=end_date, day_results=tuple(day_results))

    def _run_day(self, delivery_date: date, run_id: str) -> HistoricalReplayDayResult:
        """Run one day's sources through the two ordered phases, then derive completeness.

        Sources are processed in ``source_batch.deliveries`` order (the
        order the provider returned them in) within each phase. Ingestion
        is fully attempted for every expected source before the
        warehouse phase begins for any source -- the two phases are
        never interleaved.

        Completeness is derived from logical completion state (across
        every replay attempt for this date), not merely this
        invocation's own latest-attempt outcome. This means a date that
        was already fully complete from an earlier successful run still
        returns normally here even if the current attempt's connectors
        all failed (e.g. because the immutable GCS destinations already
        exist) -- the earlier success is not erased by a later failure.
        This call's own outcome, failures included, always remains
        inspectable through the returned ``HistoricalReplayDayResult``.
        """
        source_batch = self.source_provider.get_daily_delivery(delivery_date)
        self._validate_batch_membership(source_batch, DAILY_SOURCE_OBJECTS, delivery_date)

        outcomes = self._run_ingestion_phase(source_batch.deliveries, delivery_date, run_id)
        warehouse_results = self._run_warehouse_phase(outcomes, delivery_date, run_id)

        connector_results = tuple(outcome.connector_result for outcome in outcomes)
        ingestion_result = RunnerResult(
            results=connector_results, status=_derive_ingestion_status(connector_results)
        )

        day_result = HistoricalReplayDayResult(
            delivery_date=delivery_date,
            source_batch=source_batch,
            ingestion_result=ingestion_result,
            warehouse_results=warehouse_results,
        )

        # Logical completion is monotonic: a source that has ever
        # reached SUCCESS|WAREHOUSE remains logically complete even if
        # *this* invocation's own attempt failed (e.g. connectors
        # failing because the immutable GCS destination already exists
        # from an earlier successful run). Completeness is therefore
        # derived from get_completed_for_date(), not from this run's own
        # latest-attempt events -- a failed replay of an already-complete
        # date must not be mistaken for losing that completion.
        completed_records = self.replay_state_store.get_completed_for_date(delivery_date)
        if not is_date_complete(completed_records, DAILY_SOURCE_OBJECTS):
            latest_records = self.replay_state_store.get_latest_for_date(delivery_date)
            completed_source_objects = {record.source_object for record in completed_records}
            raise HistoricalReplayError(
                f"date {delivery_date.isoformat()} is incomplete after attempting all safe work "
                f"({self._summarize_incomplete_sources(latest_records, completed_source_objects)})",
                delivery_date=delivery_date,
                stage="date_completion",
                partial_day_result=day_result,
            )

        return day_result

    def _run_ingestion_phase(
        self, deliveries: tuple[SourceDelivery, ...], delivery_date: date, run_id: str
    ) -> list[_SourceIngestionOutcome]:
        """Attempt ingestion for every expected source; never stop on an individual failure.

        Before each connector attempt, a RUNNING|INGESTION event is
        appended. A connector's own well-behaved FAILED result (the
        normal outcome of a source-level problem) does not stop this
        loop -- the remaining independent sources are still attempted.
        An unexpected exception escaping the connector run (a
        programming-contract violation per BaseConnector's own
        docstring, not an ordinary ingestion failure) does abort
        immediately, with the original exception preserved as cause.
        """
        outcomes: list[_SourceIngestionOutcome] = []
        for delivery in deliveries:
            source_object = delivery.source_object
            source_started_at = _now()

            self._append_state(
                ReplayStateRecord.running(
                    run_id=run_id,
                    event_id=str(uuid4()),
                    delivery_date=delivery_date,
                    source_object=source_object,
                    stage=ReplayStage.INGESTION,
                    started_at=source_started_at,
                    recorded_at=_now(),
                ),
                delivery_date=delivery_date,
                source_object=source_object,
            )

            connector = self._build_connector(delivery)
            try:
                single_result = IngestionRunner([connector]).run_all(ingestion_date=delivery_date)
            except Exception as exc:
                completion_time = _now()
                self._append_state(
                    ReplayStateRecord.failed(
                        run_id=run_id,
                        event_id=str(uuid4()),
                        delivery_date=delivery_date,
                        source_object=source_object,
                        stage=ReplayStage.INGESTION,
                        started_at=source_started_at,
                        completed_at=completion_time,
                        recorded_at=completion_time,
                        error_message=str(exc),
                    ),
                    delivery_date=delivery_date,
                    source_object=source_object,
                )
                raise HistoricalReplayError(
                    f"unexpected error during ingestion for source_object={source_object!r} on "
                    f"{delivery_date.isoformat()}: {exc}",
                    delivery_date=delivery_date,
                    stage="ingestion",
                    source_object=source_object,
                ) from exc

            connector_result = single_result.results[0]

            if single_result.succeeded_count != 1:
                completion_time = _now()
                self._append_state(
                    ReplayStateRecord.failed(
                        run_id=run_id,
                        event_id=str(uuid4()),
                        delivery_date=delivery_date,
                        source_object=source_object,
                        stage=ReplayStage.INGESTION,
                        started_at=source_started_at,
                        completed_at=completion_time,
                        recorded_at=completion_time,
                        error_message=connector_result.metadata.error_message,
                    ),
                    delivery_date=delivery_date,
                    source_object=source_object,
                )
                outcomes.append(
                    _SourceIngestionOutcome(
                        source_object=source_object,
                        source_started_at=source_started_at,
                        connector_result=connector_result,
                        ingestion_succeeded=False,
                    )
                )
                continue  # attempt-all-safe-work: keep going, do not stop the date

            outcomes.append(
                _SourceIngestionOutcome(
                    source_object=source_object,
                    source_started_at=source_started_at,
                    connector_result=connector_result,
                    ingestion_succeeded=True,
                )
            )

        return outcomes

    def _run_warehouse_phase(
        self, outcomes: list[_SourceIngestionOutcome], delivery_date: date, run_id: str
    ) -> tuple[BigQueryLoadResult, ...]:
        """Load every ingestion-eligible source; never stop on an individual failure.

        A source whose ingestion did not succeed is skipped entirely --
        no RUNNING or FAILED warehouse event is fabricated for it, since
        warehouse was genuinely never attempted; its latest state
        correctly remains whatever ingestion recorded. A warehouse
        failure for one eligible source does not stop the remaining
        eligible sources from being attempted.
        """
        warehouse_results: list[BigQueryLoadResult] = []
        for outcome in outcomes:
            if not outcome.ingestion_succeeded:
                continue  # not eligible; latest state remains FAILED|INGESTION

            source_object = outcome.source_object
            metadata = outcome.connector_result.metadata

            self._append_state(
                ReplayStateRecord.running(
                    run_id=run_id,
                    event_id=str(uuid4()),
                    delivery_date=delivery_date,
                    source_object=source_object,
                    stage=ReplayStage.WAREHOUSE,
                    started_at=outcome.source_started_at,
                    recorded_at=_now(),
                ),
                delivery_date=delivery_date,
                source_object=source_object,
            )

            try:
                load_result = self.bigquery_loader.load(
                    source_object=metadata.source_object,
                    gcs_uri=metadata.landing_path,
                    ingestion_date=delivery_date,
                )
            except Exception as exc:
                completion_time = _now()
                self._append_state(
                    ReplayStateRecord.failed(
                        run_id=run_id,
                        event_id=str(uuid4()),
                        delivery_date=delivery_date,
                        source_object=source_object,
                        stage=ReplayStage.WAREHOUSE,
                        started_at=outcome.source_started_at,
                        completed_at=completion_time,
                        recorded_at=completion_time,
                        error_message=str(exc),
                    ),
                    delivery_date=delivery_date,
                    source_object=source_object,
                )
                continue  # attempt-all-safe-work: keep going, do not stop the date

            completion_time = _now()
            self._append_state(
                ReplayStateRecord.success(
                    run_id=run_id,
                    event_id=str(uuid4()),
                    delivery_date=delivery_date,
                    source_object=source_object,
                    started_at=outcome.source_started_at,
                    completed_at=completion_time,
                    recorded_at=completion_time,
                ),
                delivery_date=delivery_date,
                source_object=source_object,
            )
            warehouse_results.append(load_result)

        return tuple(warehouse_results)

    def _append_state(self, record: ReplayStateRecord, *, delivery_date: date, source_object: str) -> None:
        """Persist one replay-state event, failing the replay clearly if that fails.

        Operational replay state is part of the control plane, not a
        best-effort side channel: if persistence fails, processing does
        not continue "trusting" an untracked source -- even when the
        underlying connector/warehouse work already succeeded. Neither
        GCS nor BigQuery is rolled back in that case; the immutable
        artifacts already written remain exactly as they are, and this
        is surfaced as a control-plane failure for a future recovery
        design to reconcile, not silently ignored here. Unlike ordinary
        source-level failures, a state-store append failure always
        aborts the current replay immediately -- it is never treated as
        "safe work to continue past."
        """
        try:
            self.replay_state_store.append(record)
        except Exception as exc:
            raise HistoricalReplayError(
                f"failed to persist replay state (stage={record.stage.value}, status={record.status.value}) "
                f"for source_object={source_object!r} on {delivery_date.isoformat()}: {exc}",
                delivery_date=delivery_date,
                stage="state_store",
                source_object=source_object,
            ) from exc

    @staticmethod
    def _summarize_incomplete_sources(
        latest_records: tuple[ReplayStateRecord, ...], completed_source_objects: set[str]
    ) -> str:
        """Build a short, modest summary of why a date is incomplete.

        Not a generic workflow-exception framework -- just enough text
        to name every expected source that has never logically
        completed, with its latest known attempt status/stage, so an
        incomplete-date error is never reduced to a single opaque
        source_object the way earlier stage-specific errors are. A
        source in ``completed_source_objects`` is skipped here even if
        its latest attempt event is FAILED or RUNNING -- an earlier
        success means it is not part of why the date is incomplete.
        """
        by_source = {record.source_object: record for record in latest_records}
        parts = []
        for source_object in sorted(DAILY_SOURCE_OBJECTS):
            if source_object in completed_source_objects:
                continue
            record = by_source.get(source_object)
            if record is None:
                parts.append(f"{source_object}=not attempted")
            else:
                parts.append(f"{source_object}={record.status.value}|{record.stage.value}")
        return ", ".join(parts) if parts else "unknown"

    def _run_ingestion_batch(
        self,
        source_batch: SourceDeliveryBatch,
        ingestion_date: date,
        error_date: date,
        *,
        stage: str,
    ) -> RunnerResult:
        """Run every delivery's connector as one IngestionRunner batch.

        Used only by ``run_initial_load()``, which remains out of scope
        for per-source replay-state tracking and preserves the simpler
        ADR-009 all-or-nothing batch behavior.
        """
        connectors = [self._build_connector(delivery) for delivery in source_batch.deliveries]
        ingestion_result = IngestionRunner(connectors).run_all(ingestion_date=ingestion_date)

        if ingestion_result.succeeded_count != ingestion_result.total_count:
            raise HistoricalReplayError(
                f"{stage} did not fully succeed for {error_date.isoformat()}: "
                f"{ingestion_result.succeeded_count}/{ingestion_result.total_count} connectors succeeded "
                f"(status={ingestion_result.status.value})",
                delivery_date=error_date,
                stage="ingestion",
            )

        return ingestion_result

    def _load_warehouse_batch(
        self, ingestion_result: RunnerResult, ingestion_date: date
    ) -> tuple[BigQueryLoadResult, ...]:
        """Load every successfully-ingested source into BigQuery.

        Used only by ``run_initial_load()``.
        """
        results = []
        for connector_result in ingestion_result.results:
            metadata = connector_result.metadata
            try:
                load_result = self.bigquery_loader.load(
                    source_object=metadata.source_object,
                    gcs_uri=metadata.landing_path,
                    ingestion_date=ingestion_date,
                )
            except Exception as exc:
                raise HistoricalReplayError(
                    f"warehouse load failed for source_object={metadata.source_object!r} on "
                    f"{ingestion_date.isoformat()}: {exc}",
                    delivery_date=ingestion_date,
                    stage="warehouse",
                    source_object=metadata.source_object,
                ) from exc
            results.append(load_result)
        return tuple(results)

    def _build_connector(self, delivery: SourceDelivery) -> BaseConnector:
        connector_class = CONNECTOR_MAP.get(delivery.source_object)
        if connector_class is None:
            raise ValueError(f"unsupported source_object for historical replay: {delivery.source_object!r}")
        return connector_class(source_file=delivery.path, storage_manager=self.storage_manager)

    @staticmethod
    def _validate_batch_membership(
        source_batch: SourceDeliveryBatch, expected_source_objects: frozenset[str], error_date: date
    ) -> None:
        """Verify the provider returned exactly the expected source set.

        Runs before any connector is built, before ``IngestionRunner`` is
        called, before ``StorageManager`` is touched, before
        ``BigQueryRawLoader`` is touched, and before any per-source
        replay-state event is written -- a provider returning the wrong
        source set (missing sources, unexpected extras, or both) must
        never be silently treated as that day's intended batch. No
        per-source ``ReplayStateRecord`` is written for this failure:
        Mercury cannot truthfully attribute a membership mismatch to any
        specific source.
        """
        actual_source_objects = {delivery.source_object for delivery in source_batch.deliveries}
        missing = expected_source_objects - actual_source_objects
        unexpected = actual_source_objects - expected_source_objects
        if missing or unexpected:
            details = []
            if missing:
                details.append(f"missing: {', '.join(sorted(missing))}")
            if unexpected:
                details.append(f"unexpected: {', '.join(sorted(unexpected))}")
            raise HistoricalReplayError(
                f"source delivery for {error_date.isoformat()} does not match the expected source "
                f"set ({'; '.join(details)})",
                delivery_date=error_date,
                stage="source_delivery",
            )

    @staticmethod
    def _validate_range(start_date: date, end_date: date) -> None:
        _require_date(start_date, "start_date")
        _require_date(end_date, "end_date")
        if start_date > end_date:
            raise ValueError(f"start_date ({start_date.isoformat()}) cannot be after end_date ({end_date.isoformat()})")

    @staticmethod
    def _iter_dates(start_date: date, end_date: date):
        current = start_date
        while current <= end_date:
            yield current
            current += timedelta(days=1)