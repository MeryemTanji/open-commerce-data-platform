"""Unit tests for mercury_ingestion.connectors.base."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

import pytest

from mercury_ingestion.common.metadata import IngestionMetadata, IngestionStatus
from mercury_ingestion.common.storage import LocalStorageManager
from mercury_ingestion.connectors.base import BaseConnector, ConnectorRunResult

SOURCE_SYSTEM = "olist"
SOURCE_OBJECT = "orders"


class _RecordingConnector(BaseConnector):
    """Minimal concrete connector whose hooks are injected per test.

    Every hook call is appended to ``self.calls`` so tests can assert on
    lifecycle ordering without needing real source-format parsing logic.
    """

    def __init__(
        self,
        *args: object,
        validate_fn: Callable[[], None] | None = None,
        count_fn: Callable[[], object] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._validate_fn = validate_fn or (lambda: None)
        self._count_fn = count_fn or (lambda: 5)
        self.calls: list[str] = []

    def validate_source(self) -> None:
        self.calls.append("validate_source")
        self._validate_fn()

    def count_records(self) -> int:
        self.calls.append("count_records")
        return self._count_fn()  # type: ignore[return-value]


class _RecordingStorageManager(LocalStorageManager):
    """LocalStorageManager subclass that records when save_file is called."""

    def __init__(self, root_directory: Path, calls: list[str]) -> None:
        super().__init__(root_directory)
        self._calls = calls

    def save_file(self, *args: object, **kwargs: object):  # noqa: ANN201
        self._calls.append("save_file")
        return super().save_file(*args, **kwargs)  # type: ignore[arg-type]


def _write_source_file(tmp_path: Path, name: str = "orders.csv", content: bytes = b"id\n1\n") -> Path:
    source_file = tmp_path / "source" / name
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(content)
    return source_file


def _make_connector(
    tmp_path: Path,
    *,
    source_file: Path | None = None,
    storage_manager: LocalStorageManager | None = None,
    schema_version: str | None = None,
    validate_fn: Callable[[], None] | None = None,
    count_fn: Callable[[], object] | None = None,
) -> _RecordingConnector:
    return _RecordingConnector(
        source_file=source_file or _write_source_file(tmp_path),
        source_system=SOURCE_SYSTEM,
        source_object=SOURCE_OBJECT,
        storage_manager=storage_manager or LocalStorageManager(tmp_path / "landing"),
        schema_version=schema_version,
        validate_fn=validate_fn,
        count_fn=count_fn,
    )


class TestSuccessfulLifecycle:
    def test_run_returns_connector_run_result(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)

        result = connector.run()

        assert isinstance(result, ConnectorRunResult)

    def test_successful_metadata_fields(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, count_fn=lambda: 7)

        result = connector.run()
        metadata = result.metadata

        assert metadata.status is IngestionStatus.SUCCESS
        assert metadata.landing_path is not None
        assert Path(metadata.landing_path).exists()
        assert metadata.checksum is not None
        assert metadata.file_size_bytes is not None
        assert metadata.file_size_bytes > 0
        assert metadata.record_count == 7
        assert metadata.completed_at is not None

    def test_validate_source_runs_before_count_records(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)

        connector.run()

        assert connector.calls.index("validate_source") < connector.calls.index("count_records")

    def test_count_records_runs_before_storage(self, tmp_path: Path) -> None:
        calls: list[str] = []
        storage_manager = _RecordingStorageManager(tmp_path / "landing", calls)
        connector = _RecordingConnector(
            source_file=_write_source_file(tmp_path),
            source_system=SOURCE_SYSTEM,
            source_object=SOURCE_OBJECT,
            storage_manager=storage_manager,
        )
        connector.calls = calls  # share the same list so ordering is comparable

        connector.run()

        assert calls.index("count_records") < calls.index("save_file")

    def test_provided_ingestion_date_is_used_in_landing_path(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)

        result = connector.run(ingestion_date=date(2026, 1, 1))

        assert "ingestion_date=2026-01-01" in result.metadata.landing_path

    def test_default_ingestion_date_uses_current_utc_date(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)

        result = connector.run()

        today = datetime.now(timezone.utc).date().isoformat()
        assert f"ingestion_date={today}" in result.metadata.landing_path

    def test_schema_version_is_copied_into_metadata(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, schema_version="v2")

        result = connector.run()

        assert result.metadata.schema_version == "v2"


class TestFailureHandling:
    def test_validation_failure_returns_failed_metadata(self, tmp_path: Path) -> None:
        def _fail_validation() -> None:
            raise ValueError("bad source")

        connector = _make_connector(tmp_path, validate_fn=_fail_validation)

        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED
        assert "bad source" in result.metadata.error_message

    def test_record_counting_failure_returns_failed_metadata(self, tmp_path: Path) -> None:
        def _fail_count() -> int:
            raise RuntimeError("count failed")

        connector = _make_connector(tmp_path, count_fn=_fail_count)

        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED
        assert "count failed" in result.metadata.error_message

    def test_storage_failure_returns_failed_metadata(self, tmp_path: Path) -> None:
        storage_manager = LocalStorageManager(tmp_path / "landing")
        source_file = _write_source_file(tmp_path)
        connector = _RecordingConnector(
            source_file=source_file,
            source_system=SOURCE_SYSTEM,
            source_object=SOURCE_OBJECT,
            storage_manager=storage_manager,
        )
        # Land the file once so the second run collides (FileExistsError).
        connector.run(ingestion_date=date(2026, 1, 1))

        second_connector = _RecordingConnector(
            source_file=source_file,
            source_system=SOURCE_SYSTEM,
            source_object=SOURCE_OBJECT,
            storage_manager=storage_manager,
        )
        result = second_connector.run(ingestion_date=date(2026, 1, 1))

        assert result.metadata.status is IngestionStatus.FAILED
        assert "already exists" in result.metadata.error_message

    def test_failure_metadata_contains_exception_message(self, tmp_path: Path) -> None:
        def _fail_validation() -> None:
            raise ValueError("very specific problem")

        connector = _make_connector(tmp_path, validate_fn=_fail_validation)

        result = connector.run()

        assert result.metadata.error_message == "very specific problem"

    def test_failed_metadata_excludes_success_storage_fields(self, tmp_path: Path) -> None:
        def _fail_validation() -> None:
            raise ValueError("bad source")

        connector = _make_connector(tmp_path, validate_fn=_fail_validation)

        result = connector.run()

        assert result.metadata.landing_path is None
        assert result.metadata.checksum is None
        assert result.metadata.file_size_bytes is None
        assert result.metadata.record_count is None


class TestRecordCountValidation:
    def test_non_integer_record_count_produces_failed_metadata(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, count_fn=lambda: "5")

        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED
        assert "int" in result.metadata.error_message

    def test_bool_record_count_produces_failed_metadata(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, count_fn=lambda: True)

        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED

    def test_negative_record_count_produces_failed_metadata(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path, count_fn=lambda: -1)

        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED
        assert "non-negative" in result.metadata.error_message


class TestConstructorValidation:
    def test_source_file_must_be_a_path(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            _RecordingConnector(
                source_file="orders.csv",  # type: ignore[arg-type]
                source_system=SOURCE_SYSTEM,
                source_object=SOURCE_OBJECT,
                storage_manager=LocalStorageManager(tmp_path / "landing"),
            )

    def test_storage_manager_must_be_local_storage_manager(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            _RecordingConnector(
                source_file=_write_source_file(tmp_path),
                source_system=SOURCE_SYSTEM,
                source_object=SOURCE_OBJECT,
                storage_manager=object(),  # type: ignore[arg-type]
            )

    def test_blank_source_system_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            _RecordingConnector(
                source_file=_write_source_file(tmp_path),
                source_system="   ",
                source_object=SOURCE_OBJECT,
                storage_manager=LocalStorageManager(tmp_path / "landing"),
            )

    def test_blank_source_object_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            _RecordingConnector(
                source_file=_write_source_file(tmp_path),
                source_system=SOURCE_SYSTEM,
                source_object="",
                storage_manager=LocalStorageManager(tmp_path / "landing"),
            )

    def test_source_file_need_not_exist_at_construction(self, tmp_path: Path) -> None:
        # Construction should succeed even if the file is missing; only
        # run() (via validate_source/storage) should surface that problem.
        missing_file = tmp_path / "does_not_exist.csv"
        connector = _RecordingConnector(
            source_file=missing_file,
            source_system=SOURCE_SYSTEM,
            source_object=SOURCE_OBJECT,
            storage_manager=LocalStorageManager(tmp_path / "landing"),
        )
        assert connector.source_file == missing_file


class TestConnectorRunResult:
    def test_rejects_started_metadata(self) -> None:
        started = IngestionMetadata.start(
            source_system=SOURCE_SYSTEM,
            source_object=SOURCE_OBJECT,
            source_file_name="orders.csv",
        )

        with pytest.raises(ValueError):
            ConnectorRunResult(metadata=started)

    def test_is_immutable(self, tmp_path: Path) -> None:
        connector = _make_connector(tmp_path)
        result = connector.run()

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.metadata = result.metadata  # type: ignore[misc]


class TestUncaughtExceptions:
    def test_keyboard_interrupt_is_not_caught(self, tmp_path: Path) -> None:
        def _raise_keyboard_interrupt() -> None:
            raise KeyboardInterrupt

        connector = _make_connector(tmp_path, validate_fn=_raise_keyboard_interrupt)

        with pytest.raises(KeyboardInterrupt):
            connector.run()

    def test_system_exit_is_not_caught(self, tmp_path: Path) -> None:
        def _raise_system_exit() -> None:
            raise SystemExit

        connector = _make_connector(tmp_path, validate_fn=_raise_system_exit)

        with pytest.raises(SystemExit):
            connector.run()