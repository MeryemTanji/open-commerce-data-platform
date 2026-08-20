"""Unit tests for mercury_ingestion.sources.base."""

from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path
from typing import final

import pytest

from mercury_ingestion.sources.base import SourceDelivery, SourceDeliveryBatch, SourceDeliveryProvider


def _delivery(
    source_object: str = "orders",
    path: Path = Path("orders.csv"),
    delivery_date: date | None = date(2017, 5, 1),
    record_count: int = 5,
) -> SourceDelivery:
    return SourceDelivery(
        source_object=source_object, path=path, delivery_date=delivery_date, record_count=record_count
    )


class TestSourceDelivery:
    def test_valid_construction(self) -> None:
        delivery = _delivery()

        assert delivery.source_object == "orders"
        assert delivery.record_count == 5

    def test_is_immutable(self) -> None:
        delivery = _delivery()

        with pytest.raises(dataclasses.FrozenInstanceError):
            delivery.record_count = 10  # type: ignore[misc]

    def test_blank_source_object_rejected(self) -> None:
        with pytest.raises(ValueError):
            _delivery(source_object="   ")

    def test_non_path_rejected(self) -> None:
        with pytest.raises(TypeError):
            SourceDelivery(source_object="orders", path="orders.csv", delivery_date=None, record_count=0)  # type: ignore[arg-type]

    def test_negative_record_count_rejected(self) -> None:
        with pytest.raises(ValueError):
            _delivery(record_count=-1)

    def test_invalid_delivery_date_type_rejected(self) -> None:
        with pytest.raises(TypeError):
            SourceDelivery(source_object="orders", path=Path("x.csv"), delivery_date="2017-05-01", record_count=0)  # type: ignore[arg-type]

    def test_none_delivery_date_accepted_for_initial_deliveries(self) -> None:
        delivery = _delivery(delivery_date=None)

        assert delivery.delivery_date is None


