"""Tests for Mercury's structured production event contract."""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from mercury_ingestion.runtime.structured_logging import (
    build_terminal_event,
    emit_structured_event,
)


_BASE_SUMMARY = {
    "workflow_execution_id": "workflow-123",
    "ingestion_run_id": "run-456",
    "environment": "dev",
    "delivery_date": "2017-05-01",
    "final_status": "success",
    "failure_category": None,
}


class TestBuildTerminalEvent:
    def test_adds_observability_envelope_and_preserves_summary(self) -> None:
        occurred_at = datetime(
            2026,
            11,
            10,
            12,
            30,
            tzinfo=timezone.utc,
        )

        event = build_terminal_event(
            summary=_BASE_SUMMARY,
            event_name="mercury.ingestion.completed",
            command="run-day",
            stage="ingestion",
            occurred_at=occurred_at,
        )

        assert event == {
            "event_schema_version": "1.0",
            "event_name": "mercury.ingestion.completed",
            "occurred_at": "2026-11-10T12:30:00Z",
            "command": "run-day",
            "stage": "ingestion",
            **_BASE_SUMMARY,
        }

    def test_generated_timestamp_is_timezone_aware_utc(self) -> None:
        event = build_terminal_event(
            summary=_BASE_SUMMARY,
            event_name="mercury.ingestion.completed",
            command="run-day",
            stage="ingestion",
        )

        occurred_at = event["occurred_at"]

        assert isinstance(occurred_at, str)
        assert occurred_at.endswith("Z")
        assert datetime.fromisoformat(
            occurred_at.replace("Z", "+00:00")
        ).tzinfo is not None

    def test_supplied_timestamp_is_normalized_to_utc(self) -> None:
        occurred_at = datetime(
            2026,
            11,
            10,
            14,
            30,
            tzinfo=timezone(timedelta(hours=2)),
        )

        event = build_terminal_event(
            summary=_BASE_SUMMARY,
            event_name="mercury.readiness.completed",
            command="check-readiness",
            stage="readiness",
            occurred_at=occurred_at,
        )

        assert event["occurred_at"] == "2026-11-10T12:30:00Z"

    def test_naive_timestamp_is_rejected(self) -> None:
        with pytest.raises(
            ValueError,
            match="occurred_at must be timezone-aware",
        ):
            build_terminal_event(
                summary=_BASE_SUMMARY,
                event_name="mercury.ingestion.completed",
                command="run-day",
                stage="ingestion",
                occurred_at=datetime(2026, 11, 10, 12, 30),
            )

    @pytest.mark.parametrize(
        ("field_name", "value"),
        (
            ("event_name", ""),
            ("event_name", "   "),
            ("command", ""),
            ("command", "   "),
            ("stage", ""),
            ("stage", "   "),
        ),
    )
    def test_blank_event_metadata_is_rejected(
        self,
        field_name: str,
        value: str,
    ) -> None:
        arguments = {
            "summary": _BASE_SUMMARY,
            "event_name": "mercury.ingestion.completed",
            "command": "run-day",
            "stage": "ingestion",
        }
        arguments[field_name] = value

        with pytest.raises(
            ValueError,
            match=rf"{field_name} cannot be blank",
        ):
            build_terminal_event(**arguments)

    @pytest.mark.parametrize(
        "reserved_key",
        (
            "event_schema_version",
            "event_name",
            "occurred_at",
            "command",
            "stage",
        ),
    )
    def test_summary_cannot_override_event_metadata(
        self,
        reserved_key: str,
    ) -> None:
        summary = {
            **_BASE_SUMMARY,
            reserved_key: "unsafe-override",
        }

        with pytest.raises(
            ValueError,
            match="reserved event metadata",
        ):
            build_terminal_event(
                summary=summary,
                event_name="mercury.ingestion.completed",
                command="run-day",
                stage="ingestion",
            )

    def test_input_summary_is_not_mutated(self) -> None:
        summary = dict(_BASE_SUMMARY)
        original = dict(summary)

        build_terminal_event(
            summary=summary,
            event_name="mercury.ingestion.completed",
            command="run-day",
            stage="ingestion",
        )

        assert summary == original


class TestEmitStructuredEvent:
    def test_emits_one_compact_json_line(self) -> None:
        stream = io.StringIO()
        event = build_terminal_event(
            summary=_BASE_SUMMARY,
            event_name="mercury.ingestion.completed",
            command="run-day",
            stage="ingestion",
            occurred_at=datetime(
                2026,
                11,
                10,
                12,
                30,
                tzinfo=timezone.utc,
            ),
        )

        emit_structured_event(
            event,
            stream=stream,
        )

        output = stream.getvalue()

        assert output.endswith("\n")
        assert output.count("\n") == 1
        assert " " not in output
        assert json.loads(output) == event