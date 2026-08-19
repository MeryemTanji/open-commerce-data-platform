"""Unit tests for mercury_ingestion.orchestration.replay.

Fully offline: LocalStorageManager/a fake GCS-shaped StorageManager write
to a temp directory (real, no network), and only the BigQuery client
boundary is faked. The source provider and replay-state store are
lightweight test doubles implementing their respective ABCs directly, so
tests can construct arbitrary batches and simulate control-plane
failures without depending on the real Olist simulator or BigQuery.

Per ADR-010's final daily execution model, a source failure (ingestion
or warehouse) does NOT stop other independent sources for the same
date -- Mercury attempts all safe work within a date. Only a state-store
append failure aborts immediately, and only an incomplete date (derived
after all safe work is attempted) stops a historical range. Several
tests below intentionally supersede the older ADR-009 fail-fast-within-
date expectations; each such test is clearly marked.
"""

from __future__ import annotations

import csv
import hashlib
import inspect
from datetime import date
from pathlib import Path
from typing import Callable

import pytest
from google.api_core import exceptions as gcs_exceptions

from mercury_ingestion.common.storage import LocalStorageManager, StorageManager, StorageResult
from mercury_ingestion.orchestration.replay import (
    CONNECTOR_MAP,
    DAILY_SOURCE_OBJECTS,
    HistoricalReplayError,
    HistoricalReplayRunner,
)
from mercury_ingestion.orchestration.state import (
    ReplayStage,
    ReplayStateRecord,
    ReplayStateStore,
    ReplayStatus,
)
from mercury_ingestion.sources.base import SourceDelivery, SourceDeliveryBatch, SourceDeliveryProvider
from mercury_ingestion.warehouse import bigquery_loader as bigquery_loader_module
from mercury_ingestion.warehouse.bigquery_loader import BigQueryRawLoader

CUSTOMERS_HEADER = ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"]
PRODUCTS_HEADER = [
    "product_id",
    "product_category_name",
    "product_name_lenght",
    "product_description_lenght",
    "product_photos_qty",
    "product_weight_g",
    "product_length_cm",
    "product_height_cm",
    "product_width_cm",
]
SELLERS_HEADER = ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"]
GEOLOCATION_HEADER = ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"]
ORDERS_HEADER = [
    "order_id",
    "customer_id",
    "order_status",
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]
ORDER_ITEMS_HEADER = ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"]
PAYMENTS_HEADER = ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"]
REVIEWS_HEADER = [
    "review_id",
    "order_id",
    "review_score",
    "review_comment_title",
    "review_comment_message",
    "review_creation_date",
    "review_answer_timestamp",
]


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
    return path


# --- Fake BigQuery client boundary (offline, no network) -------------------


class _FakeBQJob:
    def __init__(self, output_rows: int, job_id: str, raise_exc: BaseException | None) -> None:
        self.output_rows = output_rows
        self.job_id = job_id
        self._raise_exc = raise_exc

    def result(self) -> "_FakeBQJob":
        if self._raise_exc is not None:
            raise self._raise_exc
        return self


class _FakeBigQueryClient:
    def __init__(self, project: str | None = None, location: str | None = None, **kwargs: object) -> None:
        self.project = project
        self.location = location
        self.load_calls: list[dict[str, object]] = []
        self.raise_for_destination: dict[str, BaseException] = {}
        self._job_counter = 0

    def load_table_from_uri(
        self,
        source_uris: object,
        destination: object,
        *,
        job_config: object = None,
        location: str | None = None,
        **kwargs: object,
    ) -> _FakeBQJob:
        self._job_counter += 1
        self.load_calls.append({"source_uris": source_uris, "destination": destination, "location": location})
        raise_exc = self.raise_for_destination.get(str(destination))
        return _FakeBQJob(output_rows=1, job_id=f"job-{self._job_counter}", raise_exc=raise_exc)


@pytest.fixture(autouse=True)
def _fake_bigquery_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bigquery_loader_module.bigquery, "Client", _FakeBigQueryClient)


def _make_bigquery_loader() -> BigQueryRawLoader:
    return BigQueryRawLoader(project_id="mercury-data-platform-dev", dataset_id="raw")


# --- Fake GCS-shaped StorageManager (offline, no network) ------------------
#
# HistoricalReplayRunner accepts the StorageManager abstraction, not a
# hard-coded GCSStorageManager, so these tests exercise it with a small
# fake that mirrors GCS's real, load-bearing behavior: it returns
# gs://-style landing paths (so BigQueryRawLoader's own URI validation
# passes, exactly as it would against real GCS) and it enforces the same
# create-only, no-overwrite guarantee as the real GCSStorageManager,
# without ever touching the network.


class _FakeGcsStorageManager(StorageManager):
    def __init__(self, local_root: Path, bucket_name: str = "mercury-data-platform-dev-raw-01") -> None:
        self.local_root = local_root
        self.bucket_name = bucket_name
        self._landed_objects: set[str] = set()

    def save_file(self, source_file: Path, source_system: str, source_object: str, ingestion_date: date) -> StorageResult:
        object_name = (
            f"raw/{source_system}/{source_object}/ingestion_date={ingestion_date.isoformat()}/{source_file.name}"
        )
        if object_name in self._landed_objects:
            raise FileExistsError(f"destination object already exists: gs://{self.bucket_name}/{object_name}")

        content = source_file.read_bytes()
        destination_path = self.local_root / object_name
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_bytes(content)
        self._landed_objects.add(object_name)

        return StorageResult(
            landing_path=f"gs://{self.bucket_name}/{object_name}",
            checksum=hashlib.sha256(content).hexdigest(),
            file_size_bytes=len(content),
        )


# --- Test source provider double --------------------------------------------


