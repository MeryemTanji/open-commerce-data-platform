"""Mercury's historical replay orchestration layer (ADR-009).

``HistoricalReplayRunner`` coordinates existing, independently-proven
components — a ``SourceDeliveryProvider``, Mercury's concrete
connectors, the existing ``IngestionRunner``, a ``StorageManager``, and
``BigQueryRawLoader`` — into a single historical-replay workflow. It
reimplements none of their internal behavior: no CSV parsing, no Olist
temporal selection, no source schema validation, no checksum
computation, no GCS object-naming or upload mechanics, no BigQuery
schemas, partition decorators, or write-disposition rules, and no
BigQuery client creation. Those all remain exactly where they already
live.

This module is distinct from ``mercury_ingestion.runner``, whose
``IngestionRunner`` executes a batch of connectors and stays exactly as
it is -- ``HistoricalReplayRunner`` sits one level above it, adding
source delivery and warehouse loading around an ``IngestionRunner`` run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from mercury_ingestion.common.storage import StorageManager
from mercury_ingestion.connectors.base import BaseConnector
from mercury_ingestion.connectors.customers import CustomerConnector
from mercury_ingestion.connectors.geolocations import GeolocationConnector
from mercury_ingestion.connectors.order_items import OrderItemsConnector
from mercury_ingestion.connectors.orders import OrdersConnector
from mercury_ingestion.connectors.payments import PaymentsConnector
from mercury_ingestion.connectors.products import ProductsConnector
from mercury_ingestion.connectors.reviews import ReviewsConnector
from mercury_ingestion.connectors.sellers import SellersConnector
from mercury_ingestion.runner import IngestionRunner, RunnerResult
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


class HistoricalReplayError(Exception):
    """Raised when a stage of historical replay fails for a given day.

    Carries orchestration context (which delivery date, which stage,
    and -- for warehouse failures -- which source object) without
    hiding the underlying cause, which remains available via normal
    exception chaining (``raise ... from exc``).
    """

    def __init__(self, message: str, *, delivery_date: date, stage: str, source_object: str | None = None) -> None:
        super().__init__(message)
        self.delivery_date = delivery_date
        self.stage = stage
        self.source_object = source_object


def _require_date(value: object, field_name: str) -> None:
    if not isinstance(value, date):
        raise TypeError(f"{field_name} must be a datetime.date")


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
    """Outcome of a single ``run_day()`` call."""

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


class HistoricalReplayRunner:
    """Coordinates source delivery, ingestion, and warehouse loading.

    Dependencies are injected rather than constructed internally: this
    class never creates a GCP client, a storage manager, or a source
    provider itself. It accepts the ``StorageManager`` abstraction
    (not a hard-coded ``GCSStorageManager``), so any conforming
    implementation -- local or cloud -- can be used; ``BigQueryRawLoader``
    remains solely responsible for validating that a landing path is a
    ``gs://`` URI, which this class does not duplicate.
    """

    def __init__(
        self,
        source_provider: SourceDeliveryProvider,
        storage_manager: StorageManager,
        bigquery_loader: BigQueryRawLoader,
    ) -> None:
        if not isinstance(source_provider, SourceDeliveryProvider):
            raise TypeError("source_provider must be a SourceDeliveryProvider")
        if not isinstance(storage_manager, StorageManager):
            raise TypeError("storage_manager must be a StorageManager")
        if not isinstance(bigquery_loader, BigQueryRawLoader):
            raise TypeError("bigquery_loader must be a BigQueryRawLoader")

        self.source_provider = source_provider
        self.storage_manager = storage_manager
        self.bigquery_loader = bigquery_loader

    def run_initial_load(self, ingestion_date: date) -> HistoricalReplayInitialResult:
        """Run the master/reference sources through ingestion and warehouse loading.

        ``ingestion_date`` is explicit -- the connectors and
        ``BigQueryRawLoader`` both require a platform ingestion date even
        though the resulting BigQuery tables are unpartitioned; this
        runner never manufactures one internally.
        """
        _require_date(ingestion_date, "ingestion_date")

        source_batch = self.source_provider.get_initial_delivery()
        self._validate_batch_membership(source_batch, INITIAL_SOURCE_OBJECTS, ingestion_date)
        ingestion_result = self._run_ingestion(source_batch, ingestion_date, ingestion_date, stage="initial ingestion")
        warehouse_results = self._load_warehouse(ingestion_result, ingestion_date)

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
        """Run one complete transactional day: delivery -> ingestion -> warehouse.

        BigQuery loading never begins until every connector in the day's
        ingestion batch has succeeded.
        """
        _require_date(delivery_date, "delivery_date")

        source_batch = self.source_provider.get_daily_delivery(delivery_date)
        self._validate_batch_membership(source_batch, DAILY_SOURCE_OBJECTS, delivery_date)
        ingestion_result = self._run_ingestion(source_batch, delivery_date, delivery_date, stage="ingestion")
        warehouse_results = self._load_warehouse(ingestion_result, delivery_date)

        return HistoricalReplayDayResult(
            delivery_date=delivery_date,
            source_batch=source_batch,
            ingestion_result=ingestion_result,
            warehouse_results=warehouse_results,
        )

    def run_range(self, start_date: date, end_date: date) -> HistoricalReplayRangeResult:
        """Run each day in the inclusive range in order, stopping at the first failure.

        A day's failure (ingestion or warehouse) stops the range
        immediately -- later dates are never attempted. Version 1 has no
        continue-on-error mode, retries, or resume/checkpointing.
        """
        self._validate_range(start_date, end_date)

        day_results: list[HistoricalReplayDayResult] = []
        for day in self._iter_dates(start_date, end_date):
            day_results.append(self.run_day(day))  # propagates on failure, stopping the loop

        return HistoricalReplayRangeResult(start_date=start_date, end_date=end_date, day_results=tuple(day_results))

    def _run_ingestion(
        self,
        source_batch: SourceDeliveryBatch,
        ingestion_date: date,
        error_date: date,
        *,
        stage: str,
    ) -> RunnerResult:
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

    def _load_warehouse(self, ingestion_result: RunnerResult, ingestion_date: date) -> tuple[BigQueryLoadResult, ...]:
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
        called, before ``StorageManager`` is touched, and before
        ``BigQueryRawLoader`` is touched -- a provider returning the
        wrong source set (missing sources, unexpected extras, or both)
        must never be silently treated as that day's intended batch.
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