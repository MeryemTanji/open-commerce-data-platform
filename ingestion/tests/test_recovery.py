"""Unit tests for mercury_ingestion.orchestration.recovery.

Pure domain logic -- no BigQuery, no GCS, no connectors, no network, no
I/O of any kind. Every test operates purely on in-memory Python objects.
"""

from __future__ import annotations

import dataclasses
import inspect
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from mercury_ingestion.orchestration import recovery as recovery_module
from mercury_ingestion.orchestration.recovery import (
    RecoveryAction,
    RecoveryEvidence,
    RecoveryPlan,
    RecoveryPlanItem,
    RecoveryPlanner,
)
from mercury_ingestion.orchestration.state import ReplayStage, ReplayStateRecord, ReplayStatus

DELIVERY_DATE = date(2017, 5, 19)
STARTED = datetime(2026, 8, 18, 10, 0, 0, tzinfo=timezone.utc)
COMPLETED = datetime(2026, 8, 18, 10, 5, 0, tzinfo=timezone.utc)
RECORDED = datetime(2026, 8, 18, 10, 5, 1, tzinfo=timezone.utc)


def _evidence(**overrides: object) -> RecoveryEvidence:
    fields = {
        "delivery_date": DELIVERY_DATE,
        "source_object": "orders",
        "logical_completion": False,
        "valid_gcs_raw": False,
        "bigquery_raw_present": False,
        "latest_attempt": None,
    }
    fields.update(overrides)
    return RecoveryEvidence(**fields)  # type: ignore[arg-type]


def _failed_attempt(
    source_object: str = "orders",
    delivery_date: date = DELIVERY_DATE,
    stage: ReplayStage = ReplayStage.INGESTION,
) -> ReplayStateRecord:
    return ReplayStateRecord.failed(
        run_id="run-b",
        event_id="evt-failed",
        delivery_date=delivery_date,
        source_object=source_object,
        stage=stage,
        started_at=STARTED,
        completed_at=COMPLETED,
        recorded_at=RECORDED,
        error_message="connector broke",
    )


def _running_attempt(source_object: str = "orders", delivery_date: date = DELIVERY_DATE) -> ReplayStateRecord:
    return ReplayStateRecord.running(
        run_id="run-c",
        event_id="evt-running",
        delivery_date=delivery_date,
        source_object=source_object,
        stage=ReplayStage.INGESTION,
        started_at=STARTED,
        recorded_at=RECORDED,
    )


class TestRecoveryAction:
    def test_exact_values(self) -> None:
        assert RecoveryAction.SKIP.value == "skip"
        assert RecoveryAction.INGEST_AND_LOAD.value == "ingest_and_load"
        assert RecoveryAction.LOAD_ONLY.value == "load_only"
        assert RecoveryAction.RECONCILE.value == "reconcile"
        assert RecoveryAction.MANUAL_REVIEW.value == "manual_review"

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            RecoveryAction("not_a_real_action")


class TestRecoveryEvidenceValidation:
    def test_valid_construction(self) -> None:
        evidence = _evidence()

        assert evidence.source_object == "orders"

    def test_is_immutable(self) -> None:
        evidence = _evidence()

        with pytest.raises(dataclasses.FrozenInstanceError):
            evidence.logical_completion = True  # type: ignore[misc]

    def test_invalid_delivery_date_rejected(self) -> None:
        with pytest.raises(TypeError):
            _evidence(delivery_date="2017-05-19")

    def test_blank_source_object_rejected(self) -> None:
        with pytest.raises(ValueError):
            _evidence(source_object="   ")

    def test_non_string_source_object_rejected(self) -> None:
        with pytest.raises(TypeError):
            _evidence(source_object=123)

    def test_non_bool_logical_completion_rejected(self) -> None:
        with pytest.raises(TypeError):
            _evidence(logical_completion=1)

    def test_non_bool_valid_gcs_raw_rejected(self) -> None:
        with pytest.raises(TypeError):
            _evidence(valid_gcs_raw="yes")

    def test_non_bool_bigquery_raw_present_rejected(self) -> None:
        with pytest.raises(TypeError):
            _evidence(bigquery_raw_present=0)

    def test_latest_attempt_none_accepted(self) -> None:
        evidence = _evidence(latest_attempt=None)

        assert evidence.latest_attempt is None

    def test_latest_attempt_replay_state_record_accepted(self) -> None:
        evidence = _evidence(latest_attempt=_failed_attempt())

        assert evidence.latest_attempt is not None

    def test_latest_attempt_wrong_type_rejected(self) -> None:
        with pytest.raises(TypeError):
            _evidence(latest_attempt="not a record")

    def test_latest_attempt_mismatched_delivery_date_rejected(self) -> None:
        mismatched = _failed_attempt(delivery_date=date(2017, 5, 20))

        with pytest.raises(ValueError):
            _evidence(latest_attempt=mismatched)

    def test_latest_attempt_mismatched_source_object_rejected(self) -> None:
        mismatched = _failed_attempt(source_object="payments")

        with pytest.raises(ValueError):
            _evidence(source_object="orders", latest_attempt=mismatched)


