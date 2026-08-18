"""Unit tests for mercury_ingestion.orchestration.state.

Pure Python domain model -- no BigQuery, no network, no I/O of any kind.
"""

from __future__ import annotations

import dataclasses
import inspect
from datetime import date, datetime, timezone
from pathlib import Path
from typing import final

import pytest

from mercury_ingestion.orchestration import state as state_module
from mercury_ingestion.orchestration.state import (
    ReplayStage,
    ReplayStateRecord,
    ReplayStateStore,
    ReplayStatus,
    is_date_complete,
)

DELIVERY_DATE = date(2017, 5, 1)
STARTED = datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc)
COMPLETED = datetime(2026, 8, 17, 10, 5, 0, tzinfo=timezone.utc)
RECORDED = datetime(2026, 8, 17, 10, 5, 1, tzinfo=timezone.utc)
LATER_RECORDED = datetime(2026, 8, 17, 11, 0, 0, tzinfo=timezone.utc)
NAIVE = datetime(2026, 8, 17, 10, 0, 0)


def _record(**overrides: object) -> ReplayStateRecord:
    fields = {
        "run_id": "run-1",
        "event_id": "evt-1",
        "delivery_date": DELIVERY_DATE,
        "source_object": "orders",
        "status": ReplayStatus.RUNNING,
        "stage": ReplayStage.INGESTION,
        "started_at": STARTED,
        "completed_at": None,
        "error_message": None,
        "recorded_at": RECORDED,
    }
    fields.update(overrides)
    return ReplayStateRecord(**fields)  # type: ignore[arg-type]


class TestReplayStatus:
    def test_exact_values(self) -> None:
        assert ReplayStatus.RUNNING.value == "running"
        assert ReplayStatus.SUCCESS.value == "success"
        assert ReplayStatus.FAILED.value == "failed"

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            ReplayStatus("not_a_status")


class TestReplayStage:
    def test_exact_values(self) -> None:
        assert ReplayStage.SOURCE_DELIVERY.value == "source_delivery"
        assert ReplayStage.INGESTION.value == "ingestion"
        assert ReplayStage.WAREHOUSE.value == "warehouse"

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            ReplayStage("not_a_stage")


class TestReplayStateRecordConstruction:
    def test_valid_running_construction(self) -> None:
        record = _record(status=ReplayStatus.RUNNING, completed_at=None, error_message=None)

        assert record.status is ReplayStatus.RUNNING
        assert record.completed_at is None

    def test_valid_success_construction(self) -> None:
        record = _record(status=ReplayStatus.SUCCESS, stage=ReplayStage.WAREHOUSE, completed_at=COMPLETED, error_message=None)

        assert record.status is ReplayStatus.SUCCESS
        assert record.completed_at == COMPLETED

    def test_valid_failed_construction(self) -> None:
        record = _record(status=ReplayStatus.FAILED, completed_at=COMPLETED, error_message="boom")

        assert record.status is ReplayStatus.FAILED
        assert record.error_message == "boom"

    def test_is_immutable(self) -> None:
        record = _record()

        with pytest.raises(dataclasses.FrozenInstanceError):
            record.status = ReplayStatus.SUCCESS  # type: ignore[misc]

    def test_blank_event_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            _record(event_id="   ")

    def test_blank_source_object_rejected(self) -> None:
        with pytest.raises(ValueError):
            _record(source_object="")

    def test_invalid_delivery_date_rejected(self) -> None:
        with pytest.raises(TypeError):
            _record(delivery_date="2017-05-01")

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(TypeError):
            _record(status="running")

    def test_invalid_stage_rejected(self) -> None:
        with pytest.raises(TypeError):
            _record(stage="ingestion")

    def test_naive_started_at_rejected(self) -> None:
        with pytest.raises(ValueError):
            _record(started_at=NAIVE)

    def test_naive_recorded_at_rejected(self) -> None:
        with pytest.raises(ValueError):
            _record(recorded_at=NAIVE)

    def test_naive_completed_at_rejected(self) -> None:
        with pytest.raises(ValueError):
            _record(status=ReplayStatus.SUCCESS, stage=ReplayStage.WAREHOUSE, completed_at=NAIVE)

    def test_completed_at_before_started_at_rejected(self) -> None:
        too_early = STARTED.replace(hour=9)
        with pytest.raises(ValueError):
            _record(status=ReplayStatus.SUCCESS, stage=ReplayStage.WAREHOUSE, completed_at=too_early)

    def test_running_with_completed_at_rejected(self) -> None:
        with pytest.raises(ValueError):
            _record(status=ReplayStatus.RUNNING, completed_at=COMPLETED)

    def test_running_with_error_message_rejected(self) -> None:
        with pytest.raises(ValueError):
            _record(status=ReplayStatus.RUNNING, error_message="oops")

    def test_success_without_completed_at_rejected(self) -> None:
        with pytest.raises(ValueError):
            _record(status=ReplayStatus.SUCCESS, stage=ReplayStage.WAREHOUSE, completed_at=None)

    def test_success_with_error_message_rejected(self) -> None:
        with pytest.raises(ValueError):
            _record(
                status=ReplayStatus.SUCCESS,
                stage=ReplayStage.WAREHOUSE,
                completed_at=COMPLETED,
                error_message="should not be here",
            )

    def test_failed_without_completed_at_rejected(self) -> None:
        with pytest.raises(ValueError):
            _record(status=ReplayStatus.FAILED, completed_at=None)

    def test_failed_with_error_message_accepted(self) -> None:
        record = _record(status=ReplayStatus.FAILED, completed_at=COMPLETED, error_message="upstream failure")

        assert record.error_message == "upstream failure"

    def test_failed_with_none_error_message_accepted(self) -> None:
        record = _record(status=ReplayStatus.FAILED, completed_at=COMPLETED, error_message=None)

        assert record.error_message is None


