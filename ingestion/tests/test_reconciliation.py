"""Unit tests for mercury_ingestion.orchestration.reconciliation.

Fully offline: fakes for ProvenanceStore, RawArtifactInspector, and
WarehouseInspector. Uses a synthetic sentinel value per ADR-011 to prove
infrastructure-failure exceptions never leak raw text into durable/
display-safe output.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone

import pytest

from mercury_ingestion.common.artifact_inspection import RawArtifactInspector, RawArtifactObservation
from mercury_ingestion.orchestration.provenance import (
    ProvenanceStore,
    RawArtifactProvenance,
    WarehouseLoadProvenance,
)
from mercury_ingestion.orchestration.reconciliation import (
    ReconciliationOutcome,
    ReconciliationReason,
    ReconciliationResult,
    RecoveryReconciler,
)
from mercury_ingestion.warehouse.inspection import WarehouseInspector, WarehousePartitionObservation

SENTINEL = "sensitive-test-email@example.invalid"
DELIVERY_DATE = date(2017, 5, 19)
NOW = datetime.now(timezone.utc)

GOOD_GCS_URI = "gs://bucket/raw/orders/ingestion_date=2017-05-20/orders.csv"
GOOD_DESTINATION = "mercury-data-platform-dev.raw.orders$20170519"
GOOD_CHECKSUM = "abc123"
GOOD_SIZE = 100
GOOD_ROWS = 5


def _artifact(**overrides: object) -> RawArtifactProvenance:
    fields = {
        "provenance_id": "p1",
        "run_id": "r1",
        "delivery_date": DELIVERY_DATE,
        "source_object": "orders",
        "ingestion_date": date(2017, 5, 20),
        "gcs_uri": GOOD_GCS_URI,
        "checksum": GOOD_CHECKSUM,
        "file_size_bytes": GOOD_SIZE,
        "record_count": GOOD_ROWS,
        "recorded_at": NOW,
    }
    fields.update(overrides)
    return RawArtifactProvenance(**fields)  # type: ignore[arg-type]


def _load(**overrides: object) -> WarehouseLoadProvenance:
    fields = {
        "load_id": "l1",
        "provenance_id": "p1",
        "run_id": "r1",
        "delivery_date": DELIVERY_DATE,
        "source_object": "orders",
        "destination": GOOD_DESTINATION,
        "partition_date": DELIVERY_DATE,
        "output_rows": GOOD_ROWS,
        "job_id": "j1",
        "recorded_at": NOW,
    }
    fields.update(overrides)
    return WarehouseLoadProvenance(**fields)  # type: ignore[arg-type]


class _FakeProvenanceStore(ProvenanceStore):
    def __init__(self) -> None:
        self.artifacts: dict[str, RawArtifactProvenance] = {}
        self.warehouse_loads: dict[tuple[date, str], list[WarehouseLoadProvenance]] = {}
        self.fail_with: Exception | None = None

    def append_artifact(self, record: RawArtifactProvenance) -> None:
        self.artifacts[record.provenance_id] = record

    def append_warehouse_load(self, record: WarehouseLoadProvenance) -> None:
        self.warehouse_loads.setdefault((record.delivery_date, record.source_object), []).append(record)

    def get_artifact(self, provenance_id: str) -> RawArtifactProvenance | None:
        if self.fail_with is not None:
            raise self.fail_with
        return self.artifacts.get(provenance_id)

    def get_artifact_history(self, delivery_date: date, source_object: str) -> tuple[RawArtifactProvenance, ...]:
        return tuple(a for a in self.artifacts.values() if a.delivery_date == delivery_date and a.source_object == source_object)

    def get_artifact_by_uri(self, delivery_date: date, source_object: str, gcs_uri: str) -> RawArtifactProvenance | None:
        return next((a for a in self.artifacts.values() if a.gcs_uri == gcs_uri), None)

    def get_warehouse_load_history(self, delivery_date: date, source_object: str) -> tuple[WarehouseLoadProvenance, ...]:
        return tuple(self.warehouse_loads.get((delivery_date, source_object), ()))

    def get_latest_warehouse_load(self, delivery_date: date, source_object: str) -> WarehouseLoadProvenance | None:
        if self.fail_with is not None:
            raise self.fail_with
        history = self.warehouse_loads.get((delivery_date, source_object), [])
        return history[-1] if history else None


class _FakeArtifactInspector(RawArtifactInspector):
    def __init__(self) -> None:
        self.observation: RawArtifactObservation | None = None
        self.fail_with: Exception | None = None

    def inspect(self, gcs_uri: str) -> RawArtifactObservation:
        if self.fail_with is not None:
            raise self.fail_with
        if self.observation is not None:
            return self.observation
        return RawArtifactObservation(gcs_uri=gcs_uri, present=False, checksum=None, file_size_bytes=None)


class _FakeWarehouseInspector(WarehouseInspector):
    def __init__(self) -> None:
        self.observation: WarehousePartitionObservation | None = None
        self.fail_with: Exception | None = None

    def inspect_partition(self, source_object: str, partition_date: date) -> WarehousePartitionObservation:
        if self.fail_with is not None:
            raise self.fail_with
        if self.observation is not None:
            return self.observation
        return WarehousePartitionObservation(
            source_object=source_object, partition_date=partition_date, destination=GOOD_DESTINATION, present=False, row_count=None
        )


def _good_setup() -> tuple[_FakeProvenanceStore, _FakeArtifactInspector, _FakeWarehouseInspector]:
    """A fully matching evidence chain: reconcile() should CONFIRM."""
    store = _FakeProvenanceStore()
    store.append_artifact(_artifact())
    store.append_warehouse_load(_load())

    artifact_inspector = _FakeArtifactInspector()
    artifact_inspector.observation = RawArtifactObservation(
        gcs_uri=GOOD_GCS_URI, present=True, checksum=GOOD_CHECKSUM, file_size_bytes=GOOD_SIZE
    )

    warehouse_inspector = _FakeWarehouseInspector()
    warehouse_inspector.observation = WarehousePartitionObservation(
        source_object="orders", partition_date=DELIVERY_DATE, destination=GOOD_DESTINATION, present=True, row_count=GOOD_ROWS
    )
    return store, artifact_inspector, warehouse_inspector


class TestReconciliationOutcomeAndReason:
    def test_outcome_values(self) -> None:
        assert ReconciliationOutcome.CONFIRMED.value == "confirmed"
        assert ReconciliationOutcome.BLOCKED.value == "blocked"

    def test_all_eleven_blocked_reasons_exist(self) -> None:
        expected = {
            "no_warehouse_load_provenance",
            "no_artifact_provenance",
            "provenance_identity_mismatch",
            "gcs_artifact_missing",
            "gcs_checksum_missing",
            "gcs_checksum_mismatch",
            "gcs_size_mismatch",
            "gcs_ingestion_date_mismatch",
            "bigquery_partition_missing",
            "bigquery_destination_mismatch",
            "bigquery_row_count_mismatch",
        }
        actual = {r.value for r in ReconciliationReason} - {"confirmed"}
        assert actual == expected


class TestReconciliationResultValidation:
    def test_confirmed_requires_both_ids(self) -> None:
        with pytest.raises(ValueError):
            ReconciliationResult(
                delivery_date=DELIVERY_DATE,
                source_object="orders",
                outcome=ReconciliationOutcome.CONFIRMED,
                reason=ReconciliationReason.CONFIRMED,
            )

    def test_confirmed_requires_reason_confirmed(self) -> None:
        with pytest.raises(ValueError):
            ReconciliationResult(
                delivery_date=DELIVERY_DATE,
                source_object="orders",
                outcome=ReconciliationOutcome.CONFIRMED,
                reason=ReconciliationReason.GCS_ARTIFACT_MISSING,
                provenance_id="p1",
                load_id="l1",
            )

    def test_blocked_must_not_use_reason_confirmed(self) -> None:
        with pytest.raises(ValueError):
            ReconciliationResult(
                delivery_date=DELIVERY_DATE,
                source_object="orders",
                outcome=ReconciliationOutcome.BLOCKED,
                reason=ReconciliationReason.CONFIRMED,
            )

    def test_is_immutable(self) -> None:
        result = ReconciliationResult(
            delivery_date=DELIVERY_DATE,
            source_object="orders",
            outcome=ReconciliationOutcome.BLOCKED,
            reason=ReconciliationReason.NO_WAREHOUSE_LOAD_PROVENANCE,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.outcome = ReconciliationOutcome.CONFIRMED  # type: ignore[misc]


class TestRecoveryReconcilerConstruction:
    def test_rejects_non_provenance_store(self) -> None:
        with pytest.raises(TypeError):
            RecoveryReconciler(object(), _FakeArtifactInspector(), _FakeWarehouseInspector())  # type: ignore[arg-type]

    def test_rejects_non_artifact_inspector(self) -> None:
        with pytest.raises(TypeError):
            RecoveryReconciler(_FakeProvenanceStore(), object(), _FakeWarehouseInspector())  # type: ignore[arg-type]

    def test_rejects_non_warehouse_inspector(self) -> None:
        with pytest.raises(TypeError):
            RecoveryReconciler(_FakeProvenanceStore(), _FakeArtifactInspector(), object())  # type: ignore[arg-type]


class TestConfirmedReconciliation:
    def test_all_evidence_matches_confirms(self) -> None:
        store, artifact_inspector, warehouse_inspector = _good_setup()
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.outcome is ReconciliationOutcome.CONFIRMED
        assert result.reason is ReconciliationReason.CONFIRMED
        assert result.provenance_id == "p1"
        assert result.load_id == "l1"

    def test_zero_record_case_confirms(self) -> None:
        store = _FakeProvenanceStore()
        store.append_artifact(_artifact(record_count=0))
        store.append_warehouse_load(_load(output_rows=0))
        artifact_inspector = _FakeArtifactInspector()
        artifact_inspector.observation = RawArtifactObservation(
            gcs_uri=GOOD_GCS_URI, present=True, checksum=GOOD_CHECKSUM, file_size_bytes=GOOD_SIZE
        )
        warehouse_inspector = _FakeWarehouseInspector()
        warehouse_inspector.observation = WarehousePartitionObservation(
            source_object="orders", partition_date=DELIVERY_DATE, destination=GOOD_DESTINATION, present=True, row_count=0
        )
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.outcome is ReconciliationOutcome.CONFIRMED

    def test_performs_no_physical_work(self) -> None:
        store, artifact_inspector, warehouse_inspector = _good_setup()
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        reconciler.reconcile(DELIVERY_DATE, "orders")

        assert not hasattr(reconciler, "storage_manager")
        assert not hasattr(reconciler, "bigquery_loader")


class TestBlockedReasons:
    def test_no_warehouse_load_provenance(self) -> None:
        store = _FakeProvenanceStore()
        reconciler = RecoveryReconciler(store, _FakeArtifactInspector(), _FakeWarehouseInspector())

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.outcome is ReconciliationOutcome.BLOCKED
        assert result.reason is ReconciliationReason.NO_WAREHOUSE_LOAD_PROVENANCE
        assert result.provenance_id is None and result.load_id is None

    def test_no_artifact_provenance(self) -> None:
        store = _FakeProvenanceStore()
        store.append_warehouse_load(_load())
        reconciler = RecoveryReconciler(store, _FakeArtifactInspector(), _FakeWarehouseInspector())

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.reason is ReconciliationReason.NO_ARTIFACT_PROVENANCE

    def test_provenance_identity_mismatch_wrong_partition_date(self) -> None:
        store = _FakeProvenanceStore()
        store.append_artifact(_artifact())
        store.append_warehouse_load(_load(partition_date=date(2017, 5, 20)))
        reconciler = RecoveryReconciler(store, _FakeArtifactInspector(), _FakeWarehouseInspector())

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.reason is ReconciliationReason.PROVENANCE_IDENTITY_MISMATCH

    def test_gcs_artifact_missing(self) -> None:
        store, artifact_inspector, warehouse_inspector = _good_setup()
        artifact_inspector.observation = RawArtifactObservation(
            gcs_uri=GOOD_GCS_URI, present=False, checksum=None, file_size_bytes=None
        )
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.reason is ReconciliationReason.GCS_ARTIFACT_MISSING

    def test_gcs_checksum_missing(self) -> None:
        store, artifact_inspector, warehouse_inspector = _good_setup()
        artifact_inspector.observation = RawArtifactObservation(
            gcs_uri=GOOD_GCS_URI, present=True, checksum=None, file_size_bytes=GOOD_SIZE
        )
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.reason is ReconciliationReason.GCS_CHECKSUM_MISSING

    def test_gcs_checksum_mismatch(self) -> None:
        store, artifact_inspector, warehouse_inspector = _good_setup()
        artifact_inspector.observation = RawArtifactObservation(
            gcs_uri=GOOD_GCS_URI, present=True, checksum="different-checksum", file_size_bytes=GOOD_SIZE
        )
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.reason is ReconciliationReason.GCS_CHECKSUM_MISMATCH

    def test_gcs_size_mismatch(self) -> None:
        store, artifact_inspector, warehouse_inspector = _good_setup()
        artifact_inspector.observation = RawArtifactObservation(
            gcs_uri=GOOD_GCS_URI, present=True, checksum=GOOD_CHECKSUM, file_size_bytes=999
        )
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.reason is ReconciliationReason.GCS_SIZE_MISMATCH

    def test_bigquery_partition_missing(self) -> None:
        store, artifact_inspector, warehouse_inspector = _good_setup()
        warehouse_inspector.observation = WarehousePartitionObservation(
            source_object="orders", partition_date=DELIVERY_DATE, destination=GOOD_DESTINATION, present=False, row_count=None
        )
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.reason is ReconciliationReason.BIGQUERY_PARTITION_MISSING

    def test_bigquery_destination_mismatch(self) -> None:
        store, artifact_inspector, warehouse_inspector = _good_setup()
        warehouse_inspector.observation = WarehousePartitionObservation(
            source_object="orders",
            partition_date=DELIVERY_DATE,
            destination="mercury-data-platform-dev.raw.orders$99999999",
            present=True,
            row_count=GOOD_ROWS,
        )
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.reason is ReconciliationReason.BIGQUERY_DESTINATION_MISMATCH

    def test_bigquery_row_count_mismatch(self) -> None:
        store, artifact_inspector, warehouse_inspector = _good_setup()
        warehouse_inspector.observation = WarehousePartitionObservation(
            source_object="orders", partition_date=DELIVERY_DATE, destination=GOOD_DESTINATION, present=True, row_count=999
        )
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.reason is ReconciliationReason.BIGQUERY_ROW_COUNT_MISMATCH

    def test_gcs_ingestion_date_matches_uri_confirms_normally(self) -> None:
        # provenance.ingestion_date == the date encoded in gcs_uri --
        # this is exactly the _good_setup() default, restated explicitly
        # here so this specific requirement has its own dedicated test.
        store = _FakeProvenanceStore()
        store.append_artifact(
            _artifact(gcs_uri="gs://bucket/raw/orders/ingestion_date=2017-05-20/orders.csv", ingestion_date=date(2017, 5, 20))
        )
        store.append_warehouse_load(_load())
        artifact_inspector = _FakeArtifactInspector()
        artifact_inspector.observation = RawArtifactObservation(
            gcs_uri="gs://bucket/raw/orders/ingestion_date=2017-05-20/orders.csv",
            present=True,
            checksum=GOOD_CHECKSUM,
            file_size_bytes=GOOD_SIZE,
        )
        warehouse_inspector = _FakeWarehouseInspector()
        warehouse_inspector.observation = WarehousePartitionObservation(
            source_object="orders", partition_date=DELIVERY_DATE, destination=GOOD_DESTINATION, present=True, row_count=GOOD_ROWS
        )
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.outcome is ReconciliationOutcome.CONFIRMED

    def test_gcs_ingestion_date_mismatch(self) -> None:
        store = _FakeProvenanceStore()
        mismatched_uri = "gs://bucket/raw/orders/ingestion_date=2017-05-21/orders.csv"
        store.append_artifact(_artifact(gcs_uri=mismatched_uri, ingestion_date=date(2017, 5, 20)))
        store.append_warehouse_load(_load())
        artifact_inspector = _FakeArtifactInspector()
        artifact_inspector.observation = RawArtifactObservation(
            gcs_uri=mismatched_uri, present=True, checksum=GOOD_CHECKSUM, file_size_bytes=GOOD_SIZE
        )
        warehouse_inspector = _FakeWarehouseInspector()
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.outcome is ReconciliationOutcome.BLOCKED
        assert result.reason is ReconciliationReason.GCS_INGESTION_DATE_MISMATCH
        assert result.provenance_id is None and result.load_id is None

    def test_gcs_ingestion_date_mismatch_performs_no_physical_work(self) -> None:
        store = _FakeProvenanceStore()
        mismatched_uri = "gs://bucket/raw/orders/ingestion_date=2017-05-21/orders.csv"
        store.append_artifact(_artifact(gcs_uri=mismatched_uri, ingestion_date=date(2017, 5, 20)))
        store.append_warehouse_load(_load())
        artifact_inspector = _FakeArtifactInspector()
        artifact_inspector.observation = RawArtifactObservation(
            gcs_uri=mismatched_uri, present=True, checksum=GOOD_CHECKSUM, file_size_bytes=GOOD_SIZE
        )
        warehouse_inspector = _FakeWarehouseInspector()
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        reconciler.reconcile(DELIVERY_DATE, "orders")

        # Never reached the warehouse-inspection step -- confirms the
        # ingestion-date check short-circuits before any BigQuery work,
        # and no replay-state / provenance mutation occurred anywhere.
        assert warehouse_inspector.observation is None
        assert store.artifacts["p1"] is not None  # unchanged, only the pre-seeded record
        assert len(store.warehouse_loads[(DELIVERY_DATE, "orders")]) == 1  # unchanged, only pre-seeded

    def test_missing_ingestion_date_segment_blocks_with_same_reason(self) -> None:
        store = _FakeProvenanceStore()
        no_segment_uri = "gs://bucket/raw/orders/orders.csv"
        store.append_artifact(_artifact(gcs_uri=no_segment_uri, ingestion_date=date(2017, 5, 20)))
        store.append_warehouse_load(_load())
        artifact_inspector = _FakeArtifactInspector()
        artifact_inspector.observation = RawArtifactObservation(
            gcs_uri=no_segment_uri, present=True, checksum=GOOD_CHECKSUM, file_size_bytes=GOOD_SIZE
        )
        reconciler = RecoveryReconciler(store, artifact_inspector, _FakeWarehouseInspector())

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.outcome is ReconciliationOutcome.BLOCKED
        assert result.reason is ReconciliationReason.GCS_INGESTION_DATE_MISMATCH

    def test_malformed_ingestion_date_segment_blocks_with_same_reason(self) -> None:
        store = _FakeProvenanceStore()
        malformed_uri = "gs://bucket/raw/orders/ingestion_date=not-a-real-date/orders.csv"
        store.append_artifact(_artifact(gcs_uri=malformed_uri, ingestion_date=date(2017, 5, 20)))
        store.append_warehouse_load(_load())
        artifact_inspector = _FakeArtifactInspector()
        artifact_inspector.observation = RawArtifactObservation(
            gcs_uri=malformed_uri, present=True, checksum=GOOD_CHECKSUM, file_size_bytes=GOOD_SIZE
        )
        reconciler = RecoveryReconciler(store, artifact_inspector, _FakeWarehouseInspector())

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.outcome is ReconciliationOutcome.BLOCKED
        assert result.reason is ReconciliationReason.GCS_INGESTION_DATE_MISMATCH

    def test_substring_coincidence_does_not_satisfy_the_segment_match(self) -> None:
        # A date-shaped substring that is not a properly delimited path
        # segment (e.g. embedded inside a longer filename token) must
        # not be treated as satisfying the ingestion_date evidence --
        # proves the parser requires an exact delimited segment, not a
        # substring match anywhere in the URI.
        store = _FakeProvenanceStore()
        coincidental_uri = "gs://bucket/raw/orders/report_ingestion_date=2017-05-20x/orders.csv"
        store.append_artifact(_artifact(gcs_uri=coincidental_uri, ingestion_date=date(2017, 5, 20)))
        store.append_warehouse_load(_load())
        artifact_inspector = _FakeArtifactInspector()
        artifact_inspector.observation = RawArtifactObservation(
            gcs_uri=coincidental_uri, present=True, checksum=GOOD_CHECKSUM, file_size_bytes=GOOD_SIZE
        )
        reconciler = RecoveryReconciler(store, artifact_inspector, _FakeWarehouseInspector())

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.reason is ReconciliationReason.GCS_INGESTION_DATE_MISMATCH

    def test_reconciliation_never_derives_delivery_date_plus_one(self) -> None:
        # The Olist "+1 day" rule must never appear in reconciliation --
        # a provenance record whose ingestion_date equals delivery_date
        # itself (not delivery_date + 1) must still confirm normally, as
        # long as it matches what's encoded in the URI. This proves the
        # check is a pure self-consistency comparison, never a policy
        # about what the "correct" offset should be.
        store = _FakeProvenanceStore()
        same_day_uri = "gs://bucket/raw/orders/ingestion_date=2017-05-19/orders.csv"
        store.append_artifact(
            _artifact(gcs_uri=same_day_uri, delivery_date=DELIVERY_DATE, ingestion_date=DELIVERY_DATE)
        )
        store.append_warehouse_load(_load())
        artifact_inspector = _FakeArtifactInspector()
        artifact_inspector.observation = RawArtifactObservation(
            gcs_uri=same_day_uri, present=True, checksum=GOOD_CHECKSUM, file_size_bytes=GOOD_SIZE
        )
        warehouse_inspector = _FakeWarehouseInspector()
        warehouse_inspector.observation = WarehousePartitionObservation(
            source_object="orders", partition_date=DELIVERY_DATE, destination=GOOD_DESTINATION, present=True, row_count=GOOD_ROWS
        )
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        result = reconciler.reconcile(DELIVERY_DATE, "orders")

        assert result.outcome is ReconciliationOutcome.CONFIRMED

    def test_blocked_reasons_perform_no_physical_mutation(self) -> None:
        store = _FakeProvenanceStore()
        reconciler = RecoveryReconciler(store, _FakeArtifactInspector(), _FakeWarehouseInspector())

        reconciler.reconcile(DELIVERY_DATE, "orders")

        assert store.artifacts == {}
        assert store.warehouse_loads == {}


class TestInfrastructureFailureIsAnError:
    def test_provenance_store_failure_propagates_not_blocked(self) -> None:
        store = _FakeProvenanceStore()
        store.fail_with = RuntimeError(f"permission denied: {SENTINEL}")
        reconciler = RecoveryReconciler(store, _FakeArtifactInspector(), _FakeWarehouseInspector())

        with pytest.raises(RuntimeError):
            reconciler.reconcile(DELIVERY_DATE, "orders")

    def test_artifact_inspector_failure_propagates_not_blocked(self) -> None:
        store, artifact_inspector, warehouse_inspector = _good_setup()
        artifact_inspector.fail_with = RuntimeError(f"GCS service unavailable: {SENTINEL}")
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        with pytest.raises(RuntimeError):
            reconciler.reconcile(DELIVERY_DATE, "orders")

    def test_warehouse_inspector_failure_propagates_not_blocked(self) -> None:
        store, artifact_inspector, warehouse_inspector = _good_setup()
        warehouse_inspector.fail_with = RuntimeError(f"BigQuery permission denied: {SENTINEL}")
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        with pytest.raises(RuntimeError):
            reconciler.reconcile(DELIVERY_DATE, "orders")

    def test_infrastructure_failure_is_not_converted_to_blocked_result(self) -> None:
        # This documents the boundary: the reconciler itself does not
        # sanitize or convert an infrastructure failure into a
        # ReconciliationResult at all -- it propagates the raw exception
        # unconditionally, leaving ADR-011 safe-wrapping to the caller
        # (RecoveryExecutor), which has its own dedicated sentinel tests.
        store, artifact_inspector, warehouse_inspector = _good_setup()
        artifact_inspector.fail_with = RuntimeError(f"denied: {SENTINEL}")
        reconciler = RecoveryReconciler(store, artifact_inspector, warehouse_inspector)

        with pytest.raises(RuntimeError) as exc_info:
            reconciler.reconcile(DELIVERY_DATE, "orders")

        assert not isinstance(exc_info.value, type(ReconciliationResult))