class TestRecoveryPlanItemValidation:
    def test_valid_construction(self) -> None:
        evidence = _evidence()
        item = RecoveryPlanItem(source_object="orders", action=RecoveryAction.SKIP, reason="already complete", evidence=evidence)

        assert item.action is RecoveryAction.SKIP

    def test_is_immutable(self) -> None:
        evidence = _evidence()
        item = RecoveryPlanItem(source_object="orders", action=RecoveryAction.SKIP, reason="already complete", evidence=evidence)

        with pytest.raises(dataclasses.FrozenInstanceError):
            item.action = RecoveryAction.RECONCILE  # type: ignore[misc]

    def test_blank_source_object_rejected(self) -> None:
        with pytest.raises(ValueError):
            RecoveryPlanItem(source_object="  ", action=RecoveryAction.SKIP, reason="x", evidence=_evidence())

    def test_invalid_action_rejected(self) -> None:
        with pytest.raises(TypeError):
            RecoveryPlanItem(source_object="orders", action="skip", reason="x", evidence=_evidence())  # type: ignore[arg-type]

    def test_blank_reason_rejected(self) -> None:
        with pytest.raises(ValueError):
            RecoveryPlanItem(source_object="orders", action=RecoveryAction.SKIP, reason="   ", evidence=_evidence())

    def test_invalid_evidence_type_rejected(self) -> None:
        with pytest.raises(TypeError):
            RecoveryPlanItem(source_object="orders", action=RecoveryAction.SKIP, reason="x", evidence="not evidence")  # type: ignore[arg-type]

    def test_source_object_must_match_evidence(self) -> None:
        evidence = _evidence(source_object="orders")

        with pytest.raises(ValueError):
            RecoveryPlanItem(source_object="payments", action=RecoveryAction.SKIP, reason="x", evidence=evidence)


class TestRecoveryPlanValidation:
    def test_valid_construction(self) -> None:
        item = RecoveryPlanner().decide(_evidence(logical_completion=True))
        plan = RecoveryPlan(delivery_date=DELIVERY_DATE, items=(item,))

        assert len(plan.items) == 1

    def test_is_immutable(self) -> None:
        plan = RecoveryPlan(delivery_date=DELIVERY_DATE, items=())

        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.delivery_date = date(2017, 5, 20)  # type: ignore[misc]

    def test_empty_plan_is_deliberately_allowed(self) -> None:
        plan = RecoveryPlan(delivery_date=DELIVERY_DATE, items=())

        assert plan.items == ()

    def test_non_tuple_items_rejected(self) -> None:
        item = RecoveryPlanner().decide(_evidence(logical_completion=True))

        with pytest.raises(TypeError):
            RecoveryPlan(delivery_date=DELIVERY_DATE, items=[item])  # type: ignore[arg-type]

    def test_non_recovery_plan_item_member_rejected(self) -> None:
        with pytest.raises(TypeError):
            RecoveryPlan(delivery_date=DELIVERY_DATE, items=("not an item",))  # type: ignore[arg-type]

    def test_duplicate_source_object_rejected(self) -> None:
        planner = RecoveryPlanner()
        item_a = planner.decide(_evidence(source_object="orders", logical_completion=True))
        item_b = planner.decide(_evidence(source_object="orders", logical_completion=True))

        with pytest.raises(ValueError):
            RecoveryPlan(delivery_date=DELIVERY_DATE, items=(item_a, item_b))

    def test_mixed_delivery_dates_rejected(self) -> None:
        planner = RecoveryPlanner()
        item_a = planner.decide(_evidence(delivery_date=DELIVERY_DATE, source_object="orders", logical_completion=True))
        other_date = date(2017, 5, 20)
        item_b = planner.decide(_evidence(delivery_date=other_date, source_object="payments", logical_completion=True))

        with pytest.raises(ValueError):
            RecoveryPlan(delivery_date=DELIVERY_DATE, items=(item_a, item_b))

    def test_invalid_delivery_date_rejected(self) -> None:
        with pytest.raises(TypeError):
            RecoveryPlan(delivery_date="2017-05-19", items=())  # type: ignore[arg-type]


