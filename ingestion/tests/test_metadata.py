"""Unit tests for mercury_ingestion.common.metadata."""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta, timezone

import pytest

from mercury_ingestion.common.metadata import IngestionMetadata, IngestionStatus


def _started() -> IngestionMetadata:
    return IngestionMetadata.start(
        source_system="olist",
        source_object="orders",
        source_file_name="orders.csv",
        schema_version="v1",
    )


def _success() -> IngestionMetadata:
    return _started().mark_success(
        landing_path="raw/olist/orders/2026-07-14/orders.csv",
        file_size_bytes=1024,
        checksum="abc123",
        record_count=10,
    )


class TestStart:
    def test_start_creates_valid_utc_aware_started_record(self) -> None:
        meta = _started()

        assert meta.status is IngestionStatus.STARTED
        assert meta.started_at.tzinfo is not None
        assert meta.started_at.utcoffset() == timedelta(0)
        assert meta.completed_at is None

    def test_start_generates_unique_uuids_across_executions(self) -> None:
        first = _started()
        second = _started()

        assert isinstance(first.ingestion_id, type(second.ingestion_id))
        assert first.ingestion_id != second.ingestion_id


class TestMarkSuccess:
    def test_mark_success_returns_new_instance_and_leaves_original_unchanged(self) -> None:
        started = _started()

        completed = started.mark_success(
            landing_path="raw/olist/orders/2026-07-14/orders.csv",
            file_size_bytes=1024,
            checksum="abc123",
            record_count=10,
        )

        assert completed is not started
        assert completed.status is IngestionStatus.SUCCESS
        assert completed.completed_at is not None
        assert completed.completed_at >= started.started_at

        # original is untouched
        assert started.status is IngestionStatus.STARTED
        assert started.completed_at is None
        assert started.landing_path is None


class TestMarkFailed:
    def test_mark_failed_returns_new_instance(self) -> None:
        started = _started()

        failed = started.mark_failed("connection timed out")

        assert failed is not started
        assert failed.status is IngestionStatus.FAILED
        assert failed.error_message == "connection timed out"
        assert failed.completed_at is not None
        assert started.status is IngestionStatus.STARTED


class TestMarkSkipped:
    def test_mark_skipped_returns_new_instance(self) -> None:
        started = _started()

        skipped = started.mark_skipped("no new data since last run")

        assert skipped is not started
        assert skipped.status is IngestionStatus.SKIPPED
        assert skipped.error_message == "no new data since last run"
        assert skipped.completed_at is not None
        assert started.status is IngestionStatus.STARTED


class TestTerminalTransitionsRejected:
    def test_mark_success_from_success_raises(self) -> None:
        with pytest.raises(ValueError):
            _success().mark_success(
                landing_path="raw/y", file_size_bytes=2, checksum="d", record_count=2
            )

    def test_mark_failed_from_failed_raises(self) -> None:
        failed = _started().mark_failed("boom")

        with pytest.raises(ValueError):
            failed.mark_failed("boom again")

    def test_mark_skipped_from_skipped_raises(self) -> None:
        skipped = _started().mark_skipped("no data")

        with pytest.raises(ValueError):
            skipped.mark_skipped("no data again")

    def test_mark_success_from_failed_raises(self) -> None:
        failed = _started().mark_failed("boom")

        with pytest.raises(ValueError):
            failed.mark_success(
                landing_path="raw/y", file_size_bytes=2, checksum="d", record_count=2
            )


class TestBlankSourceFields:
    def test_blank_source_system_raises(self) -> None:
        with pytest.raises(ValueError):
            IngestionMetadata.start(
                source_system="  ",
                source_object="orders",
                source_file_name="orders.csv",
            )

    def test_blank_source_object_raises(self) -> None:
        with pytest.raises(ValueError):
            IngestionMetadata.start(
                source_system="olist",
                source_object="",
                source_file_name="orders.csv",
            )

    def test_blank_source_file_name_raises(self) -> None:
        with pytest.raises(ValueError):
            IngestionMetadata.start(
                source_system="olist",
                source_object="orders",
                source_file_name="   ",
            )

    def test_blank_schema_version_raises(self) -> None:
        with pytest.raises(ValueError):
            IngestionMetadata.start(
                source_system="olist",
                source_object="orders",
                source_file_name="orders.csv",
                schema_version="   ",
            )

    def test_none_schema_version_is_allowed(self) -> None:
        meta = IngestionMetadata.start(
            source_system="olist",
            source_object="orders",
            source_file_name="orders.csv",
        )

        assert meta.schema_version is None


class TestSuccessFieldValidation:
    def test_blank_landing_path_raises(self) -> None:
        with pytest.raises(ValueError):
            _started().mark_success(
                landing_path="   ",
                file_size_bytes=1024,
                checksum="abc123",
                record_count=10,
            )

    def test_blank_checksum_raises(self) -> None:
        with pytest.raises(ValueError):
            _started().mark_success(
                landing_path="raw/x",
                file_size_bytes=1024,
                checksum="",
                record_count=10,
            )

    def test_missing_required_field_raises(self) -> None:
        started = _started()

        with pytest.raises(ValueError):
            dataclasses.replace(
                started,
                status=IngestionStatus.SUCCESS,
                completed_at=datetime.now(timezone.utc),
                # landing_path, file_size_bytes, checksum, record_count left as None
            )


