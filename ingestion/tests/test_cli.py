"""Contract tests for Mercury's production ingestion command."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from mercury_ingestion import cli
from mercury_ingestion.orchestration.replay import HistoricalReplayError
from mercury_ingestion.runtime.config import RuntimeConfigurationError
from mercury_ingestion.simulation.olist import SOURCE_FILENAMES


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


@pytest.fixture
def successful_result() -> SimpleNamespace:
    return SimpleNamespace(
        run_id="replay-run-123",
        source_batch=SimpleNamespace(
            deliveries=(object(), object(), object(), object())
        ),
        warehouse_results=(object(), object(), object(), object()),
    )


def _install_successful_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    runtime_config: SimpleNamespace,
    successful_result: SimpleNamespace,
) -> tuple[list[dict[str, object]], list[date]]:
    materializer_calls: list[dict[str, object]] = []
    run_dates: list[date] = []

    monkeypatch.setattr(
        cli.RuntimeConfig,
        "from_environment",
        lambda: runtime_config,
    )

    class FakeMaterializer:
        def __init__(self, **kwargs: object) -> None:
            materializer_calls.append(dict(kwargs))

        def materialize(self, destination_directory: Path) -> Path:
            materializer_calls[-1]["destination_directory"] = (
                destination_directory
            )
            return destination_directory

    class FakeRunner:
        def run_day(self, delivery_date: date) -> SimpleNamespace:
            run_dates.append(delivery_date)
            return successful_result

    monkeypatch.setattr(cli, "GCSSourceMaterializer", FakeMaterializer)
    monkeypatch.setattr(
        cli,
        "build_olist_replay_runner",
        lambda **_: FakeRunner(),
    )

    return materializer_calls, run_dates


def _read_summary(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1
    assert captured.err == ""
    return json.loads(lines[0])


class TestSuccessfulRunDay:
    def test_returns_zero_and_emits_governed_summary(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        runtime_config: SimpleNamespace,
        successful_result: SimpleNamespace,
    ) -> None:
        _, run_dates = _install_successful_dependencies(
            monkeypatch,
            runtime_config,
            successful_result,
        )

        exit_code = cli.main(
            ["run-day", "--delivery-date", "2017-05-01"]
        )

        assert exit_code == 0
        assert run_dates == [date(2017, 5, 1)]
        assert _read_summary(capsys) == {
            "workflow_execution_id": "workflow-123",
            "ingestion_run_id": "replay-run-123",
            "environment": "test",
            "delivery_date": "2017-05-01",
            "source_count": 4,
            "completed_source_count": 4,
            "failed_source_count": 0,
            "final_status": "success",
            "failure_category": None,
        }

    def test_materializes_the_complete_governed_olist_input_set(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        runtime_config: SimpleNamespace,
        successful_result: SimpleNamespace,
    ) -> None:
        materializer_calls, _ = _install_successful_dependencies(
            monkeypatch,
            runtime_config,
            successful_result,
        )

        assert (
            cli.main(["run-day", "--delivery-date", "2017-05-01"])
            == 0
        )
        _read_summary(capsys)

        assert len(materializer_calls) == 1
        assert materializer_calls[0]["source_uri"] == (
            runtime_config.source_input_uri
        )
        assert materializer_calls[0]["project_id"] == (
            runtime_config.project_id
        )
        assert materializer_calls[0]["required_filenames"] == tuple(
            SOURCE_FILENAMES.values()
        )
        assert isinstance(
            materializer_calls[0]["destination_directory"], Path
        )

    def test_builds_runner_from_runtime_configuration(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        runtime_config: SimpleNamespace,
        successful_result: SimpleNamespace,
    ) -> None:
        runner_arguments: list[dict[str, object]] = []

        monkeypatch.setattr(
            cli.RuntimeConfig,
            "from_environment",
            lambda: runtime_config,
        )

        class FakeMaterializer:
            def __init__(self, **_: object) -> None:
                pass

            def materialize(self, destination_directory: Path) -> Path:
                return destination_directory

        class FakeRunner:
            def run_day(self, _: date) -> SimpleNamespace:
                return successful_result

        def fake_factory(**kwargs: object) -> FakeRunner:
            runner_arguments.append(dict(kwargs))
            return FakeRunner()

        monkeypatch.setattr(cli, "GCSSourceMaterializer", FakeMaterializer)
        monkeypatch.setattr(
            cli,
            "build_olist_replay_runner",
            fake_factory,
        )

        assert (
            cli.main(["run-day", "--delivery-date", "2017-05-01"])
            == 0
        )
        _read_summary(capsys)

        assert len(runner_arguments) == 1
        arguments = runner_arguments[0]
        assert arguments["project_id"] == runtime_config.project_id
        assert arguments["raw_bucket_name"] == runtime_config.raw_bucket
        assert arguments["raw_dataset_id"] == runtime_config.raw_dataset
        assert arguments["metadata_dataset_id"] == (
            runtime_config.metadata_dataset
        )
        assert arguments["location"] == runtime_config.region
        assert isinstance(arguments["source_directory"], Path)
        assert isinstance(arguments["simulation_directory"], Path)
        assert arguments["source_directory"] != (
            arguments["simulation_directory"]
        )


class TestInvalidRequest:
    @pytest.mark.parametrize(
        "arguments",
        (
            ["run-day"],
            ["run-day", "--delivery-date", "not-a-date"],
            ["run-day", "--delivery-date", "2017-02-30"],
            ["unsupported-command"],
            [],
        ),
    )
    def test_returns_64_without_starting_runtime(
        self,
        arguments: list[str],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        configuration_requested = False

        def fail_if_called() -> None:
            nonlocal configuration_requested
            configuration_requested = True
            raise AssertionError("runtime must not start")

        monkeypatch.setattr(
            cli.RuntimeConfig,
            "from_environment",
            fail_if_called,
        )

        assert cli.main(arguments) == 64
        assert configuration_requested is False

        summary = _read_summary(capsys)
        assert summary["final_status"] == "invalid_request"
        assert summary["failure_category"] == "command_input"
        assert summary["ingestion_run_id"] is None

    def test_invalid_runtime_configuration_returns_64(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def raise_configuration_error() -> None:
            raise RuntimeConfigurationError("secret configuration detail")

        monkeypatch.setattr(
            cli.RuntimeConfig,
            "from_environment",
            raise_configuration_error,
        )

        exit_code = cli.main(
            ["run-day", "--delivery-date", "2017-05-01"]
        )

        assert exit_code == 64
        summary = _read_summary(capsys)
        assert summary["final_status"] == "invalid_request"
        assert summary["failure_category"] == "runtime_configuration"
        assert "secret configuration detail" not in json.dumps(summary)


class TestIncompleteDelivery:
    def test_partial_replay_returns_one_and_preserves_run_id(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        runtime_config: SimpleNamespace,
    ) -> None:
        partial_result = SimpleNamespace(
            run_id="partial-run-456",
            source_batch=SimpleNamespace(
                deliveries=(object(), object(), object(), object())
            ),
            warehouse_results=(object(), object(), object()),
        )

        replay_error = HistoricalReplayError(
            "unsafe raw exception detail",
            delivery_date=date(2017, 5, 1),
            stage="date_completion",
            source_object="payments",
            partial_day_result=partial_result,
        )

        monkeypatch.setattr(
            cli.RuntimeConfig,
            "from_environment",
            lambda: runtime_config,
        )

        class FakeMaterializer:
            def __init__(self, **_: object) -> None:
                pass

            def materialize(self, destination_directory: Path) -> Path:
                return destination_directory

        class FakeRunner:
            def run_day(self, _: date) -> None:
                raise replay_error

        monkeypatch.setattr(cli, "GCSSourceMaterializer", FakeMaterializer)
        monkeypatch.setattr(
            cli,
            "build_olist_replay_runner",
            lambda **_: FakeRunner(),
        )

        exit_code = cli.main(
            ["run-day", "--delivery-date", "2017-05-01"]
        )

        assert exit_code == 1
        summary = _read_summary(capsys)
        assert summary == {
            "workflow_execution_id": "workflow-123",
            "ingestion_run_id": "partial-run-456",
            "environment": "test",
            "delivery_date": "2017-05-01",
            "source_count": 4,
            "completed_source_count": 3,
            "failed_source_count": 1,
            "final_status": "incomplete",
            "failure_category": "date_completion",
        }
        assert "unsafe raw exception detail" not in json.dumps(summary)
        assert "payments" not in json.dumps(summary)


class TestExecutionFailure:
    def test_failure_before_a_day_result_returns_two(
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

        class FailingMaterializer:
            def __init__(self, **_: object) -> None:
                pass

            def materialize(self, _: Path) -> Path:
                raise FileNotFoundError("sensitive object path")

        monkeypatch.setattr(
            cli,
            "GCSSourceMaterializer",
            FailingMaterializer,
        )

        exit_code = cli.main(
            ["run-day", "--delivery-date", "2017-05-01"]
        )

        assert exit_code == 2
        summary = _read_summary(capsys)
        assert summary["workflow_execution_id"] == "workflow-123"
        assert summary["ingestion_run_id"] is None
        assert summary["final_status"] == "failed"
        assert summary["failure_category"] == "source_materialization"
        assert "sensitive object path" not in json.dumps(summary)

    def test_replay_failure_without_partial_result_returns_two(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        runtime_config: SimpleNamespace,
    ) -> None:
        replay_error = HistoricalReplayError(
            "unsafe provider failure",
            delivery_date=date(2017, 5, 1),
            stage="source_delivery",
        )

        monkeypatch.setattr(
            cli.RuntimeConfig,
            "from_environment",
            lambda: runtime_config,
        )

        class FakeMaterializer:
            def __init__(self, **_: object) -> None:
                pass

            def materialize(self, destination_directory: Path) -> Path:
                return destination_directory

        class FailingRunner:
            def run_day(self, _: date) -> None:
                raise replay_error

        monkeypatch.setattr(cli, "GCSSourceMaterializer", FakeMaterializer)
        monkeypatch.setattr(
            cli,
            "build_olist_replay_runner",
            lambda **_: FailingRunner(),
        )

        exit_code = cli.main(
            ["run-day", "--delivery-date", "2017-05-01"]
        )

        assert exit_code == 2
        summary = _read_summary(capsys)
        assert summary["final_status"] == "failed"
        assert summary["failure_category"] == "source_delivery"
        assert "unsafe provider failure" not in json.dumps(summary)


def test_module_executes_main_under_python_m(monkeypatch: pytest.MonkeyPatch) -> None:
    source = Path(cli.__file__).read_text(encoding="utf-8")

    assert 'if __name__ == "__main__":' in source
    assert "raise SystemExit(main())" in source
