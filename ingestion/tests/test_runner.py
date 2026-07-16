"""Unit tests for mercury_ingestion.runner."""

from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path
from typing import Callable

import pytest

from mercury_ingestion.common.metadata import IngestionMetadata
from mercury_ingestion.connectors.base import BaseConnector, ConnectorRunResult
from mercury_ingestion.runner import IngestionRunner, RunnerResult, RunnerStatus, run_connectors


class _StubConnector(BaseConnector):
    """A BaseConnector test double whose run() outcome is fully controlled.

    This deliberately bypasses the real lifecycle (validate/count/store)
    so tests can construct SUCCESS, FAILED, or SKIPPED outcomes directly,
    and can record how it was called.
    """

    def __init__(
        self,
        name: str,
        outcome: str,
        calls: list[str] | None = None,
        ingestion_dates_seen: list[date | None] | None = None,
        raise_instead: BaseException | None = None,
    ) -> None:
        # Intentionally skip BaseConnector.__init__: this stub does not
        # need a real source_file/storage_manager to exercise the runner.
        self.name = name
        self.outcome = outcome
        self.calls = calls if calls is not None else []
        self.ingestion_dates_seen = ingestion_dates_seen if ingestion_dates_seen is not None else []
        self.raise_instead = raise_instead

    def validate_source(self) -> None:  # pragma: no cover - not exercised
        pass

    def count_records(self) -> int:  # pragma: no cover - not exercised
        return 0

    def run(self, ingestion_date: date | None = None) -> ConnectorRunResult:
        self.calls.append(self.name)
        self.ingestion_dates_seen.append(ingestion_date)

        if self.raise_instead is not None:
            raise self.raise_instead

        metadata = IngestionMetadata.start(
            source_system="stub_system",
            source_object="stub_object",
            source_file_name=f"{self.name}.csv",
        )
        if self.outcome == "success":
            metadata = metadata.mark_success(
                landing_path=f"raw/stub/{self.name}.csv",
                file_size_bytes=10,
                checksum="abc123",
                record_count=1,
            )
        elif self.outcome == "failed":
            metadata = metadata.mark_failed("stub failure")
        elif self.outcome == "skipped":
            metadata = metadata.mark_skipped("stub skip")
        else:
            raise ValueError(f"unknown outcome: {self.outcome}")

        return ConnectorRunResult(metadata=metadata)


def _stub(name: str, outcome: str, **kwargs: object) -> _StubConnector:
    return _StubConnector(name=name, outcome=outcome, **kwargs)  # type: ignore[arg-type]


class TestConstruction:
    def test_empty_connectors_iterable_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            IngestionRunner([])

    def test_non_base_connector_item_is_rejected(self) -> None:
        with pytest.raises(TypeError):
            IngestionRunner([_stub("a", "success"), object()])  # type: ignore[list-item]

    def test_generators_are_accepted_and_eagerly_captured(self) -> None:
        def _generator():
            yield _stub("a", "success")
            yield _stub("b", "success")

        runner = IngestionRunner(_generator())

        assert len(runner.connectors) == 2

    def test_connector_order_is_preserved(self) -> None:
        connectors = [_stub("first", "success"), _stub("second", "success"), _stub("third", "success")]

        runner = IngestionRunner(connectors)

        assert [c.name for c in runner.connectors] == ["first", "second", "third"]

    def test_connectors_are_not_executed_during_construction(self) -> None:
        calls: list[str] = []
        connector = _stub("a", "success", calls=calls)

        IngestionRunner([connector])

        assert calls == []


