"""Orchestration layer for running one or more Mercury connectors.

``BaseConnector`` owns the ingestion lifecycle for a single source: it
knows how to validate, count, and land that source's data, and it always
returns terminal metadata rather than raising for ordinary ingestion
problems. ``IngestionRunner`` sits one level above that — it coordinates
running several already-configured connectors in a batch and aggregates
their outcomes into a single, stable result. It contains no source-specific
logic of its own; it only calls ``connector.run()`` and summarizes what
came back.

The resulting exit code is intended for future callers such as a Cloud Run
Job, a scheduler, or a CI/CD pipeline step, which typically only have a
process exit status to make a pass/fail decision on.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import Enum

from mercury_ingestion.common.metadata import IngestionStatus
from mercury_ingestion.connectors.base import BaseConnector, ConnectorRunResult


class RunnerStatus(str, Enum):
    """Overall outcome of running a batch of connectors.

    - ``SUCCESS``: every connector succeeded or was skipped (no failures).
    - ``PARTIAL_FAILURE``: at least one connector succeeded or was
      skipped, and at least one failed.
    - ``FAILED``: every connector failed.
    """

    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"


def _derive_status(results: tuple[ConnectorRunResult, ...]) -> RunnerStatus:
    """Derive the batch-level status from individual connector outcomes."""
    failed_count = sum(1 for result in results if result.metadata.status is IngestionStatus.FAILED)
    if failed_count == 0:
        return RunnerStatus.SUCCESS
    if failed_count == len(results):
        return RunnerStatus.FAILED
    return RunnerStatus.PARTIAL_FAILURE


_EXIT_CODES: dict[RunnerStatus, int] = {
    RunnerStatus.SUCCESS: 0,
    RunnerStatus.PARTIAL_FAILURE: 1,
    RunnerStatus.FAILED: 2,
}


@dataclass(frozen=True, slots=True)
class RunnerResult:
    """Aggregated outcome of a connector batch run.

    Deliberately narrow: individual connector detail (paths, checksums,
    record counts, error messages) already lives inside each contained
    ``ConnectorRunResult.metadata``, so this type only summarizes counts
    and an overall status rather than duplicating that detail.
    """

    results: tuple[ConnectorRunResult, ...]
    status: RunnerStatus

    def __post_init__(self) -> None:
        if not self.results:
            raise ValueError("RunnerResult requires at least one result")

        expected_status = _derive_status(self.results)
        if self.status is not expected_status:
            raise ValueError(
                f"status '{self.status.value}' is inconsistent with contained "
                f"connector metadata; expected '{expected_status.value}'"
            )

    @property
    def succeeded_count(self) -> int:
        return sum(1 for result in self.results if result.metadata.status is IngestionStatus.SUCCESS)

    @property
    def failed_count(self) -> int:
        return sum(1 for result in self.results if result.metadata.status is IngestionStatus.FAILED)

    @property
    def skipped_count(self) -> int:
        return sum(1 for result in self.results if result.metadata.status is IngestionStatus.SKIPPED)

    @property
    def total_count(self) -> int:
        return len(self.results)

    @property
    def exit_code(self) -> int:
        return _EXIT_CODES[self.status]


class IngestionRunner:
    """Coordinates running a fixed batch of already-configured connectors.

    The runner does not construct connectors, inspect source data, create
    metadata, or write raw files itself — it only calls each connector's
    ``run()`` method, in order, and aggregates the results. Constructing a
    runner has no side effects; connectors are executed only when
    ``run_all()`` is called.
    """

    def __init__(self, connectors: Iterable[BaseConnector]) -> None:
        connectors_tuple = tuple(connectors)
        if not connectors_tuple:
            raise ValueError("connectors cannot be empty")
        for connector in connectors_tuple:
            if not isinstance(connector, BaseConnector):
                raise TypeError(
                    f"all connectors must be BaseConnector instances, got {type(connector).__name__}"
                )

        self.connectors = connectors_tuple

    def run_all(self, ingestion_date: date | None = None) -> RunnerResult:
        """Run every connector once, in order, and aggregate the outcomes.

        ``BaseConnector.run()`` already converts ordinary ingestion
        problems into FAILED metadata, so this method does not catch
        exceptions on its own behalf. If a connector implementation
        raises an ordinary ``Exception`` directly instead of returning a
        ``ConnectorRunResult``, that is a programming-contract violation
        rather than a normal ingestion failure, and it is allowed to
        propagate unchanged. ``BaseException`` subclasses such as
        ``KeyboardInterrupt`` and ``SystemExit`` are never caught here
        either.

        The same ``ingestion_date`` is passed to every connector; this is
        intentional so a single batch run lands all sources under a
        consistent partition.
        """
        results = tuple(
            connector.run(ingestion_date=ingestion_date) for connector in self.connectors
        )
        status = _derive_status(results)
        return RunnerResult(results=results, status=status)


def run_connectors(
    connectors: Iterable[BaseConnector],
    ingestion_date: date | None = None,
) -> RunnerResult:
    """Convenience function: build an ``IngestionRunner`` and run it once."""
    return IngestionRunner(connectors).run_all(ingestion_date=ingestion_date)