class TestSuccessStageInvariant:
    def test_success_with_warehouse_stage_is_valid(self) -> None:
        record = _record(status=ReplayStatus.SUCCESS, stage=ReplayStage.WAREHOUSE, completed_at=COMPLETED)

        assert record.status is ReplayStatus.SUCCESS
        assert record.stage is ReplayStage.WAREHOUSE

    def test_success_with_source_delivery_stage_rejected(self) -> None:
        with pytest.raises(ValueError):
            _record(status=ReplayStatus.SUCCESS, stage=ReplayStage.SOURCE_DELIVERY, completed_at=COMPLETED)

    def test_success_with_ingestion_stage_rejected(self) -> None:
        with pytest.raises(ValueError):
            _record(status=ReplayStatus.SUCCESS, stage=ReplayStage.INGESTION, completed_at=COMPLETED)

    @pytest.mark.parametrize("stage", [ReplayStage.SOURCE_DELIVERY, ReplayStage.INGESTION, ReplayStage.WAREHOUSE])
    def test_running_remains_valid_at_every_stage(self, stage: ReplayStage) -> None:
        record = _record(status=ReplayStatus.RUNNING, stage=stage, completed_at=None, error_message=None)

        assert record.stage is stage

    @pytest.mark.parametrize("stage", [ReplayStage.SOURCE_DELIVERY, ReplayStage.INGESTION, ReplayStage.WAREHOUSE])
    def test_failed_remains_valid_at_every_stage(self, stage: ReplayStage) -> None:
        record = _record(status=ReplayStatus.FAILED, stage=stage, completed_at=COMPLETED, error_message="boom")

        assert record.stage is stage

    def test_success_classmethod_always_produces_warehouse_stage(self) -> None:
        record = ReplayStateRecord.success(
            run_id="run-5",
            event_id="evt-5",
            delivery_date=DELIVERY_DATE,
            source_object="orders",
            started_at=STARTED,
            completed_at=COMPLETED,
            recorded_at=RECORDED,
        )

        assert record.stage is ReplayStage.WAREHOUSE


