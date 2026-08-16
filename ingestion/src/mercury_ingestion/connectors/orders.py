"""Mercury's second concrete ingestion connector: orders.

This module implements the local, Olist-backed extraction of Nova
Commerce's order-management operational system. Its CSV-specific
technical validation and record counting are inherited from
``BaseCsvConnector`` (per ADR-005); this module supplies only the source
identity, required schema, and domain documentation for the orders
source.

Deduplication, timestamp parsing, delivery-consistency checks, business
rules, and referential integrity against the customer source are all
downstream Dataform staging concerns, not raw ingestion concerns.

A future API-based order source (or a different file format) can be
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
        "order_id",
        "customer_id",
        "order_status",
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    }
)


@final
class OrdersConnector(BaseCsvConnector):
    """Ingests Nova Commerce's orders CSV (Olist-backed, local file).

    This connector performs technical, structural validation only — it
    confirms the file is readable, correctly typed, and has the columns
    downstream layers depend on. It does not judge the quality of the
    business data itself. In particular it does not: reject unexpected
    ``order_status`` values, require delivery or approval dates to be
    populated, validate timestamp consistency, deduplicate ``order_id``
    values, or check that ``customer_id`` exists in the customer source.
    Those checks belong to later staging/canonical transformations, not
    to raw ingestion.
    """

    SOURCE_SYSTEM = "order_platform"
    SOURCE_OBJECT = "orders"

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