"""Unit tests for mercury_ingestion.orchestration.bigquery_provenance.

No real GCP credentials, project, dataset, or network access are used.
Only the BigQuery client boundary is faked.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from google.cloud import bigquery

from mercury_ingestion.orchestration import bigquery_provenance as bp_module
from mercury_ingestion.orchestration.bigquery_provenance import (
    ARTIFACT_PROVENANCE_SCHEMA,
    WAREHOUSE_LOAD_PROVENANCE_SCHEMA,
    BigQueryProvenanceStore,
)
from mercury_ingestion.orchestration.provenance import RawArtifactProvenance, WarehouseLoadProvenance

PROJECT_ID = "mercury-data-platform-dev"
DELIVERY_DATE = date(2017, 5, 19)
RECORDED = datetime(2026, 8, 17, 10, 5, 1, tzinfo=timezone.utc)
SENTINEL = "sensitive-test-email@example.invalid"


class _FakeRow(dict):
    """Mimics a BigQuery Row's __getitem__ access using plain dict storage."""


class _FakeQueryJob:
    def __init__(self, rows: list[_FakeRow]) -> None:
        self._rows = rows

    def result(self) -> list[_FakeRow]:
        return list(self._rows)


class _FakeClient:
    def __init__(self, project: str | None = None, location: str | None = None, **kwargs: object) -> None:
        self.project = project
        self.location = location
        self.create_dataset_calls: list[dict[str, object]] = []
        self.create_table_calls: list[dict[str, object]] = []
        self.insert_calls: list[dict[str, object]] = []
        self.query_calls: list[dict[str, object]] = []
        self.next_insert_errors: list[object] = []
        self.next_query_rows: list[_FakeRow] = []

    def create_dataset(self, dataset: object, exists_ok: bool = False, **kwargs: object) -> object:
        self.create_dataset_calls.append({"dataset": dataset, "exists_ok": exists_ok})
        return dataset

    def create_table(self, table: object, exists_ok: bool = False, **kwargs: object) -> object:
        self.create_table_calls.append({"table": table, "exists_ok": exists_ok})
        return table

    def insert_rows_json(
        self, table: object, json_rows: list[dict[str, object]], row_ids: object = None, **kwargs: object
    ) -> list[object]:
        self.insert_calls.append({"table": table, "json_rows": json_rows, "row_ids": row_ids})
        return self.next_insert_errors

    def query(
        self, query: str, job_config: bigquery.QueryJobConfig | None = None, location: str | None = None, **kwargs: object
    ) -> _FakeQueryJob:
        self.query_calls.append({"query": query, "job_config": job_config, "location": location})
        return _FakeQueryJob(self.next_query_rows)


@pytest.fixture(autouse=True)
def _fake_bigquery_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bp_module.bigquery, "Client", _FakeClient)


def _make_store() -> BigQueryProvenanceStore:
    return BigQueryProvenanceStore(project_id=PROJECT_ID, location="europe-west4")


def _artifact(**overrides: object) -> RawArtifactProvenance:
    fields = {
        "provenance_id": "p1",
        "run_id": "r1",
        "delivery_date": DELIVERY_DATE,
        "source_object": "orders",
        "ingestion_date": date(2017, 5, 20),
        "gcs_uri": "gs://bucket/orders.csv",
        "checksum": "abc123",
        "file_size_bytes": 100,
        "record_count": 5,
        "recorded_at": RECORDED,
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
        "destination": "proj.raw.orders$20170519",
        "partition_date": DELIVERY_DATE,
        "output_rows": 5,
        "job_id": "j1",
        "recorded_at": RECORDED,
    }
    fields.update(overrides)
    return WarehouseLoadProvenance(**fields)  # type: ignore[arg-type]


def _artifact_row(record: RawArtifactProvenance) -> _FakeRow:
    return _FakeRow(
        provenance_id=record.provenance_id,
        run_id=record.run_id,
        delivery_date=record.delivery_date,
        source_object=record.source_object,
        ingestion_date=record.ingestion_date,
        gcs_uri=record.gcs_uri,
        checksum=record.checksum,
        file_size_bytes=record.file_size_bytes,
        record_count=record.record_count,
        recorded_at=record.recorded_at,
    )


