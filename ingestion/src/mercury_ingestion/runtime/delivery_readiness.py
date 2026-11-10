"""Durable delivery-readiness evaluation for production orchestration.

This module answers one narrow operational question:

    Is one logical delivery date durably complete and therefore eligible
    for downstream transformation?

Readiness is derived exclusively from the replay-state store's logical
completion interface. It does not inspect the latest attempt, execute
ingestion, provision resources, or invoke downstream processing.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date

from mercury_ingestion.orchestration.state import ReplayStateStore


@dataclass(frozen=True, slots=True)
class DeliveryReadinessResult:
    """Immutable result of evaluating one delivery-date contract."""

    delivery_date: date
    expected_source_objects: tuple[str, ...]
    completed_source_objects: tuple[str, ...]
    missing_source_objects: tuple[str, ...]
    unexpected_source_objects: tuple[str, ...]
    is_ready: bool


def _normalize_expected_source_objects(
    expected_source_objects: Collection[str],
) -> frozenset[str]:
    """Validate and normalize the governed source-object contract."""

    if isinstance(expected_source_objects, (str, bytes)):
        raise TypeError(
            "expected_source_objects must be a collection of strings"
        )

    normalized: list[str] = []

    for source_object in expected_source_objects:
        if not isinstance(source_object, str):
            raise TypeError(
                "every expected source object must be a string"
            )

        if not source_object.strip():
            raise ValueError(
                "expected source objects cannot be blank"
            )

        normalized.append(source_object)

    if not normalized:
        raise ValueError(
            "expected_source_objects cannot be empty"
        )

    if len(normalized) != len(set(normalized)):
        raise ValueError(
            "expected_source_objects cannot contain duplicates"
        )

    return frozenset(normalized)


def evaluate_delivery_readiness(
    *,
    replay_state_store: ReplayStateStore,
    delivery_date: date,
    expected_source_objects: Collection[str],
) -> DeliveryReadinessResult:
    """Evaluate whether one delivery date may proceed downstream.

    A date is ready only when its durable logical-completion set exactly
    matches the governed expected-source contract.

    Later failed retries do not revoke an earlier success because
    ``ReplayStateStore.get_completed_for_date()`` deliberately exposes
    monotonic logical completion rather than latest-attempt state.
    """

    if not isinstance(delivery_date, date):
        raise TypeError(
            "delivery_date must be a datetime.date"
        )

    expected = _normalize_expected_source_objects(
        expected_source_objects
    )

    completed_records = replay_state_store.get_completed_for_date(
        delivery_date
    )

    completed = frozenset(
        record.source_object
        for record in completed_records
    )

    missing = expected - completed
    unexpected = completed - expected

    return DeliveryReadinessResult(
        delivery_date=delivery_date,
        expected_source_objects=tuple(sorted(expected)),
        completed_source_objects=tuple(sorted(completed)),
        missing_source_objects=tuple(sorted(missing)),
        unexpected_source_objects=tuple(sorted(unexpected)),
        is_ready=not missing and not unexpected,
    )