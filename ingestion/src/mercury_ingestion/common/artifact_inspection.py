"""Mercury's generic read-only Raw artifact inspection contract (ADR-010 Phase 3C).

This module exists to answer one narrow question -- "does this exact
immutable Raw artifact still exist, and what does its technical metadata
say?" -- without ever reading the artifact's contents. It is deliberately
separate from ``StorageManager`` (write-only: lands one artifact) and
from any BigQuery concept; nothing here knows about GCS clients,
BigQuery, or connectors.

``RawArtifactInspector`` implementations must never download an object,
read its contents, generate a signed or public URL, change its ACLs, or
mutate it in any way. Only technical metadata (existence, size, and
Mercury's own ``mercury_sha256`` custom metadata) may be read.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


def _require_non_blank(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


@dataclass(frozen=True, slots=True)
class RawArtifactObservation:
    """What a read-only inspection of one GCS URI actually observed.

    ``present=False`` means the object does not exist at ``gcs_uri`` --
    in that case ``checksum``/``file_size_bytes`` are always ``None``.
    ``present=True`` with ``checksum=None`` means the object exists but
    has no ``mercury_sha256`` custom metadata (e.g. an artifact created
    before this metadata contract existed) -- that is a legitimate,
    distinct observation, not an error.
    """

    gcs_uri: str
    present: bool
    checksum: str | None
    file_size_bytes: int | None

    def __post_init__(self) -> None:
        _require_non_blank(self.gcs_uri, "gcs_uri")
        if not self.gcs_uri.startswith("gs://"):
            raise ValueError(f"gcs_uri must start with 'gs://': {self.gcs_uri!r}")
        if not isinstance(self.present, bool):
            raise TypeError("present must be a bool")
        if self.checksum is not None and not isinstance(self.checksum, str):
            raise TypeError("checksum must be a string or None")
        if self.checksum is not None and not self.checksum.strip():
            raise ValueError("checksum cannot be blank when present")
        if self.file_size_bytes is not None:
            if not isinstance(self.file_size_bytes, int) or isinstance(self.file_size_bytes, bool):
                raise TypeError("file_size_bytes must be an int or None")
            if self.file_size_bytes < 0:
                raise ValueError("file_size_bytes cannot be negative")
        if not self.present and (self.checksum is not None or self.file_size_bytes is not None):
            raise ValueError("an absent artifact (present=False) cannot carry checksum/file_size_bytes")


class RawArtifactInspector(ABC):
    """Read-only capability contract: inspect one Raw artifact's technical metadata.

    Implementations must validate that ``gcs_uri`` is a well-formed
    ``gs://`` URI and must never inspect an arbitrary, malformed
    location. A "not found" condition from the backend must be
    translated into ``RawArtifactObservation(present=False, ...)``
    rather than propagating as an exception; any other backend failure
    (permission denied, service unavailable, ...) is a genuine
    inspection-infrastructure failure and must propagate unchanged, so
    the caller can distinguish "we know it's missing" from "we could not
    find out."
    """

    @abstractmethod
    def inspect(self, gcs_uri: str) -> RawArtifactObservation:
        """Return what is currently observable about the artifact at ``gcs_uri``."""