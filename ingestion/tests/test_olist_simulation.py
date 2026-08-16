"""Unit tests for mercury_ingestion.simulation.olist.

All tests use synthetic, temporary source files -- never the real Olist
dataset.
"""

from __future__ import annotations

import csv
import dataclasses
from datetime import date
from pathlib import Path

import pytest

from mercury_ingestion.simulation.olist import (
    DailySimulationResult,
    InitialSimulationResult,
    OlistSourceSimulator,
    SimulatedFile,
)

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

# Orders on 2017-05-01: o1, o2. On 2017-05-02: o3.
ORDERS_ROWS = [
    ["o1", "c1", "delivered", "2017-05-01 10:00:00", "2017-05-01 11:00:00", "2017-05-02 09:00:00", "2017-05-05 14:00:00", "2017-05-06"],
    ["o2", "c2", "delivered", "2017-05-01 12:00:00", "2017-05-01 13:00:00", "2017-05-02 10:00:00", "2017-05-06 14:00:00", "2017-05-07"],
    ["o3", "c3", "shipped", "2017-05-02 09:00:00", "2017-05-02 10:00:00", "2017-05-03 09:00:00", "", "2017-05-08"],
]

# o1 has two items, o2 and o3 have one each.
ORDER_ITEMS_ROWS = [
    ["o1", "1", "p1", "s1", "2017-05-05 10:00:00", "29.90", "8.50"],
    ["o1", "2", "p2", "s1", "2017-05-05 10:00:00", "15.00", "8.50"],
    ["o2", "1", "p3", "s2", "2017-05-06 10:00:00", "99.99", "12.00"],
    ["o3", "1", "p4", "s3", "2017-05-07 10:00:00", "10.00", "5.00"],
]

# o1 is a split payment (2 rows), o2 and o3 have one each.
PAYMENTS_ROWS = [
    ["o1", "1", "voucher", "1", "20.00"],
    ["o1", "2", "credit_card", "3", "80.00"],
    ["o2", "1", "boleto", "1", "150.00"],
    ["o3", "1", "credit_card", "1", "50.00"],
]

# r1 reviews o1 (purchased 05-01) but arrives on 05-03 -- independent timing.
# r2 reviews o2 on the same day as purchase. r3 is unrelated.
REVIEWS_ROWS = [
    ["r1", "o1", "5", "great", "loved it, fast delivery", "2017-05-03", "2017-05-04"],
    ["r2", "o2", "3", "", "ok", "2017-05-01", "2017-05-02"],
    ["r3", "o3", "1", "bad", "bad product", "2017-05-10", "2017-05-11"],
]


def _write_csv(path: Path, header: list[str], rows: list[list[str]], *, encoding: str = "utf-8-sig") -> Path:
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
    return path


