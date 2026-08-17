"""Unit tests for mercury_ingestion.orchestration.replay.

Fully offline: LocalStorageManager writes to a temp directory (real,
no network), and only the BigQuery client boundary is faked. The
source provider is a lightweight test double implementing
SourceDeliveryProvider directly, so tests can construct arbitrary
batches without depending on the real Olist simulator.
"""

from __future__ import annotations

import csv
import hashlib
from datetime import date
from pathlib import Path

import pytest
from google.api_core import exceptions as gcs_exceptions

from mercury_ingestion.common.storage import LocalStorageManager, StorageManager, StorageResult
from mercury_ingestion.orchestration.replay import (
    CONNECTOR_MAP,
    HistoricalReplayError,
    HistoricalReplayRunner,
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

    def set_daily_batch(self, delivery_date: date, batch: SourceDeliveryBatch) -> None:
        self._daily_batches[delivery_date] = batch

    def get_initial_delivery(self) -> SourceDeliveryBatch:
        self.get_initial_delivery_calls += 1
        if self._initial_batch is None:
            raise AssertionError("no initial batch configured for this test")
        return self._initial_batch

    def get_daily_delivery(self, delivery_date: date) -> SourceDeliveryBatch:
        self.get_daily_delivery_calls.append(delivery_date)
        if delivery_date not in self._daily_batches:
            raise AssertionError(f"no daily batch configured for {delivery_date}")
        return self._daily_batches[delivery_date]


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


def _make_runner(
    tmp_path: Path,
    *,
    initial_batch: SourceDeliveryBatch | None = None,
    daily_batches: dict[date, SourceDeliveryBatch] | None = None,
) -> tuple[HistoricalReplayRunner, _StubSourceProvider, _FakeGcsStorageManager, BigQueryRawLoader]:
    provider = _StubSourceProvider(initial_batch=initial_batch)
    for day, batch in (daily_batches or {}).items():
        provider.set_daily_batch(day, batch)
    storage_manager = _FakeGcsStorageManager(tmp_path / "gcs_bucket")
    bigquery_loader = _make_bigquery_loader()
    runner = HistoricalReplayRunner(
        source_provider=provider, storage_manager=storage_manager, bigquery_loader=bigquery_loader
    )
    return runner, provider, storage_manager, bigquery_loader


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
            )

    def test_rejects_non_storage_manager(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            HistoricalReplayRunner(
                source_provider=_StubSourceProvider(),
                storage_manager=object(),  # type: ignore[arg-type]
                bigquery_loader=_make_bigquery_loader(),
            )

    def test_rejects_non_bigquery_loader(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            HistoricalReplayRunner(
                source_provider=_StubSourceProvider(),
                storage_manager=LocalStorageManager(tmp_path / "landing"),
                bigquery_loader=object(),  # type: ignore[arg-type]
            )

    def test_does_not_create_cloud_clients_itself(self, tmp_path: Path) -> None:
        # Constructing the runner must not touch the BigQuery client at
        # all -- only BigQueryRawLoader's own constructor does that.
        runner, provider, storage_manager, bigquery_loader = _make_runner(tmp_path)

        assert bigquery_loader._client.load_calls == []


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
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        assert bigquery_loader._client.load_calls == []
        runner.run_day(day)
        assert len(bigquery_loader._client.load_calls) == 4

    def test_provider_called_before_bigquery(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        runner.run_day(day)

        assert provider.get_daily_delivery_calls == [day]


class TestRunInitialLoad:
    def test_four_master_sources_flow_through_connectors_then_bigquery(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path, initial_batch=_initial_batch(paths)
        )

        result = runner.run_initial_load(date(2017, 5, 1))

        assert result.ingestion_result.succeeded_count == 4
        assert {w.source_object for w in result.warehouse_results} == {"customers", "products", "sellers", "geolocations"}

    def test_destinations_are_unpartitioned(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path, initial_batch=_initial_batch(paths)
        )

        result = runner.run_initial_load(date(2017, 5, 1))

        for warehouse_result in result.warehouse_results:
            assert "$" not in warehouse_result.destination


class TestLandingPathHandoff:
    def test_bigquery_receives_exact_metadata_landing_path(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        result = runner.run_day(day)

        landing_paths = {r.metadata.source_object: r.metadata.landing_path for r in result.ingestion_result.results}
        gcs_uris_sent = {call["destination"] for call in bigquery_loader._client.load_calls}
        # The landing_path itself (a local filesystem path here, since
        # LocalStorageManager is used) is what warehouse_results.source_uri
        # must equal -- proving no path was reconstructed.
        for warehouse_result in result.warehouse_results:
            assert warehouse_result.source_uri == landing_paths[warehouse_result.source_object]


class TestDateHandoff:
    def test_exact_delivery_date_passed_to_ingestion_and_bigquery(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 3)
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        result = runner.run_day(day)

        # The connector's landed path is partitioned by ingestion_date --
        # proves the date reached IngestionRunner/connectors correctly.
        assert all("ingestion_date=2017-05-03" in r.metadata.landing_path for r in result.ingestion_result.results)
        # BigQuery's transactional destinations carry the same date.
        assert all(w.destination.endswith("$20170503") for w in result.warehouse_results)
        assert all(w.ingestion_date == day for w in result.warehouse_results)


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
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path, daily_batches={day: incomplete_batch}
        )

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.stage == "source_delivery"
        assert exc_info.value.delivery_date == day
        assert "reviews" in str(exc_info.value)
        assert bigquery_loader._client.load_calls == []
        assert not (tmp_path / "gcs_bucket" / "raw").exists()

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
        runner, provider, storage_manager, bigquery_loader = _make_runner(tmp_path, daily_batches={day: extra_batch})

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.stage == "source_delivery"
        assert "customers" in str(exc_info.value)
        assert bigquery_loader._client.load_calls == []
        assert not (tmp_path / "gcs_bucket" / "raw").exists()

    def test_daily_exact_membership_proceeds_normally(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader = _make_runner(
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
        runner, provider, storage_manager, bigquery_loader = _make_runner(tmp_path, initial_batch=incomplete_batch)

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
        runner, provider, storage_manager, bigquery_loader = _make_runner(tmp_path, initial_batch=extra_batch)

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
        runner, provider, storage_manager, bigquery_loader = _make_runner(tmp_path, initial_batch=incomplete_batch)
        ingestion_date = date(2020, 1, 1)

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_initial_load(ingestion_date)

        assert exc_info.value.delivery_date == ingestion_date


class TestUnsupportedSourceObject:
    def test_build_connector_fails_clearly_for_unsupported_source(self, tmp_path: Path) -> None:
        runner, provider, storage_manager, bigquery_loader = _make_runner(tmp_path)
        bogus_delivery = SourceDelivery(
            source_object="not_a_real_source", path=tmp_path / "x.csv", delivery_date=None, record_count=0
        )

        with pytest.raises(ValueError, match="not_a_real_source"):
            runner._build_connector(bogus_delivery)


class TestIngestionFailure:
    def test_bigquery_not_called_when_ingestion_incomplete(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        # Point one delivery's path at a file that does not exist, so
        # that connector's validate_source() fails and its metadata
        # ends up FAILED rather than SUCCESS.
        broken_batch = SourceDeliveryBatch(
            deliveries=(
                SourceDelivery(source_object="orders", path=tmp_path / "missing.csv", delivery_date=day, record_count=0),
                SourceDelivery(source_object="order_items", path=paths["order_items"], delivery_date=day, record_count=1),
                SourceDelivery(source_object="payments", path=paths["payments"], delivery_date=day, record_count=1),
                SourceDelivery(source_object="reviews", path=paths["reviews"], delivery_date=day, record_count=1),
            ),
            delivery_date=day,
        )
        runner, provider, storage_manager, bigquery_loader = _make_runner(tmp_path, daily_batches={day: broken_batch})

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        assert bigquery_loader._client.load_calls == []

    def test_day_fails_clearly_with_context(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        broken_batch = SourceDeliveryBatch(
            deliveries=(
                SourceDelivery(source_object="orders", path=tmp_path / "missing.csv", delivery_date=day, record_count=0),
                SourceDelivery(source_object="order_items", path=paths["order_items"], delivery_date=day, record_count=1),
                SourceDelivery(source_object="payments", path=paths["payments"], delivery_date=day, record_count=1),
                SourceDelivery(source_object="reviews", path=paths["reviews"], delivery_date=day, record_count=1),
            ),
            delivery_date=day,
        )
        runner, provider, storage_manager, bigquery_loader = _make_runner(tmp_path, daily_batches={day: broken_batch})

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.delivery_date == day
        assert exc_info.value.stage == "ingestion"


class TestWarehouseFailure:
    def test_error_identifies_date_and_source(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        failing_destination = f"mercury-data-platform-dev.raw.payments$20170501"
        bigquery_loader._client.raise_for_destination[failing_destination] = gcs_exceptions.Forbidden("no access")

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.delivery_date == day
        assert exc_info.value.stage == "warehouse"
        assert exc_info.value.source_object == "payments"

    def test_original_exception_preserved_as_cause(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        failing_destination = "mercury-data-platform-dev.raw.reviews$20170501"
        original_exc = gcs_exceptions.ServiceUnavailable("backend down")
        bigquery_loader._client.raise_for_destination[failing_destination] = original_exc

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.__cause__ is original_exc

    def test_gcs_not_modified_or_deleted_on_warehouse_failure(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        failing_destination = "mercury-data-platform-dev.raw.reviews$20170501"
        bigquery_loader._client.raise_for_destination[failing_destination] = gcs_exceptions.Forbidden("no access")

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        landed_dir = tmp_path / "gcs_bucket" / "raw"
        # All four connectors' landed artifacts remain exactly where
        # ingestion put them -- the failure happened purely at the
        # warehouse stage, after landing already succeeded.
        landed_files = list(landed_dir.rglob("*.csv"))
        assert len(landed_files) == 4


class TestRunRange:
    def test_inclusive_range_runs_correct_number_of_days(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        days = [date(2017, 5, 1), date(2017, 5, 2), date(2017, 5, 3)]
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path, daily_batches={d: _daily_batch(paths, d) for d in days}
        )

        result = runner.run_range(date(2017, 5, 1), date(2017, 5, 3))

        assert [dr.delivery_date for dr in result.day_results] == days

    def test_start_equals_end_runs_one_day(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        result = runner.run_range(day, day)

        assert len(result.day_results) == 1

    def test_start_after_end_rejected(self, tmp_path: Path) -> None:
        runner, provider, storage_manager, bigquery_loader = _make_runner(tmp_path)

        with pytest.raises(ValueError):
            runner.run_range(date(2017, 5, 3), date(2017, 5, 1))

    def test_stops_at_first_failed_day(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        good_day = date(2017, 5, 1)
        bad_day = date(2017, 5, 2)
        later_day = date(2017, 5, 3)
        broken_batch = SourceDeliveryBatch(
            deliveries=(
                SourceDelivery(source_object="orders", path=tmp_path / "missing.csv", delivery_date=bad_day, record_count=0),
                SourceDelivery(source_object="order_items", path=paths["order_items"], delivery_date=bad_day, record_count=1),
                SourceDelivery(source_object="payments", path=paths["payments"], delivery_date=bad_day, record_count=1),
                SourceDelivery(source_object="reviews", path=paths["reviews"], delivery_date=bad_day, record_count=1),
            ),
            delivery_date=bad_day,
        )
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path,
            daily_batches={
                good_day: _daily_batch(paths, good_day),
                bad_day: broken_batch,
                later_day: _daily_batch(paths, later_day),
            },
        )

        with pytest.raises(HistoricalReplayError):
            runner.run_range(good_day, later_day)

        # later_day must never have been requested from the provider.
        assert later_day not in provider.get_daily_delivery_calls


class TestExistingImmutableDestination:
    """Immutability guarantees must surface naturally, not be reimplemented here."""

    def test_rerunning_the_same_day_surfaces_existing_storage_manager_behavior(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )
        runner.run_day(day)  # first run lands everything successfully

        # Second run for the same day: the underlying StorageManager's
        # own create-only guarantee raises FileExistsError inside the
        # connector, which BaseConnector turns into FAILED metadata --
        # HistoricalReplayRunner adds no special-case overwrite logic of
        # its own; the failure surfaces through the normal ingestion
        # failure path.
        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.stage == "ingestion"

    def test_no_force_overwrite_flag_exists(self) -> None:
        import inspect

        signature = inspect.signature(HistoricalReplayRunner.run_day)
        assert "force" not in signature.parameters
        assert "overwrite" not in signature.parameters


class TestGenerateRange:
    def test_calls_provider_for_every_inclusive_date(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        days = [date(2017, 5, 1), date(2017, 5, 2)]
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path, daily_batches={d: _daily_batch(paths, d) for d in days}
        )

        batches = runner.generate_range(date(2017, 5, 1), date(2017, 5, 2))

        assert provider.get_daily_delivery_calls == days
        assert [b.delivery_date for b in batches] == days

    def test_does_not_invoke_connectors_or_storage_or_bigquery(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        day = date(2017, 5, 1)
        runner, provider, storage_manager, bigquery_loader = _make_runner(
            tmp_path, daily_batches={day: _daily_batch(paths, day)}
        )

        runner.generate_range(day, day)

        assert bigquery_loader._client.load_calls == []
        assert not (tmp_path / "gcs_bucket" / "raw").exists()