class TestDecisionMatrix:
    """Validation Requirements #1-9 from the task: the exact truth table."""

    def test_logical_completion_yields_skip(self) -> None:
        item = RecoveryPlanner().decide(_evidence(logical_completion=True, valid_gcs_raw=False, bigquery_raw_present=False))

        assert item.action is RecoveryAction.SKIP

    def test_logical_completion_yields_skip_regardless_of_physical_evidence(self) -> None:
        item = RecoveryPlanner().decide(_evidence(logical_completion=True, valid_gcs_raw=True, bigquery_raw_present=True))

        assert item.action is RecoveryAction.SKIP

    def test_logical_completion_with_later_failed_attempt_still_skips(self) -> None:
        evidence = _evidence(logical_completion=True, latest_attempt=_failed_attempt())

        item = RecoveryPlanner().decide(evidence)

        assert item.action is RecoveryAction.SKIP

    def test_incomplete_no_gcs_no_bigquery_yields_ingest_and_load(self) -> None:
        item = RecoveryPlanner().decide(
            _evidence(logical_completion=False, valid_gcs_raw=False, bigquery_raw_present=False)
        )

        assert item.action is RecoveryAction.INGEST_AND_LOAD

    def test_incomplete_valid_gcs_no_bigquery_yields_load_only(self) -> None:
        item = RecoveryPlanner().decide(
            _evidence(logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False)
        )

        assert item.action is RecoveryAction.LOAD_ONLY

    def test_incomplete_valid_gcs_and_bigquery_yields_reconcile(self) -> None:
        item = RecoveryPlanner().decide(
            _evidence(logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=True)
        )

        assert item.action is RecoveryAction.RECONCILE

    def test_incomplete_no_gcs_but_bigquery_yields_manual_review(self) -> None:
        item = RecoveryPlanner().decide(
            _evidence(logical_completion=False, valid_gcs_raw=False, bigquery_raw_present=True)
        )

        assert item.action is RecoveryAction.MANUAL_REVIEW

    def test_latest_failed_ingestion_does_not_override_physical_evidence(self) -> None:
        without_attempt = RecoveryPlanner().decide(
            _evidence(logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False)
        )
        with_failed_attempt = RecoveryPlanner().decide(
            _evidence(
                logical_completion=False,
                valid_gcs_raw=True,
                bigquery_raw_present=False,
                latest_attempt=_failed_attempt(stage=ReplayStage.INGESTION),
            )
        )

        assert without_attempt.action == with_failed_attempt.action == RecoveryAction.LOAD_ONLY

    def test_latest_failed_warehouse_does_not_force_load_only_if_evidence_says_otherwise(self) -> None:
        item = RecoveryPlanner().decide(
            _evidence(
                logical_completion=False,
                valid_gcs_raw=False,
                bigquery_raw_present=False,
                latest_attempt=_failed_attempt(stage=ReplayStage.WAREHOUSE),
            )
        )

        assert item.action is RecoveryAction.INGEST_AND_LOAD

    def test_latest_running_state_does_not_independently_decide_action(self) -> None:
        without_attempt = RecoveryPlanner().decide(
            _evidence(logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=True)
        )
        with_running_attempt = RecoveryPlanner().decide(
            _evidence(
                logical_completion=False,
                valid_gcs_raw=True,
                bigquery_raw_present=True,
                latest_attempt=_running_attempt(),
            )
        )

        assert without_attempt.action == with_running_attempt.action == RecoveryAction.RECONCILE


