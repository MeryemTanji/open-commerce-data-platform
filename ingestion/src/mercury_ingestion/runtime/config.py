"""Validated production runtime configuration for Mercury ingestion."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

_REQUIRED_VARIABLES = (
    "MERCURY_ENVIRONMENT",
    "MERCURY_PROJECT_ID",
    "MERCURY_REGION",
    "MERCURY_RAW_BUCKET",
    "MERCURY_RAW_DATASET",
    "MERCURY_METADATA_DATASET",
    "MERCURY_SOURCE_INPUT_URI",
    "MERCURY_WORKFLOW_EXECUTION_ID",
)


class RuntimeConfigurationError(ValueError):
    """Raised when production runtime configuration is invalid."""


def _require_gcs_uri(source_uri: str) -> None:
    parsed = urlsplit(source_uri)

    if (
        parsed.scheme != "gs"
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeConfigurationError(
            "MERCURY_SOURCE_INPUT_URI must be a valid gs:// URI"
        )


def _require_bucket_name(bucket_name: str) -> None:
    if (
        "://" in bucket_name
        or "/" in bucket_name
        or "\\" in bucket_name
    ):
        raise RuntimeConfigurationError(
            "MERCURY_RAW_BUCKET must be a bucket name, not a URI"
        )


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Infrastructure and correlation settings for one runtime."""

    environment: str
    project_id: str
    region: str
    raw_bucket: str
    raw_dataset: str
    metadata_dataset: str
    source_input_uri: str
    workflow_execution_id: str

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "RuntimeConfig":
        """Load and validate the production environment contract.

        The supplied mapping exists primarily for deterministic unit
        testing. When omitted, the current process environment is used.
        """

        source = os.environ if environment is None else environment

        missing_or_blank = [
            variable_name
            for variable_name in _REQUIRED_VARIABLES
            if not isinstance(source.get(variable_name), str)
            or not source[variable_name].strip()
        ]

        if missing_or_blank:
            raise RuntimeConfigurationError(
                "missing or blank required runtime configuration: "
                + ", ".join(missing_or_blank)
            )

        values = {
            variable_name: source[variable_name].strip()
            for variable_name in _REQUIRED_VARIABLES
        }

        _require_gcs_uri(values["MERCURY_SOURCE_INPUT_URI"])
        _require_bucket_name(values["MERCURY_RAW_BUCKET"])

        if (
            values["MERCURY_RAW_DATASET"]
            == values["MERCURY_METADATA_DATASET"]
        ):
            raise RuntimeConfigurationError(
                "MERCURY_RAW_DATASET and "
                "MERCURY_METADATA_DATASET must identify "
                "different datasets"
            )

        return cls(
            environment=values["MERCURY_ENVIRONMENT"],
            project_id=values["MERCURY_PROJECT_ID"],
            region=values["MERCURY_REGION"],
            raw_bucket=values["MERCURY_RAW_BUCKET"],
            raw_dataset=values["MERCURY_RAW_DATASET"],
            metadata_dataset=values[
                "MERCURY_METADATA_DATASET"
            ],
            source_input_uri=values[
                "MERCURY_SOURCE_INPUT_URI"
            ],
            workflow_execution_id=values[
                "MERCURY_WORKFLOW_EXECUTION_ID"
            ],
        )