def _load_row(record: WarehouseLoadProvenance) -> _FakeRow:
    return _FakeRow(
        load_id=record.load_id,
        provenance_id=record.provenance_id,
        run_id=record.run_id,
        delivery_date=record.delivery_date,
        source_object=record.source_object,
        destination=record.destination,
        partition_date=record.partition_date,
        output_rows=record.output_rows,
        job_id=record.job_id,
        recorded_at=record.recorded_at,
    )


class TestConstructor:
    def test_valid_construction(self) -> None:
        store = _make_store()
        assert store.project_id == PROJECT_ID

    def test_blank_project_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            BigQueryProvenanceStore(project_id="")

    def test_construction_performs_no_network_call(self) -> None:
        store = _make_store()
        assert store._client.create_dataset_calls == []
        assert store._client.create_table_calls == []


class TestSchemas:
    def test_artifact_schema_field_names(self) -> None:
        names = [f.name for f in ARTIFACT_PROVENANCE_SCHEMA]
        assert names == [
            "provenance_id",
            "run_id",
            "delivery_date",
            "source_object",
            "ingestion_date",
            "gcs_uri",
            "checksum",
            "file_size_bytes",
            "record_count",
            "recorded_at",
        ]

    def test_warehouse_schema_field_names(self) -> None:
        names = [f.name for f in WAREHOUSE_LOAD_PROVENANCE_SCHEMA]
        assert names == [
            "load_id",
            "provenance_id",
            "run_id",
            "delivery_date",
            "source_object",
            "destination",
            "partition_date",
            "output_rows",
            "job_id",
            "recorded_at",
        ]

    def test_all_fields_required(self) -> None:
        assert all(f.mode == "REQUIRED" for f in ARTIFACT_PROVENANCE_SCHEMA)
        assert all(f.mode == "REQUIRED" for f in WAREHOUSE_LOAD_PROVENANCE_SCHEMA)


class TestResourceInitialization:
    def test_ensure_resources_creates_dataset_and_both_tables(self) -> None:
        store = _make_store()

        store.ensure_resources()

        assert len(store._client.create_dataset_calls) == 1
        assert len(store._client.create_table_calls) == 2
        assert store._client.create_dataset_calls[0]["exists_ok"] is True
        assert all(call["exists_ok"] is True for call in store._client.create_table_calls)

    def test_never_touches_replay_state_table(self) -> None:
        store = _make_store()

        store.ensure_resources()

        table_names = {call["table"].table_id for call in store._client.create_table_calls}
        assert "historical_replay_state" not in table_names

    def test_tables_partitioned_by_delivery_date_clustered_by_source_object(self) -> None:
        store = _make_store()

        store.ensure_resources()

        for call in store._client.create_table_calls:
            table = call["table"]
            assert table.time_partitioning.field == "delivery_date"
            assert table.clustering_fields == ["source_object"]


class TestAppendArtifact:
    def test_inserts_one_row(self) -> None:
        store = _make_store()
        record = _artifact()

        store.append_artifact(record)

        assert len(store._client.insert_calls) == 1
        assert store._client.insert_calls[0]["row_ids"] == ["p1"]

    def test_row_content_matches_record(self) -> None:
        store = _make_store()
        record = _artifact()

        store.append_artifact(record)

        row = store._client.insert_calls[0]["json_rows"][0]
        assert row["provenance_id"] == "p1"
        assert row["gcs_uri"] == "gs://bucket/orders.csv"
        assert row["checksum"] == "abc123"

    def test_rejects_non_raw_artifact_provenance(self) -> None:
        store = _make_store()
        with pytest.raises(TypeError):
            store.append_artifact(object())  # type: ignore[arg-type]

    def test_insert_error_sentinel_never_in_exception_message(self) -> None:
        # ADR-011: the persistence adapter's own exception message must
        # never embed the backend/provider-generated `errors` payload.
        store = _make_store()
        store._client.next_insert_errors = [{"index": 0, "errors": [f"insert failed for row containing {SENTINEL}"]}]

        with pytest.raises(RuntimeError) as exc_info:
            store.append_artifact(_artifact())

        assert SENTINEL not in str(exc_info.value)
        assert str(exc_info.value) == "failed to append artifact provenance"

    def test_insert_errors_raise(self) -> None:
        store = _make_store()
        store._client.next_insert_errors = [{"index": 0, "errors": ["boom"]}]

        with pytest.raises(RuntimeError):
            store.append_artifact(_artifact())

    def test_never_uses_update_delete_merge_truncate(self) -> None:
        import inspect

        source_text = inspect.getsource(BigQueryProvenanceStore)
        for forbidden in ("UPDATE ", "DELETE ", "MERGE ", "TRUNCATE "):
            assert forbidden not in source_text