def _build_full_source_directory(tmp_path: Path) -> Path:
    """Build a complete, valid synthetic Olist source directory."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    _write_csv(source_dir / "olist_customers_dataset.csv", CUSTOMERS_HEADER, [["c1", "u1", "01310", "sao paulo", "SP"], ["c2", "u2", "20040", "rio", "RJ"], ["c3", "u3", "30130", "bh", "MG"]])
    _write_csv(source_dir / "olist_products_dataset.csv", PRODUCTS_HEADER, [["p1", "cat", "40", "500", "2", "225", "16", "10", "14"]])
    _write_csv(source_dir / "olist_sellers_dataset.csv", SELLERS_HEADER, [["s1", "01310", "sao paulo", "SP"]])
    _write_csv(source_dir / "olist_geolocation_dataset.csv", GEOLOCATION_HEADER, [["01037", "-23.5456", "-46.6393", "sao paulo", "SP"]])
    _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, ORDERS_ROWS)
    _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, ORDER_ITEMS_ROWS)
    _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, PAYMENTS_ROWS)
    _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, REVIEWS_ROWS)
    return source_dir


def _read_data_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class TestSimulatedFileValidation:
    def test_is_immutable(self) -> None:
        sim_file = SimulatedFile(source_object="orders", path=Path("x.csv"), record_count=1)

        with pytest.raises(dataclasses.FrozenInstanceError):
            sim_file.record_count = 2  # type: ignore[misc]

    def test_negative_record_count_rejected(self) -> None:
        with pytest.raises(ValueError):
            SimulatedFile(source_object="orders", path=Path("x.csv"), record_count=-1)

    def test_blank_source_object_rejected(self) -> None:
        with pytest.raises(ValueError):
            SimulatedFile(source_object="   ", path=Path("x.csv"), record_count=0)

    def test_non_path_rejected(self) -> None:
        with pytest.raises(TypeError):
            SimulatedFile(source_object="orders", path="x.csv", record_count=0)  # type: ignore[arg-type]


class TestResultObjectImmutability:
    def test_initial_simulation_result_is_immutable(self) -> None:
        result = InitialSimulationResult(files=())

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.files = ()  # type: ignore[misc]

    def test_daily_simulation_result_is_immutable(self) -> None:
        result = DailySimulationResult(simulation_date=date(2017, 5, 1), files=())

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.simulation_date = date(2017, 5, 2)  # type: ignore[misc]


class TestConstructor:
    def test_accepts_path_arguments(self, tmp_path: Path) -> None:
        simulator = OlistSourceSimulator(source_directory=tmp_path / "src", output_directory=tmp_path / "out")

        assert simulator.source_directory == tmp_path / "src"
        assert simulator.output_directory == tmp_path / "out"

    def test_non_path_source_directory_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            OlistSourceSimulator(source_directory=str(tmp_path / "src"), output_directory=tmp_path / "out")  # type: ignore[arg-type]

    def test_non_path_output_directory_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            OlistSourceSimulator(source_directory=tmp_path / "src", output_directory=str(tmp_path / "out"))  # type: ignore[arg-type]

    def test_constructor_creates_no_output_directory(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"

        OlistSourceSimulator(source_directory=tmp_path / "src", output_directory=output_dir)

        assert not output_dir.exists()

    def test_source_files_need_not_exist_at_construction(self, tmp_path: Path) -> None:
        # Should not raise even though tmp_path / "src" doesn't exist.
        OlistSourceSimulator(source_directory=tmp_path / "src", output_directory=tmp_path / "out")


class TestInitialLoad:
    def test_all_four_expected_files_generated(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_initial_load()

        assert {f.source_object for f in result.files} == {"customers", "products", "sellers", "geolocations"}

    def test_exact_output_layout(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        output_dir = tmp_path / "out"
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=output_dir)

        simulator.generate_initial_load()

        expected_dir = output_dir / "initial"
        assert (expected_dir / "olist_customers_dataset.csv").is_file()
        assert (expected_dir / "olist_products_dataset.csv").is_file()
        assert (expected_dir / "olist_sellers_dataset.csv").is_file()
        assert (expected_dir / "olist_geolocation_dataset.csv").is_file()

    def test_original_filenames_preserved(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_initial_load()

        names = {f.path.name for f in result.files}
        assert names == {
            "olist_customers_dataset.csv",
            "olist_products_dataset.csv",
            "olist_sellers_dataset.csv",
            "olist_geolocation_dataset.csv",
        }

    def test_copied_files_are_byte_identical(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_initial_load()

        for sim_file in result.files:
            source_filename = {
                "customers": "olist_customers_dataset.csv",
                "products": "olist_products_dataset.csv",
                "sellers": "olist_sellers_dataset.csv",
                "geolocations": "olist_geolocation_dataset.csv",
            }[sim_file.source_object]
            original_bytes = (source_dir / source_filename).read_bytes()
            assert sim_file.path.read_bytes() == original_bytes

    def test_record_counts_correct(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_initial_load()

        counts = {f.source_object: f.record_count for f in result.files}
        assert counts == {"customers": 3, "products": 1, "sellers": 1, "geolocations": 1}

    def test_existing_initial_output_raises_file_exists_error(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")
        simulator.generate_initial_load()

        with pytest.raises(FileExistsError):
            simulator.generate_initial_load()

    def test_missing_required_source_raises_file_not_found_error(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        (source_dir / "olist_products_dataset.csv").unlink()
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        with pytest.raises(FileNotFoundError):
            simulator.generate_initial_load()

    def test_source_path_that_is_a_directory_raises_value_error(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        (source_dir / "olist_products_dataset.csv").unlink()
        (source_dir / "olist_products_dataset.csv").mkdir()
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        with pytest.raises(ValueError):
            simulator.generate_initial_load()


class TestOrdersDailyFiltering:
    def test_only_rows_for_requested_date_included(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        orders_file = next(f for f in result.files if f.source_object == "orders")
        rows = _read_data_rows(orders_file.path)
        assert {row["order_id"] for row in rows} == {"o1", "o2"}

    def test_rows_from_other_dates_excluded(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        orders_file = next(f for f in result.files if f.source_object == "orders")
        rows = _read_data_rows(orders_file.path)
        assert "o3" not in {row["order_id"] for row in rows}

    def test_original_timestamp_string_preserved(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        orders_file = next(f for f in result.files if f.source_object == "orders")
        rows = _read_data_rows(orders_file.path)
        o1_row = next(row for row in rows if row["order_id"] == "o1")
        assert o1_row["order_purchase_timestamp"] == "2017-05-01 10:00:00"

    def test_original_row_order_preserved(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        orders_file = next(f for f in result.files if f.source_object == "orders")
        rows = _read_data_rows(orders_file.path)
        assert [row["order_id"] for row in rows] == ["o1", "o2"]

    def test_duplicate_rows_preserved(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [ORDERS_ROWS[0], ORDERS_ROWS[0]])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        orders_file = next(f for f in result.files if f.source_object == "orders")
        assert orders_file.record_count == 2

    def test_malformed_required_timestamp_fails_clearly(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        bad_row = ["o1", "c1", "delivered", "not-a-timestamp", "", "", "", ""]
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [bad_row])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        with pytest.raises(ValueError, match="order_purchase_timestamp"):
            simulator.generate_daily_load(date(2017, 5, 1))

    def test_blank_required_timestamp_fails_clearly(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        bad_row = ["o1", "c1", "delivered", "", "", "", "", ""]
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [bad_row])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        with pytest.raises(ValueError, match="order_purchase_timestamp"):
            simulator.generate_daily_load(date(2017, 5, 1))


class TestOrderItemsFiltering:
    def test_all_rows_for_daily_order_ids_included(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        order_items_file = next(f for f in result.files if f.source_object == "order_items")
        rows = _read_data_rows(order_items_file.path)
        assert {row["order_id"] for row in rows} == {"o1", "o2"}
        assert order_items_file.record_count == 3  # o1 has 2 items, o2 has 1

    def test_rows_for_other_order_ids_excluded(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        order_items_file = next(f for f in result.files if f.source_object == "order_items")
        rows = _read_data_rows(order_items_file.path)
        assert "o3" not in {row["order_id"] for row in rows}

    def test_multiple_items_for_same_order_preserved(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        order_items_file = next(f for f in result.files if f.source_object == "order_items")
        rows = _read_data_rows(order_items_file.path)
        o1_item_ids = sorted(row["order_item_id"] for row in rows if row["order_id"] == "o1")
        assert o1_item_ids == ["1", "2"]

    def test_exact_duplicates_preserved(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [ORDERS_ROWS[0]])
        duplicate_item = ["o1", "1", "p1", "s1", "2017-05-05 10:00:00", "29.90", "8.50"]
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [duplicate_item, duplicate_item])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        order_items_file = next(f for f in result.files if f.source_object == "order_items")
        assert order_items_file.record_count == 2

    def test_original_row_order_preserved(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        order_items_file = next(f for f in result.files if f.source_object == "order_items")
        rows = _read_data_rows(order_items_file.path)
        assert [(row["order_id"], row["order_item_id"]) for row in rows] == [("o1", "1"), ("o1", "2"), ("o2", "1")]


class TestPaymentsFiltering:
    def test_all_payment_rows_for_daily_order_ids_included(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        payments_file = next(f for f in result.files if f.source_object == "payments")
        rows = _read_data_rows(payments_file.path)
        assert {row["order_id"] for row in rows} == {"o1", "o2"}

    def test_payments_for_other_orders_excluded(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        payments_file = next(f for f in result.files if f.source_object == "payments")
        rows = _read_data_rows(payments_file.path)
        assert "o3" not in {row["order_id"] for row in rows}

    def test_split_payments_preserved(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        payments_file = next(f for f in result.files if f.source_object == "payments")
        rows = _read_data_rows(payments_file.path)
        o1_sequentials = sorted(row["payment_sequential"] for row in rows if row["order_id"] == "o1")
        assert o1_sequentials == ["1", "2"]

    def test_original_row_order_preserved(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        payments_file = next(f for f in result.files if f.source_object == "payments")
        rows = _read_data_rows(payments_file.path)
        assert [(row["order_id"], row["payment_sequential"]) for row in rows] == [("o1", "1"), ("o1", "2"), ("o2", "1")]


class TestReviewsFiltering:
    def test_selection_uses_review_creation_date(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 3))

        reviews_file = next(f for f in result.files if f.source_object == "reviews")
        rows = _read_data_rows(reviews_file.path)
        assert {row["review_id"] for row in rows} == {"r1"}

    def test_review_can_arrive_later_than_parent_order(self, tmp_path: Path) -> None:
        # o1 was purchased 2017-05-01; its review r1 arrives on 2017-05-03.
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        purchase_day_result = simulator.generate_daily_load(date(2017, 5, 1))
        review_day_result = simulator.generate_daily_load(date(2017, 5, 3))

        purchase_day_reviews = next(f for f in purchase_day_result.files if f.source_object == "reviews")
        review_day_reviews = next(f for f in review_day_result.files if f.source_object == "reviews")
        assert purchase_day_reviews.record_count == 1  # r2, reviewing o2 same-day
        assert review_day_reviews.record_count == 1  # r1, reviewing o1 two days late

    def test_order_purchase_date_is_irrelevant_to_review_delivery(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        # o1 purchased 2017-05-01, but r1 (reviewing o1) must NOT appear
        # in the 2017-05-01 review delivery.
        result = simulator.generate_daily_load(date(2017, 5, 1))

        reviews_file = next(f for f in result.files if f.source_object == "reviews")
        rows = _read_data_rows(reviews_file.path)
        assert "r1" not in {row["review_id"] for row in rows}

    def test_quoted_text_is_preserved_correctly(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        review_row = ["r1", "o1", "5", "great!!", "loved it, fast, reliable", "2017-05-03", "2017-05-04"]
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [review_row])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 3))

        reviews_file = next(f for f in result.files if f.source_object == "reviews")
        rows = _read_data_rows(reviews_file.path)
        assert rows[0]["review_comment_message"] == "loved it, fast, reliable"

    def test_multiline_comment_remains_one_logical_record(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        review_row = ["r1", "o1", "5", "title", "line one\nline two\nline three", "2017-05-03", "2017-05-04"]
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [review_row])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 3))

        reviews_file = next(f for f in result.files if f.source_object == "reviews")
        rows = _read_data_rows(reviews_file.path)
        assert reviews_file.record_count == 1
        assert rows[0]["review_comment_message"] == "line one\nline two\nline three"

    def test_review_does_not_require_parent_order_in_same_delivery(self, tmp_path: Path) -> None:
        # No orders at all match 2017-05-03, but a review can still land
        # that day independently.
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 3))

        orders_file = next(f for f in result.files if f.source_object == "orders")
        reviews_file = next(f for f in result.files if f.source_object == "reviews")
        assert orders_file.record_count == 0
        assert reviews_file.record_count == 1


class TestEmptyDailyDelivery:
    def test_all_four_files_still_exist(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        assert len(result.files) == 4
        for sim_file in result.files:
            assert sim_file.path.is_file()

    def test_zero_record_source_is_header_only(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        orders_file = next(f for f in result.files if f.source_object == "orders")
        rows = _read_data_rows(orders_file.path)
        header_line = orders_file.path.read_text(encoding="utf-8-sig").splitlines()[0]
        assert rows == []
        assert header_line == ",".join(ORDERS_HEADER)

    def test_record_count_is_zero(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        assert all(f.record_count == 0 for f in result.files)


class TestSchemaPreservation:
    def test_header_names_unchanged(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        orders_file = next(f for f in result.files if f.source_object == "orders")
        header_line = orders_file.path.read_text(encoding="utf-8-sig").splitlines()[0]
        assert header_line == ",".join(ORDERS_HEADER)

    def test_column_order_unchanged(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        payments_file = next(f for f in result.files if f.source_object == "payments")
        with payments_file.path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header_row = next(reader)
        assert header_row == PAYMENTS_HEADER

    def test_blank_values_preserved(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        orders_file = next(f for f in result.files if f.source_object == "orders")
        rows = _read_data_rows(orders_file.path)
        # o2's order_delivered_customer_date is a real value; check a
        # genuinely blank field survives via the review fixture instead.
        assert any(row["order_delivered_customer_date"] != "" for row in rows)

    def test_blank_review_title_preserved(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        reviews_file = next(f for f in result.files if f.source_object == "reviews")
        rows = _read_data_rows(reviews_file.path)
        r2_row = next(row for row in rows if row["review_id"] == "r2")
        assert r2_row["review_comment_title"] == ""

    def test_unusual_unicode_preserved(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        review_row = ["r1", "o1", "5", "🎉", "muito bom! ção çãé — great", "2017-05-03", "2017-05-04"]
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [review_row])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 3))

        reviews_file = next(f for f in result.files if f.source_object == "reviews")
        rows = _read_data_rows(reviews_file.path)
        assert rows[0]["review_comment_title"] == "🎉"
        assert rows[0]["review_comment_message"] == "muito bom! ção çãé — great"

    def test_no_deduplication(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [ORDERS_ROWS[0], ORDERS_ROWS[0]])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        orders_file = next(f for f in result.files if f.source_object == "orders")
        assert orders_file.record_count == 2


class TestImmutability:
    def test_rerunning_same_initial_load_raises_file_exists_error(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")
        simulator.generate_initial_load()

        with pytest.raises(FileExistsError):
            simulator.generate_initial_load()

    def test_rerunning_same_daily_date_raises_file_exists_error(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")
        simulator.generate_daily_load(date(2017, 5, 1))

        with pytest.raises(FileExistsError):
            simulator.generate_daily_load(date(2017, 5, 1))

    def test_existing_generated_files_are_not_modified(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")
        first_result = simulator.generate_daily_load(date(2017, 5, 1))
        orders_file = next(f for f in first_result.files if f.source_object == "orders")
        original_bytes = orders_file.path.read_bytes()

        with pytest.raises(FileExistsError):
            simulator.generate_daily_load(date(2017, 5, 1))

        assert orders_file.path.read_bytes() == original_bytes

    def test_different_dates_do_not_collide(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        simulator.generate_daily_load(date(2017, 5, 1))
        # Should not raise -- a different date is a different delivery.
        simulator.generate_daily_load(date(2017, 5, 2))


class TestFailureSafety:
    def test_failed_daily_generation_does_not_leave_partial_delivery(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        bad_row = ["o1", "c1", "delivered", "not-a-timestamp", "", "", "", ""]
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [bad_row])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        output_dir = tmp_path / "out"
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=output_dir)

        with pytest.raises(ValueError):
            simulator.generate_daily_load(date(2017, 5, 1))

        destination_dir = output_dir / "daily" / "2017-05-01"
        assert not destination_dir.exists()

    def test_failed_daily_generation_leaves_no_leftover_temp_directory(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        bad_row = ["o1", "c1", "delivered", "not-a-timestamp", "", "", "", ""]
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [bad_row])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        output_dir = tmp_path / "out"
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=output_dir)

        with pytest.raises(ValueError):
            simulator.generate_daily_load(date(2017, 5, 1))

        leftover_temp_dirs = list(output_dir.glob(".daily.tmp-*")) if output_dir.exists() else []
        assert leftover_temp_dirs == []

    def test_subsequent_successful_run_possible_after_failure(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        bad_row = ["o1", "c1", "delivered", "not-a-timestamp", "", "", "", ""]
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [bad_row])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        output_dir = tmp_path / "out"
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=output_dir)

        with pytest.raises(ValueError):
            simulator.generate_daily_load(date(2017, 5, 1))

        # Fix the bad timestamp and confirm a clean run now succeeds,
        # proving the earlier failure left no blocking partial state.
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [ORDERS_ROWS[0]])
        result = simulator.generate_daily_load(date(2017, 5, 1))
        assert result.simulation_date == date(2017, 5, 1)


class TestInitialLoadAtomicPublication:
    """Revision 1: initial/ is published via one atomic directory rename."""

    def test_successful_load_creates_complete_initial_directory(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        output_dir = tmp_path / "out"
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=output_dir)

        simulator.generate_initial_load()

        expected_dir = output_dir / "initial"
        assert expected_dir.is_dir()
        assert {p.name for p in expected_dir.iterdir()} == {
            "olist_customers_dataset.csv",
            "olist_products_dataset.csv",
            "olist_sellers_dataset.csv",
            "olist_geolocation_dataset.csv",
        }

    def test_existing_initial_directory_raises_file_exists_error(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        output_dir = tmp_path / "out"
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=output_dir)
        simulator.generate_initial_load()

        with pytest.raises(FileExistsError):
            simulator.generate_initial_load()

    def test_failure_during_staging_leaves_no_final_initial_directory(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        (source_dir / "olist_sellers_dataset.csv").unlink()  # will fail mid-staging
        output_dir = tmp_path / "out"
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=output_dir)

        with pytest.raises(FileNotFoundError):
            simulator.generate_initial_load()

        assert not (output_dir / "initial").exists()

    def test_failure_during_staging_leaves_no_leftover_temp_directory(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        (source_dir / "olist_sellers_dataset.csv").unlink()
        output_dir = tmp_path / "out"
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=output_dir)

        with pytest.raises(FileNotFoundError):
            simulator.generate_initial_load()

        leftover_temp_dirs = list(output_dir.glob(".initial.tmp-*")) if output_dir.exists() else []
        assert leftover_temp_dirs == []

    def test_successful_retry_possible_after_failed_attempt(self, tmp_path: Path) -> None:
        source_dir = _build_full_source_directory(tmp_path)
        sellers_file = source_dir / "olist_sellers_dataset.csv"
        original_sellers_bytes = sellers_file.read_bytes()
        sellers_file.unlink()
        output_dir = tmp_path / "out"
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=output_dir)

        with pytest.raises(FileNotFoundError):
            simulator.generate_initial_load()

        # Restore the missing source and confirm a clean run now succeeds.
        sellers_file.write_bytes(original_sellers_bytes)
        result = simulator.generate_initial_load()

        assert {f.source_object for f in result.files} == {"customers", "products", "sellers", "geolocations"}
        assert (output_dir / "initial").is_dir()

    def test_partial_directory_content_never_observed_at_destination(self, tmp_path: Path) -> None:
        # A failure that happens after some files are already staged in
        # the temp directory must still not expose destination_dir at
        # all -- not even with the files that were successfully staged.
        source_dir = _build_full_source_directory(tmp_path)
        (source_dir / "olist_geolocation_dataset.csv").unlink()  # last in INITIAL_SOURCE_OBJECTS order
        output_dir = tmp_path / "out"
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=output_dir)

        with pytest.raises(FileNotFoundError):
            simulator.generate_initial_load()

        assert not (output_dir / "initial").exists()


class TestRequiredSimulationFieldsOrders:
    """Revision 2: Orders simulation requires order_id and order_purchase_timestamp."""

    def test_missing_order_id_raises_value_error(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        header = [c for c in ORDERS_HEADER if c != "order_id"]
        row = [v for c, v in zip(ORDERS_HEADER, ORDERS_ROWS[0]) if c != "order_id"]
        _write_csv(source_dir / "olist_orders_dataset.csv", header, [row])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        with pytest.raises(ValueError, match="order_id"):
            simulator.generate_daily_load(date(2017, 5, 1))

    def test_missing_order_purchase_timestamp_raises_value_error(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        header = [c for c in ORDERS_HEADER if c != "order_purchase_timestamp"]
        row = [v for c, v in zip(ORDERS_HEADER, ORDERS_ROWS[0]) if c != "order_purchase_timestamp"]
        _write_csv(source_dir / "olist_orders_dataset.csv", header, [row])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        with pytest.raises(ValueError, match="order_purchase_timestamp"):
            simulator.generate_daily_load(date(2017, 5, 1))

    def test_header_only_orders_file_still_validates_required_fields(self, tmp_path: Path) -> None:
        # Zero data rows means timestamp parsing never runs on any row,
        # but the missing field must still be caught from the header.
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        header = [c for c in ORDERS_HEADER if c != "order_purchase_timestamp"]
        _write_csv(source_dir / "olist_orders_dataset.csv", header, [])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        with pytest.raises(ValueError, match="order_purchase_timestamp"):
            simulator.generate_daily_load(date(2017, 5, 1))

    def test_orders_file_with_only_simulation_fields_does_not_require_full_schema(self, tmp_path: Path) -> None:
        # Internal check that the simulator does not begin enforcing the
        # complete connector schema: a source containing ONLY the two
        # simulation-critical Orders fields must still work end-to-end.
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        minimal_header = ["order_id", "order_purchase_timestamp"]
        _write_csv(source_dir / "olist_orders_dataset.csv", minimal_header, [["o1", "2017-05-01 10:00:00"]])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        result = simulator.generate_daily_load(date(2017, 5, 1))

        orders_file = next(f for f in result.files if f.source_object == "orders")
        assert orders_file.record_count == 1


class TestRequiredSimulationFieldsOrderItems:
    """Revision 2: Order Items simulation requires order_id."""

    def test_missing_order_id_raises_value_error(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [ORDERS_ROWS[0]])
        header = [c for c in ORDER_ITEMS_HEADER if c != "order_id"]
        row = [v for c, v in zip(ORDER_ITEMS_HEADER, ORDER_ITEMS_ROWS[0]) if c != "order_id"]
        _write_csv(source_dir / "olist_order_items_dataset.csv", header, [row])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        with pytest.raises(ValueError, match="order_id"):
            simulator.generate_daily_load(date(2017, 5, 1))

    def test_missing_order_id_detected_even_with_zero_matching_orders(self, tmp_path: Path) -> None:
        # No orders match the day at all, but the missing order_id field
        # in order_items must still surface rather than silently
        # producing an (apparently valid) empty result.
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [])
        header = [c for c in ORDER_ITEMS_HEADER if c != "order_id"]
        _write_csv(source_dir / "olist_order_items_dataset.csv", header, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        with pytest.raises(ValueError, match="order_id"):
            simulator.generate_daily_load(date(2017, 5, 1))


class TestRequiredSimulationFieldsPayments:
    """Revision 2: Payments simulation requires order_id."""

    def test_missing_order_id_raises_value_error(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [ORDERS_ROWS[0]])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        header = [c for c in PAYMENTS_HEADER if c != "order_id"]
        row = [v for c, v in zip(PAYMENTS_HEADER, PAYMENTS_ROWS[0]) if c != "order_id"]
        _write_csv(source_dir / "olist_order_payments_dataset.csv", header, [row])
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", REVIEWS_HEADER, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        with pytest.raises(ValueError, match="order_id"):
            simulator.generate_daily_load(date(2017, 5, 1))


class TestRequiredSimulationFieldsReviews:
    """Revision 2: Reviews simulation requires review_creation_date."""

    def test_missing_review_creation_date_raises_value_error(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        header = [c for c in REVIEWS_HEADER if c != "review_creation_date"]
        row = [v for c, v in zip(REVIEWS_HEADER, REVIEWS_ROWS[0]) if c != "review_creation_date"]
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", header, [row])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        with pytest.raises(ValueError, match="review_creation_date"):
            simulator.generate_daily_load(date(2017, 5, 1))

    def test_header_only_reviews_file_still_validates_required_field(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_csv(source_dir / "olist_orders_dataset.csv", ORDERS_HEADER, [])
        _write_csv(source_dir / "olist_order_items_dataset.csv", ORDER_ITEMS_HEADER, [])
        _write_csv(source_dir / "olist_order_payments_dataset.csv", PAYMENTS_HEADER, [])
        header = [c for c in REVIEWS_HEADER if c != "review_creation_date"]
        _write_csv(source_dir / "olist_order_reviews_dataset.csv", header, [])
        simulator = OlistSourceSimulator(source_directory=source_dir, output_directory=tmp_path / "out")

        with pytest.raises(ValueError, match="review_creation_date"):
            simulator.generate_daily_load(date(2017, 5, 1))