"""Mercury's fourth concrete ingestion connector: products.

This module implements the local, Olist-backed extraction of Nova
Commerce's product catalogue, under the ``product_catalog`` source
system. Its CSV-specific technical validation and record counting are
inherited from ``BaseCsvConnector`` (per ADR-005); this module supplies
only the source identity, required schema, and domain documentation for
the products source.

Dataset grain: one row represents one product. The expected source-level
key is ``product_id``. This connector does not validate that key's
uniqueness — key uniqueness, numeric type casting, data-quality
assertions, source-column renaming, and canonical modelling are all
downstream Dataform staging concerns, not raw ingestion concerns.

Raw Landing preserves the source exactly as received, including its
spelling quirks: the columns ``product_name_lenght`` and
``product_description_lenght`` retain the source dataset's original
"lenght" typo. Ingestion must never rename, retype, or otherwise "fix"
source columns — a future staging model is the right place to rename
them to something clearer such as ``product_name_length``.

The related file ``product_category_name_translation.csv`` is a
separate source object and is intentionally out of scope here; it will
be handled by its own connector. This connector never joins, enriches,
or translates ``product_category_name`` values.

A future API-based product source (or a different file format) can be
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
        "product_id",
        "product_category_name",
        "product_name_lenght",
        "product_description_lenght",
        "product_photos_qty",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    }
)


@final
class ProductsConnector(BaseCsvConnector):
    """Ingests Nova Commerce's products CSV (Olist-backed, local file).

    Grain: one row per product. The expected source key is
    ``product_id`` — this connector does not validate its uniqueness.

    This connector performs technical, structural validation only — it
    confirms the file is readable, correctly typed, and has the columns
    downstream layers depend on. It does not judge the quality of the
    business data itself. In particular it does not: reject a blank
    ``product_category_name``, reject negative or zero product
    dimensions/weight, reject a blank ``product_photos_qty``, validate
    uniqueness of ``product_id``, or translate/enrich category names.
    Those checks and transformations belong to later staging/canonical
    models, not to raw ingestion. Source column names — including the
    source dataset's ``lenght`` spelling — are preserved exactly as
    received.
    """

    SOURCE_SYSTEM = "product_catalog"
    SOURCE_OBJECT = "products"

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