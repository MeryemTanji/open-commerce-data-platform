"""Shared CSV technical validation and counting for Mercury connectors.

Per ADR-005, this module answers exactly one question: "how does Mercury
technically validate and count a CSV source?" It implements the two
hooks ``BaseConnector`` requires — ``validate_source()`` and
``count_records()`` — with the CSV-specific behavior that was proven
identical across all eight concrete Olist connectors before this
abstraction was introduced.

``BaseCsvConnector`` deliberately does not know anything about what a
row *means* for a given source: no source identity, no dataset grain, no
natural-key semantics, no business-quality boundary. Those all remain the
responsibility of concrete connectors, which supply their fixed source
identity and required-column contract explicitly rather than having it
discovered implicitly from class attributes.
"""

from __future__ import annotations

import csv
from pathlib import Path

from mercury_ingestion.common.storage import LocalStorageManager
from mercury_ingestion.connectors.base import BaseConnector

_ENCODING = "utf-8-sig"


class BaseCsvConnector(BaseConnector):
    """CSV-format base connector: shared technical validation and counting.

    Concrete CSV connectors inherit from this class and supply their own
    fixed source identity, required-column contract, and domain
    documentation. This class contains no source-specific knowledge —
    only the CSV mechanics common to every connector built on top of it.
    """

    def __init__(
        self,
        source_file: Path,
        source_system: str,
        source_object: str,
        required_columns: frozenset[str],
        storage_manager: LocalStorageManager,
        schema_version: str | None = "1.0",
    ) -> None:
        super().__init__(
            source_file=source_file,
            source_system=source_system,
            source_object=source_object,
            storage_manager=storage_manager,
            schema_version=schema_version,
        )
        self.required_columns = frozenset(required_columns)

    def validate_source(self) -> None:
        """Validate technical CSV structure only; raise on missing/malformed input.

        Raises:
            FileNotFoundError: if the source file does not exist.
            ValueError: if the source is not a regular file, is not a
                ``.csv`` file, is empty, has no header, or is missing
                required columns.
            UnicodeDecodeError: propagates unchanged if the file cannot be
                decoded as UTF-8; ``BaseConnector`` converts it to FAILED
                metadata like any other exception.
        """
        if not self.source_file.exists():
            raise FileNotFoundError(f"source_file does not exist: {self.source_file}")
        if not self.source_file.is_file():
            raise ValueError(f"source_file is not a regular file: {self.source_file}")
        if self.source_file.suffix.lower() != ".csv":
            raise ValueError(f"source_file must have a .csv extension: {self.source_file}")
        if self.source_file.stat().st_size == 0:
            raise ValueError(f"source_file is empty: {self.source_file}")

        with self.source_file.open(encoding=_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames
            if not fieldnames:
                raise ValueError(f"source_file has no header row: {self.source_file}")

            missing = self.required_columns - set(fieldnames)
            if missing:
                raise ValueError(
                    "source_file is missing required columns: "
                    f"{', '.join(sorted(missing))}"
                )

    def count_records(self) -> int:
        """Return the number of data rows in the CSV, excluding the header.

        ``csv.DictReader`` skips blank physical lines on its own, so they
        are not counted as records, and resolves multiline quoted fields
        into a single logical row per Python CSV semantics. Duplicate
        rows are never deduplicated here.
        """
        with self.source_file.open(encoding=_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            return sum(1 for _ in reader)