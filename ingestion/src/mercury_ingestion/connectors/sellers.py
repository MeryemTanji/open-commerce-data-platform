"""Mercury's fifth concrete ingestion connector: sellers.

This module implements the local, Olist-backed extraction of Nova
Commerce's marketplace seller source, under the ``marketplace_platform``
source system. Its CSV-specific technical validation and record
counting are inherited from ``BaseCsvConnector`` (per ADR-005); this
module supplies only the source identity, required schema, and domain
documentation for the sellers source.

Dataset grain: one row represents one seller. The expected source-level
key is ``seller_id``. This connector does not validate that key's
uniqueness — key uniqueness, geographic standardization, zip/state
validation, data-quality assertions, and canonical seller modelling are
all downstream Dataform staging concerns, not raw ingestion concerns.

A future API-based seller source (or a different file format) can be
added as a separate connector that reuses Mercury's shared connector
lifecycle unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import final

from mercury_ingestion.common.storage import StorageManager
from mercury_ingestion.connectors.csv_base import BaseCsvConnector

REQUIRED_COLUMNS = frozenset(
    {
        "seller_id",
        "seller_zip_code_prefix",
        "seller_city",
        "seller_state",
    }
)


@final
class SellersConnector(BaseCsvConnector):
    """Ingests Nova Commerce's sellers CSV (Olist-backed, local file).

    Grain: one row per seller. The expected source key is ``seller_id``
    — this connector does not validate its uniqueness.

    This connector performs technical, structural validation only — it
    confirms the file is readable, correctly typed, and has the columns
    downstream layers depend on. It does not judge the quality of the
    business data itself. In particular it does not: reject a blank
    ``seller_state`` or ``seller_city``, validate ``seller_zip_code_prefix``
    formatting, reject blank zip codes, validate uniqueness of
    ``seller_id``, or standardize city/state spelling. Those checks
    belong to later staging/canonical models, not to raw ingestion.
    """

    SOURCE_SYSTEM = "marketplace_platform"
    SOURCE_OBJECT = "sellers"

    def __init__(
        self,
        source_file: Path,
        storage_manager: StorageManager,
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