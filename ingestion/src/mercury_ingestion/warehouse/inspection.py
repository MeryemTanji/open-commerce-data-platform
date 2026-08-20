"""Mercury's generic read-only warehouse inspection contract (ADR-010 Phase 3C).

Deliberately separate from ``BigQueryRawLoader`` (load-only: it never
reads back what it loaded). This module answers one narrow question --
"does this exact BigQuery transactional partition exist, and how many
rows does it contain?" -- using metadata only, never a query over Raw
business columns.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


def _require_non_blank(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


@dataclass(frozen=True, slots=True)
class WarehousePartitionObservation:
    """What a read-only inspection of one BigQuery transactional partition observed.

    ``present=False`` means the partition does not exist -- in that case
    ``row_count`` is always ``None``. ``destination`` always reports the
    exact table/partition identifier that was inspected, regardless of
    whether it was found, so a caller can compare it against provenance
    without a second lookup.
    """

    source_object: str
    partition_date: date
    destination: str
    present: bool
    row_count: int | None

    def __post_init__(self) -> None:
        _require_non_blank(self.source_object, "source_object")
        if not isinstance(self.partition_date, date):
            raise TypeError("partition_date must be a datetime.date")
        _require_non_blank(self.destination, "destination")
        if not isinstance(self.present, bool):
            raise TypeError("present must be a bool")
        if self.row_count is not None:
            if not isinstance(self.row_count, int) or isinstance(self.row_count, bool):
                raise TypeError("row_count must be an int or None")
            if self.row_count < 0:
                raise ValueError("row_count cannot be negative")
        if not self.present and self.row_count is not None:
            raise ValueError("an absent partition (present=False) cannot carry a row_count")


class WarehouseInspector(ABC):
    """Read-only capability contract: inspect one BigQuery transactional partition.

    Implementations must read partition-level metadata only (e.g.
    ``INFORMATION_SCHEMA.PARTITIONS``) -- never Raw business columns,
    and never issue any write, table-creation, or dataset-creation
    operation. A "partition not found" condition must be translated into
    ``WarehousePartitionObservation(present=False, ...)`` rather than
    propagating as an exception; any other backend failure (permission
    denied, service unavailable, ...) is a genuine inspection-
    infrastructure failure and must propagate unchanged.
    """

    @abstractmethod
    def inspect_partition(self, source_object: str, partition_date: date) -> WarehousePartitionObservation:
        """Return what is currently observable about this source's partition for this date."""