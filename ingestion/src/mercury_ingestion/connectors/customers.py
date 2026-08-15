"""Mercury's first concrete ingestion connector: customers.

This module implements the local, Olist-backed extraction of Nova
Commerce's customer operational system. Its CSV-specific technical
validation and record counting are inherited from ``BaseCsvConnector``
(per ADR-005); this module supplies only the source identity, required
schema, and domain documentation for the customer source.

A future API-based customer source (or a different file format) can be
added as a separate connector that reuses Mercury's shared connector
lifecycle unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import final

from mercury_ingestion.common.storage import LocalStorageManager
from mercury_ingestion.connectors.csv_base import BaseCsvConnector

REQUIRED_COLUMNS = frozenset(
    {
        "customer_id",
        "customer_unique_id",
        "customer_zip_code_prefix",
        "customer_city",
        "customer_state",
    }
)


@final
class CustomerConnector(BaseCsvConnector):
    """Ingests Nova Commerce's customer CSV (Olist-backed, local file).

    This connector performs technical, structural validation only — it
    confirms the file is readable, correctly typed, and has the columns
    downstream layers depend on. It does not judge the quality of the
    business data itself (e.g. it does not check for duplicate customers,
    standardize city/state spelling, or validate zip code formats). Those
    concerns belong to later staging/canonical transformations, not to
    raw ingestion.
    """

    SOURCE_SYSTEM = "customer_platform"
    SOURCE_OBJECT = "customers"

    def __init__(
        self,
        source_file: Path,
        storage_manager: LocalStorageManager,
        schema_version: str | None = "1.0",
    ) -> None:
        super().__init__(
            source_file=source_file,
            source_system=self.SOURCE_SYSTEM,
            source_object=self.SOURCE_OBJECT,
            required_columns=REQUIRED_COLUMNS,
            storage_manager=storage_manager,
            schema_version=schema_version,
        )