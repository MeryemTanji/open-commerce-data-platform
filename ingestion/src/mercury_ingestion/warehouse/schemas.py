"""Mercury's Raw BigQuery schema registry.

Per ADR-008, every Raw BigQuery table column is a nullable ``STRING`` in
Version 1 — no autodetection, no business typing, no platform metadata
columns. This module is the single, explicit source of truth for:

- which ``source_object`` values Mercury's warehouse layer supports;
- the exact Raw schema (field names, in source order) for each one;
- which sources are master/reference (whole-table replace) versus
  transactional (partition-level replace), per ADR-007/ADR-008.

This module performs no I/O and makes no BigQuery API calls — it only
declares static configuration that ``BigQueryRawLoader`` reads.
"""

from __future__ import annotations

from google.cloud import bigquery


def _string_fields(*names: str) -> tuple[bigquery.SchemaField, ...]:
    """Build a tuple of nullable STRING fields, in the given order."""
    return tuple(bigquery.SchemaField(name, "STRING", mode="NULLABLE") for name in names)


# Explicit Raw schema per stable Mercury source_object. Field order
# matches the source CSV's own column order; nothing is renamed,
# reordered, or business-typed here -- including the source dataset's
# own "lenght" spelling in the Products schema, which is preserved
# exactly rather than corrected.
RAW_SCHEMAS: dict[str, tuple[bigquery.SchemaField, ...]] = {
    "customers": _string_fields(
        "customer_id",
        "customer_unique_id",
        "customer_zip_code_prefix",
        "customer_city",
        "customer_state",
    ),
    "orders": _string_fields(
        "order_id",
        "customer_id",
        "order_status",
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ),
    "order_items": _string_fields(
        "order_id",
        "order_item_id",
        "product_id",
        "seller_id",
        "shipping_limit_date",
        "price",
        "freight_value",
    ),
    "products": _string_fields(
        "product_id",
        "product_category_name",
        "product_name_lenght",
        "product_description_lenght",
        "product_photos_qty",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ),
    "sellers": _string_fields(
        "seller_id",
        "seller_zip_code_prefix",
        "seller_city",
        "seller_state",
    ),
    "payments": _string_fields(
        "order_id",
        "payment_sequential",
        "payment_type",
        "payment_installments",
        "payment_value",
    ),
    "reviews": _string_fields(
        "review_id",
        "order_id",
        "review_score",
        "review_comment_title",
        "review_comment_message",
        "review_creation_date",
        "review_answer_timestamp",
    ),
    "geolocations": _string_fields(
        "geolocation_zip_code_prefix",
        "geolocation_lat",
        "geolocation_lng",
        "geolocation_city",
        "geolocation_state",
    ),
}

# Sources with no reliable creation/change timestamp (ADR-007): loaded
# as a whole-table WRITE_TRUNCATE replace, unpartitioned.
MASTER_REFERENCE_SOURCE_OBJECTS: frozenset[str] = frozenset(
    {"customers", "products", "sellers", "geolocations"}
)

# Sources with defensible temporal information (ADR-007): loaded as an
# ingestion-time partitioned table, WRITE_TRUNCATE scoped to one
# explicit historical partition per load.
TRANSACTIONAL_SOURCE_OBJECTS: frozenset[str] = frozenset(
    {"orders", "order_items", "payments", "reviews"}
)

SUPPORTED_SOURCE_OBJECTS: frozenset[str] = frozenset(RAW_SCHEMAS.keys())


def get_raw_schema(source_object: str) -> tuple[bigquery.SchemaField, ...]:
    """Return the explicit Raw schema for a supported source_object.

    Raises:
        ValueError: if ``source_object`` is not a supported Mercury
            warehouse source.
    """
    try:
        return RAW_SCHEMAS[source_object]
    except KeyError:
        raise ValueError(f"unsupported source_object: {source_object!r}") from None


def is_master_reference(source_object: str) -> bool:
    """Return True if source_object loads as a whole-table replace."""
    return source_object in MASTER_REFERENCE_SOURCE_OBJECTS


def is_transactional(source_object: str) -> bool:
    """Return True if source_object loads as a partitioned daily replace."""
    return source_object in TRANSACTIONAL_SOURCE_OBJECTS