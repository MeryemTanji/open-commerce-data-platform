"""Unit tests for Mercury production runtime configuration."""

from __future__ import annotations

import dataclasses

import pytest

from mercury_ingestion.runtime.config import (
    RuntimeConfig,
    RuntimeConfigurationError,
)


def _valid_environment() -> dict[str, str]:
    return {
        "MERCURY_ENVIRONMENT": "dev",
        "MERCURY_PROJECT_ID": "mercury-data-platform-dev",
        "MERCURY_REGION": "europe-west4",
        "MERCURY_RAW_BUCKET": "mercury-data-platform-dev-raw-01",
        "MERCURY_RAW_DATASET": "raw",
        "MERCURY_METADATA_DATASET": "metadata",
        "MERCURY_SOURCE_INPUT_URI": (
            "gs://mercury-simulation-input/olist/source"
        ),
        "MERCURY_WORKFLOW_EXECUTION_ID": "workflow-123",
    }


class TestRuntimeConfigLoading:
    def test_loads_complete_configuration(self) -> None:
        config = RuntimeConfig.from_environment(
            _valid_environment()
        )

        assert config.environment == "dev"
        assert config.project_id == "mercury-data-platform-dev"
        assert config.region == "europe-west4"
        assert (
            config.raw_bucket
            == "mercury-data-platform-dev-raw-01"
        )
        assert config.raw_dataset == "raw"
        assert config.metadata_dataset == "metadata"
        assert config.source_input_uri == (
            "gs://mercury-simulation-input/olist/source"
        )
        assert config.workflow_execution_id == "workflow-123"

    def test_surrounding_whitespace_is_removed(self) -> None:
        environment = _valid_environment()
        environment["MERCURY_ENVIRONMENT"] = "  dev  "
        environment["MERCURY_PROJECT_ID"] = (
            "  mercury-data-platform-dev  "
        )

        config = RuntimeConfig.from_environment(environment)

        assert config.environment == "dev"
        assert config.project_id == "mercury-data-platform-dev"

    def test_reads_process_environment_by_default(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for name, value in _valid_environment().items():
            monkeypatch.setenv(name, value)

        config = RuntimeConfig.from_environment()

        assert config.environment == "dev"
        assert config.workflow_execution_id == "workflow-123"

    def test_configuration_is_immutable(self) -> None:
        config = RuntimeConfig.from_environment(
            _valid_environment()
        )

        with pytest.raises(dataclasses.FrozenInstanceError):
            config.environment = "prod"  # type: ignore[misc]


class TestRequiredValues:
    @pytest.mark.parametrize(
        "variable_name",
        [
            "MERCURY_ENVIRONMENT",
            "MERCURY_PROJECT_ID",
            "MERCURY_REGION",
            "MERCURY_RAW_BUCKET",
            "MERCURY_RAW_DATASET",
            "MERCURY_METADATA_DATASET",
            "MERCURY_SOURCE_INPUT_URI",
            "MERCURY_WORKFLOW_EXECUTION_ID",
        ],
    )
    def test_missing_required_variable_is_rejected(
        self,
        variable_name: str,
    ) -> None:
        environment = _valid_environment()
        del environment[variable_name]

        with pytest.raises(
            RuntimeConfigurationError,
            match=variable_name,
        ):
            RuntimeConfig.from_environment(environment)

    @pytest.mark.parametrize(
        "blank_value",
        ["", " ", "\t", "\n"],
    )
    def test_blank_required_value_is_rejected(
        self,
        blank_value: str,
    ) -> None:
        environment = _valid_environment()
        environment["MERCURY_PROJECT_ID"] = blank_value

        with pytest.raises(
            RuntimeConfigurationError,
            match="MERCURY_PROJECT_ID",
        ):
            RuntimeConfig.from_environment(environment)

    def test_all_missing_values_are_reported_together(
        self,
    ) -> None:
        with pytest.raises(
            RuntimeConfigurationError
        ) as error:
            RuntimeConfig.from_environment({})

        message = str(error.value)

        for variable_name in _valid_environment():
            assert variable_name in message


class TestConfigurationSemantics:
    @pytest.mark.parametrize(
        "source_input_uri",
        [
            "https://example.com/olist",
            "file:///tmp/olist",
            "olist/source",
            "gs://",
        ],
    )
    def test_malformed_source_input_uri_is_rejected(
        self,
        source_input_uri: str,
    ) -> None:
        environment = _valid_environment()
        environment[
            "MERCURY_SOURCE_INPUT_URI"
        ] = source_input_uri

        with pytest.raises(
            RuntimeConfigurationError,
            match="MERCURY_SOURCE_INPUT_URI",
        ):
            RuntimeConfig.from_environment(environment)

    def test_raw_bucket_must_be_a_bucket_name_not_uri(
        self,
    ) -> None:
        environment = _valid_environment()
        environment["MERCURY_RAW_BUCKET"] = (
            "gs://mercury-data-platform-dev-raw-01"
        )

        with pytest.raises(
            RuntimeConfigurationError,
            match="MERCURY_RAW_BUCKET",
        ):
            RuntimeConfig.from_environment(environment)

    def test_raw_and_metadata_datasets_must_differ(
        self,
    ) -> None:
        environment = _valid_environment()
        environment["MERCURY_METADATA_DATASET"] = "raw"

        with pytest.raises(
            RuntimeConfigurationError,
            match="must identify different datasets",
        ):
            RuntimeConfig.from_environment(environment)