class TestReplayStateRecordConvenienceConstructors:
    def test_running_classmethod(self) -> None:
        record = ReplayStateRecord.running(
            run_id="run-2",
            event_id="evt-2",
            delivery_date=DELIVERY_DATE,
            source_object="orders",
            stage=ReplayStage.SOURCE_DELIVERY,
            started_at=STARTED,
            recorded_at=RECORDED,
        )

        assert record.status is ReplayStatus.RUNNING
        assert record.completed_at is None
        assert record.error_message is None

    def test_success_classmethod(self) -> None:
        record = ReplayStateRecord.success(
            run_id="run-3",
            event_id="evt-3",
            delivery_date=DELIVERY_DATE,
            source_object="orders",
            started_at=STARTED,
            completed_at=COMPLETED,
            recorded_at=RECORDED,
        )

        assert record.status is ReplayStatus.SUCCESS
        assert record.stage is ReplayStage.WAREHOUSE
        assert record.completed_at == COMPLETED

    def test_failed_classmethod(self) -> None:
        record = ReplayStateRecord.failed(
            run_id="run-4",
            event_id="evt-4",
            delivery_date=DELIVERY_DATE,
            source_object="orders",
            stage=ReplayStage.INGESTION,
            started_at=STARTED,
            completed_at=COMPLETED,
            recorded_at=RECORDED,
            error_message="connector failed",
        )

        assert record.status is ReplayStatus.FAILED
        assert record.error_message == "connector failed"


class TestDateCompletion:
    EXPECTED = frozenset({"orders", "order_items", "payments", "reviews"})

    def _success(self, source_object: str) -> ReplayStateRecord:
        return _record(
            source_object=source_object,
            status=ReplayStatus.SUCCESS,
            stage=ReplayStage.WAREHOUSE,
            completed_at=COMPLETED,
        )

    def test_complete_date_returns_true(self) -> None:
        records = tuple(self._success(obj) for obj in self.EXPECTED)

        assert is_date_complete(records, self.EXPECTED) is True

    def test_missing_source_returns_false(self) -> None:
        records = tuple(self._success(obj) for obj in ("orders", "order_items", "payments"))

        assert is_date_complete(records, self.EXPECTED) is False

    def test_failed_source_returns_false(self) -> None:
        records = (
            self._success("orders"),
            self._success("order_items"),
            _record(source_object="payments", status=ReplayStatus.FAILED, completed_at=COMPLETED),
            self._success("reviews"),
        )

        assert is_date_complete(records, self.EXPECTED) is False

    def test_running_source_returns_false(self) -> None:
        records = (
            self._success("orders"),
            self._success("order_items"),
            _record(source_object="payments", status=ReplayStatus.RUNNING, completed_at=None),
            self._success("reviews"),
        )

        assert is_date_complete(records, self.EXPECTED) is False

    def test_unexpected_source_returns_false(self) -> None:
        records = tuple(self._success(obj) for obj in ("orders", "order_items", "payments", "reviews", "customers"))

        assert is_date_complete(records, self.EXPECTED) is False

    def test_empty_records_returns_false(self) -> None:
        assert is_date_complete((), self.EXPECTED) is False

    def test_duplicate_source_object_rejected(self) -> None:
        records = (self._success("orders"), self._success("orders"))

        with pytest.raises(ValueError):
            is_date_complete(records, self.EXPECTED)

    def test_empty_expected_source_set_rejected(self) -> None:
        with pytest.raises(ValueError):
            is_date_complete((self._success("orders"),), frozenset())

    def test_non_tuple_records_rejected(self) -> None:
        with pytest.raises(TypeError):
            is_date_complete([self._success("orders")], self.EXPECTED)  # type: ignore[arg-type]

    def test_non_replay_state_record_member_rejected(self) -> None:
        with pytest.raises(TypeError):
            is_date_complete(("not a record",), self.EXPECTED)  # type: ignore[arg-type]

    def test_same_date_accepted(self) -> None:
        same_date = date(2017, 5, 12)
        records = tuple(
            _record(
                source_object=obj,
                delivery_date=same_date,
                status=ReplayStatus.SUCCESS,
                stage=ReplayStage.WAREHOUSE,
                completed_at=COMPLETED,
            )
            for obj in self.EXPECTED
        )

        assert is_date_complete(records, self.EXPECTED) is True

    def test_mixed_delivery_dates_rejected(self) -> None:
        day_one = date(2017, 5, 12)
        day_two = date(2017, 5, 13)
        records = (
            _record(source_object="orders", delivery_date=day_one, status=ReplayStatus.SUCCESS, stage=ReplayStage.WAREHOUSE, completed_at=COMPLETED),
            _record(source_object="order_items", delivery_date=day_one, status=ReplayStatus.SUCCESS, stage=ReplayStage.WAREHOUSE, completed_at=COMPLETED),
            _record(source_object="payments", delivery_date=day_two, status=ReplayStatus.SUCCESS, stage=ReplayStage.WAREHOUSE, completed_at=COMPLETED),
            _record(source_object="reviews", delivery_date=day_two, status=ReplayStatus.SUCCESS, stage=ReplayStage.WAREHOUSE, completed_at=COMPLETED),
        )

        with pytest.raises(ValueError):
            is_date_complete(records, self.EXPECTED)

    def test_mixed_dates_raises_not_false(self) -> None:
        # Explicitly distinguishes malformed input (raise) from a
        # legitimately incomplete date (False).
        day_one = date(2017, 5, 12)
        day_two = date(2017, 5, 13)
        records = (
            _record(source_object="orders", delivery_date=day_one, status=ReplayStatus.SUCCESS, stage=ReplayStage.WAREHOUSE, completed_at=COMPLETED),
            _record(source_object="order_items", delivery_date=day_two, status=ReplayStatus.SUCCESS, stage=ReplayStage.WAREHOUSE, completed_at=COMPLETED),
        )

        with pytest.raises(ValueError, match="delivery_date"):
            is_date_complete(records, self.EXPECTED)