class TestSuccessfulRuns:
    def test_one_successful_connector_produces_success(self) -> None:
        runner = IngestionRunner([_stub("a", "success")])

        result = runner.run_all()

        assert result.status is RunnerStatus.SUCCESS

    def test_multiple_successful_connectors_produce_success(self) -> None:
        runner = IngestionRunner([_stub("a", "success"), _stub("b", "success")])

        result = runner.run_all()

        assert result.status is RunnerStatus.SUCCESS

    def test_success_plus_skipped_produces_success(self) -> None:
        runner = IngestionRunner([_stub("a", "success"), _stub("b", "skipped")])

        result = runner.run_all()

        assert result.status is RunnerStatus.SUCCESS

    def test_connectors_execute_exactly_once(self) -> None:
        calls: list[str] = []
        connectors = [_stub("a", "success", calls=calls), _stub("b", "success", calls=calls)]
        runner = IngestionRunner(connectors)

        runner.run_all()

        assert calls == ["a", "b"]

    def test_connectors_execute_in_supplied_order(self) -> None:
        calls: list[str] = []
        connectors = [
            _stub("first", "success", calls=calls),
            _stub("second", "failed", calls=calls),
            _stub("third", "skipped", calls=calls),
        ]
        runner = IngestionRunner(connectors)

        runner.run_all()

        assert calls == ["first", "second", "third"]

    def test_provided_ingestion_date_is_passed_to_every_connector(self) -> None:
        seen: list[date | None] = []
        connectors = [
            _stub("a", "success", ingestion_dates_seen=seen),
            _stub("b", "success", ingestion_dates_seen=seen),
        ]
        runner = IngestionRunner(connectors)

        runner.run_all(ingestion_date=date(2026, 7, 16))

        assert seen == [date(2026, 7, 16), date(2026, 7, 16)]

    def test_none_ingestion_date_is_passed_through_as_none(self) -> None:
        seen: list[date | None] = []
        connector = _stub("a", "success", ingestion_dates_seen=seen)
        runner = IngestionRunner([connector])

        runner.run_all()

        assert seen == [None]

    def test_run_connectors_matches_ingestion_runner_behavior(self) -> None:
        connectors_for_runner = [_stub("a", "success"), _stub("b", "failed")]
        connectors_for_function = [_stub("a", "success"), _stub("b", "failed")]

        via_runner = IngestionRunner(connectors_for_runner).run_all()
        via_function = run_connectors(connectors_for_function)

        assert via_runner.status == via_function.status
        assert via_runner.total_count == via_function.total_count
        assert via_runner.exit_code == via_function.exit_code


class TestFailureAggregation:
    def test_all_failed_connectors_produce_failed(self) -> None:
        runner = IngestionRunner([_stub("a", "failed"), _stub("b", "failed")])

        result = runner.run_all()

        assert result.status is RunnerStatus.FAILED

    def test_success_plus_failure_produces_partial_failure(self) -> None:
        runner = IngestionRunner([_stub("a", "success"), _stub("b", "failed")])

        result = runner.run_all()

        assert result.status is RunnerStatus.PARTIAL_FAILURE

    def test_skipped_plus_failure_produces_partial_failure(self) -> None:
        runner = IngestionRunner([_stub("a", "skipped"), _stub("b", "failed")])

        result = runner.run_all()

        assert result.status is RunnerStatus.PARTIAL_FAILURE

    def test_result_counts_are_correct(self) -> None:
        runner = IngestionRunner(
            [
                _stub("a", "success"),
                _stub("b", "success"),
                _stub("c", "failed"),
                _stub("d", "skipped"),
            ]
        )

        result = runner.run_all()

        assert result.succeeded_count == 2
        assert result.failed_count == 1
        assert result.skipped_count == 1

    def test_total_count_is_correct(self) -> None:
        runner = IngestionRunner([_stub("a", "success"), _stub("b", "failed"), _stub("c", "skipped")])

        result = runner.run_all()

        assert result.total_count == 3

    @pytest.mark.parametrize(
        ("outcomes", "expected_exit_code"),
        [
            (["success", "success"], 0),
            (["success", "failed"], 1),
            (["failed", "failed"], 2),
        ],
    )
    def test_exit_codes_are_correct_for_all_statuses(
        self, outcomes: list[str], expected_exit_code: int
    ) -> None:
        connectors = [_stub(f"c{i}", outcome) for i, outcome in enumerate(outcomes)]
        runner = IngestionRunner(connectors)

        result = runner.run_all()

        assert result.exit_code == expected_exit_code


class TestRunnerResultValidation:
    def test_rejects_empty_results(self) -> None:
        with pytest.raises(ValueError):
            RunnerResult(results=(), status=RunnerStatus.SUCCESS)

    def test_rejects_status_inconsistent_with_metadata(self) -> None:
        connector = _stub("a", "success")
        connector_result = connector.run()

        with pytest.raises(ValueError):
            RunnerResult(results=(connector_result,), status=RunnerStatus.FAILED)

    def test_is_immutable(self) -> None:
        connector = _stub("a", "success")
        result = RunnerResult(results=(connector.run(),), status=RunnerStatus.SUCCESS)

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.status = RunnerStatus.FAILED  # type: ignore[misc]


class TestUnexpectedExceptions:
    def test_keyboard_interrupt_propagates(self) -> None:
        connector = _stub("a", "success", raise_instead=KeyboardInterrupt())
        runner = IngestionRunner([connector])

        with pytest.raises(KeyboardInterrupt):
            runner.run_all()

    def test_system_exit_propagates(self) -> None:
        connector = _stub("a", "success", raise_instead=SystemExit())
        runner = IngestionRunner([connector])

        with pytest.raises(SystemExit):
            runner.run_all()

    def test_unexpected_ordinary_exception_propagates(self) -> None:
        connector = _stub("a", "success", raise_instead=RuntimeError("connector bug"))
        runner = IngestionRunner([connector])

        with pytest.raises(RuntimeError, match="connector bug"):
            runner.run_all()