class _StubSourceProvider(SourceDeliveryProvider):
    """A controllable SourceDeliveryProvider for orchestration tests."""

    def __init__(self, initial_batch: SourceDeliveryBatch | None = None) -> None:
        self._initial_batch = initial_batch
        self._daily_batches: dict[date, SourceDeliveryBatch] = {}
        self.get_initial_delivery_calls = 0
        self.get_daily_delivery_calls: list[date] = []
        self.fail_daily_dates: set[date] = set()

    def set_daily_batch(self, delivery_date: date, batch: SourceDeliveryBatch) -> None:
        self._daily_batches[delivery_date] = batch

    def get_initial_delivery(self) -> SourceDeliveryBatch:
        self.get_initial_delivery_calls += 1
        if self._initial_batch is None:
            raise AssertionError("no initial batch configured for this test")
        return self._initial_batch

    def get_daily_delivery(self, delivery_date: date) -> SourceDeliveryBatch:
        self.get_daily_delivery_calls.append(delivery_date)
        if delivery_date in self.fail_daily_dates:
            raise RuntimeError(f"simulated provider failure for {delivery_date.isoformat()}")
        if delivery_date not in self._daily_batches:
            raise AssertionError(f"no daily batch configured for {delivery_date}")
        return self._daily_batches[delivery_date]


# --- In-memory ReplayStateStore test double ---------------------------------


class _InMemoryReplayStateStore(ReplayStateStore):
    """A controllable, fully offline ReplayStateStore for orchestration tests.

    ``fail_when`` lets a test simulate the state-store control plane
    itself failing for a specific event (matched by predicate), without
    needing a real backend.
    """

    def __init__(self) -> None:
        self.events: list[ReplayStateRecord] = []
        self.fail_when: Callable[[ReplayStateRecord], bool] | None = None

    def append(self, record: ReplayStateRecord) -> None:
        if self.fail_when is not None and self.fail_when(record):
            raise RuntimeError(
                f"simulated state-store failure for {record.source_object} "
                f"{record.status.value}|{record.stage.value}"
            )
        self.events.append(record)

    def get_history(self, delivery_date: date, source_object: str) -> tuple[ReplayStateRecord, ...]:
        matches = [e for e in self.events if e.delivery_date == delivery_date and e.source_object == source_object]
        return tuple(sorted(matches, key=lambda e: e.recorded_at))

    def get_latest(self, delivery_date: date, source_object: str) -> ReplayStateRecord | None:
        history = self.get_history(delivery_date, source_object)
        return history[-1] if history else None

    def get_latest_for_date(self, delivery_date: date) -> tuple[ReplayStateRecord, ...]:
        by_source: dict[str, ReplayStateRecord] = {}
        for event in self.events:
            if event.delivery_date != delivery_date:
                continue
            current = by_source.get(event.source_object)
            if current is None or event.recorded_at >= current.recorded_at:
                by_source[event.source_object] = event
        return tuple(by_source[key] for key in sorted(by_source))

    def get_completed_for_date(self, delivery_date: date) -> tuple[ReplayStateRecord, ...]:
        by_source: dict[str, ReplayStateRecord] = {}
        for event in self.events:
            if event.delivery_date != delivery_date or event.status is not ReplayStatus.SUCCESS:
                continue
            current = by_source.get(event.source_object)
            if current is None or event.recorded_at >= current.recorded_at:
                by_source[event.source_object] = event
        return tuple(by_source[key] for key in sorted(by_source))


def _write_source_files(tmp_path: Path) -> dict[str, Path]:
    """Write one minimal, valid source CSV per Mercury source object."""
    source_dir = tmp_path / "sources"
    source_dir.mkdir(exist_ok=True)
    paths: dict[str, Path] = {}
    paths["customers"] = _write_csv(source_dir / "customers.csv", CUSTOMERS_HEADER, [["c1", "u1", "01310", "sp", "SP"]])
    paths["products"] = _write_csv(source_dir / "products.csv", PRODUCTS_HEADER, [["p1", "cat", "40", "500", "2", "225", "16", "10", "14"]])
    paths["sellers"] = _write_csv(source_dir / "sellers.csv", SELLERS_HEADER, [["s1", "01310", "sp", "SP"]])
    paths["geolocations"] = _write_csv(source_dir / "geolocation.csv", GEOLOCATION_HEADER, [["01037", "-23.5", "-46.6", "sp", "SP"]])
    paths["orders"] = _write_csv(
        source_dir / "orders.csv", ORDERS_HEADER, [["o1", "c1", "delivered", "2017-05-01 10:00:00", "", "", "", ""]]
    )
    paths["order_items"] = _write_csv(source_dir / "order_items.csv", ORDER_ITEMS_HEADER, [["o1", "1", "p1", "s1", "", "29.90", "8.50"]])
    paths["payments"] = _write_csv(source_dir / "payments.csv", PAYMENTS_HEADER, [["o1", "1", "voucher", "1", "20.00"]])
    paths["reviews"] = _write_csv(
        source_dir / "reviews.csv", REVIEWS_HEADER, [["r1", "o1", "5", "great", "loved it", "2017-05-01", "2017-05-02"]]
    )
    return paths


def _initial_batch(paths: dict[str, Path]) -> SourceDeliveryBatch:
    return SourceDeliveryBatch(
        deliveries=(
            SourceDelivery(source_object="customers", path=paths["customers"], delivery_date=None, record_count=1),
            SourceDelivery(source_object="products", path=paths["products"], delivery_date=None, record_count=1),
            SourceDelivery(source_object="sellers", path=paths["sellers"], delivery_date=None, record_count=1),
            SourceDelivery(source_object="geolocations", path=paths["geolocations"], delivery_date=None, record_count=1),
        ),
        delivery_date=None,
    )


def _daily_batch(paths: dict[str, Path], delivery_date: date) -> SourceDeliveryBatch:
    return SourceDeliveryBatch(
        deliveries=(
            SourceDelivery(source_object="orders", path=paths["orders"], delivery_date=delivery_date, record_count=1),
            SourceDelivery(source_object="order_items", path=paths["order_items"], delivery_date=delivery_date, record_count=1),
            SourceDelivery(source_object="payments", path=paths["payments"], delivery_date=delivery_date, record_count=1),
            SourceDelivery(source_object="reviews", path=paths["reviews"], delivery_date=delivery_date, record_count=1),
        ),
        delivery_date=delivery_date,
    )


def _daily_batch_with_broken_source(
    paths: dict[str, Path], delivery_date: date, broken_source_object: str, tmp_path: Path
) -> SourceDeliveryBatch:
    """Build a daily batch where exactly one source points at a missing file."""
    deliveries = []
    for source_object in ("orders", "order_items", "payments", "reviews"):
        path = tmp_path / "missing.csv" if source_object == broken_source_object else paths[source_object]
        deliveries.append(SourceDelivery(source_object=source_object, path=path, delivery_date=delivery_date, record_count=1))
    return SourceDeliveryBatch(deliveries=tuple(deliveries), delivery_date=delivery_date)


