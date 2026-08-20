"""Unit tests for mercury_ingestion.orchestration.provenance."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone

import pytest

from mercury_ingestion.orchestration.provenance import (
    ProvenanceStore,
    RawArtifactProvenance,
    WarehouseLoadProvenance,
)

NOW = datetime.now(timezone.utc)


def _artifact(**overrides: object) -> RawArtifactProvenance:
    fields = {
        "provenance_id": "p1",
        "run_id": "r1",
        "delivery_date": date(2017, 5, 19),
        "source_object": "orders",
        "ingestion_date": date(2017, 5, 20),
        "gcs_uri": "gs://bucket/orders.csv",
        "checksum": "abc123",
        "file_size_bytes": 100,
        "record_count": 5,
        "recorded_at": NOW,
    }
    fields.update(overrides)
    return RawArtifactProvenance(**fields)  # type: ignore[arg-type]


def _load(**overrides: object) -> WarehouseLoadProvenance:
    fields = {
        "load_id": "l1",
        "provenance_id": "p1",
        "run_id": "r1",
        "delivery_date": date(2017, 5, 19),
        "source_object": "orders",
        "destination": "proj.raw.orders$20170519",
        "partition_date": date(2017, 5, 19),
        "output_rows": 5,
        "job_id": "j1",
        "recorded_at": NOW,
    }
    fields.update(overrides)
    return WarehouseLoadProvenance(**fields)  # type: ignore[arg-type]


class TestRawArtifactProvenance:
    def test_valid_construction(self) -> None:
        assert _artifact().provenance_id == "p1"

    def test_is_immutable(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            _artifact().checksum = "other"  # type: ignore[misc]

    def test_blank_provenance_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            _artifact(provenance_id="   ")

    def test_blank_run_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            _artifact(run_id="")

    def test_blank_source_object_rejected(self) -> None:
        with pytest.raises(ValueError):
            _artifact(source_object="")

    def test_invalid_delivery_date_rejected(self) -> None:
        with pytest.raises(TypeError):
            _artifact(delivery_date="2017-05-19")

    def test_invalid_ingestion_date_rejected(self) -> None:
        with pytest.raises(TypeError):
            _artifact(ingestion_date="2017-05-20")

    def test_ingestion_date_may_differ_from_delivery_date(self) -> None:
        artifact = _artifact(delivery_date=date(2017, 5, 19), ingestion_date=date(2017, 5, 20))
        assert artifact.delivery_date != artifact.ingestion_date

    def test_ingestion_date_need_not_be_plus_one_day(self) -> None:
        # This model must not encode the Olist-specific "+1 day" rule --
        # any ingestion_date is structurally acceptable here.
        artifact = _artifact(delivery_date=date(2017, 5, 19), ingestion_date=date(2017, 5, 19))
        assert artifact.ingestion_date == artifact.delivery_date

    def test_non_gs_uri_rejected(self) -> None:
        with pytest.raises(ValueError):
            _artifact(gcs_uri="https://example.com/orders.csv")

    def test_blank_checksum_rejected(self) -> None:
        with pytest.raises(ValueError):
            _artifact(checksum="")

    def test_negative_file_size_rejected(self) -> None:
        with pytest.raises(ValueError):
            _artifact(file_size_bytes=-1)

    def test_negative_record_count_rejected(self) -> None:
        with pytest.raises(ValueError):
            _artifact(record_count=-1)

    def test_zero_record_count_accepted(self) -> None:
        assert _artifact(record_count=0).record_count == 0

    def test_naive_recorded_at_rejected(self) -> None:
        with pytest.raises(ValueError):
            _artifact(recorded_at=datetime(2017, 5, 19, 10, 0, 0))

    def test_non_datetime_recorded_at_rejected(self) -> None:
        with pytest.raises(TypeError):
            _artifact(recorded_at="2017-05-19T10:00:00Z")


class TestWarehouseLoadProvenance:
    def test_valid_construction(self) -> None:
        assert _load().load_id == "l1"

    def test_is_immutable(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            _load().output_rows = 10  # type: ignore[misc]

    def test_blank_load_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            _load(load_id="")

    def test_blank_provenance_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            _load(provenance_id="")

    def test_blank_destination_rejected(self) -> None:
        with pytest.raises(ValueError):
            _load(destination="")

    def test_blank_job_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            _load(job_id="")

    def test_invalid_delivery_date_rejected(self) -> None:
        with pytest.raises(TypeError):
            _load(delivery_date="2017-05-19")

    def test_invalid_partition_date_rejected(self) -> None:
        with pytest.raises(TypeError):
            _load(partition_date="2017-05-19")

    def test_negative_output_rows_rejected(self) -> None:
        with pytest.raises(ValueError):
            _load(output_rows=-1)

    def test_zero_output_rows_accepted(self) -> None:
        assert _load(output_rows=0).output_rows == 0

    def test_naive_recorded_at_rejected(self) -> None:
        with pytest.raises(ValueError):
            _load(recorded_at=datetime(2017, 5, 19, 10, 0, 0))


class TestProvenanceStoreIsAbstract:
    def test_cannot_be_instantiated_directly(self) -> None:
        with pytest.raises(TypeError):
            ProvenanceStore()  # type: ignore[abstract]


class _InMemoryProvenanceStore(ProvenanceStore):
    """Minimal in-memory fake exercising the full ProvenanceStore contract."""

    def __init__(self) -> None:
        self.artifacts: list[RawArtifactProvenance] = []
        self.warehouse_loads: list[WarehouseLoadProvenance] = []

    def append_artifact(self, record: RawArtifactProvenance) -> None:
        self.artifacts.append(record)

    def append_warehouse_load(self, record: WarehouseLoadProvenance) -> None:
        self.warehouse_loads.append(record)

    def get_artifact(self, provenance_id: str) -> RawArtifactProvenance | None:
        return next((a for a in self.artifacts if a.provenance_id == provenance_id), None)

    def get_artifact_history(self, delivery_date: date, source_object: str) -> tuple[RawArtifactProvenance, ...]:
        matches = [a for a in self.artifacts if a.delivery_date == delivery_date and a.source_object == source_object]
        return tuple(sorted(matches, key=lambda a: a.recorded_at))

    def get_artifact_by_uri(self, delivery_date: date, source_object: str, gcs_uri: str) -> RawArtifactProvenance | None:
        return next(
            (
                a
                for a in self.artifacts
                if a.delivery_date == delivery_date and a.source_object == source_object and a.gcs_uri == gcs_uri
            ),
            None,
        )

    def get_warehouse_load_history(self, delivery_date: date, source_object: str) -> tuple[WarehouseLoadProvenance, ...]:
        matches = [
            w for w in self.warehouse_loads if w.delivery_date == delivery_date and w.source_object == source_object
        ]
        return tuple(sorted(matches, key=lambda w: w.recorded_at))

    def get_latest_warehouse_load(self, delivery_date: date, source_object: str) -> WarehouseLoadProvenance | None:
        history = self.get_warehouse_load_history(delivery_date, source_object)
        return history[-1] if history else None


class TestProvenanceStoreContract:
    def test_append_and_get_artifact(self) -> None:
        store = _InMemoryProvenanceStore()
        artifact = _artifact()
        store.append_artifact(artifact)

        assert store.get_artifact("p1") == artifact

    def test_get_artifact_missing_returns_none(self) -> None:
        store = _InMemoryProvenanceStore()
        assert store.get_artifact("does-not-exist") is None

    def test_artifact_history_is_oldest_first(self) -> None:
        store = _InMemoryProvenanceStore()
        early = _artifact(provenance_id="p1", recorded_at=datetime(2017, 5, 19, 8, tzinfo=timezone.utc))
        late = _artifact(provenance_id="p2", recorded_at=datetime(2017, 5, 19, 10, tzinfo=timezone.utc))
        store.append_artifact(late)
        store.append_artifact(early)

        history = store.get_artifact_history(date(2017, 5, 19), "orders")

        assert [a.provenance_id for a in history] == ["p1", "p2"]

    def test_get_artifact_by_uri(self) -> None:
        store = _InMemoryProvenanceStore()
        artifact = _artifact(gcs_uri="gs://bucket/specific.csv")
        store.append_artifact(artifact)

        found = store.get_artifact_by_uri(date(2017, 5, 19), "orders", "gs://bucket/specific.csv")

        assert found == artifact

    def test_get_latest_warehouse_load_is_deterministic(self) -> None:
        store = _InMemoryProvenanceStore()
        early = _load(load_id="l1", recorded_at=datetime(2017, 5, 19, 8, tzinfo=timezone.utc))
        late = _load(load_id="l2", recorded_at=datetime(2017, 5, 19, 10, tzinfo=timezone.utc))
        store.append_warehouse_load(early)
        store.append_warehouse_load(late)

        latest = store.get_latest_warehouse_load(date(2017, 5, 19), "orders")

        assert latest.load_id == "l2"

    def test_get_latest_warehouse_load_missing_returns_none(self) -> None:
        store = _InMemoryProvenanceStore()
        assert store.get_latest_warehouse_load(date(2017, 5, 19), "orders") is None

    def test_multiple_artifact_records_may_exist_for_one_pair(self) -> None:
        # Append-only: a later recovery attempt may legitimately create a
        # second immutable artifact for the same (delivery_date, source_object).
        store = _InMemoryProvenanceStore()
        store.append_artifact(_artifact(provenance_id="p1", gcs_uri="gs://bucket/attempt1.csv"))
        store.append_artifact(_artifact(provenance_id="p2", gcs_uri="gs://bucket/attempt2.csv"))

        history = store.get_artifact_history(date(2017, 5, 19), "orders")

        assert len(history) == 2