"""Mercury's third concrete ingestion connector: order items.

This module implements the local, Olist-backed extraction of Nova
Commerce's order-line-item data, which belongs to the same
``order_platform`` source system as the orders source. It validates the
technical structure of the source CSV (file type, encoding, required
columns) and counts logical records; everything else in the ingestion
lifecycle — metadata, immutable landing, success/failure handling — is
provided by ``BaseConnector``.

Dataset grain: one row represents one item within one order. The
expected source-level composite key is ``(order_id, order_item_id)``.
This connector does not validate that key's uniqueness — composite-key
uniqueness, type casting, timestamp validation, price/freight assertions,
referential integrity to orders/products/sellers, and deduplication (if
required) are all downstream Dataform staging concerns, not raw
ingestion concerns.

A future API-based order-item source (or a different file format) can be
added as a separate connector that implements the same two hooks while
reusing Mercury's shared connector lifecycle unchanged.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import final

from mercury_ingestion.common.storage import LocalStorageManager
from mercury_ingestion.connectors.base import BaseConnector

_ENCODING = "utf-8-sig"

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
class OrderItemsConnector(BaseConnector):
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
        storage_manager: LocalStorageManager,
        schema_version: str | None = "1.0",
    ) -> None:
        super().__init__(
            source_file=source_file,
            source_system=self.SOURCE_SYSTEM,
            source_object=self.SOURCE_OBJECT,
            storage_manager=storage_manager,
            schema_version=schema_version,
        )

    def validate_source(self) -> None:
        """Validate technical structure only; raise on missing/malformed input.

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

            missing = REQUIRED_COLUMNS - set(fieldnames)
            if missing:
                raise ValueError(
                    "source_file is missing required columns: "
                    f"{', '.join(sorted(missing))}"
                )

    def count_records(self) -> int:
        """Return the number of data rows in the CSV, excluding the header.

        ``csv.DictReader`` skips blank physical lines on its own, so they
        are not counted as order-item records.
        """
        with self.source_file.open(encoding=_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            return sum(1 for _ in reader)