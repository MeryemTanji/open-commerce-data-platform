"""Tests for the production delivery-readiness gate."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from mercury_ingestion.runtime.delivery_readiness import (
    DeliveryReadinessResult,
    evaluate_delivery_readiness,
)


DELIVERY_DATE = date(2017, 5, 1)

EXPECTED_SOURCES = frozenset(
    {
        "orders",
        "order_items",
        "payments",
        "reviews",
    }
)


class FakeReplayStateStore:
    """Minimal replay-state test double for readiness evaluation."""

    def __init__(self, completed_source_objects: set[str]) -> None:
        self.completed_source_objects = completed_source_objects
        self.requested_dates: list[date] = []

    def get_completed_for_date(
        self,
        delivery_date: date,
    ) -> tuple[SimpleNamespace, ...]:
        self.requested_dates.append(delivery_date)

        return tuple(
            SimpleNamespace(source_object=source_object)
            for source_object in self.completed_source_objects
        )


def test_ready_when_completed_sources_exactly_match_contract() -> None:
    store = FakeReplayStateStore(set(EXPECTED_SOURCES))

    result = evaluate_delivery_readiness(
        replay_state_store=store,
        delivery_date=DELIVERY_DATE,
        expected_source_objects=EXPECTED_SOURCES,
    )

    assert result == DeliveryReadinessResult(
        delivery_date=DELIVERY_DATE,
        expected_source_objects=(
            "order_items",
            "orders",
            "payments",
            "reviews",
        ),
        completed_source_objects=(
            "order_items",
            "orders",
            "payments",
            "reviews",
        ),
        missing_source_objects=(),
        unexpected_source_objects=(),
        is_ready=True,
    )
    assert store.requested_dates == [DELIVERY_DATE]


def test_not_ready_when_expected_source_is_missing() -> None:
    store = FakeReplayStateStore(
        {
            "orders",
            "order_items",
            "reviews",
        }
    )

    result = evaluate_delivery_readiness(
        replay_state_store=store,
        delivery_date=DELIVERY_DATE,
        expected_source_objects=EXPECTED_SOURCES,
    )

    assert result.is_ready is False
    assert result.missing_source_objects == ("payments",)
    assert result.unexpected_source_objects == ()


def test_not_ready_when_unexpected_source_is_completed() -> None:
    store = FakeReplayStateStore(
        set(EXPECTED_SOURCES) | {"unexpected_source"}
    )

    result = evaluate_delivery_readiness(
        replay_state_store=store,
        delivery_date=DELIVERY_DATE,
        expected_source_objects=EXPECTED_SOURCES,
    )

    assert result.is_ready is False
    assert result.missing_source_objects == ()
    assert result.unexpected_source_objects == (
        "unexpected_source",
    )


def test_reports_missing_and_unexpected_sources_together() -> None:
    store = FakeReplayStateStore(
        {
            "orders",
            "order_items",
            "reviews",
            "unexpected_source",
        }
    )

    result = evaluate_delivery_readiness(
        replay_state_store=store,
        delivery_date=DELIVERY_DATE,
        expected_source_objects=EXPECTED_SOURCES,
    )

    assert result.is_ready is False
    assert result.missing_source_objects == ("payments",)
    assert result.unexpected_source_objects == (
        "unexpected_source",
    )


def test_empty_completion_state_is_not_ready() -> None:
    store = FakeReplayStateStore(set())

    result = evaluate_delivery_readiness(
        replay_state_store=store,
        delivery_date=DELIVERY_DATE,
        expected_source_objects=EXPECTED_SOURCES,
    )

    assert result.is_ready is False
    assert result.completed_source_objects == ()
    assert result.missing_source_objects == (
        "order_items",
        "orders",
        "payments",
        "reviews",
    )


def test_delivery_date_must_be_a_date() -> None:
    store = FakeReplayStateStore(set())

    with pytest.raises(
        TypeError,
        match="delivery_date must be a datetime.date",
    ):
        evaluate_delivery_readiness(
            replay_state_store=store,
            delivery_date="2017-05-01",  # type: ignore[arg-type]
            expected_source_objects=EXPECTED_SOURCES,
        )

    assert store.requested_dates == []


@pytest.mark.parametrize(
    "expected_source_objects",
    [
        frozenset(),
        frozenset({""}),
        frozenset({"   "}),
    ],
)
def test_expected_source_contract_must_be_valid(
    expected_source_objects: frozenset[str],
) -> None:
    store = FakeReplayStateStore(set())

    with pytest.raises(ValueError):
        evaluate_delivery_readiness(
            replay_state_store=store,
            delivery_date=DELIVERY_DATE,
            expected_source_objects=expected_source_objects,
        )

    assert store.requested_dates == []