class TestReplayStateStoreAbstraction:
    def test_cannot_be_instantiated_directly(self) -> None:
        with pytest.raises(TypeError):
            ReplayStateStore()  # type: ignore[abstract]

    def test_concrete_subclass_satisfies_the_contract(self) -> None:
        @final
        class _InMemoryStore(ReplayStateStore):
            def __init__(self) -> None:
                self._events: list[ReplayStateRecord] = []

            def append(self, record: ReplayStateRecord) -> None:
                self._events.append(record)

            def get_history(self, delivery_date: date, source_object: str) -> tuple[ReplayStateRecord, ...]:
                matches = [e for e in self._events if e.delivery_date == delivery_date and e.source_object == source_object]
                return tuple(sorted(matches, key=lambda e: e.recorded_at))

            def get_latest(self, delivery_date: date, source_object: str) -> ReplayStateRecord | None:
                history = self.get_history(delivery_date, source_object)
                return history[-1] if history else None

            def get_latest_for_date(self, delivery_date: date) -> tuple[ReplayStateRecord, ...]:
                by_source: dict[str, ReplayStateRecord] = {}
                for event in self._events:
                    if event.delivery_date != delivery_date:
                        continue
                    current = by_source.get(event.source_object)
                    if current is None or event.recorded_at > current.recorded_at:
                        by_source[event.source_object] = event
                return tuple(by_source[key] for key in sorted(by_source))

            def get_completed_for_date(self, delivery_date: date) -> tuple[ReplayStateRecord, ...]:
                by_source: dict[str, ReplayStateRecord] = {}
                for event in self._events:
                    if event.delivery_date != delivery_date or event.status is not ReplayStatus.SUCCESS:
                        continue
                    current = by_source.get(event.source_object)
                    if current is None or event.recorded_at > current.recorded_at:
                        by_source[event.source_object] = event
                return tuple(by_source[key] for key in sorted(by_source))

        store = _InMemoryStore()
        assert isinstance(store, ReplayStateStore)
        assert store.get_latest(DELIVERY_DATE, "orders") is None
        assert store.get_completed_for_date(DELIVERY_DATE) == ()

        running = _record(status=ReplayStatus.RUNNING)
        store.append(running)
        assert store.get_latest(DELIVERY_DATE, "orders") == running
        assert store.get_history(DELIVERY_DATE, "orders") == (running,)
        assert store.get_latest_for_date(DELIVERY_DATE) == (running,)
        assert store.get_completed_for_date(DELIVERY_DATE) == ()


