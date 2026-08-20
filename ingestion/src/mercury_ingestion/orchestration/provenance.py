"""Mercury's provenance domain model (ADR-010 Phase 3C).

Provenance is deliberately separate from replay state: ``ReplayStateRecord``
(see ``state.py``) remains responsible only for orchestration progress
(what ran, when, did it succeed) and gains no new fields here.
Provenance instead answers a narrower, physically-grounded question --
"exactly which immutable Raw artifact was produced, and exactly which
BigQuery load consumed it?" -- durably enough that a later reconciliation
can prove end-to-end physical success without re-executing anything or
reading source/customer content.

Like replay state, provenance is append-only: a new immutable Raw
artifact (e.g. produced by a later recovery attempt) creates a new
``RawArtifactProvenance`` record rather than overwriting the earlier
one, and multiple records may legitimately exist historically for one
``(delivery_date, source_object)``. Nothing here is ever updated or
deleted.

This module has no knowledge of BigQuery, GCS, connectors, or any Google
Cloud client -- ``BigQueryProvenanceStore`` (a separate module) is the
concrete backend that implements the ``ProvenanceStore`` contract
defined here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime


def _require_non_blank(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


def _require_date(value: object, field_name: str) -> None:
    if not isinstance(value, date):
        raise TypeError(f"{field_name} must be a datetime.date")


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative")


@dataclass(frozen=True, slots=True)
class RawArtifactProvenance:
    """Durable technical evidence that one immutable Raw artifact was landed.

    Deliberately limited to control-plane technical facts -- no source
    row values, customer identifiers, or any business content ever
    belongs here. ``ingestion_date`` is recorded as-supplied (whatever
    date the artifact was actually landed under); this record makes no
    assumption about its relationship to ``delivery_date`` (e.g. it does
    not require or encode Mercury's Olist-specific "+1 day" convention
    -- that remains entirely the Olist provider's concern).
    """

    provenance_id: str
    run_id: str
    delivery_date: date
    source_object: str
    ingestion_date: date
    gcs_uri: str
    checksum: str
    file_size_bytes: int
    record_count: int
    recorded_at: datetime

    def __post_init__(self) -> None:
        _require_non_blank(self.provenance_id, "provenance_id")
        _require_non_blank(self.run_id, "run_id")
        _require_date(self.delivery_date, "delivery_date")
        _require_non_blank(self.source_object, "source_object")
        _require_date(self.ingestion_date, "ingestion_date")
        _require_non_blank(self.gcs_uri, "gcs_uri")
        if not self.gcs_uri.startswith("gs://"):
            raise ValueError(f"gcs_uri must start with 'gs://': {self.gcs_uri!r}")
        _require_non_blank(self.checksum, "checksum")
        _require_non_negative_int(self.file_size_bytes, "file_size_bytes")
        _require_non_negative_int(self.record_count, "record_count")
        _require_aware(self.recorded_at, "recorded_at")


@dataclass(frozen=True, slots=True)
class WarehouseLoadProvenance:
    """Durable technical evidence that one BigQuery load consumed a specific Raw artifact.

    ``provenance_id`` links this record to the exact
    ``RawArtifactProvenance`` that was loaded -- a Raw artifact record
    alone cannot prove BigQuery was ever loaded from it, and a warehouse
    load record alone cannot prove which artifact it came from; only the
    pair together constitutes proof of end-to-end physical completion.
    """

    load_id: str
    provenance_id: str
    run_id: str
    delivery_date: date
    source_object: str
    destination: str
    partition_date: date
    output_rows: int
    job_id: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        _require_non_blank(self.load_id, "load_id")
        _require_non_blank(self.provenance_id, "provenance_id")
        _require_non_blank(self.run_id, "run_id")
        _require_date(self.delivery_date, "delivery_date")
        _require_non_blank(self.source_object, "source_object")
        _require_non_blank(self.destination, "destination")
        _require_date(self.partition_date, "partition_date")
        _require_non_negative_int(self.output_rows, "output_rows")
        _require_non_blank(self.job_id, "job_id")
        _require_aware(self.recorded_at, "recorded_at")


class ProvenanceStore(ABC):
    """Persistence contract for append-only artifact/warehouse-load provenance.

    Deliberately narrow and free of any backend-specific concept, just
    like ``ReplayStateStore`` -- concrete implementations own their own
    identifiers, SQL, and schema.
    """

    @abstractmethod
    def append_artifact(self, record: RawArtifactProvenance) -> None:
        """Persist one new Raw artifact provenance record. Never updates or deletes."""

    @abstractmethod
    def append_warehouse_load(self, record: WarehouseLoadProvenance) -> None:
        """Persist one new warehouse-load provenance record. Never updates or deletes."""

    @abstractmethod
    def get_artifact(self, provenance_id: str) -> RawArtifactProvenance | None:
        """Return the Raw artifact provenance record with this exact ID, or None."""

    @abstractmethod
    def get_artifact_history(self, delivery_date: date, source_object: str) -> tuple[RawArtifactProvenance, ...]:
        """Return every Raw artifact provenance record for this pair, oldest first."""

    @abstractmethod
    def get_artifact_by_uri(
        self, delivery_date: date, source_object: str, gcs_uri: str
    ) -> RawArtifactProvenance | None:
        """Return the Raw artifact provenance record matching this exact URI, or None."""

    @abstractmethod
    def get_warehouse_load_history(self, delivery_date: date, source_object: str) -> tuple[WarehouseLoadProvenance, ...]:
        """Return every warehouse-load provenance record for this pair, oldest first."""

    @abstractmethod
    def get_latest_warehouse_load(self, delivery_date: date, source_object: str) -> WarehouseLoadProvenance | None:
        """Return the most recently recorded warehouse-load provenance record for this pair, or None."""