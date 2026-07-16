"""Unit and end-to-end tests for mercury_ingestion.connectors.customers."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from mercury_ingestion.common.metadata import IngestionStatus
from mercury_ingestion.common.storage import LocalStorageManager
from mercury_ingestion.connectors.customers import REQUIRED_COLUMNS, CustomerConnector

HEADER = [
    "customer_id",
    "customer_unique_id",
    "customer_zip_code_prefix",
    "customer_city",
    "customer_state",
]

SAMPLE_ROWS = [
    ["c1", "u1", "01310", "sao paulo", "SP"],
    ["c2", "u2", "20040", "rio de janeiro", "RJ"],
    ["c3", "u3", "30130", "belo horizonte", "MG"],
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


def _valid_customers_csv(tmp_path: Path, name: str = "customers.csv") -> Path:
    return _write_csv(tmp_path / name, HEADER, SAMPLE_ROWS)


def _make_connector(
    tmp_path: Path,
    source_file: Path,
    *,
    storage_manager: LocalStorageManager | None = None,
    schema_version: str | None = "1.0",
) -> CustomerConnector:
    return CustomerConnector(
        source_file=source_file,
        storage_manager=storage_manager or LocalStorageManager(tmp_path / "landing"),
        schema_version=schema_version,
    )


class TestConstruction:
    def test_source_system_is_customer_platform(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_customers_csv(tmp_path))
        assert connector.source_system == "customer_platform"

    def test_source_object_is_customers(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_customers_csv(tmp_path))
        assert connector.source_object == "customers"

    def test_default_schema_version_is_1_0(self, tmp_path: Path) -> None:
        connector = CustomerConnector(
            source_file=_valid_customers_csv(tmp_path),
            storage_manager=LocalStorageManager(tmp_path / "landing"),
        )
        assert connector.schema_version == "1.0"

    def test_custom_schema_version_is_preserved(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_customers_csv(tmp_path), schema_version="2.0")
        assert connector.schema_version == "2.0"


class TestValidateSource:
    def test_valid_csv_passes(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_customers_csv(tmp_path))
        connector.validate_source()  # should not raise

    def test_required_columns_in_different_order(self, tmp_path: Path) -> None:
        shuffled_header = list(reversed(HEADER))
        shuffled_rows = [list(reversed(row)) for row in SAMPLE_ROWS]
        source_file = _write_csv(tmp_path / "customers.csv", shuffled_header, shuffled_rows)

        connector = _make_connector(tmp_path, source_file)
        connector.validate_source()  # should not raise

    def test_extra_columns_are_accepted(self, tmp_path: Path) -> None:
        header = [*HEADER, "loyalty_tier"]
        rows = [[*row, "gold"] for row in SAMPLE_ROWS]
        source_file = _write_csv(tmp_path / "customers.csv", header, rows)

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
        source_file = _write_csv(tmp_path / "customers.txt", HEADER, SAMPLE_ROWS)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED

    def test_uppercase_csv_extension_is_accepted(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "customers.CSV", HEADER, SAMPLE_ROWS)

        connector = _make_connector(tmp_path, source_file)
        connector.validate_source()  # should not raise

    def test_empty_file_produces_failed_metadata(self, tmp_path: Path) -> None:
        source_file = tmp_path / "customers.csv"
        source_file.write_bytes(b"")

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED

    def test_missing_header_produces_failed_metadata(self, tmp_path: Path) -> None:
        source_file = tmp_path / "customers.csv"
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
        source_file = _write_csv(tmp_path / "customers.csv", header, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED
        assert missing_column in result.metadata.error_message

    def test_invalid_utf8_produces_failed_metadata(self, tmp_path: Path) -> None:
        source_file = tmp_path / "customers.csv"
        # Invalid byte placed inside the header line itself, so it is hit
        # during validate_source()'s header read.
        broken_header = b"customer_id,customer_unique_id,customer_zip_code_prefix,customer_city,customer_st\xffate\n"
        source_file.write_bytes(broken_header + b"c1,u1,111,city,ST\n")

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED


class TestCountRecords:
    def test_excludes_header(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "customers.csv", HEADER, SAMPLE_ROWS[:1])

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 1

    def test_multiple_rows_counted_correctly(self, tmp_path: Path) -> None:
        source_file = _valid_customers_csv(tmp_path)

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == len(SAMPLE_ROWS)

    def test_header_only_csv_returns_zero(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "customers.csv", HEADER, [])

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 0

    def test_blank_lines_are_not_counted(self, tmp_path: Path) -> None:
        content = (
            "customer_id,customer_unique_id,customer_zip_code_prefix,customer_city,customer_state\n"
            "c1,u1,111,city1,ST\n"
            "\n"
            "c2,u2,222,city2,ST\n"
        )
        source_file = tmp_path / "customers.csv"
        source_file.write_text(content, encoding="utf-8-sig")

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 2

    def test_quoted_fields_containing_commas_are_handled(self, tmp_path: Path) -> None:
        rows = [["c1", "u1", "111", "Sao Paulo, capital", "SP"]]
        source_file = _write_csv(tmp_path / "customers.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 1


class TestEndToEndLifecycle:
    def test_run_returns_success(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_customers_csv(tmp_path))

        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS

    def test_record_count_matches_number_of_customer_rows(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_customers_csv(tmp_path))

        result = connector.run()

        assert result.metadata.record_count == len(SAMPLE_ROWS)

    def test_file_lands_under_expected_path(self, tmp_path: Path) -> None:
        source_file = _valid_customers_csv(tmp_path)
        connector = _make_connector(tmp_path, source_file)

        result = connector.run(ingestion_date=date(2026, 7, 16))

        expected = (
            tmp_path
            / "landing"
            / "raw"
            / "customer_platform"
            / "customers"
            / "ingestion_date=2026-07-16"
            / source_file.name
        )
        assert Path(result.metadata.landing_path) == expected

    def test_landed_bytes_match_source_bytes(self, tmp_path: Path) -> None:
        source_file = _valid_customers_csv(tmp_path)
        original_bytes = source_file.read_bytes()
        connector = _make_connector(tmp_path, source_file)

        result = connector.run()

        assert Path(result.metadata.landing_path).read_bytes() == original_bytes

    def test_successful_metadata_contains_expected_fields(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_customers_csv(tmp_path))

        result = connector.run()
        metadata = result.metadata

        assert metadata.checksum is not None
        assert metadata.file_size_bytes is not None
        assert metadata.landing_path is not None
        assert metadata.completed_at is not None

    def test_schema_version_appears_in_completed_metadata(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_customers_csv(tmp_path), schema_version="9.9")

        result = connector.run()

        assert result.metadata.schema_version == "9.9"

    def test_validation_failure_does_not_land_a_raw_file(self, tmp_path: Path) -> None:
        header = [column for column in HEADER if column != "customer_state"]
        rows = [row[:-1] for row in SAMPLE_ROWS]
        source_file = _write_csv(tmp_path / "customers.csv", header, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED
        raw_root = tmp_path / "landing" / "raw"
        assert not raw_root.exists()

    def test_source_file_remains_unchanged_after_failure(self, tmp_path: Path) -> None:
        header = [column for column in HEADER if column != "customer_state"]
        rows = [row[:-1] for row in SAMPLE_ROWS]
        source_file = _write_csv(tmp_path / "customers.csv", header, rows)
        original_bytes = source_file.read_bytes()

        connector = _make_connector(tmp_path, source_file)
        connector.run()

        assert source_file.read_bytes() == original_bytes