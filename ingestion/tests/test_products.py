"""Unit and end-to-end tests for mercury_ingestion.connectors.products."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from mercury_ingestion.common.metadata import IngestionStatus
from mercury_ingestion.common.storage import LocalStorageManager
from mercury_ingestion.connectors.products import REQUIRED_COLUMNS, ProductsConnector

HEADER = [
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

SAMPLE_ROWS = [
    ["p1", "beleza_saude", "40", "500", "2", "225", "16", "10", "14"],
    ["p2", "esporte_lazer", "55", "800", "1", "1000", "30", "20", "20"],
    ["p3", "moveis_decoracao", "30", "250", "3", "5000", "50", "40", "30"],
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


def _valid_products_csv(tmp_path: Path, name: str = "products.csv") -> Path:
    return _write_csv(tmp_path / name, HEADER, SAMPLE_ROWS)


def _make_connector(
    tmp_path: Path,
    source_file: Path,
    *,
    storage_manager: LocalStorageManager | None = None,
    schema_version: str | None = "1.0",
) -> ProductsConnector:
    return ProductsConnector(
        source_file=source_file,
        storage_manager=storage_manager or LocalStorageManager(tmp_path / "landing"),
        schema_version=schema_version,
    )


class TestConstruction:
    def test_source_system_is_product_catalog(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_products_csv(tmp_path))
        assert connector.source_system == "product_catalog"

    def test_source_object_is_products(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_products_csv(tmp_path))
        assert connector.source_object == "products"

    def test_default_schema_version_is_1_0(self, tmp_path: Path) -> None:
        connector = ProductsConnector(
            source_file=_valid_products_csv(tmp_path),
            storage_manager=LocalStorageManager(tmp_path / "landing"),
        )
        assert connector.schema_version == "1.0"

    def test_custom_schema_version_is_preserved(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_products_csv(tmp_path), schema_version="2.0")
        assert connector.schema_version == "2.0"


class TestValidateSource:
    def test_valid_csv_passes(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_products_csv(tmp_path))
        connector.validate_source()  # should not raise

    def test_required_columns_in_different_order(self, tmp_path: Path) -> None:
        shuffled_header = list(reversed(HEADER))
        shuffled_rows = [list(reversed(row)) for row in SAMPLE_ROWS]
        source_file = _write_csv(tmp_path / "products.csv", shuffled_header, shuffled_rows)

        connector = _make_connector(tmp_path, source_file)
        connector.validate_source()  # should not raise

    def test_extra_columns_are_accepted(self, tmp_path: Path) -> None:
        header = [*HEADER, "brand_name"]
        rows = [[*row, "acme"] for row in SAMPLE_ROWS]
        source_file = _write_csv(tmp_path / "products.csv", header, rows)

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
        source_file = _write_csv(tmp_path / "products.txt", HEADER, SAMPLE_ROWS)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED

    def test_uppercase_csv_extension_is_accepted(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "products.CSV", HEADER, SAMPLE_ROWS)

        connector = _make_connector(tmp_path, source_file)
        connector.validate_source()  # should not raise

    def test_empty_file_produces_failed_metadata(self, tmp_path: Path) -> None:
        source_file = tmp_path / "products.csv"
        source_file.write_bytes(b"")

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED

    def test_missing_header_produces_failed_metadata(self, tmp_path: Path) -> None:
        source_file = tmp_path / "products.csv"
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
        source_file = _write_csv(tmp_path / "products.csv", header, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED
        # Per ADR-011, the missing-column name is no longer echoed into
        # persisted error text -- only Mercury's safe operational-error
        # category is. This intentionally supersedes the pre-ADR-011
        # expectation that arbitrary validation text was persisted
        # verbatim.
        assert 'category=source_validation_failed' in result.metadata.error_message
        assert missing_column not in result.metadata.error_message

    def test_invalid_utf8_produces_failed_metadata(self, tmp_path: Path) -> None:
        source_file = tmp_path / "products.csv"
        # Invalid byte placed inside the header line itself, so it is hit
        # during validate_source()'s header read.
        broken_header = (
            b"product_id,product_category_name,product_name_lenght,"
            b"product_description_lenght,product_photos_qty,product_weight_g,"
            b"product_length_cm,product_height_cm,product_width_c\xffm\n"
        )
        source_file.write_bytes(broken_header + b"p1,cat,40,500,2,225,16,10,14\n")

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED


class TestBusinessQualityBoundary:
    """Proves technically valid but business-suspicious rows still ingest.

    Raw ingestion answers "can Mercury safely receive and preserve this
    extract?", not "is every row logically correct?" — that distinction
    is the architectural boundary this connector is built around.
    """

    def test_blank_product_category_name_is_accepted(self, tmp_path: Path) -> None:
        rows = [["p1", "", "40", "500", "2", "225", "16", "10", "14"]]
        source_file = _write_csv(tmp_path / "products.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS

    def test_negative_product_weight_is_accepted(self, tmp_path: Path) -> None:
        rows = [["p1", "cat", "40", "500", "2", "-225", "16", "10", "14"]]
        source_file = _write_csv(tmp_path / "products.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS

    def test_zero_product_dimensions_are_accepted(self, tmp_path: Path) -> None:
        rows = [["p1", "cat", "40", "500", "2", "225", "0", "0", "0"]]
        source_file = _write_csv(tmp_path / "products.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS

    def test_negative_product_dimensions_are_accepted(self, tmp_path: Path) -> None:
        rows = [["p1", "cat", "40", "500", "2", "225", "-16", "-10", "-14"]]
        source_file = _write_csv(tmp_path / "products.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS

    def test_blank_product_photos_qty_is_accepted(self, tmp_path: Path) -> None:
        rows = [["p1", "cat", "40", "500", "", "225", "16", "10", "14"]]
        source_file = _write_csv(tmp_path / "products.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS

    def test_duplicate_product_id_values_are_accepted(self, tmp_path: Path) -> None:
        rows = [
            ["p1", "cat", "40", "500", "2", "225", "16", "10", "14"],
            ["p1", "other_cat", "45", "600", "1", "300", "20", "15", "18"],
        ]
        source_file = _write_csv(tmp_path / "products.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS
        assert result.metadata.record_count == 2

    def test_unusual_category_name_is_accepted(self, tmp_path: Path) -> None:
        rows = [["p1", "not_a_real_olist_category_xyz", "40", "500", "2", "225", "16", "10", "14"]]
        source_file = _write_csv(tmp_path / "products.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS


class TestSourceSemanticsPreservation:
    """Proves ingestion never silently transforms source semantics."""

    def test_header_preserves_product_name_lenght_typo(self, tmp_path: Path) -> None:
        source_file = _valid_products_csv(tmp_path)

        header_line = source_file.read_text(encoding="utf-8-sig").splitlines()[0]

        assert "product_name_lenght" in header_line
        assert "product_name_length" not in header_line

    def test_header_preserves_product_description_lenght_typo(self, tmp_path: Path) -> None:
        source_file = _valid_products_csv(tmp_path)

        header_line = source_file.read_text(encoding="utf-8-sig").splitlines()[0]

        assert "product_description_lenght" in header_line
        assert "product_description_length" not in header_line

    def test_no_category_translation_is_applied(self, tmp_path: Path) -> None:
        rows = [["p1", "beleza_saude", "40", "500", "2", "225", "16", "10", "14"]]
        source_file = _write_csv(tmp_path / "products.csv", HEADER, rows)
        connector = _make_connector(tmp_path, source_file)

        result = connector.run()

        landed_content = Path(result.metadata.landing_path).read_text(encoding="utf-8-sig")
        # Category stays exactly as sourced (e.g. Portuguese), never
        # translated or enriched with an English equivalent.
        assert "beleza_saude" in landed_content
        assert "health_beauty" not in landed_content

    def test_landed_bytes_exactly_match_source_bytes(self, tmp_path: Path) -> None:
        source_file = _valid_products_csv(tmp_path)
        original_bytes = source_file.read_bytes()
        connector = _make_connector(tmp_path, source_file)

        result = connector.run()

        assert Path(result.metadata.landing_path).read_bytes() == original_bytes


class TestCountRecords:
    def test_excludes_header(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "products.csv", HEADER, SAMPLE_ROWS[:1])

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 1

    def test_multiple_rows_counted_correctly(self, tmp_path: Path) -> None:
        source_file = _valid_products_csv(tmp_path)

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == len(SAMPLE_ROWS)

    def test_header_only_csv_returns_zero(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "products.csv", HEADER, [])

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 0

    def test_blank_lines_are_not_counted(self, tmp_path: Path) -> None:
        content = (
            "product_id,product_category_name,product_name_lenght,"
            "product_description_lenght,product_photos_qty,product_weight_g,"
            "product_length_cm,product_height_cm,product_width_cm\n"
            "p1,cat,40,500,2,225,16,10,14\n"
            "\n"
            "p2,cat,55,800,1,1000,30,20,20\n"
        )
        source_file = tmp_path / "products.csv"
        source_file.write_text(content, encoding="utf-8-sig")

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 2

    def test_quoted_fields_containing_commas_are_handled(self, tmp_path: Path) -> None:
        rows = [["p1", "cat, with comma", "40", "500", "2", "225", "16", "10", "14"]]
        source_file = _write_csv(tmp_path / "products.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 1


class TestEndToEndLifecycle:
    def test_run_returns_success(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_products_csv(tmp_path))

        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS

    def test_record_count_matches_number_of_product_rows(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_products_csv(tmp_path))

        result = connector.run()

        assert result.metadata.record_count == len(SAMPLE_ROWS)

    def test_file_lands_under_expected_path(self, tmp_path: Path) -> None:
        source_file = _valid_products_csv(tmp_path)
        connector = _make_connector(tmp_path, source_file)

        result = connector.run(ingestion_date=date(2026, 7, 16))

        expected = (
            tmp_path
            / "landing"
            / "raw"
            / "product_catalog"
            / "products"
            / "ingestion_date=2026-07-16"
            / source_file.name
        )
        assert Path(result.metadata.landing_path) == expected

    def test_successful_metadata_contains_expected_fields(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_products_csv(tmp_path))

        result = connector.run()
        metadata = result.metadata

        assert metadata.checksum is not None
        assert metadata.file_size_bytes is not None
        assert metadata.landing_path is not None
        assert metadata.completed_at is not None

    def test_schema_version_appears_in_completed_metadata(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_products_csv(tmp_path), schema_version="9.9")

        result = connector.run()

        assert result.metadata.schema_version == "9.9"

    def test_validation_failure_does_not_land_a_raw_file(self, tmp_path: Path) -> None:
        header = [column for column in HEADER if column != "product_category_name"]
        rows = [row[:1] + row[2:] for row in SAMPLE_ROWS]
        source_file = _write_csv(tmp_path / "products.csv", header, rows)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED
        raw_root = tmp_path / "landing" / "raw"
        assert not raw_root.exists()

    def test_source_file_remains_unchanged_after_success(self, tmp_path: Path) -> None:
        source_file = _valid_products_csv(tmp_path)
        original_bytes = source_file.read_bytes()

        connector = _make_connector(tmp_path, source_file)
        connector.run()

        assert source_file.read_bytes() == original_bytes

    def test_source_file_remains_unchanged_after_failure(self, tmp_path: Path) -> None:
        header = [column for column in HEADER if column != "product_category_name"]
        rows = [row[:1] + row[2:] for row in SAMPLE_ROWS]
        source_file = _write_csv(tmp_path / "products.csv", header, rows)
        original_bytes = source_file.read_bytes()

        connector = _make_connector(tmp_path, source_file)
        connector.run()

        assert source_file.read_bytes() == original_bytes