class TestPlanOrderingAndInspection:
    def test_plan_orders_by_source_object_regardless_of_input_order(self) -> None:
        # Superseded contract: the planner used to simply preserve
        # whatever order the caller's evidence iterable happened to be
        # in. Per this revision, the planner itself now guarantees
        # source_object-ascending ordering -- this input is deliberately
        # NOT already sorted ("orders" before "order_items" is not
        # alphabetical, since '_' sorts before 's').
        planner = RecoveryPlanner()
        evidence = [
            _evidence(source_object="orders", logical_completion=True),
            _evidence(source_object="order_items", logical_completion=True),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False),
            _evidence(source_object="reviews", logical_completion=True),
        ]

        plan = planner.plan(DELIVERY_DATE, evidence)

        assert [item.source_object for item in plan.items] == ["order_items", "orders", "payments", "reviews"]

    def test_different_input_orders_produce_identical_plan_ordering(self) -> None:
        planner = RecoveryPlanner()
        first_order = [
            _evidence(source_object="reviews", logical_completion=True),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False),
            _evidence(source_object="orders", logical_completion=True),
            _evidence(source_object="order_items", logical_completion=True),
        ]
        second_order = [
            _evidence(source_object="order_items", logical_completion=True),
            _evidence(source_object="orders", logical_completion=True),
            _evidence(source_object="reviews", logical_completion=True),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False),
        ]

        plan_from_first_order = planner.plan(DELIVERY_DATE, first_order)
        plan_from_second_order = planner.plan(DELIVERY_DATE, second_order)

        expected_order = ["order_items", "orders", "payments", "reviews"]
        assert [item.source_object for item in plan_from_first_order.items] == expected_order
        assert [item.source_object for item in plan_from_second_order.items] == expected_order

    def test_action_remains_associated_with_correct_source_after_sorting(self) -> None:
        planner = RecoveryPlanner()
        evidence = [
            _evidence(source_object="reviews", logical_completion=True),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False),
            _evidence(source_object="orders", logical_completion=True),
            _evidence(source_object="order_items", logical_completion=True),
        ]

        plan = planner.plan(DELIVERY_DATE, evidence)

        actions_by_source = {item.source_object: item.action for item in plan.items}
        assert actions_by_source["payments"] is RecoveryAction.LOAD_ONLY
        assert actions_by_source["orders"] is RecoveryAction.SKIP
        assert actions_by_source["order_items"] is RecoveryAction.SKIP
        assert actions_by_source["reviews"] is RecoveryAction.SKIP

    def test_plan_accepts_a_generic_iterable_not_just_a_list(self) -> None:
        # RecoveryPlanner.plan() is typed to accept Iterable[RecoveryEvidence];
        # a generator (consumed once, no inherent stable order guarantee
        # of its own) must still produce the same deterministic result.
        planner = RecoveryPlanner()

        def _evidence_generator():
            yield _evidence(source_object="reviews", logical_completion=True)
            yield _evidence(source_object="orders", logical_completion=True)
            yield _evidence(source_object="order_items", logical_completion=True)
            yield _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False)

        plan = planner.plan(DELIVERY_DATE, _evidence_generator())

        assert [item.source_object for item in plan.items] == ["order_items", "orders", "payments", "reviews"]

    def test_inspection_properties_correct_after_deterministic_ordering(self) -> None:
        planner = RecoveryPlanner()
        evidence = [
            _evidence(source_object="reviews", logical_completion=False, valid_gcs_raw=False, bigquery_raw_present=True),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False),
            _evidence(source_object="orders", logical_completion=True),
            _evidence(
                source_object="order_items", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=True
            ),
        ]

        plan = planner.plan(DELIVERY_DATE, evidence)

        assert {item.source_object for item in plan.needs_execution} == {"payments"}
        assert {item.source_object for item in plan.requires_reconciliation} == {"order_items"}
        assert {item.source_object for item in plan.requires_manual_review} == {"reviews"}
        assert {item.source_object for item in plan.skipped} == {"orders"}
        # And the properties themselves preserve the plan's deterministic
        # source_object ordering, not merely the correct membership.
        assert [item.source_object for item in plan.items] == ["order_items", "orders", "payments", "reviews"]

    def test_plan_identifies_sources_requiring_execution(self) -> None:
        planner = RecoveryPlanner()
        evidence = [
            _evidence(source_object="orders", logical_completion=True),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False),
            _evidence(source_object="reviews", logical_completion=False, valid_gcs_raw=False, bigquery_raw_present=False),
        ]

        plan = planner.plan(DELIVERY_DATE, evidence)

        assert {item.source_object for item in plan.needs_execution} == {"payments", "reviews"}

    def test_plan_identifies_reconciliation_required_sources(self) -> None:
        planner = RecoveryPlanner()
        evidence = [
            _evidence(source_object="orders", logical_completion=True),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=True),
        ]

        plan = planner.plan(DELIVERY_DATE, evidence)

        assert [item.source_object for item in plan.requires_reconciliation] == ["payments"]

    def test_plan_identifies_manual_review_required_sources(self) -> None:
        planner = RecoveryPlanner()
        evidence = [
            _evidence(source_object="orders", logical_completion=True),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=False, bigquery_raw_present=True),
        ]

        plan = planner.plan(DELIVERY_DATE, evidence)

        assert [item.source_object for item in plan.requires_manual_review] == ["payments"]

    def test_completed_sources_excluded_from_needs_execution(self) -> None:
        planner = RecoveryPlanner()
        evidence = [
            _evidence(source_object="orders", logical_completion=True),
            _evidence(source_object="order_items", logical_completion=True),
        ]

        plan = planner.plan(DELIVERY_DATE, evidence)

        assert plan.needs_execution == ()
        assert plan.requires_reconciliation == ()
        assert plan.requires_manual_review == ()
        assert {item.source_object for item in plan.skipped} == {"orders", "order_items"}

    def test_full_example_matches_expected_shape(self) -> None:
        planner = RecoveryPlanner()
        evidence = [
            _evidence(source_object="orders", logical_completion=True),
            _evidence(source_object="order_items", logical_completion=True),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False),
            _evidence(source_object="reviews", logical_completion=True),
        ]

        plan = planner.plan(DELIVERY_DATE, evidence)

        actions = {item.source_object: item.action for item in plan.items}
        assert actions == {
            "orders": RecoveryAction.SKIP,
            "order_items": RecoveryAction.SKIP,
            "payments": RecoveryAction.LOAD_ONLY,
            "reviews": RecoveryAction.SKIP,
        }