def _make_runner(
    tmp_path: Path,
    *,
    initial_batch: SourceDeliveryBatch | None = None,
    daily_batches: dict[date, SourceDeliveryBatch] | None = None,
) -> tuple[HistoricalReplayRunner, _StubSourceProvider, _FakeGcsStorageManager, BigQueryRawLoader, _InMemoryReplayStateStore]:
    provider = _StubSourceProvider(initial_batch=initial_batch)
    for day, batch in (daily_batches or {}).items():
        provider.set_daily_batch(day, batch)
    storage_manager = _FakeGcsStorageManager(tmp_path / "gcs_bucket")
    bigquery_loader = _make_bigquery_loader()
    replay_state_store = _InMemoryReplayStateStore()
    runner = HistoricalReplayRunner(
        source_provider=provider,
        storage_manager=storage_manager,
        bigquery_loader=bigquery_loader,
        replay_state_store=replay_state_store,
    )
    return runner, provider, storage_manager, bigquery_loader, replay_state_store


class TestConstruction:
    def test_accepts_valid_dependencies(self, tmp_path: Path) -> None:
        runner, *_ = _make_runner(tmp_path)

        assert isinstance(runner, HistoricalReplayRunner)

    def test_rejects_non_provider(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            HistoricalReplayRunner(
                source_provider=object(),  # type: ignore[arg-type]
                storage_manager=LocalStorageManager(tmp_path / "landing"),
                bigquery_loader=_make_bigquery_loader(),
                replay_state_store=_InMemoryReplayStateStore(),
            )

    def test_rejects_non_storage_manager(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            HistoricalReplayRunner(
                source_provider=_StubSourceProvider(),
                storage_manager=object(),  # type: ignore[arg-type]
                bigquery_loader=_make_bigquery_loader(),
                replay_state_store=_InMemoryReplayStateStore(),
            )

    def test_rejects_non_bigquery_loader(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            HistoricalReplayRunner(
                source_provider=_StubSourceProvider(),
                storage_manager=LocalStorageManager(tmp_path / "landing"),
                bigquery_loader=object(),  # type: ignore[arg-type]
                replay_state_store=_InMemoryReplayStateStore(),
            )

    def test_rejects_non_replay_state_store(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            HistoricalReplayRunner(
                source_provider=_StubSourceProvider(),
                storage_manager=LocalStorageManager(tmp_path / "landing"),
                bigquery_loader=_make_bigquery_loader(),
                replay_state_store=object(),  # type: ignore[arg-type]
            )

    def test_accepts_generic_replay_state_store_not_just_bigquery_backed(self, tmp_path: Path) -> None:
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(tmp_path)

        from mercury_ingestion.orchestration.bigquery_replay_state import BigQueryReplayStateStore

        assert not isinstance(runner.replay_state_store, BigQueryReplayStateStore)
        assert isinstance(runner.replay_state_store, ReplayStateStore)

    def test_replay_py_does_not_import_bigquery_replay_state_store(self) -> None:
        import mercury_ingestion.orchestration.replay as replay_module

        source_text = Path(inspect.getfile(replay_module)).read_text(encoding="utf-8")
        import_lines = [line for line in source_text.splitlines() if line.startswith(("import ", "from "))]
        import_block = "\n".join(import_lines)

        assert "BigQueryReplayStateStore" not in import_block
        assert "bigquery_replay_state" not in import_block

    def test_does_not_create_cloud_clients_itself(self, tmp_path: Path) -> None:
        # Constructing the runner must not touch the BigQuery client at
        # all -- only BigQueryRawLoader's own constructor does that.
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(tmp_path)

        assert bigquery_loader._client.load_calls == []

    def test_does_not_call_ensure_resources(self, tmp_path: Path) -> None:
        # ensure_resources() is a BigQueryReplayStateStore-specific
        # provisioning method; the generic ReplayStateStore contract
        # doesn't even define it, so the runner has no way to call it.
        assert not hasattr(ReplayStateStore, "ensure_resources")


class TestConnectorMapping:
    def test_all_eight_source_objects_map_to_expected_connector_classes(self) -> None:
        from mercury_ingestion.connectors.customers import CustomerConnector
        from mercury_ingestion.connectors.geolocations import GeolocationConnector
        from mercury_ingestion.connectors.order_items import OrderItemsConnector
        from mercury_ingestion.connectors.orders import OrdersConnector
        from mercury_ingestion.connectors.payments import PaymentsConnector
        from mercury_ingestion.connectors.products import ProductsConnector
        from mercury_ingestion.connectors.reviews import ReviewsConnector
        from mercury_ingestion.connectors.sellers import SellersConnector

        assert CONNECTOR_MAP == {
            "customers": CustomerConnector,
            "orders": OrdersConnector,
            "order_items": OrderItemsConnector,
            "products": ProductsConnector,
            "sellers": SellersConnector,
            "payments": PaymentsConnector,
            "reviews": ReviewsConnector,
            "geolocations": GeolocationConnector,
        }


class TestRunDayOrder:
    def test_bigquery_not_called_before_ingestion_completes(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        assert bigquery_loader._client.load_calls == []
        runner.run_day(day)
        assert len(bigquery_loader._client.load_calls) == 4

    def test_provider_called_before_bigquery(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        runner.run_day(day)

        assert provider.get_daily_delivery_calls == [day]

    def test_all_ingestion_events_precede_all_warehouse_events(self, tmp_path: Path) -> None:
        # Stage separation: no RUNNING|WAREHOUSE event may appear before
        # every expected source's ingestion attempt has completed.
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        runner.run_day(day)

        stages_in_order = [event.stage for event in replay_state_store.events]
        last_ingestion_index = max(i for i, s in enumerate(stages_in_order) if s is ReplayStage.INGESTION)
        first_warehouse_index = min(i for i, s in enumerate(stages_in_order) if s is ReplayStage.WAREHOUSE)
        assert last_ingestion_index < first_warehouse_index


class TestRunInitialLoad:
    def test_four_master_sources_flow_through_connectors_then_bigquery(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, initial_batch=_initial_batch(paths)
        )

        result = runner.run_initial_load(date(2017, 5, 1))

        assert result.ingestion_result.succeeded_count == 4
        assert {w.source_object for w in result.warehouse_results} == {"customers", "products", "sellers", "geolocations"}

    def test_destinations_are_unpartitioned(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, initial_batch=_initial_batch(paths)
        )

        result = runner.run_initial_load(date(2017, 5, 1))

        for warehouse_result in result.warehouse_results:
            assert "$" not in warehouse_result.destination

    def test_no_replay_state_events_written_for_initial_load(self, tmp_path: Path) -> None:
        # ADR-010's immediate scope is historical incremental (daily)
        # replay -- run_initial_load() is deliberately untouched.
        paths = _write_source_files(tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, initial_batch=_initial_batch(paths)
        )

        runner.run_initial_load(date(2017, 5, 1))

        assert replay_state_store.events == []


class TestLandingPathHandoff:
    def test_bigquery_receives_exact_metadata_landing_path(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        result = runner.run_day(day)

        landing_paths = {r.metadata.source_object: r.metadata.landing_path for r in result.ingestion_result.results}
        # The landing_path itself (a local filesystem path here, since
        # LocalStorageManager is used) is what warehouse_results.source_uri
        # must equal -- proving no path was reconstructed.
        for warehouse_result in result.warehouse_results:
            assert warehouse_result.source_uri == landing_paths[warehouse_result.source_object]


class TestDateHandoff:
    def test_exact_delivery_date_passed_to_ingestion_and_bigquery(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 3)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        result = runner.run_day(day)

        # The connector's landed path is partitioned by ingestion_date --
        # proves the date reached IngestionRunner/connectors correctly.
        assert all("ingestion_date=2017-05-03" in r.metadata.landing_path for r in result.ingestion_result.results)
        # BigQuery's transactional destinations carry the same date.
        assert all(w.destination.endswith("$20170503") for w in result.warehouse_results)
        assert all(w.ingestion_date == day for w in result.warehouse_results)
        # Replay-state events also carry the same delivery date.
        assert all(event.delivery_date == day for event in replay_state_store.events)


class TestBatchMembershipValidation:
    """Provider responses must exactly match the expected source set."""

    def test_daily_missing_source_rejected_before_ingestion(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        # orders, order_items, payments present; reviews missing.
        incomplete_batch = SourceDeliveryBatch(
            deliveries=(
                SourceDelivery(source_object="orders", path=paths["orders"], delivery_date=day, record_count=1),
                SourceDelivery(source_object="order_items", path=paths["order_items"], delivery_date=day, record_count=1),
                SourceDelivery(source_object="payments", path=paths["payments"], delivery_date=day, record_count=1),
            ),
            delivery_date=day,
        )
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: incomplete_batch}
        )

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.stage == "source_delivery"
        assert exc_info.value.delivery_date == day
        assert "reviews" in str(exc_info.value)
        assert bigquery_loader._client.load_calls == []
        assert not (tmp_path / "gcs_bucket" / "raw").exists()
        assert replay_state_store.events == []

    def test_daily_unexpected_source_rejected_before_ingestion(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        extra_batch = SourceDeliveryBatch(
            deliveries=(
                SourceDelivery(source_object="orders", path=paths["orders"], delivery_date=day, record_count=1),
                SourceDelivery(source_object="order_items", path=paths["order_items"], delivery_date=day, record_count=1),
                SourceDelivery(source_object="payments", path=paths["payments"], delivery_date=day, record_count=1),
                SourceDelivery(source_object="reviews", path=paths["reviews"], delivery_date=day, record_count=1),
                SourceDelivery(source_object="customers", path=paths["customers"], delivery_date=day, record_count=1),
            ),
            delivery_date=day,
        )
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: extra_batch}
        )

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.stage == "source_delivery"
        assert "customers" in str(exc_info.value)
        assert bigquery_loader._client.load_calls == []
        assert not (tmp_path / "gcs_bucket" / "raw").exists()
        assert replay_state_store.events == []

    def test_daily_exact_membership_proceeds_normally(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        result = runner.run_day(day)

        assert result.ingestion_result.succeeded_count == 4
        assert len(result.warehouse_results) == 4

    def test_initial_missing_source_rejected_before_ingestion(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        # products missing from the initial batch.
        incomplete_batch = SourceDeliveryBatch(
            deliveries=(
                SourceDelivery(source_object="customers", path=paths["customers"], delivery_date=None, record_count=1),
                SourceDelivery(source_object="sellers", path=paths["sellers"], delivery_date=None, record_count=1),
                SourceDelivery(source_object="geolocations", path=paths["geolocations"], delivery_date=None, record_count=1),
            ),
            delivery_date=None,
        )
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, initial_batch=incomplete_batch
        )

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_initial_load(date(2017, 5, 1))

        assert exc_info.value.stage == "source_delivery"
        assert "products" in str(exc_info.value)
        assert bigquery_loader._client.load_calls == []

    def test_initial_unexpected_source_rejected_before_ingestion(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        extra_batch = SourceDeliveryBatch(
            deliveries=(
                SourceDelivery(source_object="customers", path=paths["customers"], delivery_date=None, record_count=1),
                SourceDelivery(source_object="products", path=paths["products"], delivery_date=None, record_count=1),
                SourceDelivery(source_object="sellers", path=paths["sellers"], delivery_date=None, record_count=1),
                SourceDelivery(source_object="geolocations", path=paths["geolocations"], delivery_date=None, record_count=1),
                SourceDelivery(source_object="orders", path=paths["orders"], delivery_date=None, record_count=1),
            ),
            delivery_date=None,
        )
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, initial_batch=extra_batch
        )

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_initial_load(date(2017, 5, 1))

        assert exc_info.value.stage == "source_delivery"
        assert "orders" in str(exc_info.value)
        assert bigquery_loader._client.load_calls == []

    def test_error_uses_ingestion_date_context_for_initial_load(self, tmp_path: Path) -> None:
        # SourceDeliveryBatch.delivery_date is None for initial batches,
        # so the explicit ingestion_date argument must be used as the
        # error's contextual date instead.
        paths = _write_source_files(tmp_path)
        incomplete_batch = SourceDeliveryBatch(
            deliveries=(
                SourceDelivery(source_object="customers", path=paths["customers"], delivery_date=None, record_count=1),
            ),
            delivery_date=None,
        )
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, initial_batch=incomplete_batch
        )
        ingestion_date = date(2020, 1, 1)

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_initial_load(ingestion_date)

        assert exc_info.value.delivery_date == ingestion_date


class TestUnsupportedSourceObject:
    def test_build_connector_fails_clearly_for_unsupported_source(self, tmp_path: Path) -> None:
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(tmp_path)
        bogus_delivery = SourceDelivery(
            source_object="not_a_real_source", path=tmp_path / "x.csv", delivery_date=None, record_count=0
        )

        with pytest.raises(ValueError, match="not_a_real_source"):
            runner._build_connector(bogus_delivery)


class TestOneSuccessfulDateEventSequence:
    """Validation Requirements #1-6, #9-14, #21 from ADR-010."""

    def test_each_source_produces_exactly_three_events(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        runner.run_day(day)

        assert len(replay_state_store.events) == 12
        for source_object in DAILY_SOURCE_OBJECTS:
            events = [e for e in replay_state_store.events if e.source_object == source_object]
            assert len(events) == 3
            assert [(e.status, e.stage) for e in events] == [
                (ReplayStatus.RUNNING, ReplayStage.INGESTION),
                (ReplayStatus.RUNNING, ReplayStage.WAREHOUSE),
                (ReplayStatus.SUCCESS, ReplayStage.WAREHOUSE),
            ]

    def test_all_events_share_one_run_id(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        runner.run_day(day)

        run_ids = {event.run_id for event in replay_state_store.events}
        assert len(run_ids) == 1

    def test_every_event_id_is_distinct(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        runner.run_day(day)

        event_ids = [event.event_id for event in replay_state_store.events]
        assert len(event_ids) == len(set(event_ids))

    def test_all_events_share_the_delivery_date(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        runner.run_day(day)

        assert all(event.delivery_date == day for event in replay_state_store.events)

    def test_all_success_events_are_warehouse_stage(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        runner.run_day(day)

        success_events = [e for e in replay_state_store.events if e.status is ReplayStatus.SUCCESS]
        assert len(success_events) == 4
        assert all(e.stage is ReplayStage.WAREHOUSE for e in success_events)

    def test_date_completeness_derives_true(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        runner.run_day(day)

        from mercury_ingestion.orchestration.state import is_date_complete

        latest = replay_state_store.get_latest_for_date(day)
        assert is_date_complete(latest, DAILY_SOURCE_OBJECTS) is True

    def test_connector_metadata_preserved(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        result = runner.run_day(day)

        assert len(result.ingestion_result.results) == 4
        assert {r.metadata.source_object for r in result.ingestion_result.results} == DAILY_SOURCE_OBJECTS
        assert all(r.metadata.landing_path is not None for r in result.ingestion_result.results)
        assert all(r.metadata.checksum is not None for r in result.ingestion_result.results)

    def test_all_four_warehouse_results_preserved(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        result = runner.run_day(day)

        assert len(result.warehouse_results) == 4
        assert {w.source_object for w in result.warehouse_results} == DAILY_SOURCE_OBJECTS


class TestIngestionFailureContinuesSameDateWork:
    """ADR-010 intentionally supersedes ADR-009's stop-on-first-failure-within-date rule.

    payments fails ingestion; orders/order_items/reviews are still
    attempted, still proceed to warehouse, and still succeed end-to-end.
    """

    def test_reviews_still_attempted_after_payments_ingestion_fails(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        broken_batch = _daily_batch_with_broken_source(paths, day, "payments", tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: broken_batch}
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        reviews_events = [e for e in replay_state_store.events if e.source_object == "reviews"]
        assert len(reviews_events) == 3
        assert reviews_events[-1].status is ReplayStatus.SUCCESS

    def test_all_four_connector_attempts_occur(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        broken_batch = _daily_batch_with_broken_source(paths, day, "payments", tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: broken_batch}
        )

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        partial = exc_info.value.partial_day_result
        assert partial is not None
        assert len(partial.ingestion_result.results) == 4

    def test_payments_state_is_running_then_failed_ingestion_only(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        broken_batch = _daily_batch_with_broken_source(paths, day, "payments", tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: broken_batch}
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        payments_events = [e for e in replay_state_store.events if e.source_object == "payments"]
        assert [(e.status, e.stage) for e in payments_events] == [
            (ReplayStatus.RUNNING, ReplayStage.INGESTION),
            (ReplayStatus.FAILED, ReplayStage.INGESTION),
        ]

    def test_payments_gets_no_warehouse_event(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        broken_batch = _daily_batch_with_broken_source(paths, day, "payments", tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: broken_batch}
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        payments_events = [e for e in replay_state_store.events if e.source_object == "payments"]
        assert all(e.stage is not ReplayStage.WAREHOUSE for e in payments_events)

    def test_orders_order_items_reviews_proceed_to_warehouse_and_succeed(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        broken_batch = _daily_batch_with_broken_source(paths, day, "payments", tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: broken_batch}
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        for source_object in ("orders", "order_items", "reviews"):
            latest = replay_state_store.get_latest(day, source_object)
            assert latest is not None
            assert latest.status is ReplayStatus.SUCCESS
            assert latest.stage is ReplayStage.WAREHOUSE

    def test_successful_results_preserved_in_partial_day_result(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        broken_batch = _daily_batch_with_broken_source(paths, day, "payments", tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: broken_batch}
        )

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        partial = exc_info.value.partial_day_result
        assert partial is not None
        assert {w.source_object for w in partial.warehouse_results} == {"orders", "order_items", "reviews"}

    def test_date_is_incomplete(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        broken_batch = _daily_batch_with_broken_source(paths, day, "payments", tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: broken_batch}
        )

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.stage == "date_completion"
        assert "payments" in str(exc_info.value)


class TestWarehouseFailureContinuesSameDateWork:
    """ADR-010 intentionally supersedes ADR-009's stop-on-first-failure-within-date rule.

    All four ingestion attempts succeed; payments' BigQuery load fails,
    but reviews' warehouse load still occurs and still succeeds.
    """

    def test_reviews_warehouse_load_still_occurs_after_payments_warehouse_fails(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.payments$20170501"] = (
            gcs_exceptions.Forbidden("no access")
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        reviews_latest = replay_state_store.get_latest(day, "reviews")
        assert reviews_latest is not None
        assert reviews_latest.status is ReplayStatus.SUCCESS

    def test_payments_state_sequence_is_running_running_failed(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.payments$20170501"] = (
            gcs_exceptions.Forbidden("no access")
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        payments_events = [e for e in replay_state_store.events if e.source_object == "payments"]
        assert [(e.status, e.stage) for e in payments_events] == [
            (ReplayStatus.RUNNING, ReplayStage.INGESTION),
            (ReplayStatus.RUNNING, ReplayStage.WAREHOUSE),
            (ReplayStatus.FAILED, ReplayStage.WAREHOUSE),
        ]

    def test_reviews_ends_success(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.payments$20170501"] = (
            gcs_exceptions.Forbidden("no access")
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        reviews_events = [e for e in replay_state_store.events if e.source_object == "reviews"]
        assert reviews_events[-1].status is ReplayStatus.SUCCESS
        assert reviews_events[-1].stage is ReplayStage.WAREHOUSE

    def test_previous_successes_remain_nothing_rolled_back(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.payments$20170501"] = (
            gcs_exceptions.Forbidden("no access")
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        for source_object in ("orders", "order_items", "reviews"):
            latest = replay_state_store.get_latest(day, source_object)
            assert latest.status is ReplayStatus.SUCCESS

        landed_dir = tmp_path / "gcs_bucket" / "raw"
        landed_files = list(landed_dir.rglob("*.csv"))
        assert len(landed_files) == 4  # all four landed in GCS -- none deleted

    def test_date_is_incomplete(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.payments$20170501"] = (
            gcs_exceptions.Forbidden("no access")
        )

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.stage == "date_completion"

    def test_warehouse_exception_text_never_reaches_persisted_replay_state(self, tmp_path: Path) -> None:
        # Supersedes the pre-ADR-011 expectation that the raw BigQuery
        # exception message was persisted verbatim into replay state --
        # per ADR-011, persisted error_message is always a Mercury-
        # authored safe OperationalError, never str(exc). The warehouse
        # phase never raises for an ordinary per-source load failure (it
        # continues to the next eligible source), so there is no
        # exception-chaining opportunity here at all; the exception's
        # text is simply never carried into durable state.
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        sentinel_exc = gcs_exceptions.ServiceUnavailable("sensitive-test-sentinel@example.invalid")
        bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.payments$20170501"] = sentinel_exc

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        payments_failure = next(
            e for e in replay_state_store.events if e.source_object == "payments" and e.status is ReplayStatus.FAILED
        )
        assert "sensitive-test-sentinel@example.invalid" not in payments_failure.error_message
        assert "category=warehouse_load_failed" in payments_failure.error_message


class TestMultipleFailuresSameDate:
    def test_ingestion_failure_and_warehouse_failure_both_represented_independently(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        broken_batch = _daily_batch_with_broken_source(paths, day, "payments", tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: broken_batch}
        )
        bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.reviews$20170501"] = (
            gcs_exceptions.Forbidden("no access")
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        payments_latest = replay_state_store.get_latest(day, "payments")
        reviews_latest = replay_state_store.get_latest(day, "reviews")
        assert payments_latest.status is ReplayStatus.FAILED
        assert payments_latest.stage is ReplayStage.INGESTION
        assert reviews_latest.status is ReplayStatus.FAILED
        assert reviews_latest.stage is ReplayStage.WAREHOUSE

    def test_safe_work_still_attempted_for_unaffected_sources(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        broken_batch = _daily_batch_with_broken_source(paths, day, "payments", tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: broken_batch}
        )
        bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.reviews$20170501"] = (
            gcs_exceptions.Forbidden("no access")
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        for source_object in ("orders", "order_items"):
            latest = replay_state_store.get_latest(day, source_object)
            assert latest.status is ReplayStatus.SUCCESS

    def test_date_is_incomplete(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        broken_batch = _daily_batch_with_broken_source(paths, day, "payments", tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: broken_batch}
        )
        bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.reviews$20170501"] = (
            gcs_exceptions.Forbidden("no access")
        )

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.stage == "date_completion"
        assert "payments" in str(exc_info.value)
        assert "reviews" in str(exc_info.value)

    def test_no_erroneous_success_for_either_failed_source(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        broken_batch = _daily_batch_with_broken_source(paths, day, "payments", tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: broken_batch}
        )
        bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.reviews$20170501"] = (
            gcs_exceptions.Forbidden("no access")
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        for source_object in ("payments", "reviews"):
            latest = replay_state_store.get_latest(day, source_object)
            assert latest.status is not ReplayStatus.SUCCESS


class TestRunRange:
    def test_inclusive_range_runs_correct_number_of_days(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        days = [date(2017, 5, 1), date(2017, 5, 2), date(2017, 5, 3)]
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={d: _daily_batch(paths, d) for d in days}
        )

        result = runner.run_range(date(2017, 5, 1), date(2017, 5, 3))

        assert [dr.delivery_date for dr in result.day_results] == days

    def test_start_equals_end_runs_one_day(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        result = runner.run_range(day, day)

        assert len(result.day_results) == 1

    def test_start_after_end_rejected(self, tmp_path: Path) -> None:
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(tmp_path)

        with pytest.raises(ValueError):
            runner.run_range(date(2017, 5, 3), date(2017, 5, 1))

    def test_stops_after_incomplete_date(self, tmp_path: Path) -> None:
        # ADR-010 supersedes the old "stops at first failed source"
        # expectation: the range now stops only once a date's full safe
        # work has been attempted and found incomplete.
        paths = _write_source_files(tmp_path)
        good_day = date(2017, 5, 1)
        bad_day = date(2017, 5, 2)
        later_day = date(2017, 5, 3)
        broken_batch = _daily_batch_with_broken_source(paths, bad_day, "orders", tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path,
            daily_batches={
                good_day: _daily_batch(paths, good_day),
                bad_day: broken_batch,
                later_day: _daily_batch(paths, later_day),
            },
        )

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_range(good_day, later_day)

        assert exc_info.value.delivery_date == bad_day
        # later_day must never have been requested from the provider.
        assert later_day not in provider.get_daily_delivery_calls

    def test_all_safe_work_for_incomplete_day_still_occurred(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        good_day = date(2017, 5, 1)
        bad_day = date(2017, 5, 2)
        broken_batch = _daily_batch_with_broken_source(paths, bad_day, "orders", tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path,
            daily_batches={good_day: _daily_batch(paths, good_day), bad_day: broken_batch},
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_range(good_day, bad_day)

        # Even on the incomplete bad_day, the three unaffected sources
        # still completed successfully -- safe work was attempted.
        for source_object in ("order_items", "payments", "reviews"):
            latest = replay_state_store.get_latest(bad_day, source_object)
            assert latest.status is ReplayStatus.SUCCESS

    def test_first_complete_day_included_in_result_before_range_stops(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        good_day = date(2017, 5, 1)
        bad_day = date(2017, 5, 2)
        broken_batch = _daily_batch_with_broken_source(paths, bad_day, "orders", tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path,
            daily_batches={good_day: _daily_batch(paths, good_day), bad_day: broken_batch},
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_range(good_day, bad_day)

        # good_day's own events are fully recorded even though the range
        # as a whole raised on bad_day.
        good_day_latest = replay_state_store.get_latest_for_date(good_day)
        assert len(good_day_latest) == 4
        assert all(r.status is ReplayStatus.SUCCESS for r in good_day_latest)


class TestRunIdAcrossRange:
    def test_run_range_uses_one_run_id_across_all_attempted_dates(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        days = [date(2017, 5, 1), date(2017, 5, 2), date(2017, 5, 3)]
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={d: _daily_batch(paths, d) for d in days}
        )

        runner.run_range(date(2017, 5, 1), date(2017, 5, 3))

        run_ids = {event.run_id for event in replay_state_store.events}
        assert len(run_ids) == 1

    def test_separate_run_range_calls_use_different_run_ids(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day1 = date(2017, 5, 1)
        day2 = date(2017, 5, 2)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day1: _daily_batch(paths, day1), day2: _daily_batch(paths, day2)}
        )

        runner.run_range(day1, day1)
        first_run_ids = {e.run_id for e in replay_state_store.events}

        runner.run_range(day2, day2)
        all_run_ids = {e.run_id for e in replay_state_store.events}
        second_run_ids = all_run_ids - first_run_ids

        assert len(first_run_ids) == 1
        assert len(second_run_ids) == 1
        assert first_run_ids != second_run_ids

    def test_standalone_run_day_gets_its_own_run_id(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day1 = date(2017, 5, 1)
        day2 = date(2017, 5, 2)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day1: _daily_batch(paths, day1), day2: _daily_batch(paths, day2)}
        )

        runner.run_day(day1)
        first_run_ids = {e.run_id for e in replay_state_store.events}

        runner.run_day(day2)
        all_run_ids = {e.run_id for e in replay_state_store.events}
        second_run_ids = all_run_ids - first_run_ids

        assert len(first_run_ids) == 1
        assert len(second_run_ids) == 1
        assert first_run_ids != second_run_ids


class TestProviderFailure:
    def test_no_fabricated_events_when_provider_fails_before_batch_exists(self, tmp_path: Path) -> None:
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(tmp_path)
        provider.fail_daily_dates.add(day)

        with pytest.raises(RuntimeError):
            runner.run_day(day)

        assert replay_state_store.events == []

    def test_no_connector_execution_on_provider_failure(self, tmp_path: Path) -> None:
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(tmp_path)
        provider.fail_daily_dates.add(day)

        with pytest.raises(RuntimeError):
            runner.run_day(day)

        assert not (tmp_path / "gcs_bucket" / "raw").exists()

    def test_no_warehouse_execution_on_provider_failure(self, tmp_path: Path) -> None:
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(tmp_path)
        provider.fail_daily_dates.add(day)

        with pytest.raises(RuntimeError):
            runner.run_day(day)

        assert bigquery_loader._client.load_calls == []

    def test_provider_error_propagates(self, tmp_path: Path) -> None:
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(tmp_path)
        provider.fail_daily_dates.add(day)

        with pytest.raises(RuntimeError, match="simulated provider failure"):
            runner.run_day(day)


class TestStateStoreFailure:
    def test_failure_writing_running_ingestion_prevents_connector_from_running(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        replay_state_store.fail_when = (
            lambda r: r.source_object == "orders" and r.status is ReplayStatus.RUNNING and r.stage is ReplayStage.INGESTION
        )

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.stage == "state_store"
        # No source ever landed, since the very first RUNNING|INGESTION
        # append (for the first source in delivery order) already failed.
        assert not (tmp_path / "gcs_bucket" / "raw").exists()
        assert bigquery_loader._client.load_calls == []

    def test_failure_writing_running_ingestion_stops_warehouse_too(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        replay_state_store.fail_when = (
            lambda r: r.source_object == "orders" and r.status is ReplayStatus.RUNNING and r.stage is ReplayStage.INGESTION
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        assert bigquery_loader._client.load_calls == []

    def test_failure_writing_running_warehouse_prevents_bigquery_call(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        replay_state_store.fail_when = (
            lambda r: r.source_object == "orders" and r.status is ReplayStatus.RUNNING and r.stage is ReplayStage.WAREHOUSE
        )

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.stage == "state_store"
        # orders ingested fine (landed in GCS) but its BigQuery load must
        # never have been attempted, since the RUNNING|WAREHOUSE append
        # for it failed first.
        assert bigquery_loader._client.load_calls == []

    def test_failure_writing_running_warehouse_aborts_replay(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        replay_state_store.fail_when = (
            lambda r: r.source_object == "orders" and r.status is ReplayStatus.RUNNING and r.stage is ReplayStage.WAREHOUSE
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        # order_items/payments/reviews never got a chance to reach the
        # warehouse phase either, since the control-plane failure aborts
        # the entire replay immediately -- not "safe work to continue".
        for source_object in ("order_items", "payments", "reviews"):
            latest = replay_state_store.get_latest(day, source_object)
            assert latest is None or latest.stage is not ReplayStage.WAREHOUSE

    def test_failure_writing_success_warehouse_does_not_roll_back_gcs_or_bigquery(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        replay_state_store.fail_when = (
            lambda r: r.source_object == "orders" and r.status is ReplayStatus.SUCCESS
        )

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.stage == "state_store"
        # orders' GCS artifact and BigQuery load both genuinely
        # succeeded before the SUCCESS append failed -- neither is
        # rolled back.
        landed_dir = tmp_path / "gcs_bucket" / "raw"
        orders_landed_files = list((landed_dir / "order_platform" / "orders").rglob("*.csv"))
        assert len(orders_landed_files) == 1
        orders_bq_calls = [c for c in bigquery_loader._client.load_calls if "orders" in str(c["destination"])]
        assert len(orders_bq_calls) == 1

    def test_failure_writing_success_warehouse_stops_remaining_sources(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        replay_state_store.fail_when = (
            lambda r: r.source_object == "orders" and r.status is ReplayStatus.SUCCESS
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        # The ingestion phase completes fully for all four sources
        # before the warehouse phase begins (stage separation), so
        # order_items does have its ingestion events -- but since it
        # comes right after orders in warehouse-phase order, it never
        # reaches its own RUNNING|WAREHOUSE event once orders' SUCCESS
        # append aborts the replay.
        order_items_events = [e for e in replay_state_store.events if e.source_object == "order_items"]
        assert all(e.stage is ReplayStage.INGESTION for e in order_items_events)
        assert not any(e.stage is ReplayStage.WAREHOUSE for e in order_items_events)


class TestExistingImmutableDestination:
    """Immutability guarantees must surface naturally, not be reimplemented here."""

    def test_rerunning_an_already_complete_day_does_not_raise(self, tmp_path: Path) -> None:
        # Superseded expectation: rerunning an already-fully-successful
        # day used to raise, since date completion was previously
        # derived from this run's own latest-attempt events. Per the
        # monotonic-completion revision, completion is derived from
        # get_completed_for_date() -- since every source already
        # reached SUCCESS|WAREHOUSE on the first run, the date remains
        # logically complete even though every connector on this second
        # run fails immediately (create-only GCS destinations already
        # exist).
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        runner.run_day(day)  # first run lands everything successfully

        second_result = runner.run_day(day)  # must not raise

        assert second_result is not None
        # Every connector's own StorageManager create-only guarantee
        # raises FileExistsError inside each connector, which
        # BaseConnector turns into FAILED metadata -- HistoricalReplayRunner
        # adds no special-case overwrite logic of its own, and this
        # run's own failures remain fully visible on the returned result.
        assert second_result.ingestion_result.succeeded_count == 0
        assert second_result.warehouse_results == ()
        for source_object in DAILY_SOURCE_OBJECTS:
            latest = replay_state_store.get_latest(day, source_object)
            assert latest.status is ReplayStatus.FAILED
            assert latest.stage is ReplayStage.INGESTION

    def test_rerunning_an_already_complete_day_preserves_original_success_history(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        runner.run_day(day)
        runner.run_day(day)

        # The original successful events are never overwritten or
        # deleted -- append-only history means both the earlier success
        # and the later failure remain visible for each source.
        for source_object in DAILY_SOURCE_OBJECTS:
            history = replay_state_store.get_history(day, source_object)
            statuses = [event.status for event in history]
            assert ReplayStatus.SUCCESS in statuses
            assert ReplayStatus.FAILED in statuses

    def test_no_force_overwrite_flag_exists(self) -> None:
        signature = inspect.signature(HistoricalReplayRunner.run_day)
        assert "force" not in signature.parameters
        assert "overwrite" not in signature.parameters


class TestMonotonicDateCompletion:
    """The core behavior change: completion is derived from ever-succeeded
    state, not merely the current invocation's own latest-attempt outcome.
    """

    def test_run_day_does_not_raise_when_date_already_complete_despite_current_failure(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        runner.run_day(day)  # completes the date

        # Should not raise, even though this second attempt's own
        # ingestion entirely fails.
        runner.run_day(day)

    def test_run_day_still_raises_when_date_genuinely_incomplete(self, tmp_path: Path) -> None:
        # Sanity check that the monotonic-completion change did not
        # accidentally make run_day() stop raising altogether -- a date
        # that has never been completed must still raise normally.
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        broken_batch = _daily_batch_with_broken_source(paths, day, "payments", tmp_path)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: broken_batch}
        )

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.stage == "date_completion"

    def test_latest_attempt_can_regress_to_failed_while_completion_remains_success(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        runner.run_day(day)
        runner.run_day(day)  # second attempt fails for every source

        latest = replay_state_store.get_latest(day, "orders")
        completed = [r for r in replay_state_store.get_completed_for_date(day) if r.source_object == "orders"]

        assert latest.status is ReplayStatus.FAILED
        assert len(completed) == 1
        assert completed[0].status is ReplayStatus.SUCCESS

    def test_run_range_continues_past_an_already_complete_date_that_fails_on_replay(self, tmp_path: Path) -> None:
        # A range that revisits an already-complete date (e.g. as part
        # of a broader replay window) must not treat that date's own
        # failed reattempt as a fresh incompleteness gap blocking later
        # dates.
        paths = _write_source_files(tmp_path)
        already_complete_day = date(2017, 5, 1)
        next_day = date(2017, 5, 2)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path,
            daily_batches={
                already_complete_day: _daily_batch(paths, already_complete_day),
                next_day: _daily_batch(paths, next_day),
            },
        )
        runner.run_day(already_complete_day)  # complete it once, standalone

        result = runner.run_range(already_complete_day, next_day)

        assert [dr.delivery_date for dr in result.day_results] == [already_complete_day, next_day]

    def test_day_result_for_already_complete_date_reflects_this_run_not_history(self, tmp_path: Path) -> None:
        # The returned HistoricalReplayDayResult always reflects what
        # *this* invocation actually did -- it is not silently swapped
        # for a synthetic "everything succeeded" result just because the
        # date happens to be logically complete from earlier history.
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        runner.run_day(day)

        second_result = runner.run_day(day)

        assert len(second_result.ingestion_result.results) == 4
        assert all(r.metadata.status.value == "failed" for r in second_result.ingestion_result.results)


class TestGenerateRange:
    def test_calls_provider_for_every_inclusive_date(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        days = [date(2017, 5, 1), date(2017, 5, 2)]
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={d: _daily_batch(paths, d) for d in days}
        )

        batches = runner.generate_range(date(2017, 5, 1), date(2017, 5, 2))

        assert provider.get_daily_delivery_calls == days
        assert [b.delivery_date for b in batches] == days

    def test_does_not_invoke_connectors_or_storage_or_bigquery(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        runner.generate_range(day, day)

        assert bigquery_loader._client.load_calls == []
        assert not (tmp_path / "gcs_bucket" / "raw").exists()

    def test_does_not_write_replay_state(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader, replay_state_store = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        runner.generate_range(day, day)

        assert replay_state_store.events == []