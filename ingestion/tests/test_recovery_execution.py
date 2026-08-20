"""Unit tests for mercury_ingestion.orchestration.recovery_execution.

Fully offline: a fake GCS-shaped StorageManager writes to a temp
directory (real, no network), and only the BigQuery client boundary is
faked, matching the established pattern in test_historical_replay.py
and test_security_regression.py.
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import pytest
from google.api_core import exceptions as gcs_exceptions

from mercury_ingestion.common.metadata import IngestionStatus
from mercury_ingestion.common.storage import StorageManager, StorageResult
from mercury_ingestion.orchestration.recovery import RecoveryAction, RecoveryEvidence, RecoveryPlan, RecoveryPlanner
from mercury_ingestion.orchestration.recovery_execution import (
    RecoveryExecutionError,
    RecoveryExecutionOutcome,
    RecoveryExecutionResult,
    RecoveryExecutor,
    RecoveryItemExecutionResult,
    ValidatedRawArtifact,
)
from mercury_ingestion.orchestration.state import ReplayStage, ReplayStateRecord, ReplayStateStore, ReplayStatus
from mercury_ingestion.sources.base import SourceDelivery, SourceDeliveryBatch, SourceDeliveryProvider
from mercury_ingestion.warehouse import bigquery_loader as bigquery_loader_module
from mercury_ingestion.warehouse.bigquery_loader import BigQueryRawLoader

SENTINEL = "sensitive-test-email@example.invalid"
DELIVERY_DATE = date(2017, 5, 19)

ORDERS_HEADER = [
    "order_id",
    "customer_id",
    "order_status",
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]
ORDER_ITEMS_HEADER = ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"]
PAYMENTS_HEADER = ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"]
REVIEWS_HEADER = [
    "review_id",
    "order_id",
    "review_score",
    "review_comment_title",
    "review_comment_message",
    "review_creation_date",
    "review_answer_timestamp",
]


def _write_csv(tmp_path: Path, name: str, header: list[str], row: list[str]) -> Path:
    path = tmp_path / name
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerow(row)
    return path


def _write_source_files(tmp_path: Path) -> dict[str, Path]:
    return {
        "orders": _write_csv(tmp_path, "orders.csv", ORDERS_HEADER, ["o1", "c1", "delivered", "2017-05-01 10:00:00", "", "", "", ""]),
        "order_items": _write_csv(tmp_path, "order_items.csv", ORDER_ITEMS_HEADER, ["o1", "1", "p1", "s1", "", "29.90", "8.50"]),
        "payments": _write_csv(tmp_path, "payments.csv", PAYMENTS_HEADER, ["o1", "1", "voucher", "1", "20.00"]),
        "reviews": _write_csv(tmp_path, "reviews.csv", REVIEWS_HEADER, ["r1", "o1", "5", "great", "loved it", "2017-05-01", "2017-05-02"]),
    }


def _daily_batch(
    paths: dict[str, Path], delivery_date: date, only: set[str] | None = None, ingestion_date: date | None = None
) -> SourceDeliveryBatch:
    source_objects = only if only is not None else set(paths)
    deliveries = tuple(
        SourceDelivery(source_object=obj, path=paths[obj], delivery_date=delivery_date, record_count=1)
        for obj in ("orders", "order_items", "payments", "reviews")
        if obj in source_objects
    )
    return SourceDeliveryBatch(deliveries=deliveries, delivery_date=delivery_date, ingestion_date=ingestion_date)


# --- Fake BigQuery client boundary (offline, no network) -------------------


class _FakeBQJob:
    def __init__(self, output_rows: int, job_id: str, raise_exc: BaseException | None) -> None:
        self.output_rows = output_rows
        self.job_id = job_id
        self._raise_exc = raise_exc

    def result(self) -> "_FakeBQJob":
        if self._raise_exc is not None:
            raise self._raise_exc
        return self


class _FakeBigQueryClient:
    def __init__(self, project: str | None = None, location: str | None = None, **kwargs: object) -> None:
        self.load_calls: list[dict[str, object]] = []
        self.raise_for_destination: dict[str, BaseException] = {}
        self._job_counter = 0

    def load_table_from_uri(
        self,
        source_uris: object,
        destination: object,
        *,
        job_config: object = None,
        location: str | None = None,
        **kwargs: object,
    ) -> _FakeBQJob:
        self._job_counter += 1
        self.load_calls.append({"source_uris": source_uris, "destination": destination})
        raise_exc = self.raise_for_destination.get(str(destination))
        return _FakeBQJob(output_rows=1, job_id=f"job-{self._job_counter}", raise_exc=raise_exc)


@pytest.fixture(autouse=True)
def _fake_bigquery_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bigquery_loader_module.bigquery, "Client", _FakeBigQueryClient)


def _make_bigquery_loader() -> BigQueryRawLoader:
    return BigQueryRawLoader(project_id="mercury-data-platform-dev", dataset_id="raw")


class _FakeGcsStorageManager(StorageManager):
    def __init__(self, local_root: Path, bucket_name: str = "mercury-data-platform-dev-raw-01") -> None:
        self.local_root = local_root
        self.bucket_name = bucket_name
        self._landed_objects: set[str] = set()

    def save_file(self, source_file: Path, source_system: str, source_object: str, ingestion_date: date) -> StorageResult:
        object_name = f"raw/{source_system}/{source_object}/ingestion_date={ingestion_date.isoformat()}/{source_file.name}"
        if object_name in self._landed_objects:
            raise FileExistsError(f"destination object already exists: gs://{self.bucket_name}/{object_name}")
        content = source_file.read_bytes()
        destination_path = self.local_root / object_name
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_bytes(content)
        self._landed_objects.add(object_name)
        return StorageResult(
            landing_path=f"gs://{self.bucket_name}/{object_name}",
            checksum=hashlib.sha256(content).hexdigest(),
            file_size_bytes=len(content),
        )


class _RaisingSaveStorageManager(StorageManager):
    def save_file(self, source_file: Path, source_system: str, source_object: str, ingestion_date: date) -> StorageResult:
        raise RuntimeError(f"disk full while landing: {SENTINEL}")


class _NoOpStorageManager(StorageManager):
    """A StorageManager whose save_file() must never be invoked."""

    def save_file(self, source_file: Path, source_system: str, source_object: str, ingestion_date: date) -> StorageResult:
        raise AssertionError("save_file() must never be called for a malformed request")


class _StubSourceProvider(SourceDeliveryProvider):
    def __init__(self, batch: SourceDeliveryBatch | None = None) -> None:
        self._batch = batch
        self.call_count = 0
        self.fail_with: Exception | None = None

    def get_initial_delivery(self) -> SourceDeliveryBatch:  # pragma: no cover - unused
        raise NotImplementedError

    def get_daily_delivery(self, delivery_date: date) -> SourceDeliveryBatch:
        self.call_count += 1
        if self.fail_with is not None:
            raise self.fail_with
        return self._batch


class _AssertNeverCalledProvider(SourceDeliveryProvider):
    def get_initial_delivery(self) -> SourceDeliveryBatch:  # pragma: no cover - unused
        raise NotImplementedError

    def get_daily_delivery(self, delivery_date: date) -> SourceDeliveryBatch:
        raise AssertionError("source_provider.get_daily_delivery() must never be called for this plan")


class _InMemoryReplayStateStore(ReplayStateStore):
    def __init__(self) -> None:
        self.events: list[ReplayStateRecord] = []
        self.fail_when: Callable[[ReplayStateRecord], bool] | None = None

    def append(self, record: ReplayStateRecord) -> None:
        if self.fail_when is not None and self.fail_when(record):
            raise RuntimeError(f"simulated state-store failure containing {SENTINEL}")
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


class _AssertNeverAppendedStore(ReplayStateStore):
    def append(self, record: ReplayStateRecord) -> None:
        raise AssertionError("replay_state_store.append() must never be called for a malformed request")

    def get_history(self, delivery_date: date, source_object: str) -> tuple[ReplayStateRecord, ...]:
        return ()

    def get_latest(self, delivery_date: date, source_object: str) -> ReplayStateRecord | None:
        return None

    def get_latest_for_date(self, delivery_date: date) -> tuple[ReplayStateRecord, ...]:
        return ()

    def get_completed_for_date(self, delivery_date: date) -> tuple[ReplayStateRecord, ...]:
        return ()


def _make_executor(
    tmp_path: Path,
    *,
    storage_manager: StorageManager | None = None,
    source_provider: SourceDeliveryProvider | None = None,
    replay_state_store: ReplayStateStore | None = None,
) -> tuple[RecoveryExecutor, ReplayStateStore]:
    store = replay_state_store if replay_state_store is not None else _InMemoryReplayStateStore()
    executor = RecoveryExecutor(
        source_provider=source_provider or _AssertNeverCalledProvider(),
        storage_manager=storage_manager or _FakeGcsStorageManager(tmp_path / "bucket"),
        bigquery_loader=_make_bigquery_loader(),
        replay_state_store=store,
    )
    return executor, store


def _evidence(**overrides: object) -> RecoveryEvidence:
    fields = {
        "delivery_date": DELIVERY_DATE,
        "source_object": "orders",
        "logical_completion": False,
        "valid_gcs_raw": False,
        "bigquery_raw_present": False,
    }
    fields.update(overrides)
    return RecoveryEvidence(**fields)  # type: ignore[arg-type]


def _artifact(**overrides: object) -> ValidatedRawArtifact:
    fields = {
        "source_object": "payments",
        "delivery_date": DELIVERY_DATE,
        "gcs_uri": "gs://mercury-data-platform-dev-raw-01/raw/payment_platform/payments/ingestion_date=2017-05-19/payments.csv",
    }
    fields.update(overrides)
    return ValidatedRawArtifact(**fields)  # type: ignore[arg-type]


def _plan(*evidence: RecoveryEvidence) -> RecoveryPlan:
    return RecoveryPlanner().plan(DELIVERY_DATE, evidence)


class TestRecoveryExecutionOutcome:
    def test_exact_values(self) -> None:
        assert RecoveryExecutionOutcome.SKIPPED.value == "skipped"
        assert RecoveryExecutionOutcome.SUCCEEDED.value == "succeeded"
        assert RecoveryExecutionOutcome.FAILED.value == "failed"
        assert RecoveryExecutionOutcome.BLOCKED.value == "blocked"

    def test_old_success_value_no_longer_valid(self) -> None:
        with pytest.raises(ValueError):
            RecoveryExecutionOutcome("success")


class TestValidatedRawArtifact:
    def test_valid_construction(self) -> None:
        assert _artifact().gcs_uri.startswith("gs://")

    def test_is_immutable(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            _artifact().gcs_uri = "gs://other"  # type: ignore[misc]

    def test_blank_source_object_rejected(self) -> None:
        with pytest.raises(ValueError):
            _artifact(source_object="   ")

    def test_invalid_delivery_date_rejected(self) -> None:
        with pytest.raises(TypeError):
            _artifact(delivery_date="2017-05-19")

    def test_blank_gcs_uri_rejected(self) -> None:
        with pytest.raises(ValueError):
            _artifact(gcs_uri="")

    def test_non_gs_uri_rejected(self) -> None:
        with pytest.raises(ValueError):
            _artifact(gcs_uri="https://example.com/payments.csv")


class TestRecoveryItemExecutionResultNoDetailField:
    def test_no_detail_field_exists(self) -> None:
        field_names = {f.name for f in dataclasses.fields(RecoveryItemExecutionResult)}
        assert "detail" not in field_names

    def test_uses_planned_action_field_name(self) -> None:
        field_names = {f.name for f in dataclasses.fields(RecoveryItemExecutionResult)}
        assert "planned_action" in field_names
        assert "action" not in field_names


class TestRecoveryItemExecutionResultInvariants:
    def test_skip_valid(self) -> None:
        result = RecoveryItemExecutionResult(
            source_object="orders", planned_action=RecoveryAction.SKIP, outcome=RecoveryExecutionOutcome.SKIPPED
        )
        assert result.ingestion_result is None
        assert result.warehouse_result is None

    def test_is_immutable(self) -> None:
        result = RecoveryItemExecutionResult(
            source_object="orders", planned_action=RecoveryAction.SKIP, outcome=RecoveryExecutionOutcome.SKIPPED
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.outcome = RecoveryExecutionOutcome.BLOCKED  # type: ignore[misc]

    def test_skip_with_wrong_outcome_rejected(self) -> None:
        with pytest.raises(ValueError):
            RecoveryItemExecutionResult(
                source_object="orders", planned_action=RecoveryAction.SKIP, outcome=RecoveryExecutionOutcome.SUCCEEDED
            )

    def test_reconcile_valid(self) -> None:
        result = RecoveryItemExecutionResult(
            source_object="reviews", planned_action=RecoveryAction.RECONCILE, outcome=RecoveryExecutionOutcome.BLOCKED
        )
        assert result.outcome is RecoveryExecutionOutcome.BLOCKED

    def test_manual_review_valid(self) -> None:
        result = RecoveryItemExecutionResult(
            source_object="reviews", planned_action=RecoveryAction.MANUAL_REVIEW, outcome=RecoveryExecutionOutcome.BLOCKED
        )
        assert result.outcome is RecoveryExecutionOutcome.BLOCKED

    def test_blocked_does_not_imply_failed(self) -> None:
        with pytest.raises(ValueError):
            RecoveryItemExecutionResult(
                source_object="reviews", planned_action=RecoveryAction.RECONCILE, outcome=RecoveryExecutionOutcome.FAILED
            )

    def test_load_only_success_requires_warehouse_result(self) -> None:
        with pytest.raises(ValueError):
            RecoveryItemExecutionResult(
                source_object="payments",
                planned_action=RecoveryAction.LOAD_ONLY,
                outcome=RecoveryExecutionOutcome.SUCCEEDED,
                warehouse_result=None,
            )

    def test_load_only_failed_must_not_carry_warehouse_result(self, tmp_path: Path) -> None:
        executor, _ = _make_executor(tmp_path)
        plan = _plan(_evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False))
        result = executor.execute_plan(plan, [_artifact()])
        real_warehouse_result = result.items[0].warehouse_result
        assert real_warehouse_result is not None

        with pytest.raises(ValueError):
            RecoveryItemExecutionResult(
                source_object="payments",
                planned_action=RecoveryAction.LOAD_ONLY,
                outcome=RecoveryExecutionOutcome.FAILED,
                warehouse_result=real_warehouse_result,
            )

    def test_ingest_and_load_succeeded_requires_both_results(self) -> None:
        with pytest.raises(ValueError):
            RecoveryItemExecutionResult(
                source_object="orders",
                planned_action=RecoveryAction.INGEST_AND_LOAD,
                outcome=RecoveryExecutionOutcome.SUCCEEDED,
                ingestion_result=None,
                warehouse_result=None,
            )

    def test_ingest_and_load_failed_must_not_carry_warehouse_result(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        provider = _StubSourceProvider(_daily_batch(paths, DELIVERY_DATE, {"orders"}))
        executor, _ = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(_evidence(source_object="orders", logical_completion=False))
        ingest_result = executor.execute_plan(plan)

        load_only_result = executor.execute_plan(
            _plan(_evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False)),
            [_artifact()],
        )
        real_warehouse_result = load_only_result.items[0].warehouse_result

        with pytest.raises(ValueError):
            RecoveryItemExecutionResult(
                source_object="orders",
                planned_action=RecoveryAction.INGEST_AND_LOAD,
                outcome=RecoveryExecutionOutcome.FAILED,
                ingestion_result=ingest_result.items[0].ingestion_result,
                warehouse_result=real_warehouse_result,
            )


class TestRecoveryExecutionResultShape:
    def test_includes_run_id(self) -> None:
        result = RecoveryExecutionResult(delivery_date=DELIVERY_DATE, run_id="run-1", items=(), date_complete=False)
        assert result.run_id == "run-1"

    def test_includes_date_complete(self) -> None:
        result = RecoveryExecutionResult(delivery_date=DELIVERY_DATE, run_id="run-1", items=(), date_complete=True)
        assert result.date_complete is True

    def test_is_immutable(self) -> None:
        result = RecoveryExecutionResult(delivery_date=DELIVERY_DATE, run_id="run-1", items=(), date_complete=False)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.run_id = "other"  # type: ignore[misc]

    def test_blank_run_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            RecoveryExecutionResult(delivery_date=DELIVERY_DATE, run_id="   ", items=(), date_complete=False)

    def test_invalid_delivery_date_rejected(self) -> None:
        with pytest.raises(TypeError):
            RecoveryExecutionResult(delivery_date="2017-05-19", run_id="run-1", items=(), date_complete=False)  # type: ignore[arg-type]

    def test_non_tuple_items_rejected(self) -> None:
        with pytest.raises(TypeError):
            RecoveryExecutionResult(delivery_date=DELIVERY_DATE, run_id="run-1", items=[], date_complete=False)  # type: ignore[arg-type]

    def test_non_bool_date_complete_rejected(self) -> None:
        with pytest.raises(TypeError):
            RecoveryExecutionResult(delivery_date=DELIVERY_DATE, run_id="run-1", items=(), date_complete=1)  # type: ignore[arg-type]

    def test_duplicate_source_object_rejected(self) -> None:
        item = RecoveryItemExecutionResult(
            source_object="orders", planned_action=RecoveryAction.SKIP, outcome=RecoveryExecutionOutcome.SKIPPED
        )
        with pytest.raises(ValueError):
            RecoveryExecutionResult(delivery_date=DELIVERY_DATE, run_id="run-1", items=(item, item), date_complete=False)


class TestPreExecutionValidation:
    def test_wrong_artifact_delivery_date_rejected(self, tmp_path: Path) -> None:
        executor, _ = _make_executor(tmp_path, storage_manager=_NoOpStorageManager(), replay_state_store=_AssertNeverAppendedStore())
        plan = _plan(_evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False))
        wrong_date_artifact = _artifact(delivery_date=date(2017, 5, 20))

        with pytest.raises(ValueError, match="delivery_date"):
            executor.execute_plan(plan, [wrong_date_artifact])

    def test_duplicate_artifact_sources_rejected(self, tmp_path: Path) -> None:
        executor, _ = _make_executor(tmp_path, storage_manager=_NoOpStorageManager(), replay_state_store=_AssertNeverAppendedStore())
        plan = _plan(_evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False))

        with pytest.raises(ValueError, match="duplicate"):
            executor.execute_plan(plan, [_artifact(), _artifact()])

    def test_missing_load_only_artifact_rejected(self, tmp_path: Path) -> None:
        executor, _ = _make_executor(tmp_path, storage_manager=_NoOpStorageManager(), replay_state_store=_AssertNeverAppendedStore())
        plan = _plan(_evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False))

        with pytest.raises(ValueError, match="LOAD_ONLY"):
            executor.execute_plan(plan)

    def test_extra_artifact_for_skip_rejected(self, tmp_path: Path) -> None:
        executor, _ = _make_executor(tmp_path, storage_manager=_NoOpStorageManager(), replay_state_store=_AssertNeverAppendedStore())
        plan = _plan(_evidence(source_object="orders", logical_completion=True))

        with pytest.raises(ValueError, match="non-LOAD_ONLY"):
            executor.execute_plan(plan, [_artifact(source_object="orders")])

    def test_extra_artifact_for_ingest_and_load_rejected(self, tmp_path: Path) -> None:
        executor, _ = _make_executor(tmp_path, storage_manager=_NoOpStorageManager(), replay_state_store=_AssertNeverAppendedStore())
        plan = _plan(_evidence(source_object="orders", logical_completion=False))

        with pytest.raises(ValueError, match="non-LOAD_ONLY"):
            executor.execute_plan(plan, [_artifact(source_object="orders")])

    def test_malformed_request_calls_source_provider_zero_times(self, tmp_path: Path) -> None:
        provider = _AssertNeverCalledProvider()
        executor, _ = _make_executor(
            tmp_path, storage_manager=_NoOpStorageManager(), source_provider=provider, replay_state_store=_AssertNeverAppendedStore()
        )
        plan = _plan(_evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False))

        with pytest.raises(ValueError):
            executor.execute_plan(plan)

    def test_malformed_request_appends_replay_state_zero_times(self, tmp_path: Path) -> None:
        store = _AssertNeverAppendedStore()
        executor, _ = _make_executor(tmp_path, storage_manager=_NoOpStorageManager(), replay_state_store=store)
        plan = _plan(_evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False))

        with pytest.raises(ValueError):
            executor.execute_plan(plan)

    def test_malformed_request_performs_zero_bigquery_loads(self, tmp_path: Path) -> None:
        executor, _ = _make_executor(tmp_path, storage_manager=_NoOpStorageManager(), replay_state_store=_AssertNeverAppendedStore())
        plan = _plan(_evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False))

        with pytest.raises(ValueError):
            executor.execute_plan(plan)

        assert executor.bigquery_loader._client.load_calls == []


class TestSourceProviderUsage:
    def test_not_called_for_plan_with_no_ingest_and_load(self, tmp_path: Path) -> None:
        provider = _AssertNeverCalledProvider()
        executor, _ = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(
            _evidence(source_object="orders", logical_completion=True),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False),
            _evidence(source_object="reviews", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=True),
        )

        executor.execute_plan(plan, [_artifact()])

    def test_multiple_ingest_and_load_items_fetch_batch_once(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        provider = _StubSourceProvider(_daily_batch(paths, DELIVERY_DATE))
        executor, _ = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(
            _evidence(source_object="orders", logical_completion=False),
            _evidence(source_object="order_items", logical_completion=False),
            _evidence(source_object="reviews", logical_completion=False),
        )

        executor.execute_plan(plan)

        assert provider.call_count == 1

    def test_only_required_deliveries_are_executed(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        provider = _StubSourceProvider(_daily_batch(paths, DELIVERY_DATE))
        executor, store = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(
            _evidence(source_object="orders", logical_completion=False),
            _evidence(source_object="payments", logical_completion=True),
        )

        result = executor.execute_plan(plan)

        assert {item.source_object for item in result.items if item.planned_action is RecoveryAction.INGEST_AND_LOAD} == {
            "orders"
        }
        assert {e.source_object for e in store.events} == {"orders"}


class TestDuplicateSourceDeliveryDetection:
    """Item 1 of the ADR-010 Phase 3B final hardening revision.

    A real ``SourceDeliveryBatch`` can never actually contain two
    ``SourceDelivery`` entries sharing one ``source_object`` --
    ``SourceDeliveryBatch.__post_init__`` already unconditionally
    rejects that at construction time. These tests use a duck-typed
    fake batch (a plain object exposing only ``.deliveries``) that
    bypasses that validation, so ``RecoveryExecutor``'s own defense-in-
    depth check can actually be exercised. This does not weaken or
    replace ``SourceDeliveryBatch``'s own guarantee -- it is a second,
    independent safeguard should ``_fetch_deliveries()`` ever receive a
    batch-like object that did not go through that validation.
    """

    @staticmethod
    def _duplicate_batch(paths: dict[str, Path], delivery_date: date, source_object: str) -> SimpleNamespace:
        return SimpleNamespace(
            deliveries=(
                SourceDelivery(source_object=source_object, path=paths[source_object], delivery_date=delivery_date, record_count=1),
                SourceDelivery(source_object=source_object, path=paths[source_object], delivery_date=delivery_date, record_count=1),
            ),
            delivery_date=delivery_date,
            ingestion_date=None,
        )

    def test_duplicate_required_delivery_rejected(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        provider = _StubSourceProvider(self._duplicate_batch(paths, DELIVERY_DATE, "orders"))
        executor, _ = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(_evidence(source_object="orders", logical_completion=False))

        with pytest.raises(RecoveryExecutionError, match="duplicate"):
            executor.execute_plan(plan)

    def test_duplicate_delivery_writes_zero_replay_state_events(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        provider = _StubSourceProvider(self._duplicate_batch(paths, DELIVERY_DATE, "orders"))
        executor, store = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(_evidence(source_object="orders", logical_completion=False))

        with pytest.raises(RecoveryExecutionError):
            executor.execute_plan(plan)

        assert store.events == []

    def test_duplicate_delivery_performs_zero_bigquery_loads(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        provider = _StubSourceProvider(self._duplicate_batch(paths, DELIVERY_DATE, "orders"))
        executor, _ = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(_evidence(source_object="orders", logical_completion=False))

        with pytest.raises(RecoveryExecutionError):
            executor.execute_plan(plan)

        assert executor.bigquery_loader._client.load_calls == []

    def test_duplicate_delivery_performs_zero_connector_or_storage_work(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        provider = _StubSourceProvider(self._duplicate_batch(paths, DELIVERY_DATE, "orders"))
        executor, _ = _make_executor(
            tmp_path, source_provider=provider, storage_manager=_NoOpStorageManager()
        )
        plan = _plan(_evidence(source_object="orders", logical_completion=False))

        with pytest.raises(RecoveryExecutionError):
            executor.execute_plan(plan)  # _NoOpStorageManager raises AssertionError if save_file() is ever called

    def test_duplicate_delivery_for_one_source_does_not_block_unrelated_extra_sources(self, tmp_path: Path) -> None:
        # The rule is scoped to each *required* source_object -- extra,
        # unrelated deliveries elsewhere in the batch are ignored, not
        # rejected, even if the batch also happens to contain duplicates
        # for a source_object nothing in the plan actually needs.
        paths = _write_source_files(tmp_path)
        batch = SimpleNamespace(
            deliveries=(
                SourceDelivery(source_object="orders", path=paths["orders"], delivery_date=DELIVERY_DATE, record_count=1),
                SourceDelivery(source_object="reviews", path=paths["reviews"], delivery_date=DELIVERY_DATE, record_count=1),
                SourceDelivery(source_object="reviews", path=paths["reviews"], delivery_date=DELIVERY_DATE, record_count=1),
            ),
            delivery_date=DELIVERY_DATE,
            ingestion_date=None,
        )
        provider = _StubSourceProvider(batch)
        executor, store = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(_evidence(source_object="orders", logical_completion=False))  # reviews not requested at all

        result = executor.execute_plan(plan)

        assert result.items[0].outcome is RecoveryExecutionOutcome.SUCCEEDED


class TestReplayStateEventSequences:
    def test_successful_ingest_and_load_appends_three_events(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        provider = _StubSourceProvider(_daily_batch(paths, DELIVERY_DATE, {"orders"}))
        executor, store = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(_evidence(source_object="orders", logical_completion=False))

        executor.execute_plan(plan)

        events = [e for e in store.events if e.source_object == "orders"]
        assert [(e.status, e.stage) for e in events] == [
            (ReplayStatus.RUNNING, ReplayStage.INGESTION),
            (ReplayStatus.RUNNING, ReplayStage.WAREHOUSE),
            (ReplayStatus.SUCCESS, ReplayStage.WAREHOUSE),
        ]

    def test_ingest_and_load_uses_provider_ingestion_date_for_connector_not_bigquery(self, tmp_path: Path) -> None:
        """Proves INGEST_AND_LOAD keeps delivery_date/ingestion_date separated.

        Mirrors what an Olist-backed provider actually returns for a
        daily batch: a distinct ``ingestion_date`` (delivery_date + 1
        day). Connector/GCS work must use that supplied ingestion_date,
        while replay-state identity and BigQuery's ``partition_date``
        must continue to use the plan's business ``delivery_date`` (D),
        unchanged.
        """
        paths = _write_source_files(tmp_path)
        ingestion_date = DELIVERY_DATE + timedelta(days=1)
        provider = _StubSourceProvider(
            _daily_batch(paths, DELIVERY_DATE, {"orders"}, ingestion_date=ingestion_date)
        )
        executor, store = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(_evidence(source_object="orders", logical_completion=False))

        result = executor.execute_plan(plan)

        orders_result = next(item for item in result.items if item.source_object == "orders")
        assert orders_result.outcome is RecoveryExecutionOutcome.SUCCEEDED
        # Connector/GCS landing used the provider-supplied ingestion_date.
        assert "ingestion_date=2017-05-20" in orders_result.ingestion_result.metadata.landing_path
        # BigQuery's partition_date is delivery_date (D), not ingestion_date.
        assert orders_result.warehouse_result.partition_date == DELIVERY_DATE
        assert orders_result.warehouse_result.destination.endswith("$20170519")
        # Replay-state identity is delivery_date (D), unchanged.
        assert all(e.delivery_date == DELIVERY_DATE for e in store.events)

    def test_ingestion_failure_appends_running_then_failed_ingestion(self, tmp_path: Path) -> None:
        tmp_missing = tmp_path / "missing.csv"
        batch = SourceDeliveryBatch(
            deliveries=(SourceDelivery(source_object="orders", path=tmp_missing, delivery_date=DELIVERY_DATE, record_count=1),),
            delivery_date=DELIVERY_DATE,
        )
        provider = _StubSourceProvider(batch)
        executor, store = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(_evidence(source_object="orders", logical_completion=False))

        executor.execute_plan(plan)

        events = [e for e in store.events if e.source_object == "orders"]
        assert [(e.status, e.stage) for e in events] == [
            (ReplayStatus.RUNNING, ReplayStage.INGESTION),
            (ReplayStatus.FAILED, ReplayStage.INGESTION),
        ]

    def test_ingestion_failure_performs_no_warehouse_load(self, tmp_path: Path) -> None:
        tmp_missing = tmp_path / "missing.csv"
        batch = SourceDeliveryBatch(
            deliveries=(SourceDelivery(source_object="orders", path=tmp_missing, delivery_date=DELIVERY_DATE, record_count=1),),
            delivery_date=DELIVERY_DATE,
        )
        provider = _StubSourceProvider(batch)
        executor, _ = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(_evidence(source_object="orders", logical_completion=False))

        executor.execute_plan(plan)

        assert executor.bigquery_loader._client.load_calls == []

    def test_warehouse_failure_appends_full_three_event_sequence(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        provider = _StubSourceProvider(_daily_batch(paths, DELIVERY_DATE, {"orders"}))
        executor, store = _make_executor(tmp_path, source_provider=provider)
        executor.bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.orders$20170519"] = (
            gcs_exceptions.ServiceUnavailable("backend down")
        )
        plan = _plan(_evidence(source_object="orders", logical_completion=False))

        executor.execute_plan(plan)

        events = [e for e in store.events if e.source_object == "orders"]
        assert [(e.status, e.stage) for e in events] == [
            (ReplayStatus.RUNNING, ReplayStage.INGESTION),
            (ReplayStatus.RUNNING, ReplayStage.WAREHOUSE),
            (ReplayStatus.FAILED, ReplayStage.WAREHOUSE),
        ]

    def test_successful_load_only_appends_two_events(self, tmp_path: Path) -> None:
        executor, store = _make_executor(tmp_path)
        plan = _plan(_evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False))

        executor.execute_plan(plan, [_artifact()])

        events = [e for e in store.events if e.source_object == "payments"]
        assert [(e.status, e.stage) for e in events] == [
            (ReplayStatus.RUNNING, ReplayStage.WAREHOUSE),
            (ReplayStatus.SUCCESS, ReplayStage.WAREHOUSE),
        ]

    def test_failed_load_only_appends_two_events(self, tmp_path: Path) -> None:
        executor, store = _make_executor(tmp_path)
        executor.bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.payments$20170519"] = (
            gcs_exceptions.Forbidden("no access")
        )
        plan = _plan(_evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False))

        executor.execute_plan(plan, [_artifact()])

        events = [e for e in store.events if e.source_object == "payments"]
        assert [(e.status, e.stage) for e in events] == [
            (ReplayStatus.RUNNING, ReplayStage.WAREHOUSE),
            (ReplayStatus.FAILED, ReplayStage.WAREHOUSE),
        ]

    def test_skip_appends_zero_events(self, tmp_path: Path) -> None:
        executor, store = _make_executor(tmp_path)
        plan = _plan(_evidence(source_object="orders", logical_completion=True))

        executor.execute_plan(plan)

        assert store.events == []

    def test_reconcile_appends_zero_events(self, tmp_path: Path) -> None:
        executor, store = _make_executor(tmp_path)
        plan = _plan(_evidence(source_object="reviews", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=True))

        executor.execute_plan(plan)

        assert store.events == []

    def test_manual_review_appends_zero_events(self, tmp_path: Path) -> None:
        executor, store = _make_executor(tmp_path)
        plan = _plan(_evidence(source_object="reviews", logical_completion=False, valid_gcs_raw=False, bigquery_raw_present=True))

        executor.execute_plan(plan)

        assert store.events == []


class TestRunIdAndEventId:
    def test_one_execute_plan_call_uses_exactly_one_run_id(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        provider = _StubSourceProvider(_daily_batch(paths, DELIVERY_DATE, {"orders"}))
        executor, store = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(
            _evidence(source_object="orders", logical_completion=False),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False),
        )

        result = executor.execute_plan(plan, [_artifact()])

        run_ids = {e.run_id for e in store.events}
        assert len(run_ids) == 1
        assert result.run_id in run_ids

    def test_every_event_id_is_unique(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        provider = _StubSourceProvider(_daily_batch(paths, DELIVERY_DATE, {"orders"}))
        executor, store = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(
            _evidence(source_object="orders", logical_completion=False),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False),
        )

        executor.execute_plan(plan, [_artifact()])

        event_ids = [e.event_id for e in store.events]
        assert len(event_ids) == len(set(event_ids))

    def test_new_run_id_differs_from_latest_attempt_run_id(self, tmp_path: Path) -> None:
        executor, store = _make_executor(tmp_path)
        now = datetime.now(timezone.utc)
        old_attempt = ReplayStateRecord.failed(
            run_id="old-run-id",
            event_id="old-event-id",
            delivery_date=DELIVERY_DATE,
            source_object="payments",
            stage=ReplayStage.WAREHOUSE,
            started_at=now,
            completed_at=now,
            recorded_at=now,
        )
        evidence = _evidence(
            source_object="payments",
            logical_completion=False,
            valid_gcs_raw=True,
            bigquery_raw_present=False,
            latest_attempt=old_attempt,
        )
        plan = _plan(evidence)

        result = executor.execute_plan(plan, [_artifact()])

        new_run_ids = {e.run_id for e in store.events}
        assert "old-run-id" not in new_run_ids
        assert result.run_id != "old-run-id"

    def test_run_id_is_freshly_generated_each_call(self, tmp_path: Path) -> None:
        executor, _ = _make_executor(tmp_path)
        plan = _plan(_evidence(source_object="orders", logical_completion=True))

        first = executor.execute_plan(plan)
        second = executor.execute_plan(plan)

        assert first.run_id != second.run_id


class TestSourceLevelFailureIsolation:
    def test_ingestion_failure_does_not_block_sibling_load_only(self, tmp_path: Path) -> None:
        tmp_missing = tmp_path / "missing.csv"
        batch = SourceDeliveryBatch(
            deliveries=(SourceDelivery(source_object="orders", path=tmp_missing, delivery_date=DELIVERY_DATE, record_count=1),),
            delivery_date=DELIVERY_DATE,
        )
        provider = _StubSourceProvider(batch)
        executor, store = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(
            _evidence(source_object="orders", logical_completion=False),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False),
        )

        result = executor.execute_plan(plan, [_artifact()])

        outcomes = {item.source_object: item.outcome for item in result.items}
        assert outcomes["orders"] is RecoveryExecutionOutcome.FAILED
        assert outcomes["payments"] is RecoveryExecutionOutcome.SUCCEEDED
        payments_events = [e for e in store.events if e.source_object == "payments"]
        assert payments_events[-1].status is ReplayStatus.SUCCESS

    def test_warehouse_failure_does_not_block_sibling_load_only(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        provider = _StubSourceProvider(_daily_batch(paths, DELIVERY_DATE, {"orders"}))
        executor, _ = _make_executor(tmp_path, source_provider=provider)
        executor.bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.orders$20170519"] = (
            gcs_exceptions.ServiceUnavailable("backend down")
        )
        plan = _plan(
            _evidence(source_object="orders", logical_completion=False),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False),
        )

        result = executor.execute_plan(plan, [_artifact()])

        outcomes = {item.source_object: item.outcome for item in result.items}
        assert outcomes["orders"] is RecoveryExecutionOutcome.FAILED
        assert outcomes["payments"] is RecoveryExecutionOutcome.SUCCEEDED


class TestStateStoreFailure:
    def test_append_failure_aborts_immediately(self, tmp_path: Path) -> None:
        store = _InMemoryReplayStateStore()
        store.fail_when = lambda record: True
        executor, _ = _make_executor(tmp_path, replay_state_store=store)
        plan = _plan(_evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False))

        with pytest.raises(RecoveryExecutionError):
            executor.execute_plan(plan, [_artifact()])

    def test_append_failure_prevents_later_sibling_work(self, tmp_path: Path) -> None:
        store = _InMemoryReplayStateStore()
        store.fail_when = lambda record: record.source_object == "orders"
        paths = _write_source_files(tmp_path)
        provider = _StubSourceProvider(_daily_batch(paths, DELIVERY_DATE, {"orders"}))
        executor, _ = _make_executor(tmp_path, source_provider=provider, replay_state_store=store)
        plan = _plan(
            _evidence(source_object="orders", logical_completion=False),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False),
        )

        with pytest.raises(RecoveryExecutionError):
            executor.execute_plan(plan, [_artifact()])

        assert executor.bigquery_loader._client.load_calls == []

    def test_append_failure_preserves_cause(self, tmp_path: Path) -> None:
        store = _InMemoryReplayStateStore()
        store.fail_when = lambda record: True
        executor, _ = _make_executor(tmp_path, replay_state_store=store)
        plan = _plan(_evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False))

        with pytest.raises(RecoveryExecutionError) as exc_info:
            executor.execute_plan(plan, [_artifact()])

        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, RuntimeError)

    def test_append_failure_sentinel_never_leaks(self, tmp_path: Path) -> None:
        store = _InMemoryReplayStateStore()
        store.fail_when = lambda record: True
        executor, _ = _make_executor(tmp_path, replay_state_store=store)
        plan = _plan(_evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False))

        with pytest.raises(RecoveryExecutionError) as exc_info:
            executor.execute_plan(plan, [_artifact()])

        assert SENTINEL not in str(exc_info.value)
        assert SENTINEL in str(exc_info.value.__cause__)


class TestSourceProviderFailure:
    def test_provider_failure_no_source_work_occurred(self, tmp_path: Path) -> None:
        provider = _StubSourceProvider(None)
        provider.fail_with = RuntimeError(f"provider blew up: {SENTINEL}")
        executor, store = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(_evidence(source_object="orders", logical_completion=False))

        with pytest.raises(RecoveryExecutionError):
            executor.execute_plan(plan)

        assert store.events == []
        assert executor.bigquery_loader._client.load_calls == []

    def test_provider_failure_preserves_cause(self, tmp_path: Path) -> None:
        provider = _StubSourceProvider(None)
        provider.fail_with = RuntimeError(f"provider blew up: {SENTINEL}")
        executor, _ = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(_evidence(source_object="orders", logical_completion=False))

        with pytest.raises(RecoveryExecutionError) as exc_info:
            executor.execute_plan(plan)

        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, RuntimeError)

    def test_provider_failure_sentinel_never_leaks(self, tmp_path: Path) -> None:
        provider = _StubSourceProvider(None)
        provider.fail_with = RuntimeError(f"provider blew up: {SENTINEL}")
        executor, _ = _make_executor(tmp_path, source_provider=provider)
        plan = _plan(_evidence(source_object="orders", logical_completion=False))

        with pytest.raises(RecoveryExecutionError) as exc_info:
            executor.execute_plan(plan)

        assert SENTINEL not in str(exc_info.value)
        assert SENTINEL in str(exc_info.value.__cause__)


class TestSecuritySentinelRegression:
    def test_gcs_landing_failure_sentinel_never_leaks_into_replay_state(self, tmp_path: Path) -> None:
        paths = _write_source_files(tmp_path)
        provider = _StubSourceProvider(_daily_batch(paths, DELIVERY_DATE, {"orders"}))
        executor, store = _make_executor(tmp_path, source_provider=provider, storage_manager=_RaisingSaveStorageManager())
        plan = _plan(_evidence(source_object="orders", logical_completion=False))

        executor.execute_plan(plan)

        for event in store.events:
            if event.error_message is not None:
                assert SENTINEL not in event.error_message

    def test_warehouse_failure_sentinel_never_leaks_into_replay_state(self, tmp_path: Path) -> None:
        executor, store = _make_executor(tmp_path)
        executor.bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.payments$20170519"] = (
            gcs_exceptions.Forbidden(f"denied for {SENTINEL}")
        )
        plan = _plan(_evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False))

        executor.execute_plan(plan, [_artifact()])

        for event in store.events:
            if event.error_message is not None:
                assert SENTINEL not in event.error_message
                assert "category=warehouse_load_failed" in event.error_message


class TestDateCompletenessRederivation:
    def test_date_complete_derived_from_get_completed_for_date(self, tmp_path: Path) -> None:
        store = _InMemoryReplayStateStore()
        executor, _ = _make_executor(tmp_path, replay_state_store=store)
        plan = _plan(
            _evidence(source_object="orders", logical_completion=True),
            _evidence(source_object="order_items", logical_completion=True),
            _evidence(source_object="payments", logical_completion=True),
            _evidence(source_object="reviews", logical_completion=True),
        )
        now = datetime.now(timezone.utc)
        for source_object in ("orders", "order_items", "payments", "reviews"):
            store.append(
                ReplayStateRecord.success(
                    run_id="prior-run",
                    event_id=f"evt-{source_object}",
                    delivery_date=DELIVERY_DATE,
                    source_object=source_object,
                    started_at=now,
                    completed_at=now,
                    recorded_at=now,
                )
            )

        result = executor.execute_plan(plan)

        assert result.date_complete is True

    def test_date_incomplete_when_a_source_remains_blocked(self, tmp_path: Path) -> None:
        executor, _ = _make_executor(tmp_path)
        plan = _plan(
            _evidence(source_object="orders", logical_completion=True),
            _evidence(source_object="reviews", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=True),
        )

        result = executor.execute_plan(plan)

        assert result.date_complete is False

    def test_prior_success_remains_complete_after_later_recovery_failure(self, tmp_path: Path) -> None:
        store = _InMemoryReplayStateStore()
        now = datetime.now(timezone.utc)
        for source_object in ("orders", "order_items", "reviews"):
            store.append(
                ReplayStateRecord.success(
                    run_id="prior-run",
                    event_id=f"evt-{source_object}",
                    delivery_date=DELIVERY_DATE,
                    source_object=source_object,
                    started_at=now,
                    completed_at=now,
                    recorded_at=now,
                )
            )

        executor, _ = _make_executor(tmp_path, replay_state_store=store)
        executor.bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.payments$20170519"] = (
            gcs_exceptions.Forbidden("no access")
        )
        plan = _plan(
            _evidence(source_object="orders", logical_completion=True),
            _evidence(source_object="order_items", logical_completion=True),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False),
            _evidence(source_object="reviews", logical_completion=True),
        )

        result = executor.execute_plan(plan, [_artifact()])

        assert result.date_complete is False
        completed = store.get_completed_for_date(DELIVERY_DATE)
        assert {r.source_object for r in completed} == {"orders", "order_items", "reviews"}

    def test_all_four_sources_already_complete_survive_one_later_failed_reattempt(self, tmp_path: Path) -> None:
        """Item 2 of the ADR-010 Phase 3B final hardening revision.

        All four expected sources already have a prior SUCCESS|WAREHOUSE
        record for the date. This recovery execution re-attempts exactly
        one of them (payments, via LOAD_ONLY) and that new attempt
        fails. A later failed recovery attempt must not be able to
        revoke an already logically complete business date:
        date_complete must remain True, and get_completed_for_date()
        must still report all four sources as complete -- the earlier
        SUCCESS record for payments is untouched append-only history,
        not erased by the newer FAILED record sitting alongside it.
        """
        store = _InMemoryReplayStateStore()
        now = datetime.now(timezone.utc)
        for source_object in ("orders", "order_items", "payments", "reviews"):
            store.append(
                ReplayStateRecord.success(
                    run_id="prior-run",
                    event_id=f"evt-{source_object}",
                    delivery_date=DELIVERY_DATE,
                    source_object=source_object,
                    started_at=now,
                    completed_at=now,
                    recorded_at=now,
                )
            )

        executor, _ = _make_executor(tmp_path, replay_state_store=store)
        executor.bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.payments$20170519"] = (
            gcs_exceptions.ServiceUnavailable("backend unavailable during recovery re-attempt")
        )
        # orders/order_items/reviews evidence reflects their genuine
        # completion (SKIP); payments' evidence claims incomplete,
        # forcing this recovery run to re-attempt it despite the prior
        # success already sitting in durable state.
        plan = _plan(
            _evidence(source_object="orders", logical_completion=True),
            _evidence(source_object="order_items", logical_completion=True),
            _evidence(source_object="payments", logical_completion=False, valid_gcs_raw=True, bigquery_raw_present=False),
            _evidence(source_object="reviews", logical_completion=True),
        )

        result = executor.execute_plan(plan, [_artifact()])

        payments_result = next(item for item in result.items if item.source_object == "payments")
        assert payments_result.outcome is RecoveryExecutionOutcome.FAILED  # this attempt genuinely failed

        assert result.date_complete is True  # yet the date remains complete
        completed = store.get_completed_for_date(DELIVERY_DATE)
        assert {r.source_object for r in completed} == {"orders", "order_items", "payments", "reviews"}
        payments_completed = next(r for r in completed if r.source_object == "payments")
        assert payments_completed.run_id == "prior-run"  # the ORIGINAL success record, untouched


class TestRecoveryExecutorConstruction:
    def test_rejects_non_source_provider(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            RecoveryExecutor(
                source_provider=object(),  # type: ignore[arg-type]
                storage_manager=_FakeGcsStorageManager(tmp_path),
                bigquery_loader=_make_bigquery_loader(),
                replay_state_store=_InMemoryReplayStateStore(),
            )

    def test_rejects_non_storage_manager(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            RecoveryExecutor(
                source_provider=_AssertNeverCalledProvider(),
                storage_manager=object(),  # type: ignore[arg-type]
                bigquery_loader=_make_bigquery_loader(),
                replay_state_store=_InMemoryReplayStateStore(),
            )

    def test_rejects_non_bigquery_loader(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            RecoveryExecutor(
                source_provider=_AssertNeverCalledProvider(),
                storage_manager=_FakeGcsStorageManager(tmp_path),
                bigquery_loader=object(),  # type: ignore[arg-type]
                replay_state_store=_InMemoryReplayStateStore(),
            )

    def test_rejects_non_replay_state_store(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            RecoveryExecutor(
                source_provider=_AssertNeverCalledProvider(),
                storage_manager=_FakeGcsStorageManager(tmp_path),
                bigquery_loader=_make_bigquery_loader(),
                replay_state_store=object(),  # type: ignore[arg-type]
            )

    def test_does_not_hard_code_bigquery_replay_state_store(self, tmp_path: Path) -> None:
        from mercury_ingestion.orchestration.bigquery_replay_state import BigQueryReplayStateStore

        executor, _ = _make_executor(tmp_path)
        assert not isinstance(executor.replay_state_store, BigQueryReplayStateStore)
        assert isinstance(executor.replay_state_store, ReplayStateStore)


class TestSharedConnectorBuilder:
    def test_connector_map_defined_exactly_once(self) -> None:
        from mercury_ingestion.orchestration import connector_builder, replay

        assert replay.CONNECTOR_MAP is connector_builder.CONNECTOR_MAP

    def test_historical_replay_runner_uses_shared_builder(self) -> None:
        import inspect

        from mercury_ingestion.orchestration import replay as replay_module

        source_text = Path(inspect.getfile(replay_module)).read_text(encoding="utf-8")
        assert "build_connector(" in source_text

    def test_recovery_executor_uses_shared_builder(self) -> None:
        import inspect

        from mercury_ingestion.orchestration import recovery_execution as recovery_execution_module

        source_text = Path(inspect.getfile(recovery_execution_module)).read_text(encoding="utf-8")
        assert "from mercury_ingestion.orchestration.connector_builder import build_connector" in source_text


class TestNoPhase3CReconciliation:
    def test_module_defines_no_reconciliation_logic(self) -> None:
        import inspect

        from mercury_ingestion.orchestration import recovery_execution as recovery_execution_module

        source_text = Path(inspect.getfile(recovery_execution_module)).read_text(encoding="utf-8")
        assert "def reconcile" not in source_text
        assert "def _reconcile" not in source_text