class TestAppendWarehouseLoad:
    def test_inserts_one_row(self) -> None:
        store = _make_store()
        record = _load()

        store.append_warehouse_load(record)

        assert len(store._client.insert_calls) == 1
        assert store._client.insert_calls[0]["row_ids"] == ["l1"]

    def test_rejects_non_warehouse_load_provenance(self) -> None:
        store = _make_store()
        with pytest.raises(TypeError):
            store.append_warehouse_load(object())  # type: ignore[arg-type]

    def test_insert_errors_raise(self) -> None:
        store = _make_store()
        store._client.next_insert_errors = [{"index": 0, "errors": ["boom"]}]

        with pytest.raises(RuntimeError):
            store.append_warehouse_load(_load())

    def test_insert_error_sentinel_never_in_exception_message(self) -> None:
        store = _make_store()
        store._client.next_insert_errors = [{"index": 0, "errors": [f"insert failed for row containing {SENTINEL}"]}]

        with pytest.raises(RuntimeError) as exc_info:
            store.append_warehouse_load(_load())

        assert SENTINEL not in str(exc_info.value)
        assert str(exc_info.value) == "failed to append warehouse load provenance"


class TestGetArtifact:
    def test_returns_matching_record(self) -> None:
        store = _make_store()
        record = _artifact()
        store._client.next_query_rows = [_artifact_row(record)]

        result = store.get_artifact("p1")

        assert result == record

    def test_returns_none_when_absent(self) -> None:
        store = _make_store()
        store._client.next_query_rows = []

        assert store.get_artifact("missing") is None

    def test_uses_parameterized_query(self) -> None:
        store = _make_store()
        store._client.next_query_rows = []

        store.get_artifact("p1")

        job_config = store._client.query_calls[0]["job_config"]
        assert {p.name for p in job_config.query_parameters} == {"provenance_id"}


class TestGetArtifactHistory:
    def test_returns_oldest_first(self) -> None:
        store = _make_store()
        early = _artifact(provenance_id="p1")
        late = _artifact(provenance_id="p2")
        store._client.next_query_rows = [_artifact_row(early), _artifact_row(late)]

        history = store.get_artifact_history(DELIVERY_DATE, "orders")

        assert [a.provenance_id for a in history] == ["p1", "p2"]
        query = store._client.query_calls[0]["query"]
        assert "ORDER BY recorded_at ASC" in query


class TestGetArtifactByUri:
    def test_returns_matching_record(self) -> None:
        store = _make_store()
        record = _artifact()
        store._client.next_query_rows = [_artifact_row(record)]

        result = store.get_artifact_by_uri(DELIVERY_DATE, "orders", "gs://bucket/orders.csv")

        assert result == record

    def test_uses_parameterized_query(self) -> None:
        store = _make_store()
        store._client.next_query_rows = []

        store.get_artifact_by_uri(DELIVERY_DATE, "orders", "gs://bucket/orders.csv")

        job_config = store._client.query_calls[0]["job_config"]
        assert {p.name for p in job_config.query_parameters} == {"delivery_date", "source_object", "gcs_uri"}


class TestGetWarehouseLoadHistory:
    def test_returns_oldest_first(self) -> None:
        store = _make_store()
        early = _load(load_id="l1")
        late = _load(load_id="l2")
        store._client.next_query_rows = [_load_row(early), _load_row(late)]

        history = store.get_warehouse_load_history(DELIVERY_DATE, "orders")

        assert [w.load_id for w in history] == ["l1", "l2"]
        query = store._client.query_calls[0]["query"]
        assert "ORDER BY recorded_at ASC" in query


class TestGetLatestWarehouseLoad:
    def test_returns_most_recent(self) -> None:
        store = _make_store()
        record = _load(load_id="l2")
        store._client.next_query_rows = [_load_row(record)]

        result = store.get_latest_warehouse_load(DELIVERY_DATE, "orders")

        assert result.load_id == "l2"
        query = store._client.query_calls[0]["query"]
        assert "ORDER BY recorded_at DESC" in query
        assert "LIMIT 1" in query

    def test_returns_none_when_absent(self) -> None:
        store = _make_store()
        store._client.next_query_rows = []

        assert store.get_latest_warehouse_load(DELIVERY_DATE, "orders") is None