class TestLogicalCompletionSemantics:
    """Exercises the generic monotonic-completion contract via a minimal in-memory store."""

    @staticmethod
    def _make_store() -> ReplayStateStore:
        @final
        class _InMemoryStore(ReplayStateStore):
            def __init__(self) -> None:
                self.events: list[ReplayStateRecord] = []

            def append(self, record: ReplayStateRecord) -> None:
                self.events.append(record)

            def get_history(self, delivery_date: date, source_object: str) -> tuple[ReplayStateRecord, ...]:
                matches = [e for e in self.events if e.delivery_date == delivery_date and e.source_object == source_object]
                return tuple(sorted(matches, key=lambda e: e.recorded_at))

            def get_latest(self, delivery_date: date, source_object: str) -> ReplayStateRecord | None:
                history = self.get_history(delivery_date, source_object)
                return history[-1] if history else None

            def get_latest_for_date(self, delivery_date: date) -> tuple[ReplayStateRecord, ...]:
                by_source: dict[str, ReplayStateRecord] = {}
                for event in self.events:
                    if event.delivery_date != delivery_date:
                        continue
                    current = by_source.get(event.source_object)
                    if current is None or event.recorded_at >= current.recorded_at:
                        by_source[event.source_object] = event
                return tuple(by_source[key] for key in sorted(by_source))

            def get_completed_for_date(self, delivery_date: date) -> tuple[ReplayStateRecord, ...]:
                by_source: dict[str, ReplayStateRecord] = {}
                for event in self.events:
                    if event.delivery_date != delivery_date or event.status is not ReplayStatus.SUCCESS:
                        continue
                    current = by_source.get(event.source_object)
                    if current is None or event.recorded_at >= current.recorded_at:
                        by_source[event.source_object] = event
                return tuple(by_source[key] for key in sorted(by_source))

        return _InMemoryStore()

    def test_completion_result_contains_only_ever_succeeded_sources(self) -> None:
        store = self._make_store()
        store.append(_record(source_object="orders", status=ReplayStatus.RUNNING))

        assert store.get_completed_for_date(DELIVERY_DATE) == ()

    def test_later_failed_event_does_not_erase_previous_success(self) -> None:
        store = self._make_store()
        success = _record(
            source_object="orders",
            event_id="evt-success",
            run_id="run-a",
            status=ReplayStatus.SUCCESS,
            stage=ReplayStage.WAREHOUSE,
            completed_at=COMPLETED,
        )
        later_failure = _record(
            source_object="orders",
            event_id="evt-failure",
            run_id="run-b",
            status=ReplayStatus.FAILED,
            stage=ReplayStage.INGESTION,
            completed_at=COMPLETED,
            recorded_at=LATER_RECORDED,
        )
        store.append(success)
        store.append(later_failure)

        assert store.get_latest(DELIVERY_DATE, "orders") == later_failure
        completed = store.get_completed_for_date(DELIVERY_DATE)
        assert len(completed) == 1
        assert completed[0].source_object == "orders"
        assert completed[0].status is ReplayStatus.SUCCESS
        assert completed[0].event_id == "evt-success"

    def test_later_running_event_does_not_erase_previous_success(self) -> None:
        store = self._make_store()
        success = _record(
            source_object="payments",
            event_id="evt-success",
            status=ReplayStatus.SUCCESS,
            stage=ReplayStage.WAREHOUSE,
            completed_at=COMPLETED,
        )
        later_running = _record(
            source_object="payments",
            event_id="evt-running",
            status=ReplayStatus.RUNNING,
        )
        store.append(success)
        store.append(later_running)

        completed = store.get_completed_for_date(DELIVERY_DATE)
        assert len(completed) == 1
        assert completed[0].status is ReplayStatus.SUCCESS

    def test_multiple_success_attempts_return_most_recent(self) -> None:
        store = self._make_store()
        first_success = _record(
            source_object="reviews",
            event_id="evt-first",
            status=ReplayStatus.SUCCESS,
            stage=ReplayStage.WAREHOUSE,
            completed_at=COMPLETED,
            recorded_at=RECORDED,
        )
        second_success = _record(
            source_object="reviews",
            event_id="evt-second",
            status=ReplayStatus.SUCCESS,
            stage=ReplayStage.WAREHOUSE,
            completed_at=COMPLETED,
            recorded_at=LATER_RECORDED,
        )
        store.append(first_success)
        store.append(second_success)

        completed = store.get_completed_for_date(DELIVERY_DATE)
        assert len(completed) == 1
        assert completed[0].event_id == "evt-second"

    def test_source_that_never_succeeded_is_absent(self) -> None:
        store = self._make_store()
        store.append(_record(source_object="orders", status=ReplayStatus.RUNNING))
        store.append(
            _record(
                source_object="orders",
                event_id="evt-2",
                status=ReplayStatus.FAILED,
                completed_at=COMPLETED,
            )
        )

        assert store.get_completed_for_date(DELIVERY_DATE) == ()