class TestSourceDeliveryBatch:
    def test_valid_construction(self) -> None:
        batch = SourceDeliveryBatch(
            deliveries=(_delivery(source_object="orders"), _delivery(source_object="payments")),
            delivery_date=date(2017, 5, 1),
        )

        assert len(batch.deliveries) == 2

    def test_is_immutable(self) -> None:
        batch = SourceDeliveryBatch(deliveries=(_delivery(),), delivery_date=date(2017, 5, 1))

        with pytest.raises(dataclasses.FrozenInstanceError):
            batch.delivery_date = date(2017, 5, 2)  # type: ignore[misc]

    def test_duplicate_source_objects_rejected(self) -> None:
        with pytest.raises(ValueError):
            SourceDeliveryBatch(
                deliveries=(
                    _delivery(source_object="orders"),
                    _delivery(source_object="orders"),
                ),
                delivery_date=date(2017, 5, 1),
            )

    def test_non_source_delivery_member_rejected(self) -> None:
        with pytest.raises(TypeError):
            SourceDeliveryBatch(deliveries=("not a delivery",), delivery_date=None)  # type: ignore[arg-type]

    def test_deliveries_must_be_a_tuple(self) -> None:
        with pytest.raises(TypeError):
            SourceDeliveryBatch(deliveries=[_delivery()], delivery_date=date(2017, 5, 1))  # type: ignore[arg-type]

    def test_inconsistent_daily_delivery_dates_rejected(self) -> None:
        with pytest.raises(ValueError):
            SourceDeliveryBatch(
                deliveries=(_delivery(delivery_date=date(2017, 5, 1)),),
                delivery_date=date(2017, 5, 2),
            )

    def test_initial_batch_with_none_delivery_date_accepted(self) -> None:
        batch = SourceDeliveryBatch(
            deliveries=(_delivery(source_object="customers", delivery_date=None),),
            delivery_date=None,
        )

        assert batch.delivery_date is None

    def test_delivery_with_a_date_inside_a_none_batch_rejected(self) -> None:
        with pytest.raises(ValueError):
            SourceDeliveryBatch(
                deliveries=(_delivery(source_object="customers", delivery_date=date(2017, 5, 1)),),
                delivery_date=None,
            )

    def test_ingestion_date_defaults_to_none(self) -> None:
        batch = SourceDeliveryBatch(deliveries=(_delivery(),), delivery_date=date(2017, 5, 1))

        assert batch.ingestion_date is None

    def test_ingestion_date_accepts_a_date(self) -> None:
        batch = SourceDeliveryBatch(
            deliveries=(_delivery(delivery_date=date(2017, 5, 1)),),
            delivery_date=date(2017, 5, 1),
            ingestion_date=date(2017, 5, 2),
        )

        assert batch.ingestion_date == date(2017, 5, 2)

    def test_ingestion_date_accepts_none_explicitly(self) -> None:
        batch = SourceDeliveryBatch(
            deliveries=(_delivery(delivery_date=date(2017, 5, 1)),),
            delivery_date=date(2017, 5, 1),
            ingestion_date=None,
        )

        assert batch.ingestion_date is None

    def test_invalid_ingestion_date_type_rejected(self) -> None:
        with pytest.raises(TypeError):
            SourceDeliveryBatch(
                deliveries=(_delivery(delivery_date=date(2017, 5, 1)),),
                delivery_date=date(2017, 5, 1),
                ingestion_date="2017-05-02",  # type: ignore[arg-type]
            )

    def test_ingestion_date_may_differ_from_delivery_date(self) -> None:
        # No cross-field consistency check is expected here -- unlike
        # delivery_date (which every contained SourceDelivery must
        # match exactly), ingestion_date is purely a batch-level timing
        # fact and is free to differ from delivery_date.
        batch = SourceDeliveryBatch(
            deliveries=(_delivery(delivery_date=date(2017, 5, 1)),),
            delivery_date=date(2017, 5, 1),
            ingestion_date=date(2017, 5, 2),
        )

        assert batch.delivery_date != batch.ingestion_date

    def test_empty_deliveries_with_none_date_rejected(self) -> None:
        with pytest.raises(ValueError):
            SourceDeliveryBatch(deliveries=(), delivery_date=None)

    def test_empty_deliveries_with_a_date_rejected(self) -> None:
        with pytest.raises(ValueError):
            SourceDeliveryBatch(deliveries=(), delivery_date=date(2017, 5, 1))

    def test_zero_record_delivery_remains_valid(self) -> None:
        # A delivered source with zero business records (a valid
        # header-only CSV) is not the same thing as zero deliveries.
        delivery = _delivery(source_object="orders", delivery_date=date(2017, 5, 1), record_count=0)

        assert delivery.record_count == 0

    def test_zero_record_daily_batch_remains_valid(self) -> None:
        # All four daily sources present, each header-only (record_count=0).
        # This must NOT be rejected by the empty-batch check -- the batch
        # itself is non-empty, only the business record counts are zero.
        delivery_date = date(2017, 5, 1)
        batch = SourceDeliveryBatch(
            deliveries=(
                _delivery(source_object="orders", delivery_date=delivery_date, record_count=0),
                _delivery(source_object="order_items", delivery_date=delivery_date, record_count=0),
                _delivery(source_object="payments", delivery_date=delivery_date, record_count=0),
                _delivery(source_object="reviews", delivery_date=delivery_date, record_count=0),
            ),
            delivery_date=delivery_date,
        )

        assert len(batch.deliveries) == 4
        assert all(d.record_count == 0 for d in batch.deliveries)

    def test_initial_batch_with_valid_deliveries_remains_valid(self) -> None:
        batch = SourceDeliveryBatch(
            deliveries=(
                _delivery(source_object="customers", delivery_date=None, record_count=3),
                _delivery(source_object="products", delivery_date=None, record_count=1),
                _delivery(source_object="sellers", delivery_date=None, record_count=1),
                _delivery(source_object="geolocations", delivery_date=None, record_count=1),
            ),
            delivery_date=None,
        )

        assert len(batch.deliveries) == 4
        assert batch.delivery_date is None


class TestSourceDeliveryProvider:
    def test_cannot_be_instantiated_directly(self) -> None:
        with pytest.raises(TypeError):
            SourceDeliveryProvider()  # type: ignore[abstract]

    def test_concrete_subclass_satisfies_the_contract(self) -> None:
        @final
        class _StubProvider(SourceDeliveryProvider):
            def get_initial_delivery(self) -> SourceDeliveryBatch:
                return SourceDeliveryBatch(deliveries=(_delivery(source_object="customers", delivery_date=None),), delivery_date=None)

            def get_daily_delivery(self, delivery_date: date) -> SourceDeliveryBatch:
                return SourceDeliveryBatch(
                    deliveries=(_delivery(source_object="orders", delivery_date=delivery_date),), delivery_date=delivery_date
                )

        provider = _StubProvider()

        assert isinstance(provider, SourceDeliveryProvider)
        assert provider.get_initial_delivery().delivery_date is None
        assert provider.get_daily_delivery(date(2017, 5, 1)).delivery_date == date(2017, 5, 1)