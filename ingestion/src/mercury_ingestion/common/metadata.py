"""Structured metadata produced by every ingestion execution.

This module defines the immutable record that describes a single ingestion
run: what was ingested, where it landed, and how it concluded. It contains
no I/O, storage, or connector behaviour — only the data shape and the rules
that keep it internally consistent.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class IngestionStatus(str, Enum):
    """Lifecycle states of a single ingestion execution."""

    STARTED = "started"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


def _utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _require_non_blank(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class IngestionMetadata:
    """Immutable metadata describing one ingestion execution.

    Instances are created via ``start()`` and transitioned to a terminal
    state via ``mark_success()``, ``mark_failed()``, or ``mark_skipped()``.
    Each transition returns a new instance; the original is never mutated.
    """

    ingestion_id: UUID
    source_system: str
    source_object: str
    source_file_name: str
    started_at: datetime
    completed_at: datetime | None
    landing_path: str | None
    file_size_bytes: int | None
    checksum: str | None
    record_count: int | None
    status: IngestionStatus
    error_message: str | None
    schema_version: str | None

    def __post_init__(self) -> None:
        _require_non_blank(self.source_system, "source_system")
        _require_non_blank(self.source_object, "source_object")
        _require_non_blank(self.source_file_name, "source_file_name")

        if self.schema_version is not None:
            _require_non_blank(self.schema_version, "schema_version")

        _require_aware(self.started_at, "started_at")
        if self.completed_at is not None:
            _require_aware(self.completed_at, "completed_at")
            if self.completed_at < self.started_at:
                raise ValueError("completed_at cannot be earlier than started_at")

        if self.file_size_bytes is not None and self.file_size_bytes < 0:
            raise ValueError("file_size_bytes cannot be negative")
        if self.record_count is not None and self.record_count < 0:
            raise ValueError("record_count cannot be negative")

        if self.status is IngestionStatus.STARTED:
            terminal_fields = {
                "completed_at": self.completed_at,
                "landing_path": self.landing_path,
                "file_size_bytes": self.file_size_bytes,
                "checksum": self.checksum,
                "record_count": self.record_count,
                "error_message": self.error_message,
            }
            present = [name for name, value in terminal_fields.items() if value is not None]
            if present:
                raise ValueError(
                    f"started metadata must not contain terminal-state fields: "
                    f"{', '.join(present)}"
                )

        if self.status is IngestionStatus.SUCCESS:
            required = {
                "completed_at": self.completed_at,
                "landing_path": self.landing_path,
                "file_size_bytes": self.file_size_bytes,
                "checksum": self.checksum,
                "record_count": self.record_count,
            }
            missing = [name for name, value in required.items() if value is None]
            if missing:
                raise ValueError(
                    f"successful metadata is missing required fields: {', '.join(missing)}"
                )
            if not self.landing_path.strip():
                raise ValueError("successful metadata requires a non-blank landing_path")
            if not self.checksum.strip():
                raise ValueError("successful metadata requires a non-blank checksum")

        if self.status in (IngestionStatus.FAILED, IngestionStatus.SKIPPED):
            if self.completed_at is None:
                raise ValueError(f"{self.status.value} metadata requires completed_at")
            if self.error_message is None or not self.error_message.strip():
                raise ValueError(
                    f"{self.status.value} metadata requires a non-blank error_message"
                )

    @classmethod
    def start(
        cls,
        source_system: str,
        source_object: str,
        source_file_name: str,
        schema_version: str | None = None,
    ) -> IngestionMetadata:
        """Create a new metadata record in the ``started`` state."""
        return cls(
            ingestion_id=uuid4(),
            source_system=source_system,
            source_object=source_object,
            source_file_name=source_file_name,
            started_at=_utc_now(),
            completed_at=None,
            landing_path=None,
            file_size_bytes=None,
            checksum=None,
            record_count=None,
            status=IngestionStatus.STARTED,
            error_message=None,
            schema_version=schema_version,
        )

    def _require_started(self) -> None:
        if self.status is not IngestionStatus.STARTED:
            raise ValueError(
                f"can only transition from status 'started', current status is "
                f"'{self.status.value}'"
            )

    def mark_success(
        self,
        *,
        landing_path: str,
        file_size_bytes: int,
        checksum: str,
        record_count: int,
        completed_at: datetime | None = None,
    ) -> IngestionMetadata:
        """Return a new instance recorded as ``success``."""
        self._require_started()
        return replace(
            self,
            status=IngestionStatus.SUCCESS,
            completed_at=completed_at or _utc_now(),
            landing_path=landing_path,
            file_size_bytes=file_size_bytes,
            checksum=checksum,
            record_count=record_count,
        )

    def mark_failed(
        self,
        error_message: str,
        *,
        completed_at: datetime | None = None,
    ) -> IngestionMetadata:
        """Return a new instance recorded as ``failed``."""
        self._require_started()
        return replace(
            self,
            status=IngestionStatus.FAILED,
            completed_at=completed_at or _utc_now(),
            error_message=error_message,
        )

    def mark_skipped(
        self,
        reason: str,
        *,
        completed_at: datetime | None = None,
    ) -> IngestionMetadata:
        """Return a new instance recorded as ``skipped``."""
        self._require_started()
        return replace(
            self,
            status=IngestionStatus.SKIPPED,
            completed_at=completed_at or _utc_now(),
            error_message=reason,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this metadata."""
        return {
            "ingestion_id": str(self.ingestion_id),
            "source_system": self.source_system,
            "source_object": self.source_object,
            "source_file_name": self.source_file_name,
            "started_at": self.started_at.astimezone(timezone.utc).isoformat(),
            "completed_at": (
                self.completed_at.astimezone(timezone.utc).isoformat()
                if self.completed_at is not None
                else None
            ),
            "landing_path": self.landing_path,
            "file_size_bytes": self.file_size_bytes,
            "checksum": self.checksum,
            "record_count": self.record_count,
            "status": self.status.value,
            "error_message": self.error_message,
            "schema_version": self.schema_version,
        }