"""Static contract tests for Mercury's production workflow source."""

from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = (
    REPOSITORY_ROOT
    / "workflows"
    / "production_daily.yaml"
)


def _workflow_source() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_production_workflow_source_exists() -> None:
    assert WORKFLOW_PATH.is_file()


def test_ingestion_and_readiness_commands_are_ordered() -> None:
    source = _workflow_source()

    run_day_position = source.index("run-day")
    readiness_position = source.index("check-readiness")
    dataform_position = source.index(
        "create_dataform_compilation"
    )

    assert (
        run_day_position
        < readiness_position
        < dataform_position
    )


def test_cloud_run_job_calls_use_v2_connector() -> None:
    source = _workflow_source()

    connector = (
        "googleapis.run.v2.projects.locations.jobs.run"
    )

    assert source.count(connector) == 2
    assert '"run-day"' in source
    assert '"check-readiness"' in source
    assert '"--delivery-date"' in source


def test_workflow_propagates_execution_identity() -> None:
    source = _workflow_source()

    assert "GOOGLE_CLOUD_WORKFLOW_EXECUTION_ID" in source
    assert "MERCURY_WORKFLOW_EXECUTION_ID" in source


def test_dataform_compilation_precedes_invocation() -> None:
    source = _workflow_source()

    compilation_position = source.index(
        "create_dataform_compilation"
    )
    error_check_position = source.index(
        "check_dataform_compilation"
    )
    invocation_position = source.index(
        "create_dataform_invocation"
    )

    assert (
        compilation_position
        < error_check_position
        < invocation_position
    )

    assert "/compilationResults" in source
    assert "/workflowInvocations" in source
    assert "compilationErrors" in source


def test_dataform_uses_dedicated_service_account() -> None:
    source = _workflow_source()

    assert "dataform_service_account" in source
    assert "serviceAccount" in source


def test_dataform_terminal_states_are_governed() -> None:
    source = _workflow_source()

    assert '"SUCCEEDED"' in source
    assert '"FAILED"' in source
    assert '"CANCELLED"' in source
    assert "dataform_timeout_seconds" in source


def test_workflow_has_no_environment_specific_resource_ids() -> None:
    source = _workflow_source()

    assert "mercury-data-platform-dev" not in source
    assert "mercury-dataform@" not in source


def test_manual_and_scheduled_resolution_are_distinct() -> None:
    source = _workflow_source()

    assert "execution_mode" in source
    assert '"manual"' in source
    assert '"scheduled"' in source

    assert "resolve_manual_delivery_date" in source
    assert "resolve_next_scheduled_delivery" in source

    # Historical simulation dates must not be derived from the current
    # real-world calendar.
    assert "sys.now() - 86400" not in source


def test_scheduled_mode_uses_durable_simulation_clock() -> None:
    source = _workflow_source()

    assert "simulation_start_date" in source
    assert "simulation_end_date" in source
    assert "metadata_dataset" in source

    assert (
        "googleapis.bigquery.v2.jobs.query"
        in source
    )
    assert "GENERATE_DATE_ARRAY" in source
    assert "historical_replay_state" in source
    assert "status = 'success'" in source
    assert "stage = 'warehouse'" in source

    assert "ORDER BY delivery_date" in source
    assert "LIMIT 1" in source
    assert "complete_no_work_remaining" in source