class TestPlannerPurity:
    def test_decide_is_deterministic(self) -> None:
        evidence = _evidence(logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=True)
        planner = RecoveryPlanner()

        first = planner.decide(evidence)
        second = planner.decide(evidence)

        assert first.action == second.action
        assert first.reason == second.reason

    def test_planner_has_no_mutable_state_between_calls(self) -> None:
        planner = RecoveryPlanner()
        planner.decide(_evidence(source_object="orders", logical_completion=True))
        result = planner.decide(_evidence(source_object="payments", logical_completion=False))

        assert result.action is RecoveryAction.INGEST_AND_LOAD

    def test_deciding_does_not_mutate_the_evidence(self) -> None:
        evidence = _evidence(logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False)

        RecoveryPlanner().decide(evidence)

        assert evidence.valid_gcs_raw is True
        assert evidence.bigquery_raw_present is False


class TestLayerBoundaries:
    def test_recovery_module_has_no_cloud_or_pipeline_dependency(self) -> None:
        source_text = Path(inspect.getfile(recovery_module)).read_text(encoding="utf-8")
        import_lines = [line for line in source_text.splitlines() if line.startswith(("import ", "from "))]
        import_block = "\n".join(import_lines)

        assert "google" not in import_block
        assert "bigquery" not in import_block
        assert "storage" not in import_block
        assert "connectors" not in import_block
        assert "simulation" not in import_block
        assert "sources" not in import_block
        assert "replay" not in import_block  # does not import HistoricalReplayRunner either