class TestFailureAndSkipReasonValidation:
    def test_blank_failure_reason_raises(self) -> None:
        with pytest.raises(ValueError):
            _started().mark_failed("   ")

    def test_blank_skip_reason_raises(self) -> None:
        with pytest.raises(ValueError):
            _started().mark_skipped("")


class TestNegativeNumericFields:
    def test_negative_file_size_raises(self) -> None:
        with pytest.raises(ValueError):
            _started().mark_success(
                landing_path="raw/x",
                file_size_bytes=-1,
                checksum="c",
                record_count=1,
            )

    def test_negative_record_count_raises(self) -> None:
        with pytest.raises(ValueError):
            _started().mark_success(
                landing_path="raw/x",
                file_size_bytes=1,
                checksum="c",
                record_count=-1,
            )


class TestTimezoneValidation:
    def test_naive_started_at_raises(self) -> None:
        with pytest.raises(ValueError):
            IngestionMetadata(
                ingestion_id=_started().ingestion_id,
                source_system="olist",
                source_object="orders",
                source_file_name="orders.csv",
                started_at=datetime.now(),  # naive, no tzinfo
                completed_at=None,
                landing_path=None,
                file_size_bytes=None,
                checksum=None,
                record_count=None,
                status=IngestionStatus.STARTED,
                error_message=None,
                schema_version=None,
            )

    def test_naive_completed_at_raises(self) -> None:
        started = _started()

        with pytest.raises(ValueError):
            dataclasses.replace(
                started,
                status=IngestionStatus.FAILED,
                completed_at=datetime.now(),  # naive
                error_message="boom",
            )

    def test_fixed_offset_without_utcoffset_is_still_rejected_if_none(self) -> None:
        # A tzinfo-less naive datetime has both tzinfo and utcoffset() as None;
        # this confirms the stronger check still raises for that case.
        naive = datetime(2026, 7, 14, 12, 0, 0)
        assert naive.tzinfo is None
        assert naive.utcoffset() is None

        with pytest.raises(ValueError):
            dataclasses.replace(
                _started(),
                status=IngestionStatus.FAILED,
                completed_at=naive,
                error_message="boom",
            )


class TestCompletedAtOrdering:
    def test_completed_before_started_raises(self) -> None:
        started = _started()
        too_early = started.started_at - timedelta(seconds=1)

        with pytest.raises(ValueError):
            started.mark_failed("boom", completed_at=too_early)


class TestStartedStateFieldGuard:
    def test_started_with_completed_at_raises(self) -> None:
        with pytest.raises(ValueError):
            dataclasses.replace(_started(), completed_at=datetime.now(timezone.utc))

    def test_started_with_landing_path_raises(self) -> None:
        with pytest.raises(ValueError):
            dataclasses.replace(_started(), landing_path="raw/x")

    def test_started_with_file_size_bytes_raises(self) -> None:
        with pytest.raises(ValueError):
            dataclasses.replace(_started(), file_size_bytes=100)

    def test_started_with_checksum_raises(self) -> None:
        with pytest.raises(ValueError):
            dataclasses.replace(_started(), checksum="abc")

    def test_started_with_record_count_raises(self) -> None:
        with pytest.raises(ValueError):
            dataclasses.replace(_started(), record_count=5)

    def test_started_with_error_message_raises(self) -> None:
        with pytest.raises(ValueError):
            dataclasses.replace(_started(), error_message="oops")


class TestTerminalStateRequirements:
    def test_success_missing_required_fields_raises(self) -> None:
        started = _started()

        with pytest.raises(ValueError):
            dataclasses.replace(
                started,
                status=IngestionStatus.SUCCESS,
                completed_at=datetime.now(timezone.utc),
            )

    def test_failed_missing_error_message_raises(self) -> None:
        started = _started()

        with pytest.raises(ValueError):
            dataclasses.replace(
                started,
                status=IngestionStatus.FAILED,
                completed_at=datetime.now(timezone.utc),
                error_message=None,
            )

    def test_skipped_missing_completed_at_raises(self) -> None:
        started = _started()

        with pytest.raises(ValueError):
            dataclasses.replace(
                started,
                status=IngestionStatus.SKIPPED,
                completed_at=None,
                error_message="skipped for a reason",
            )


class TestToDict:
    def test_to_dict_is_json_serializable(self) -> None:
        completed = _success()

        payload = completed.to_dict()
        serialized = json.dumps(payload)  # raises if not serializable
        reloaded = json.loads(serialized)

        assert reloaded["ingestion_id"] == str(completed.ingestion_id)
        assert reloaded["status"] == "success"
        assert reloaded["file_size_bytes"] == 1024
        assert isinstance(reloaded["started_at"], str)
        assert isinstance(reloaded["completed_at"], str)

    def test_to_dict_none_fields_stay_none(self) -> None:
        started = _started()

        payload = started.to_dict()

        assert payload["completed_at"] is None
        assert payload["landing_path"] is None
        assert payload["status"] == "started"
        json.dumps(payload)  # still serializable with Nones present


class TestImmutability:
    def test_instance_is_frozen(self) -> None:
        started = _started()

        with pytest.raises(dataclasses.FrozenInstanceError):
            started.status = IngestionStatus.SUCCESS  # type: ignore[misc]

    def test_mark_methods_do_not_mutate_original(self) -> None:
        started = _started()

        started.mark_failed("some error")

        assert started.status is IngestionStatus.STARTED
        assert started.completed_at is None
        assert started.error_message is None