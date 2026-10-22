"""Production command-line entry point for Mercury ingestion.

The adapter in this module is intentionally thin. It validates the
requested unit of work, loads production runtime configuration,
materializes governed Olist source input into ephemeral storage,
constructs the existing replay runner, executes one logical delivery
date, and emits one PII-safe structured terminal summary.

All ingestion, simulation, Raw landing, warehouse loading, replay-state,
and provenance behavior remains owned by the existing Mercury
components composed here.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from mercury_ingestion.orchestration.replay import (
    HistoricalReplayError,
)
from mercury_ingestion.runtime.config import (
    RuntimeConfig,
    RuntimeConfigurationError,
)
from mercury_ingestion.runtime.gcs_source_materializer import (
    GCSSourceMaterializer,
)
from mercury_ingestion.runtime.olist_runner_factory import (
    build_olist_replay_runner,
)
from mercury_ingestion.simulation.olist import SOURCE_FILENAMES

EXIT_SUCCESS = 0
EXIT_INCOMPLETE = 1
EXIT_EXECUTION_FAILURE = 2
EXIT_INVALID_REQUEST = 64

_SAFE_REPLAY_FAILURE_CATEGORIES = frozenset(
    {
        "batch_membership",
        "date_completion",
        "ingestion",
        "provenance",
        "replay_state",
        "source_delivery",
        "warehouse",
    }
)


class CommandInputError(ValueError):
    """Raised when production command syntax or input is invalid."""


class _ProductionArgumentParser(argparse.ArgumentParser):
    """Argument parser that lets ``main`` own governed failure output."""

    def error(self, message: str) -> None:
        raise CommandInputError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _ProductionArgumentParser(
        prog="python -m mercury_ingestion.cli",
        description="Execute one Mercury production ingestion date.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    run_day_parser = subparsers.add_parser(
        "run-day",
        help="Execute one logical delivery date.",
    )
    run_day_parser.add_argument(
        "--delivery-date",
        required=True,
        help="Logical delivery date in YYYY-MM-DD format.",
    )

    return parser


def _parse_delivery_date(raw_value: str) -> date:
    try:
        parsed = date.fromisoformat(raw_value)
    except (TypeError, ValueError) as exc:
        raise CommandInputError(
            "delivery date must be a valid date in YYYY-MM-DD format"
        ) from exc

    if parsed.isoformat() != raw_value:
        raise CommandInputError(
            "delivery date must use canonical YYYY-MM-DD format"
        )

    return parsed


def _empty_summary(
    *,
    delivery_date: date | None,
    final_status: str,
    failure_category: str | None,
    config: RuntimeConfig | None = None,
) -> dict[str, Any]:
    return {
        "workflow_execution_id": (
            config.workflow_execution_id
            if config is not None
            else None
        ),
        "ingestion_run_id": None,
        "environment": (
            config.environment if config is not None else None
        ),
        "delivery_date": (
            delivery_date.isoformat()
            if delivery_date is not None
            else None
        ),
        "source_count": 0,
        "completed_source_count": 0,
        "failed_source_count": 0,
        "final_status": final_status,
        "failure_category": failure_category,
    }


def _emit_summary(summary: dict[str, Any]) -> None:
    """Write exactly one compact structured terminal summary."""

    print(
        json.dumps(
            summary,
            sort_keys=True,
            separators=(",", ":"),
        ),
        flush=True,
    )


def _safe_replay_category(stage: object) -> str:
    if (
        isinstance(stage, str)
        and stage in _SAFE_REPLAY_FAILURE_CATEGORIES
    ):
        return stage

    return "replay_failure"


def _successful_summary(
    *,
    config: RuntimeConfig,
    delivery_date: date,
    result: Any,
) -> dict[str, Any]:
    source_count = len(result.source_batch.deliveries)

    # A normally returned day result means the date is durably complete.
    # This deliberately does not infer failure from this invocation's
    # warehouse_results: an idempotent replay may encounter immutable
    # artifacts that already succeeded in an earlier invocation while
    # durable completion correctly remains true.
    return {
        "workflow_execution_id": config.workflow_execution_id,
        "ingestion_run_id": result.run_id,
        "environment": config.environment,
        "delivery_date": delivery_date.isoformat(),
        "source_count": source_count,
        "completed_source_count": source_count,
        "failed_source_count": 0,
        "final_status": "success",
        "failure_category": None,
    }


def _incomplete_summary(
    *,
    config: RuntimeConfig,
    delivery_date: date,
    error: HistoricalReplayError,
) -> dict[str, Any]:
    partial_result = error.partial_day_result

    if partial_result is None:
        raise ValueError(
            "an incomplete summary requires a partial day result"
        )

    source_count = len(partial_result.source_batch.deliveries)
    completed_source_count = len(partial_result.warehouse_results)

    return {
        "workflow_execution_id": config.workflow_execution_id,
        "ingestion_run_id": partial_result.run_id,
        "environment": config.environment,
        "delivery_date": delivery_date.isoformat(),
        "source_count": source_count,
        "completed_source_count": completed_source_count,
        "failed_source_count": (
            source_count - completed_source_count
        ),
        "final_status": "incomplete",
        "failure_category": _safe_replay_category(error.stage),
    }


def _execute_run_day(
    *,
    config: RuntimeConfig,
    delivery_date: date,
) -> Any:
    with TemporaryDirectory(prefix="mercury-ingestion-") as workspace:
        workspace_path = Path(workspace)
        source_directory = workspace_path / "source"
        simulation_directory = workspace_path / "simulation"

        materializer = GCSSourceMaterializer(
            source_uri=config.source_input_uri,
            required_filenames=tuple(SOURCE_FILENAMES.values()),
            project_id=config.project_id,
        )
        materializer.materialize(source_directory)

        runner = build_olist_replay_runner(
            source_directory=source_directory,
            simulation_directory=simulation_directory,
            project_id=config.project_id,
            raw_bucket_name=config.raw_bucket,
            raw_dataset_id=config.raw_dataset,
            metadata_dataset_id=config.metadata_dataset,
            location=config.region,
        )

        return runner.run_day(delivery_date)


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the requested production command and return its exit code."""

    arguments = list(sys.argv[1:] if argv is None else argv)

    try:
        namespace = _build_parser().parse_args(arguments)

        if namespace.command != "run-day":
            raise CommandInputError("unsupported command")

        delivery_date = _parse_delivery_date(namespace.delivery_date)

    except CommandInputError:
        _emit_summary(
            _empty_summary(
                delivery_date=None,
                final_status="invalid_request",
                failure_category="command_input",
            )
        )
        return EXIT_INVALID_REQUEST

    try:
        config = RuntimeConfig.from_environment()
    except RuntimeConfigurationError:
        _emit_summary(
            _empty_summary(
                delivery_date=delivery_date,
                final_status="invalid_request",
                failure_category="runtime_configuration",
            )
        )
        return EXIT_INVALID_REQUEST

    try:
        result = _execute_run_day(
            config=config,
            delivery_date=delivery_date,
        )

    except HistoricalReplayError as exc:
        if exc.partial_day_result is not None:
            _emit_summary(
                _incomplete_summary(
                    config=config,
                    delivery_date=delivery_date,
                    error=exc,
                )
            )
            return EXIT_INCOMPLETE

        summary = _empty_summary(
            delivery_date=delivery_date,
            final_status="failed",
            failure_category=_safe_replay_category(exc.stage),
            config=config,
        )
        _emit_summary(summary)
        return EXIT_EXECUTION_FAILURE

    except FileNotFoundError:
        _emit_summary(
            _empty_summary(
                delivery_date=delivery_date,
                final_status="failed",
                failure_category="source_materialization",
                config=config,
            )
        )
        return EXIT_EXECUTION_FAILURE

    except Exception:
        _emit_summary(
            _empty_summary(
                delivery_date=delivery_date,
                final_status="failed",
                failure_category="runtime_execution",
                config=config,
            )
        )
        return EXIT_EXECUTION_FAILURE

    _emit_summary(
        _successful_summary(
            config=config,
            delivery_date=delivery_date,
            result=result,
        )
    )
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
