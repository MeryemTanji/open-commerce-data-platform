"""Mercury's source-delivery contract (ADR-009).

This module defines the abstraction boundary between "where source data
comes from" and "how Mercury ingests it." A ``SourceDeliveryProvider``
makes one batch of already-materialized source files available; it has
no knowledge of connectors, storage backends, GCS, BigQuery, Dataform,
or orchestration. That separation is what lets a future API-based
provider slot in later without redesigning anything downstream.

``SourceDelivery`` and ``SourceDeliveryBatch`` describe only source
delivery facts — a stable source identity, where the file currently
lives, an optional business delivery date, and a record count. Nothing
here encodes GCS configuration, BigQuery schemas, partitioning, or
ingestion metadata; those belong to later stages of the pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from pathlib import Path


def _require_non_blank(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


@dataclass(frozen=True, slots=True)
class SourceDelivery:
    """One source artifact available for ingestion.

    ``delivery_date`` is ``None`` for initial/master-reference deliveries
    (which have no business date) and a concrete ``date`` for daily
    incremental deliveries.
    """

    source_object: str
    path: Path
    delivery_date: date | None
    record_count: int

    def __post_init__(self) -> None:
        _require_non_blank(self.source_object, "source_object")
        if not isinstance(self.path, Path):
            raise TypeError("path must be a pathlib.Path")
        if self.delivery_date is not None and not isinstance(self.delivery_date, date):
            raise TypeError("delivery_date must be a datetime.date or None")
        if self.record_count < 0:
            raise ValueError("record_count cannot be negative")


@dataclass(frozen=True, slots=True)
class SourceDeliveryBatch:
    """A consistent group of source deliveries for one delivery moment.

    ``delivery_date=None`` represents an initial/non-dated batch (e.g.
    master-reference sources); a concrete ``date`` represents one day's
    incremental transactional deliveries. Every contained
    ``SourceDelivery`` must carry exactly that same ``delivery_date``, so
    a batch can never silently mix dated and undated deliveries.

    ``deliveries`` must be non-empty. An empty batch would mean "no
    source was delivered at all," which is a different, more severe
    condition than a delivered source containing zero business records
    -- a valid header-only daily delivery is represented by a
    ``SourceDelivery`` with ``record_count=0``, not by an empty batch.
    """

    deliveries: tuple[SourceDelivery, ...]
    delivery_date: date | None

    def __post_init__(self) -> None:
        if not isinstance(self.deliveries, tuple):
            raise TypeError("deliveries must be a tuple")
        if not self.deliveries:
            raise ValueError(
                "SourceDeliveryBatch requires at least one SourceDelivery; an empty batch means "
                "no source was delivered at all, which is distinct from a delivered source "
                "containing zero business records (record_count=0 remains valid)"
            )
        for delivery in self.deliveries:
            if not isinstance(delivery, SourceDelivery):
                raise TypeError("every item in deliveries must be a SourceDelivery")

        source_objects = [delivery.source_object for delivery in self.deliveries]
        duplicates = {obj for obj in source_objects if source_objects.count(obj) > 1}
        if duplicates:
            raise ValueError(
                f"duplicate source_object values are not allowed in a batch: {', '.join(sorted(duplicates))}"
            )

        if self.delivery_date is not None and not isinstance(self.delivery_date, date):
            raise TypeError("delivery_date must be a datetime.date or None")

        mismatched = [
            delivery.source_object for delivery in self.deliveries if delivery.delivery_date != self.delivery_date
        ]
        if mismatched:
            raise ValueError(
                f"every delivery must carry the batch's delivery_date ({self.delivery_date!r}); "
                f"mismatched: {', '.join(sorted(mismatched))}"
            )


class SourceDeliveryProvider(ABC):
    """Makes source deliveries available, independent of how they arrive.

    Implementations decide how a batch is produced (simulation, a real
    API, a file drop, etc.) but must never depend on connectors, a
    ``StorageManager``, GCS, BigQuery, Dataform, or the orchestration
    layer. This is the extension point a future ``RestApiSourceProvider``
    or similar would implement without requiring any downstream change.
    """

    @abstractmethod
    def get_initial_delivery(self) -> SourceDeliveryBatch:
        """Return the initial/master-reference source delivery batch."""

    @abstractmethod
    def get_daily_delivery(self, delivery_date: date) -> SourceDeliveryBatch:
        """Return one day's incremental transactional delivery batch."""