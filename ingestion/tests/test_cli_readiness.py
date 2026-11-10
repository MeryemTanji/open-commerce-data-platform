"""Contract tests for Mercury's production readiness command."""

from __future__ import annotations

import json
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from mercury_ingestion import cli


@pytest.fixture
def runtime_config() -> SimpleNamespace:
    return SimpleNamespace(
        environment="test",
        project_id="mercury-test",
        region="europe-west4",
        raw_bucket="mercury-test-raw",
        raw_dataset="raw",
        metadata_dataset="metadata",
        source_input_uri="gs://mercury-input/olist",
        workflow_execution_id="workflow-123",
    )


def _read_summary(
    capsys: pytest.CaptureFixture[str],
) -> dict[str, object]:
    captured = capsys.readouterr()
    lines = [
        line
        for line in captured.out.splitlines()
        if line.strip()
    ]

    assert len(lines) == 1
    assert captured.err == ""

    event = json.loads(lines[0])

    assert event.pop("event_schema_version") == "1.0"

    occurred_at = event.pop("occurred_at")
    assert isinstance(occurred_at, str)
    assert occurred_at.endswith("Z")

    parsed_timestamp = datetime.fromisoformat(
        occurred_at.replace("Z", "+00:00")
    )
    assert parsed_timestamp.tzinfo is not None
    assert parsed_timestamp.utcoffset() is not None

    event_route = (
        event.pop("event_name"),
        event.pop("command"),
        event.pop("stage"),
    )

    assert event_route in {
        (
            "mercury.readiness.terminal",
            "check-readiness",
            "readiness",
        ),
        (
            "mercury.command.rejected",
            "check-readiness",
            "request_validation",
        ),
        (
            "mercury.command.rejected",
            "check-readiness",
            "runtime_configuration",
        ),
    }

    return event


class TestReadyDelivery:
    def test_returns_zero_and_emits_readiness_summary(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        runtime_config: SimpleNamespace,
    ) -> None:
        constructor_calls: list[dict[str, object]] = []
        requested_dates: list[date] = []

        monkeypatch.setattr(
            cli.RuntimeConfig,
            "from_environment",
            lambda: runtime_config,
        )

        class FakeReplayStateStore:
            def __init__(self, **kwargs: object) -> None:
                constructor_calls.append(dict(kwargs))

            def get_completed_for_date(
                self,
                delivery_date: date,
            ) -> tuple[SimpleNamespace, ...]:
                requested_dates.append(delivery_date)

                return tuple(
                    SimpleNamespace(source_object=source_object)
                    for source_object in (
                        "orders",
                        "order_items",
                        "payments",
                        "reviews",
                    )
                )

        monkeypatch.setattr(
            cli,
            "BigQueryReplayStateStore",
            FakeReplayStateStore,
            raising=False,
        )

        exit_code = cli.main(
            [
                "check-readiness",
                "--delivery-date",
                "2017-05-01",
            ]
        )

        assert exit_code == 0
        assert requested_dates == [date(2017, 5, 1)]
        assert constructor_calls == [
            {
                "project_id": "mercury-test",
                "dataset_id": "metadata",
                "location": "europe-west4",
            }
        ]

        assert _read_summary(capsys) == {
            "workflow_execution_id": "workflow-123",
            "environment": "test",
            "delivery_date": "2017-05-01",
            "expected_source_objects": [
                "order_items",
                "orders",
                "payments",
                "reviews",
            ],
            "completed_source_objects": [
                "order_items",
                "orders",
                "payments",
                "reviews",
            ],
            "missing_source_objects": [],
            "unexpected_source_objects": [],
            "is_ready": True,
            "final_status": "ready",
            "failure_category": None,
        }


class TestBlockedDelivery:
    def test_returns_one_and_reports_missing_sources(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        runtime_config: SimpleNamespace,
    ) -> None:
        monkeypatch.setattr(
            cli.RuntimeConfig,
            "from_environment",
            lambda: runtime_config,
        )

        class FakeReplayStateStore:
            def __init__(self, **_: object) -> None:
                pass

            def get_completed_for_date(
                self,
                _: date,
            ) -> tuple[SimpleNamespace, ...]:
                return tuple(
                    SimpleNamespace(source_object=source_object)
                    for source_object in (
                        "orders",
                        "order_items",
                        "reviews",
                    )
                )

        monkeypatch.setattr(
            cli,
            "BigQueryReplayStateStore",
            FakeReplayStateStore,
            raising=False,
        )

        exit_code = cli.main(
            [
                "check-readiness",
                "--delivery-date",
                "2017-05-01",
            ]
        )

        assert exit_code == 1

        summary = _read_summary(capsys)
        assert summary["is_ready"] is False
        assert summary["final_status"] == "blocked"
        assert summary["failure_category"] == "date_incomplete"
        assert summary["missing_source_objects"] == ["payments"]
        assert summary["unexpected_source_objects"] == []


class TestReadinessFailure:
    def test_returns_two_without_exposing_provider_details(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        runtime_config: SimpleNamespace,
    ) -> None:
        monkeypatch.setattr(
            cli.RuntimeConfig,
            "from_environment",
            lambda: runtime_config,
        )

        class FailingReplayStateStore:
            def __init__(self, **_: object) -> None:
                pass

            def get_completed_for_date(
                self,
                _: date,
            ) -> tuple[SimpleNamespace, ...]:
                raise RuntimeError(
                    "sensitive BigQuery provider detail"
                )

        monkeypatch.setattr(
            cli,
            "BigQueryReplayStateStore",
            FailingReplayStateStore,
            raising=False,
        )

        exit_code = cli.main(
            [
                "check-readiness",
                "--delivery-date",
                "2017-05-01",
            ]
        )

        assert exit_code == 2

        summary = _read_summary(capsys)
        serialized = json.dumps(summary)

        assert summary["is_ready"] is False
        assert summary["final_status"] == "failed"
        assert (
            summary["failure_category"]
            == "readiness_evaluation"
        )
        assert "sensitive BigQuery provider detail" not in serialized