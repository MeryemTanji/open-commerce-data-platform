"""Unit tests for mercury_ingestion.sources.simulated_olist."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from mercury_ingestion.simulation.olist import OlistSourceSimulator
from mercury_ingestion.sources.simulated_olist import OlistSimulatedSourceProvider

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


def _write_csv(path: Path, header: list[str], rows: list[list[str]], *, encoding: str = "utf-8-sig") -> Path:
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
    return path


def _build_source_directory(tmp_path: Path) -> Path:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    _write_csv(source_dir / "olist_customers_dataset.csv", CUSTOMERS_HEADER, [["c1", "u1", "01310", "sp", "SP"], ["c2", "u2", "20040", "rio", "RJ"]])
    _write_csv(source_dir / "olist_products_dataset.csv", PRODUCTS_HEADER, [["p1", "cat", "40", "500", "2", "225", "16", "10", "14"]])
    _write_csv(source_dir / "olist_sellers_dataset.csv", SELLERS_HEADER, [["s1", "01310", "sp", "SP"]])
    _write_csv(source_dir / "olist_geolocation_dataset.csv", GEOLOCATION_HEADER, [["01037", "-23.5", "-46.6", "sp", "SP"]])
    _write_csv(
        source_dir / "olist_orders_dataset.csv",
        ORDERS_HEADER,
        [["o1", "c1", "delivered", "2017-05-01 10:00:00", "", "", "", ""]],
    )
    _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [["o1", "1", "p1", "s1", "", "29.90", "8.50"]])
    _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [["o1", "1", "voucher", "1", "20.00"]])
    _write_csv(
        source_dir / "olist_order_reviews_dataset.csv",
        REVIEWS_HEADER,
        [["r1", "o1", "5", "great", "loved it", "2017-05-01", "2017-05-02"]],
    )
    return source_dir


class TestNewInitialDelivery:
    def test_calls_simulator_and_adapts_exactly_four_sources(self, tmp_path: Path) -> None:
        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "sim_out")
        provider = OlistSimulatedSourceProvider(simulator)

        batch = provider.get_initial_delivery()

        assert {d.source_object for d in batch.deliveries} == {"customers", "products", "sellers", "geolocations"}

    def test_paths_and_counts_preserved(self, tmp_path: Path) -> None:
        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "sim_out")
        provider = OlistSimulatedSourceProvider(simulator)

        batch = provider.get_initial_delivery()

        customers = next(d for d in batch.deliveries if d.source_object == "customers")
        assert customers.record_count == 2
        assert customers.path.is_file()
        assert customers.path.name == "olist_customers_dataset.csv"

    def test_batch_delivery_date_is_none(self, tmp_path: Path) -> None:
        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "sim_out")
        provider = OlistSimulatedSourceProvider(simulator)

        batch = provider.get_initial_delivery()

        assert batch.delivery_date is None
        assert all(d.delivery_date is None for d in batch.deliveries)


class TestNewDailyDelivery:
    def test_calls_simulator_and_adapts_exactly_four_sources(self, tmp_path: Path) -> None:
        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "sim_out")
        provider = OlistSimulatedSourceProvider(simulator)

        batch = provider.get_daily_delivery(date(2017, 5, 1))

        assert {d.source_object for d in batch.deliveries} == {"orders", "order_items", "payments", "reviews"}

    def test_daily_batch_date_preserved(self, tmp_path: Path) -> None:
        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "sim_out")
        provider = OlistSimulatedSourceProvider(simulator)

        batch = provider.get_daily_delivery(date(2017, 5, 1))

        assert batch.delivery_date == date(2017, 5, 1)

    def test_every_delivery_carries_that_date(self, tmp_path: Path) -> None:
        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "sim_out")
        provider = OlistSimulatedSourceProvider(simulator)

        batch = provider.get_daily_delivery(date(2017, 5, 1))

        assert all(d.delivery_date == date(2017, 5, 1) for d in batch.deliveries)

    def test_ingestion_date_is_delivery_date_plus_one_day(self, tmp_path: Path) -> None:
        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "sim_out")
        provider = OlistSimulatedSourceProvider(simulator)

        batch = provider.get_daily_delivery(date(2017, 5, 19))

        assert batch.delivery_date == date(2017, 5, 19)
        assert batch.ingestion_date == date(2017, 5, 20)


class TestExistingCompleteInitialDelivery:
    def test_returns_without_regenerating(self, tmp_path: Path) -> None:
        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "sim_out")
        provider = OlistSimulatedSourceProvider(simulator)
        first_batch = provider.get_initial_delivery()

        # Second call must adapt the existing delivery, not call
        # simulator.generate_initial_load() again (which would raise
        # FileExistsError).
        second_batch = provider.get_initial_delivery()

        assert {d.source_object for d in second_batch.deliveries} == {d.source_object for d in first_batch.deliveries}

    def test_record_counts_correct(self, tmp_path: Path) -> None:
        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "sim_out")
        provider = OlistSimulatedSourceProvider(simulator)
        provider.get_initial_delivery()

        second_batch = provider.get_initial_delivery()

        customers = next(d for d in second_batch.deliveries if d.source_object == "customers")
        assert customers.record_count == 2

    def test_original_files_untouched(self, tmp_path: Path) -> None:
        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "sim_out")
        provider = OlistSimulatedSourceProvider(simulator)
        first_batch = provider.get_initial_delivery()
        customers_path = next(d for d in first_batch.deliveries if d.source_object == "customers").path
        original_bytes = customers_path.read_bytes()

        provider.get_initial_delivery()

        assert customers_path.read_bytes() == original_bytes

    def test_ingestion_date_remains_none(self, tmp_path: Path) -> None:
        # Initial/reference delivery has no daily-simulation timing
        # policy applied to it -- no simulated initial ingestion date is
        # invented, for either the newly-generated or already-existing
        # path.
        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "sim_out")
        provider = OlistSimulatedSourceProvider(simulator)

        first_batch = provider.get_initial_delivery()  # newly generated
        second_batch = provider.get_initial_delivery()  # already exists on disk

        assert first_batch.delivery_date is None
        assert first_batch.ingestion_date is None
        assert second_batch.delivery_date is None
        assert second_batch.ingestion_date is None


class TestExistingCompleteDailyDelivery:
    def test_returns_without_regenerating(self, tmp_path: Path) -> None:
        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "sim_out")
        provider = OlistSimulatedSourceProvider(simulator)
        provider.get_daily_delivery(date(2017, 5, 1))

        # Simulator immutability is not weakened: calling the simulator
        # directly a second time would raise, but the provider must not
        # attempt that call at all for an already-complete delivery.
        second_batch = provider.get_daily_delivery(date(2017, 5, 1))

        assert {d.source_object for d in second_batch.deliveries} == {"orders", "order_items", "payments", "reviews"}

    def test_record_counts_correct(self, tmp_path: Path) -> None:
        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "sim_out")
        provider = OlistSimulatedSourceProvider(simulator)
        provider.get_daily_delivery(date(2017, 5, 1))

        second_batch = provider.get_daily_delivery(date(2017, 5, 1))

        orders = next(d for d in second_batch.deliveries if d.source_object == "orders")
        assert orders.record_count == 1

    def test_header_only_file_produces_zero_records(self, tmp_path: Path) -> None:
        # No orders/reviews match a day with no matching rows -- a
        # header-only file for that day, re-read as an existing delivery.
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "sim_out")
        provider = OlistSimulatedSourceProvider(simulator)
        provider.get_daily_delivery(date(2017, 5, 1))

        second_batch = provider.get_daily_delivery(date(2017, 5, 1))

        assert all(d.record_count == 0 for d in second_batch.deliveries)

    def test_existing_delivery_ingestion_date_matches_newly_generated(self, tmp_path: Path) -> None:
        # Item under test: "Existing-Delivery Requirement" -- newly
        # generated and already-materialized daily deliveries for the
        # same business date must produce identical delivery_date and
        # ingestion_date, regardless of which code path served them.
        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "sim_out")
        provider = OlistSimulatedSourceProvider(simulator)

        first_batch = provider.get_daily_delivery(date(2017, 5, 19))  # newly generated
        second_batch = provider.get_daily_delivery(date(2017, 5, 19))  # already exists on disk

        assert first_batch.delivery_date == second_batch.delivery_date == date(2017, 5, 19)
        assert first_batch.ingestion_date == second_batch.ingestion_date == date(2017, 5, 20)


class TestExistingPartialDelivery:
    def test_partial_initial_delivery_fails_clearly(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "sim_out"
        initial_dir = output_dir / "initial"
        initial_dir.mkdir(parents=True)
        # Only two of the four expected initial files present.
        (initial_dir / "olist_customers_dataset.csv").write_text("customer_id\nc1\n", encoding="utf-8-sig")
        (initial_dir / "olist_products_dataset.csv").write_text("product_id\np1\n", encoding="utf-8-sig")

        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=output_dir)
        provider = OlistSimulatedSourceProvider(simulator)

        with pytest.raises(ValueError):
            provider.get_initial_delivery()

    def test_partial_delivery_does_not_regenerate_over_it(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "sim_out"
        initial_dir = output_dir / "initial"
        initial_dir.mkdir(parents=True)
        (initial_dir / "olist_customers_dataset.csv").write_text("customer_id\nc1\n", encoding="utf-8-sig")

        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=output_dir)
        provider = OlistSimulatedSourceProvider(simulator)

        with pytest.raises(ValueError):
            provider.get_initial_delivery()

        # The partial directory's existing file must remain untouched --
        # no silent regeneration or overwrite.
        assert (initial_dir / "olist_customers_dataset.csv").read_text(encoding="utf-8-sig") == "customer_id\nc1\n"
        assert not (initial_dir / "olist_products_dataset.csv").exists()

    def test_partial_delivery_does_not_get_deleted(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "sim_out"
        initial_dir = output_dir / "initial"
        initial_dir.mkdir(parents=True)
        (initial_dir / "olist_customers_dataset.csv").write_text("customer_id\nc1\n", encoding="utf-8-sig")

        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=output_dir)
        provider = OlistSimulatedSourceProvider(simulator)

        with pytest.raises(ValueError):
            provider.get_initial_delivery()

        assert initial_dir.exists()

    def test_does_not_silently_return_a_partial_batch(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "sim_out"
        daily_dir = output_dir / "daily" / "2017-05-01"
        daily_dir.mkdir(parents=True)
        # Only orders present; order_items/payments/reviews missing.
        (daily_dir / "olist_orders_dataset.csv").write_text(",".join(ORDERS_HEADER) + "\n", encoding="utf-8-sig")

        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=output_dir)
        provider = OlistSimulatedSourceProvider(simulator)

        with pytest.raises(ValueError, match="order_items"):
            provider.get_daily_delivery(date(2017, 5, 1))


class TestCsvAwareRecordCounting:
    def test_quoted_multiline_records_count_as_one_logical_record(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "sim_out"
        daily_dir = output_dir / "daily" / "2017-05-01"
        daily_dir.mkdir(parents=True)
        _write_csv(daily_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [["r1", "o1", "5", "title", "line one\nline two\nline three", "2017-05-01", "2017-05-02"]])
        _write_csv(daily_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [])
        _write_csv(daily_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(daily_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])

        source_dir = _build_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=output_dir)
        provider = OlistSimulatedSourceProvider(simulator)

        batch = provider.get_daily_delivery(date(2017, 5, 1))

        reviews = next(d for d in batch.deliveries if d.source_object == "reviews")
        assert reviews.record_count == 1


class TestNoDownstreamCoupling:
    def test_module_does_not_reference_storage_or_bigquery_or_connectors(self) -> None:
        import inspect

        from mercury_ingestion.sources import simulated_olist as provider_module

        source_text = Path(inspect.getfile(provider_module)).read_text(encoding="utf-8")

        assert "StorageManager" not in source_text
        assert "GCSStorageManager" not in source_text
        assert "BigQueryRawLoader" not in source_text
        assert "Connector" not in source_text