class TestRunId:
    def test_valid_run_id_accepted(self) -> None:
        record = _record(run_id="run-valid")

        assert record.run_id == "run-valid"

    def test_blank_run_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            _record(run_id="   ")

    def test_non_string_run_id_rejected(self) -> None:
        with pytest.raises(TypeError):
            _record(run_id=12345)

    def test_running_constructor_carries_run_id(self) -> None:
        record = ReplayStateRecord.running(
            run_id="run-abc",
            event_id="evt-a",
            delivery_date=DELIVERY_DATE,
            source_object="orders",
            stage=ReplayStage.INGESTION,
            started_at=STARTED,
            recorded_at=RECORDED,
        )

        assert record.run_id == "run-abc"

    def test_success_constructor_carries_run_id(self) -> None:
        record = ReplayStateRecord.success(
            run_id="run-abc",
            event_id="evt-b",
            delivery_date=DELIVERY_DATE,
            source_object="orders",
            started_at=STARTED,
            completed_at=COMPLETED,
            recorded_at=RECORDED,
        )

        assert record.run_id == "run-abc"

    def test_failed_constructor_carries_run_id(self) -> None:
        record = ReplayStateRecord.failed(
            run_id="run-abc",
            event_id="evt-c",
            delivery_date=DELIVERY_DATE,
            source_object="orders",
            stage=ReplayStage.WAREHOUSE,
            started_at=STARTED,
            completed_at=COMPLETED,
            recorded_at=RECORDED,
        )

        assert record.run_id == "run-abc"

    def test_multiple_events_may_share_one_run_id(self) -> None:
        running = _record(run_id="run-xyz", event_id="evt-1", status=ReplayStatus.RUNNING)
        success = _record(
            run_id="run-xyz",
            event_id="evt-2",
            status=ReplayStatus.SUCCESS,
            stage=ReplayStage.WAREHOUSE,
            completed_at=COMPLETED,
        )

        assert running.run_id == success.run_id

    def test_event_ids_remain_distinct_across_shared_run_id(self) -> None:
        running = _record(run_id="run-xyz", event_id="evt-1", status=ReplayStatus.RUNNING)
        success = _record(
            run_id="run-xyz",
            event_id="evt-2",
            status=ReplayStatus.SUCCESS,
            stage=ReplayStage.WAREHOUSE,
            completed_at=COMPLETED,
        )

        assert running.event_id != success.event_id

    def test_same_logical_source_across_different_run_ids_remains_valid(self) -> None:
        # (delivery_date, source_object) is the logical source identity;
        # different run_ids for the same pair represent separate attempts
        # and must both construct without conflict.
        attempt_a = _record(run_id="run-a", event_id="evt-a", status=ReplayStatus.FAILED, completed_at=COMPLETED)
        attempt_b = _record(
            run_id="run-b",
            event_id="evt-b",
            status=ReplayStatus.SUCCESS,
            stage=ReplayStage.WAREHOUSE,
            completed_at=COMPLETED,
        )

        assert attempt_a.delivery_date == attempt_b.delivery_date
        assert attempt_a.source_object == attempt_b.source_object
        assert attempt_a.run_id != attempt_b.run_id


class TestLayerBoundaries:
    def test_state_module_has_no_bigquery_or_pipeline_dependency(self) -> None:
        source_text = Path(inspect.getfile(state_module)).read_text(encoding="utf-8")
        import_lines = [line for line in source_text.splitlines() if line.startswith(("import ", "from "))]
        import_block = "\n".join(import_lines)

        assert "google" not in import_block
        assert "bigquery" not in import_block
        assert "storage" not in import_block
        assert "connectors" not in import_block
        assert "simulation" not in import_block
        assert "sources" not in import_block