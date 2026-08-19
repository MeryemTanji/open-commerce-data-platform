"""Unit tests for mercury_ingestion.connectors.csv_base.

These tests target the CSV contract owned by ``BaseCsvConnector`` itself
— they use a minimal, clearly non-production test connector rather than
any real Mercury source, since ``BaseCsvConnector`` is infrastructure,
not a business source. Business/domain rules stay in each concrete
connector's own test module.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import final

import pytest

from mercury_ingestion.common.metadata import IngestionStatus
from mercury_ingestion.common.storage import LocalStorageManager
from mercury_ingestion.connectors.csv_base import BaseCsvConnector

_REQUIRED_COLUMNS = frozenset({"widget_id", "widget_name"})


@final
class _TestCsvConnector(BaseCsvConnector):
    """Minimal concrete connector used only to exercise BaseCsvConnector.

    Uses a clearly non-production source identity so it can never be
    mistaken for a real Mercury source object.
    """

    SOURCE_SYSTEM = "test_csv_base_harness"
    SOURCE_OBJECT = "widgets"

    def __init__(
        self,
        source_file: Path,
        storage_manager: LocalStorageManager,
        schema_version: str | None = "1.0",
    ) -> None:
        super().__init__(
            source_file=source_file,
            source_system=self.SOURCE_SYSTEM,
            source_object=self.SOURCE_OBJECT,
            required_columns=_REQUIRED_COLUMNS,
            storage_manager=storage_manager,
            schema_version=schema_version,
        )


HEADER = ["widget_id", "widget_name"]
SAMPLE_ROWS = [
    ["w1", "sprocket"],
    ["w2", "gizmo"],
    ["w3", "gadget"],
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


def _valid_widgets_csv(tmp_path: Path, name: str = "widgets.csv") -> Path:
    return _write_csv(tmp_path / name, HEADER, SAMPLE_ROWS)


def _make_connector(
    tmp_path: Path,
    source_file: Path,
    *,
    storage_manager: LocalStorageManager | None = None,
) -> _TestCsvConnector:
    return _TestCsvConnector(
        source_file=source_file,
        storage_manager=storage_manager or LocalStorageManager(tmp_path / "landing"),
    )


class TestValidateSource:
    def test_valid_csv_passes(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, _valid_widgets_csv(tmp_path))
        connector.validate_source()  # should not raise

    def test_missing_file_produces_failed_metadata(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, tmp_path / "does_not_exist.csv")

        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED

    def test_directory_path_produces_failed_metadata(self, tmp_path: Path) -> None:
        a_directory = tmp_path / "a_directory.csv"
        a_directory.mkdir()

        connector = _make_connector(tmp_path, a_directory)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED

    def test_non_csv_extension_produces_failed_metadata(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "widgets.txt", HEADER, SAMPLE_ROWS)

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED

    def test_uppercase_csv_extension_is_accepted(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "widgets.CSV", HEADER, SAMPLE_ROWS)

        connector = _make_connector(tmp_path, source_file)
        connector.validate_source()  # should not raise

    def test_zero_byte_file_produces_failed_metadata(self, tmp_path: Path) -> None:
        source_file = tmp_path / "widgets.csv"
        source_file.write_bytes(b"")

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED

    def test_missing_header_produces_failed_metadata(self, tmp_path: Path) -> None:
        source_file = tmp_path / "widgets.csv"
        source_file.write_text("\n", encoding="utf-8-sig")  # blank first line, no header

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED

    def test_missing_required_column_produces_failed_metadata(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "widgets.csv", ["widget_id"], [["w1"]])

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED
        # Per ADR-011, the missing-column name is no longer echoed into
        # persisted error text -- only Mercury's safe operational-error
        # category is.
        assert "category=source_validation_failed" in result.metadata.error_message
        assert "widget_name" not in result.metadata.error_message

    def test_required_columns_in_different_order_are_accepted(self, tmp_path: Path) -> None:
        source_file = _write_csv(
            tmp_path / "widgets.csv",
            list(reversed(HEADER)),
            [list(reversed(row)) for row in SAMPLE_ROWS],
        )

        connector = _make_connector(tmp_path, source_file)
        connector.validate_source()  # should not raise

    def test_additional_columns_are_accepted(self, tmp_path: Path) -> None:
        header = [*HEADER, "widget_color"]
        rows = [[*row, "blue"] for row in SAMPLE_ROWS]
        source_file = _write_csv(tmp_path / "widgets.csv", header, rows)

        connector = _make_connector(tmp_path, source_file)
        connector.validate_source()  # should not raise

    def test_invalid_utf8_produces_failed_metadata(self, tmp_path: Path) -> None:
        source_file = tmp_path / "widgets.csv"
        broken_header = b"widget_id,widget_nam\xffe\n"
        source_file.write_bytes(broken_header + b"w1,sprocket\n")

        connector = _make_connector(tmp_path, source_file)
        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED


class TestCountRecords:
    def test_header_is_excluded_from_count(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "widgets.csv", HEADER, SAMPLE_ROWS[:1])

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 1

    def test_multiple_logical_records_count_correctly(self, tmp_path: Path) -> None:
        source_file = _valid_widgets_csv(tmp_path)

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == len(SAMPLE_ROWS)

    def test_header_only_csv_returns_zero(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "widgets.csv", HEADER, [])

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 0

    def test_blank_physical_lines_are_not_counted(self, tmp_path: Path) -> None:
        content = "widget_id,widget_name\nw1,sprocket\n\nw2,gizmo\n"
        source_file = tmp_path / "widgets.csv"
        source_file.write_text(content, encoding="utf-8-sig")

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 2

    def test_quoted_commas_remain_one_logical_record(self, tmp_path: Path) -> None:
        rows = [["w1", "sprocket, deluxe edition"]]
        source_file = _write_csv(tmp_path / "widgets.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 1

    def test_multiline_quoted_field_remains_one_logical_record(self, tmp_path: Path) -> None:
        rows = [["w1", "line one\nline two\nline three"]]
        source_file = _write_csv(tmp_path / "widgets.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 1

    def test_duplicate_rows_are_counted_independently(self, tmp_path: Path) -> None:
        rows = [
            ["w1", "sprocket"],
            ["w1", "sprocket"],
            ["w1", "sprocket"],
        ]
        source_file = _write_csv(tmp_path / "widgets.csv", HEADER, rows)

        connector = _make_connector(tmp_path, source_file)

        assert connector.count_records() == 3


class TestEndToEndLifecycle:
    def test_successful_run_lands_identical_bytes(self, tmp_path: Path) -> None:
        source_file = _valid_widgets_csv(tmp_path)
        original_bytes = source_file.read_bytes()
        connector = _make_connector(tmp_path, source_file)

        result = connector.run()

        assert result.metadata.status is IngestionStatus.SUCCESS
        assert Path(result.metadata.landing_path).read_bytes() == original_bytes
        assert result.metadata.record_count == len(SAMPLE_ROWS)

    def test_technical_validation_failure_does_not_land_a_raw_file(self, tmp_path: Path) -> None:
        source_file = _write_csv(tmp_path / "widgets.csv", ["widget_id"], [["w1"]])
        root = tmp_path / "landing"
        connector = _make_connector(tmp_path, source_file, storage_manager=LocalStorageManager(root))

        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED
        assert not (root / "raw").exists()