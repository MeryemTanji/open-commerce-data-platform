"""Unit and end-to-end tests for mercury_ingestion.connectors.order_items."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from mercury_ingestion.common.metadata import IngestionStatus
from mercury_ingestion.common.storage import LocalStorageManager
from mercury_ingestion.connectors.order_items import REQUIRED_COLUMNS, OrderItemsConnector

HEADER = [
    "order_id",
    "order_item_id",
    "product_id",
    "seller_id",
    "shipping_limit_date",
    "price",
    "freight_value",
]

# One order (A) with three items, one order (B) with one item -- the
# expected real-world shape where order_id repeats across item rows.
SAMPLE_ROWS = [
    ["A", "1", "p1", "s1", "2026-01-05 10:00:00", "29.90", "8.50"],
    ["A", "2", "p2", "s1", "2026-01-05 10:00:00", "15.00", "8.50"],
    ["A", "3", "p3", "s2", "2026-01-05 10:00:00", "42.10", "8.50"],
    ["B", "1", "p4", "s3", "2026-01-06 12:00:00", "99.99", "12.00"],
]


def _write_csv(
    path: Path,
    header: list[str],
    rows: list[list[str]],
    *,
    encoding: str = "utf-8-sig",
) -> Path:
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
    return path


def _valid_order_items_csv(tmp_path: Path, name: str = "order_items.csv") -> Path:
    return _write_csv(tmp_path / name, HEADER, SAMPLE_ROWS)


def _make_connector(
    tmp_path: Path,
    source_file: Path,
    *,
    storage_manager: LocalStorageManager | None = None,
    schema_version: str | None = "1.0",
) -> OrderItemsConnector:
    return OrderItemsConnector(
        source_file=source_file,
        storage_manager=storage_manager or LocalStorageManager(tmp_path / "landing"),
        schema_version=schema_version,
    )


class TestConstruction:
    def test_source_system_is_order_platform(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_order_items_csv(tmp_path))
        assert connector.source_system == "order_platform"

    def test_source_object_is_order_items(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_order_items_csv(tmp_path))
        assert connector.source_object == "order_items"

    def test_default_schema_version_is_1_0(self, tmp_path: Path) -> None:
        connector = OrderItemsConnector(
            source_file=_valid_order_items_csv(tmp_path),
            storage_manager=LocalStorageManager(tmp_path / "landing"),
        )
        assert connector.schema_version == "1.0"

    def test_custom_schema_version_is_preserved(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_order_items_csv(tmp_path), schema_version="2.0")
        assert connector.schema_version == "2.0"


class TestValidateSource:
    def test_valid_csv_passes(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_order_items_csv(tmp_path))
        connector.validate_source()  # should not raise

    def test_required_columns_in_different_order(self, tmp_path: Path) -> None:
        shuffled_header = list(reversed(HEADER))
        shuffled_rows = [list(reversed(row)) for row in SAMPLE_ROWS]
        source_file = _write_csv(tmp_path / "order_items.csv", shuffled_header, shuffled_rows)

        connector = _make_connector(tmp_path, source_file)
        connector.validate_source()  # should not raise

    def test_extra_columns_are_accepted(self, tmp_path: Path) -> None:
        header = [*HEADER, "promotion_code"]
        rows = [[*row, "SUMMER10"] for row in SAMPLE_ROWS]
        source_file = _write_csv(tmp_path / "order_items.csv", header, rows)

        connector = _make_connector(tmp_path, source_file)
        connector.validate_source()  # should not raise

    def test_missing_source_file_produces_failed_metadata(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, tmp_path / "does_not_exist.csv")

        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED

    def test_directory_as_source_produces_failed_metadata(self, tmp_path: Path) -> None:
        a_directory = tmp_path / "a_directory.csv"
        a_directory.mkdir()

        connector = _make_connector(tmp_path, a_directory)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED

    def test_non_csv_extension_produces_failed_metadata(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "order_items.txt", HEADER, SAMPLE_ROWS)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED

    def test_uppercase_csv_extension_is_accepted(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "order_items.CSV", HEADER, SAMPLE_ROWS)

        connector = _make_connector(tmp_path, source_file)
        connector.validate_source()  # should not raise

    def test_empty_file_produces_failed_metadata(self, tmp_path: Path) -> None:
        source_file = tmp_path / "order_items.csv"
        source_file.write_bytes(b"")

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED

    def test_missing_header_produces_failed_metadata(self, tmp_path: Path) -> None:
        source_file = tmp_path / "order_items.csv"
        source_file.write_text("\n", encoding="utf-8-sig")  # blank first line, no header

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED

    @pytest.mark.parametrize("missing_column", sorted(REQUIRED_COLUMNS))
    def test_each_missing_required_column_produces_failed_metadata(
        self, tmp_path: Path, missing_column: str
    ) -> None:
        header = [column for column in HEADER if column != missing_column]
        rows = [
            [value for column, value in zip(HEADER, row) if column != missing_column]
            for row in SAMPLE_ROWS
        ]
        source_file = _write_csv(tmp_path / "order_items.csv", header, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED
        assert missing_column in result.metadata.error_message

    def test_invalid_utf8_produces_failed_metadata(self, tmp_path: Path) -> None:
        source_file = tmp_path / "order_items.csv"
        # Invalid byte placed inside the header line itself, so it is hit
        # during validate_source()'s header read.
        broken_header = (
            b"order_id,order_item_id,product_id,seller_id,"
            b"shipping_limit_date,price,freight_val\xffue\n"
        )
        source_file.write_bytes(broken_header + b"A,1,p1,s1,t1,10.00,5.00\n")

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED


class TestBusinessQualityBoundary:
    """Proves technically valid but business-suspicious rows still ingest.

    Raw ingestion answers "can Mercury safely receive and preserve this
    extract?", not "is every row logically correct?" — that distinction
    is the architectural boundary this connector is built around.
    """

    def test_negative_price_does_not_fail_validation(self, tmp_path: Path) -> None:
        rows = [["A", "1", "p1", "s1", "t1", "-29.90", "8.50"]]
        source_file = _write_csv(tmp_path / "order_items.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)
        connector.validate_source()  # should not raise

    def test_negative_freight_value_does_not_fail_validation(self, tmp_path: Path) -> None:
        rows = [["A", "1", "p1", "s1", "t1", "29.90", "-8.50"]]
        source_file = _write_csv(tmp_path / "order_items.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)
        connector.validate_source()  # should not raise

    def test_blank_shipping_limit_date_is_accepted(self, tmp_path: Path) -> None:
        rows = [["A", "1", "p1", "s1", "", "29.90", "8.50"]]
        source_file = _write_csv(tmp_path / "order_items.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS

    def test_duplicate_order_id_values_are_accepted(self, tmp_path: Path) -> None:
        # Expected, everyday shape: multiple items belonging to order "A".
        connector = _make_connector(tmp_path, _valid_order_items_csv(tmp_path))

        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS

    def test_duplicate_composite_key_is_accepted(self, tmp_path: Path) -> None:
        rows = [
            ["A", "1", "p1", "s1", "t1", "29.90", "8.50"],
            ["A", "1", "p1", "s1", "t1", "29.90", "8.50"],
        ]
        source_file = _write_csv(tmp_path / "order_items.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS
        assert result.metadata.record_count == 2

    def test_unknown_looking_product_id_is_accepted(self, tmp_path: Path) -> None:
        rows = [["A", "1", "does-not-exist-anywhere", "s1", "t1", "29.90", "8.50"]]
        source_file = _write_csv(tmp_path / "order_items.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS

    def test_unknown_looking_seller_id_is_accepted(self, tmp_path: Path) -> None:
        rows = [["A", "1", "p1", "does-not-exist-anywhere", "t1", "29.90", "8.50"]]
        source_file = _write_csv(tmp_path / "order_items.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS


class TestCountRecords:
    def test_excludes_header(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "order_items.csv", HEADER, SAMPLE_ROWS[:1])

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 1

    def test_multiple_items_from_same_order_each_counted(self, tmp_path: Path) -> None:
        # Order "A" has three item rows; all three must count as separate
        # logical records even though order_id repeats.
        source_file = _valid_order_items_csv(tmp_path)

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == len(SAMPLE_ROWS)

    def test_multiple_rows_counted_correctly(self, tmp_path: Path) -> None:
        source_file = _valid_order_items_csv(tmp_path)

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 4

    def test_header_only_csv_returns_zero(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "order_items.csv", HEADER, [])

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 0

    def test_blank_lines_are_not_counted(self, tmp_path: Path) -> None:
        content = (
            "order_id,order_item_id,product_id,seller_id,"
            "shipping_limit_date,price,freight_value\n"
            "A,1,p1,s1,t1,29.90,8.50\n"
            "\n"
            "A,2,p2,s1,t1,15.00,8.50\n"
        )
        source_file = tmp_path / "order_items.csv"
        source_file.write_text(content, encoding="utf-8-sig")

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 2

    def test_quoted_fields_containing_commas_are_handled(self, tmp_path: Path) -> None:
        rows = [["A", "1", "p1, deluxe edition", "s1", "t1", "29.90", "8.50"]]
        source_file = _write_csv(tmp_path / "order_items.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 1


class TestEndToEndLifecycle:
    def test_run_returns_success(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_order_items_csv(tmp_path))

        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS

    def test_record_count_matches_number_of_item_rows(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_order_items_csv(tmp_path))

        result = connector.run()

        assert result.metadata.record_count == len(SAMPLE_ROWS)

    def test_file_lands_under_expected_path(self, tmp_path: Path) -> None:
        source_file = _valid_order_items_csv(tmp_path)
        connector = _make_connector(tmp_path, source_file)

        result = connector.run(ingestion_date=date(2026, 7, 16))

        expected = (
            tmp_path
            / "landing"
            / "raw"
            / "order_platform"
            / "order_items"
            / "ingestion_date=2026-07-16"
            / source_file.name
        )
        assert Path(result.metadata.landing_path) == expected

    def test_landed_bytes_match_source_bytes(self, tmp_path: Path) -> None:
        source_file = _valid_order_items_csv(tmp_path)
        original_bytes = source_file.read_bytes()
        connector = _make_connector(tmp_path, source_file)

        result = connector.run()

        assert Path(result.metadata.landing_path).read_bytes() == original_bytes

    def test_successful_metadata_contains_expected_fields(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_order_items_csv(tmp_path))

        result = connector.run()
        metadata = result.metadata

        assert metadata.checksum is not None
        assert metadata.file_size_bytes is not None
        assert metadata.landing_path is not None
        assert metadata.completed_at is not None

    def test_schema_version_appears_in_completed_metadata(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_order_items_csv(tmp_path), schema_version="9.9")

        result = connector.run()

        assert result.metadata.schema_version == "9.9"

    def test_validation_failure_does_not_land_a_raw_file(self, tmp_path: Path) -> None:
        header = [column for column in HEADER if column != "product_id"]
        rows = [row[:2] + row[3:] for row in SAMPLE_ROWS]
        source_file = _write_csv(tmp_path / "order_items.csv", header, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED
        raw_root = tmp_path / "landing" / "raw"
        assert not raw_root.exists()

    def test_source_file_remains_unchanged_after_success(self, tmp_path: Path) -> None:
        source_file = _valid_order_items_csv(tmp_path)
        original_bytes = source_file.read_bytes()

        connector = _make_connector(tmp_path, source_file)
        connector.run()

        assert source_file.read_bytes() == original_bytes

    def test_source_file_remains_unchanged_after_failure(self, tmp_path: Path) -> None:
        header = [column for column in HEADER if column != "product_id"]
        rows = [row[:2] + row[3:] for row in SAMPLE_ROWS]
        source_file = _write_csv(tmp_path / "order_items.csv", header, rows)
        original_bytes = source_file.read_bytes()

        connector = _make_connector(tmp_path, source_file)
        connector.run()

        assert source_file.read_bytes() == original_bytes