"""Mercury's third concrete ingestion connector: order items.

This module implements the local, Olist-backed extraction of Nova
Commerce's order-line-item data, which belongs to the same
``order_platform`` source system as the orders source. Its CSV-specific
technical validation and record counting are inherited from
``BaseCsvConnector`` (per ADR-005); this module supplies only the source
identity, required schema, and domain documentation for the order-items
source.

Dataset grain: one row represents one item within one order. The
expected source-level composite key is ``(order_id, order_item_id)``.
This connector does not validate that key's uniqueness — composite-key
uniqueness, type casting, timestamp validation, price/freight assertions,
referential integrity to orders/products/sellers, and deduplication (if
required) are all downstream Dataform staging concerns, not raw
ingestion concerns.

A future API-based order-item source (or a different file format) can be
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
        "order_item_id",
        "product_id",
        "seller_id",
        "shipping_limit_date",
        "price",
        "freight_value",
    }
)


@final
class OrderItemsConnector(BaseCsvConnector):
    """Ingests Nova Commerce's order-items CSV (Olist-backed, local file).

    Grain: one row per item within one order. The expected source key is
    ``(order_id, order_item_id)`` — a given ``order_id`` is expected to
    repeat across multiple rows, once per item in that order.

    This connector performs technical, structural validation only — it
    confirms the file is readable, correctly typed, and has the columns
    downstream layers depend on. It does not judge the quality of the
    business data itself. In particular it does not: reject negative
    ``price`` or ``freight_value`` values, require ``shipping_limit_date``
    to be populated or well-formed, validate uniqueness of
    ``(order_id, order_item_id)``, or check that ``product_id``,
    ``seller_id``, or ``order_id`` exist in their respective sources.
    Those checks belong to later staging/canonical transformations, not
    to raw ingestion.
    """

    SOURCE_SYSTEM = "order_platform"
    SOURCE_OBJECT = "order_items"

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