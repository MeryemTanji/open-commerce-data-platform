"""Base connector lifecycle shared by every Mercury ingestion connector.

This module defines the Template Method that every concrete connector
follows: create started metadata, validate the source, count its records,
land the file unchanged, and record success or failure. It contains no
source-format-specific (CSV, API, etc.) or business logic — that belongs
in concrete subclasses.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from mercury_ingestion.common.metadata import IngestionMetadata, IngestionStatus
from mercury_ingestion.common.storage import LocalStorageManager


def _require_non_blank(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


def _utc_today() -> date:
    """Return the current UTC calendar date."""
    return datetime.now(timezone.utc).date()


@dataclass(frozen=True, slots=True)
class ConnectorRunResult:
    """Outcome of a single connector run.

    Deliberately narrow: all technical detail about a successful landing
    (path, checksum, size, record count) already lives inside the
    completed ``metadata``, so this type only wraps that metadata rather
    than duplicating fields.
    """

    metadata: IngestionMetadata

    def __post_init__(self) -> None:
        terminal_statuses = (
            IngestionStatus.SUCCESS,
            IngestionStatus.FAILED,
            IngestionStatus.SKIPPED,
        )
        if self.metadata.status not in terminal_statuses:
            raise ValueError(
                "ConnectorRunResult requires terminal metadata (success, failed, "
                f"or skipped), got '{self.metadata.status.value}'"
            )


class BaseConnector(ABC):
    """Template Method base class for Mercury ingestion connectors.

    Subclasses implement only the two source-specific hooks,
    ``validate_source()`` and ``count_records()``. Everything else —
    metadata lifecycle, landing the file, and success/failure handling —
    is handled once here so every connector behaves consistently.
    """

    def __init__(
        self,
        source_file: Path,
        source_system: str,
        source_object: str,
        storage_manager: LocalStorageManager,
        schema_version: str | None = None,
    ) -> None:
        if not isinstance(source_file, Path):
            raise TypeError("source_file must be a pathlib.Path")
        if not isinstance(storage_manager, LocalStorageManager):
            raise TypeError("storage_manager must be a LocalStorageManager")

        _require_non_blank(source_system, "source_system")
        _require_non_blank(source_object, "source_object")
        _require_non_blank(source_file.name, "source_file.name")

        self.source_file = source_file
        self.source_system = source_system
        self.source_object = source_object
        self.storage_manager = storage_manager
        self.schema_version = schema_version

    def run(self, ingestion_date: date | None = None) -> ConnectorRunResult:
        """Execute the standard ingestion lifecycle.

        Order of operations: ``validate_source()`` -> ``count_records()``
        -> ``storage_manager.save_file()`` -> mark the metadata as success.

        Version 1 design decision: any ``Exception`` raised after metadata
        has started is caught here and converted into FAILED metadata,
        rather than propagating. This keeps the contract of ``run()``
        simple for callers (it always returns a ``ConnectorRunResult``,
        never raises for source-level problems) and matches how this
        result will eventually be persisted and reported on. This is a
        deliberate trade-off for version 1 and may be revisited once
        proper logging and orchestration-level error handling exist.

        ``BaseException`` is intentionally not caught: ``KeyboardInterrupt``
        and ``SystemExit`` must always propagate so the process can still
        be interrupted or exited normally.
        """
        metadata = IngestionMetadata.start(
            source_system=self.source_system,
            source_object=self.source_object,
            source_file_name=self.source_file.name,
            schema_version=self.schema_version,
        )
        resolved_ingestion_date = ingestion_date if ingestion_date is not None else _utc_today()

        try:
            self.validate_source()
            record_count = self._validated_record_count()

            storage_result = self.storage_manager.save_file(
                source_file=self.source_file,
                source_system=self.source_system,
                source_object=self.source_object,
                ingestion_date=resolved_ingestion_date,
            )

            metadata = metadata.mark_success(
                landing_path=storage_result.landing_path,
                file_size_bytes=storage_result.file_size_bytes,
                checksum=storage_result.checksum,
                record_count=record_count,
            )
        except Exception as exc:  # noqa: BLE001 - intentionally broad, see docstring
            metadata = metadata.mark_failed(str(exc))

        return ConnectorRunResult(metadata=metadata)

    def _validated_record_count(self) -> int:
        """Call ``count_records()`` and enforce its return-type contract."""
        record_count = self.count_records()
        if isinstance(record_count, bool) or not isinstance(record_count, int):
            raise TypeError(
                f"count_records() must return an int, got {type(record_count).__name__}"
            )
        if record_count < 0:
            raise ValueError("count_records() must return a non-negative value")
        return record_count

    @abstractmethod
    def validate_source(self) -> None:
        """Perform technical source-level validation.

        Must not land files, create metadata, apply business
        transformations, or modify the source file.
        """

    @abstractmethod
    def count_records(self) -> int:
        """Return the number of logical source records.

        Must not land files, create metadata, apply business
        transformations, or modify the source file. The source may be
        read more than once in version 1; this is not yet optimized.
        """