"""Unit tests for mercury_ingestion.warehouse.schemas.

Pure static configuration -- no BigQuery client, no network access.
"""

from __future__ import annotations

import pytest
from google.cloud import bigquery

from mercury_ingestion.warehouse.schemas import (
    MASTER_REFERENCE_SOURCE_OBJECTS,
    RAW_SCHEMAS,
    SUPPORTED_SOURCE_OBJECTS,
    TRANSACTIONAL_SOURCE_OBJECTS,
    get_raw_schema,
    is_master_reference,
    is_transactional,
)

EXPECTED_SOURCE_OBJECTS = frozenset(
    {"customers", "orders", "order_items", "products", "sellers", "payments", "reviews", "geolocations"}
)

EXPECTED_FIELD_NAMES: dict[str, list[str]] = {
    "customers": ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"],
    "orders": [
        "order_id",
        "customer_id",
        "order_status",
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "order_items": ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"],
    "products": [
        "product_id",
        "product_category_name",
        "product_name_lenght",
        "product_description_lenght",
        "product_photos_qty",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ],
    "sellers": ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"],
    "payments": ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"],
    "reviews": [
        "review_id",
        "order_id",
        "review_score",
        "review_comment_title",
        "review_comment_message",
        "review_creation_date",
        "review_answer_timestamp",
    ],
    "geolocations": ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"],
}


class TestRegistry:
    def test_all_eight_supported_source_objects_exist(self) -> None:
        assert SUPPORTED_SOURCE_OBJECTS == EXPECTED_SOURCE_OBJECTS

    def test_no_unexpected_source_objects(self) -> None:
        assert set(RAW_SCHEMAS.keys()) == EXPECTED_SOURCE_OBJECTS

    def test_schemas_are_deterministic(self) -> None:
        assert get_raw_schema("orders") == get_raw_schema("orders")

    def test_unsupported_source_object_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            get_raw_schema("unknown_source")


class TestEveryFieldIsStringAndNullable:
    @pytest.mark.parametrize("source_object", sorted(EXPECTED_SOURCE_OBJECTS))
    def test_all_fields_are_nullable_string(self, source_object: str) -> None:
        schema = get_raw_schema(source_object)

        assert len(schema) > 0
        for field in schema:
            assert field.field_type == "STRING"
            assert field.mode == "NULLABLE"


class TestExactFieldNamesAndOrder:
    @pytest.mark.parametrize("source_object", sorted(EXPECTED_SOURCE_OBJECTS))
    def test_field_names_and_order_match(self, source_object: str) -> None:
        schema = get_raw_schema(source_object)

        assert [field.name for field in schema] == EXPECTED_FIELD_NAMES[source_object]

    def test_products_preserves_name_lenght_spelling(self) -> None:
        field_names = [field.name for field in get_raw_schema("products")]

        assert "product_name_lenght" in field_names
        assert "product_name_length" not in field_names

    def test_products_preserves_description_lenght_spelling(self) -> None:
        field_names = [field.name for field in get_raw_schema("products")]

        assert "product_description_lenght" in field_names
        assert "product_description_length" not in field_names


class TestClassification:
    def test_master_reference_objects(self) -> None:
        assert MASTER_REFERENCE_SOURCE_OBJECTS == {"customers", "products", "sellers", "geolocations"}

    def test_transactional_objects(self) -> None:
        assert TRANSACTIONAL_SOURCE_OBJECTS == {"orders", "order_items", "payments", "reviews"}

    def test_classifications_do_not_overlap(self) -> None:
        assert MASTER_REFERENCE_SOURCE_OBJECTS & TRANSACTIONAL_SOURCE_OBJECTS == set()

    def test_every_supported_object_belongs_to_exactly_one_classification(self) -> None:
        union = MASTER_REFERENCE_SOURCE_OBJECTS | TRANSACTIONAL_SOURCE_OBJECTS
        assert union == SUPPORTED_SOURCE_OBJECTS

    @pytest.mark.parametrize("source_object", sorted(MASTER_REFERENCE_SOURCE_OBJECTS))
    def test_is_master_reference_true_for_master_objects(self, source_object: str) -> None:
        assert is_master_reference(source_object) is True
        assert is_transactional(source_object) is False

    @pytest.mark.parametrize("source_object", sorted(TRANSACTIONAL_SOURCE_OBJECTS))
    def test_is_transactional_true_for_transactional_objects(self, source_object: str) -> None:
        assert is_transactional(source_object) is True
        assert is_master_reference(source_object) is False