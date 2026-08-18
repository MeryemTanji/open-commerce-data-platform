"""Unit tests for mercury_ingestion.orchestration.bigquery_replay_state.

No real GCP credentials, project, dataset, or network access are used.
Only the BigQuery client boundary is faked; ``bigquery.Dataset``,
``bigquery.Table``, ``bigquery.SchemaField``, ``bigquery.TimePartitioning``,
and ``bigquery.QueryJobConfig``/``ScalarQueryParameter`` are used for
real, since constructing them has no network side effects, matching the
existing ``test_bigquery_loader.py`` testing style.
"""

from __future__ import annotations

import inspect
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from google.cloud import bigquery

from mercury_ingestion.orchestration import bigquery_replay_state as brs_module
from mercury_ingestion.orchestration.bigquery_replay_state import (
    REPLAY_STATE_SCHEMA,
    BigQueryReplayStateStore,
)
from mercury_ingestion.orchestration.state import ReplayStage, ReplayStateRecord, ReplayStatus

PROJECT_ID = "mercury-data-platform-dev"
DELIVERY_DATE = date(2017, 5, 1)
STARTED = datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc)
COMPLETED = datetime(2026, 8, 17, 10, 5, 0, tzinfo=timezone.utc)
RECORDED = datetime(2026, 8, 17, 10, 5, 1, tzinfo=timezone.utc)


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
    monkeypatch.setattr(brs_module.bigquery, "Client", _FakeClient)


def _make_store(location: str | None = "europe-west4") -> BigQueryReplayStateStore:
    return BigQueryReplayStateStore(project_id=PROJECT_ID, location=location)


def _row(record: ReplayStateRecord) -> _FakeRow:
    """Build a fake query-result row from a ReplayStateRecord (already-typed values, as BigQuery's client returns)."""
    return _FakeRow(
        run_id=record.run_id,
        event_id=record.event_id,
        delivery_date=record.delivery_date,
        source_object=record.source_object,
        status=record.status.value,
        stage=record.stage.value,
        started_at=record.started_at,
        completed_at=record.completed_at,
        error_message=record.error_message,
        recorded_at=record.recorded_at,
    )


def _running(source_object: str = "orders", event_id: str = "evt-1", run_id: str = "run-1") -> ReplayStateRecord:
    return ReplayStateRecord.running(
        run_id=run_id,
        event_id=event_id,
        delivery_date=DELIVERY_DATE,
        source_object=source_object,
        stage=ReplayStage.INGESTION,
        started_at=STARTED,
        recorded_at=RECORDED,
    )


def _success(source_object: str = "orders", event_id: str = "evt-2", run_id: str = "run-1") -> ReplayStateRecord:
    return ReplayStateRecord.success(
        run_id=run_id,
        event_id=event_id,
        delivery_date=DELIVERY_DATE,
        source_object=source_object,
        started_at=STARTED,
        completed_at=COMPLETED,
        recorded_at=RECORDED,
    )


class TestConstructor:
    def test_valid_construction(self) -> None:
        store = _make_store()

        assert store.project_id == PROJECT_ID
        assert store.dataset_id == "metadata"
        assert store.table_id == "historical_replay_state"

    def test_blank_project_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            BigQueryReplayStateStore(project_id="   ")

    def test_blank_dataset_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            BigQueryReplayStateStore(project_id=PROJECT_ID, dataset_id="")

    def test_blank_table_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            BigQueryReplayStateStore(project_id=PROJECT_ID, table_id="  ")

    def test_blank_location_rejected_when_supplied(self) -> None:
        with pytest.raises(ValueError):
            BigQueryReplayStateStore(project_id=PROJECT_ID, location="   ")

    def test_none_location_accepted(self) -> None:
        store = BigQueryReplayStateStore(project_id=PROJECT_ID, location=None)

        assert store.location is None

    def test_no_network_lookup_during_construction(self) -> None:
        store = _make_store()

        assert store._client.create_dataset_calls == []
        assert store._client.create_table_calls == []
        assert store._client.insert_calls == []
        assert store._client.query_calls == []

    def test_client_constructed_with_expected_project_and_location(self) -> None:
        store = BigQueryReplayStateStore(project_id=PROJECT_ID, location="us-central1")

        assert store._client.project == PROJECT_ID
        assert store._client.location == "us-central1"


class TestResourceInitialization:
    def test_metadata_dataset_is_targeted(self) -> None:
        store = _make_store()

        store.ensure_resources()

        dataset = store._client.create_dataset_calls[0]["dataset"]
        assert dataset.dataset_id == "metadata"
        assert dataset.project == PROJECT_ID

    def test_historical_replay_table_is_targeted(self) -> None:
        store = _make_store()

        store.ensure_resources()

        table = store._client.create_table_calls[0]["table"]
        assert table.table_id == "historical_replay_state"

    def test_dataset_creation_is_idempotent(self) -> None:
        store = _make_store()

        store.ensure_resources()

        assert store._client.create_dataset_calls[0]["exists_ok"] is True

    def test_table_creation_is_idempotent(self) -> None:
        store = _make_store()

        store.ensure_resources()

        assert store._client.create_table_calls[0]["exists_ok"] is True

    def test_explicit_schema_matches_specification(self) -> None:
        store = _make_store()

        store.ensure_resources()

        table = store._client.create_table_calls[0]["table"]
        assert list(table.schema) == list(REPLAY_STATE_SCHEMA)

    def test_schema_contains_required_string_run_id(self) -> None:
        run_id_field = next(field for field in REPLAY_STATE_SCHEMA if field.name == "run_id")

        assert run_id_field.field_type == "STRING"
        assert run_id_field.mode == "REQUIRED"

    def test_run_id_is_first_column(self) -> None:
        assert REPLAY_STATE_SCHEMA[0].name == "run_id"

    def test_partition_field_is_delivery_date(self) -> None:
        store = _make_store()

        store.ensure_resources()

        table = store._client.create_table_calls[0]["table"]
        assert table.time_partitioning.field == "delivery_date"

    def test_partition_type_is_day(self) -> None:
        store = _make_store()

        store.ensure_resources()

        table = store._client.create_table_calls[0]["table"]
        assert table.time_partitioning.type_ == bigquery.TimePartitioningType.DAY

    def test_clustering_contains_source_object(self) -> None:
        store = _make_store()

        store.ensure_resources()

        table = store._client.create_table_calls[0]["table"]
        assert table.clustering_fields == ["source_object"]

    def test_no_raw_resource_is_touched(self) -> None:
        store = _make_store()

        store.ensure_resources()

        dataset = store._client.create_dataset_calls[0]["dataset"]
        table = store._client.create_table_calls[0]["table"]
        assert dataset.dataset_id != "raw"
        assert "raw" not in table.table_id

    def test_calling_twice_does_not_raise(self) -> None:
        store = _make_store()

        store.ensure_resources()
        store.ensure_resources()  # must not raise -- idempotent

        assert len(store._client.create_dataset_calls) == 2
        assert len(store._client.create_table_calls) == 2


class TestAppend:
    def test_one_event_produces_one_inserted_row(self) -> None:
        store = _make_store()

        store.append(_running())

        assert len(store._client.insert_calls) == 1
        assert len(store._client.insert_calls[0]["json_rows"]) == 1

    def test_run_id_serialized(self) -> None:
        store = _make_store()

        store.append(_running(run_id="run-serialize-check"))

        row = store._client.insert_calls[0]["json_rows"][0]
        assert row["run_id"] == "run-serialize-check"

    def test_enum_values_serialized_as_plain_strings(self) -> None:
        store = _make_store()

        store.append(_running())

        row = store._client.insert_calls[0]["json_rows"][0]
        assert row["status"] == "running"
        assert row["stage"] == "ingestion"

    def test_date_serialized_as_iso_string(self) -> None:
        store = _make_store()

        store.append(_running())

        row = store._client.insert_calls[0]["json_rows"][0]
        assert row["delivery_date"] == "2017-05-01"

    def test_timestamps_serialized_as_utc_iso_strings(self) -> None:
        store = _make_store()

        store.append(_success())

        row = store._client.insert_calls[0]["json_rows"][0]
        assert row["started_at"] == "2026-08-17T10:00:00+00:00"
        assert row["completed_at"] == "2026-08-17T10:05:00+00:00"

    def test_null_completed_at_preserved(self) -> None:
        store = _make_store()

        store.append(_running())

        row = store._client.insert_calls[0]["json_rows"][0]
        assert row["completed_at"] is None

    def test_null_error_message_preserved(self) -> None:
        store = _make_store()

        store.append(_success())

        row = store._client.insert_calls[0]["json_rows"][0]
        assert row["error_message"] is None

    def test_insertion_errors_propagate_clearly(self) -> None:
        store = _make_store()
        store._client.next_insert_errors = [{"index": 0, "errors": [{"reason": "invalid"}]}]

        with pytest.raises(RuntimeError):
            store.append(_running())

    def test_append_uses_insert_not_update_delete_merge_truncate(self) -> None:
        source_text = Path(inspect.getfile(brs_module)).read_text(encoding="utf-8")

        assert "UPDATE " not in source_text
        assert "DELETE " not in source_text
        assert "MERGE " not in source_text
        assert "TRUNCATE" not in source_text

    def test_two_events_for_same_pair_both_appended_with_distinct_ids(self) -> None:
        store = _make_store()
        running = _running(event_id="evt-running")
        success = ReplayStateRecord.success(
            run_id="run-1",
            event_id="evt-success",
            delivery_date=DELIVERY_DATE,
            source_object="orders",
            started_at=STARTED,
            completed_at=COMPLETED,
            recorded_at=RECORDED,
        )

        store.append(running)
        store.append(success)

        assert len(store._client.insert_calls) == 2
        event_ids = {call["json_rows"][0]["event_id"] for call in store._client.insert_calls}
        assert event_ids == {"evt-running", "evt-success"}

    def test_append_passes_event_id_as_row_id(self) -> None:
        store = _make_store()
        record = _running(event_id="evt-dedup-check")

        store.append(record)

        assert store._client.insert_calls[0]["row_ids"] == ["evt-dedup-check"]

    def test_append_rejects_non_record(self) -> None:
        store = _make_store()

        with pytest.raises(TypeError):
            store.append("not a record")  # type: ignore[arg-type]


class TestGetHistory:
    def test_queries_exact_date_and_source(self) -> None:
        store = _make_store()

        store.get_history(DELIVERY_DATE, "orders")

        params = store._client.query_calls[0]["job_config"].query_parameters
        values = {p.name: p.value for p in params}
        assert values["delivery_date"] == DELIVERY_DATE
        assert values["source_object"] == "orders"

    def test_uses_query_parameters_not_string_interpolation(self) -> None:
        store = _make_store()

        store.get_history(DELIVERY_DATE, "orders")

        query = store._client.query_calls[0]["query"]
        assert "@delivery_date" in query
        assert "@source_object" in query
        assert DELIVERY_DATE.isoformat() not in query

    def test_returns_replay_state_record_objects(self) -> None:
        store = _make_store()
        record = _running()
        store._client.next_query_rows = [_row(record)]

        history = store.get_history(DELIVERY_DATE, "orders")

        assert len(history) == 1
        assert isinstance(history[0], ReplayStateRecord)
        assert history[0].event_id == record.event_id

    def test_run_id_restored_on_deserialization(self) -> None:
        store = _make_store()
        record = _running(run_id="run-roundtrip-check")
        store._client.next_query_rows = [_row(record)]

        history = store.get_history(DELIVERY_DATE, "orders")

        assert history[0].run_id == "run-roundtrip-check"

    def test_query_orders_chronologically_oldest_first(self) -> None:
        store = _make_store()

        store.get_history(DELIVERY_DATE, "orders")

        query = store._client.query_calls[0]["query"]
        assert "ORDER BY recorded_at ASC" in query

    def test_empty_history_returns_empty_tuple(self) -> None:
        store = _make_store()
        store._client.next_query_rows = []

        history = store.get_history(DELIVERY_DATE, "orders")

        assert history == ()

    def test_blank_source_object_rejected(self) -> None:
        store = _make_store()

        with pytest.raises(ValueError):
            store.get_history(DELIVERY_DATE, "   ")

    def test_invalid_delivery_date_rejected(self) -> None:
        store = _make_store()

        with pytest.raises(TypeError):
            store.get_history("2017-05-01", "orders")  # type: ignore[arg-type]


class TestGetLatest:
    def test_returns_latest_record(self) -> None:
        store = _make_store()
        record = _success()
        store._client.next_query_rows = [_row(record)]

        latest = store.get_latest(DELIVERY_DATE, "orders")

        assert latest is not None
        assert latest.event_id == record.event_id

    def test_no_state_returns_none(self) -> None:
        store = _make_store()
        store._client.next_query_rows = []

        assert store.get_latest(DELIVERY_DATE, "orders") is None

    def test_uses_date_and_source_query_parameters(self) -> None:
        store = _make_store()

        store.get_latest(DELIVERY_DATE, "payments")

        params = store._client.query_calls[0]["job_config"].query_parameters
        values = {p.name: p.value for p in params}
        assert values["delivery_date"] == DELIVERY_DATE
        assert values["source_object"] == "payments"

    def test_orders_by_recorded_at_desc(self) -> None:
        store = _make_store()

        store.get_latest(DELIVERY_DATE, "orders")

        query = store._client.query_calls[0]["query"]
        assert "ORDER BY recorded_at DESC" in query

    def test_does_not_mutate_history(self) -> None:
        store = _make_store()
        store._client.next_query_rows = [_row(_success())]

        store.get_latest(DELIVERY_DATE, "orders")

        assert store._client.insert_calls == []


class TestGetLatestForDate:
    def test_returns_at_most_one_per_source_object(self) -> None:
        store = _make_store()
        store._client.next_query_rows = [
            _row(_success(source_object="orders")),
            _row(_success(source_object="payments", event_id="evt-p")),
        ]

        results = store.get_latest_for_date(DELIVERY_DATE)

        assert len(results) == 2
        assert {r.source_object for r in results} == {"orders", "payments"}

    def test_latest_status_chosen_correctly(self) -> None:
        # Simulates the SQL having already resolved RUNNING -> SUCCESS by
        # recorded_at DESC + ROW_NUMBER filtering to rn = 1.
        store = _make_store()
        latest_success = _success(source_object="orders", event_id="evt-latest")
        store._client.next_query_rows = [_row(latest_success)]

        results = store.get_latest_for_date(DELIVERY_DATE)

        assert results[0].status is ReplayStatus.SUCCESS
        assert results[0].event_id == "evt-latest"

    def test_multiple_source_objects_returned(self) -> None:
        store = _make_store()
        store._client.next_query_rows = [
            _row(_success(source_object="orders")),
            _row(_success(source_object="order_items", event_id="evt-oi")),
            _row(_success(source_object="payments", event_id="evt-p")),
            _row(_success(source_object="reviews", event_id="evt-r")),
        ]

        results = store.get_latest_for_date(DELIVERY_DATE)

        assert len(results) == 4

    def test_query_orders_by_source_object_ascending(self) -> None:
        store = _make_store()

        store.get_latest_for_date(DELIVERY_DATE)

        query = store._client.query_calls[0]["query"]
        assert "ORDER BY source_object ASC" in query

    def test_query_uses_window_function_for_latest_per_source(self) -> None:
        store = _make_store()

        store.get_latest_for_date(DELIVERY_DATE)

        query = store._client.query_calls[0]["query"]
        assert "ROW_NUMBER()" in query
        assert "PARTITION BY source_object" in query

    def test_empty_date_returns_empty_tuple(self) -> None:
        store = _make_store()
        store._client.next_query_rows = []

        assert store.get_latest_for_date(DELIVERY_DATE) == ()

    def test_invalid_delivery_date_rejected(self) -> None:
        store = _make_store()

        with pytest.raises(TypeError):
            store.get_latest_for_date("2017-05-01")  # type: ignore[arg-type]


class TestGetCompletedForDate:
    def test_returns_at_most_one_per_source_object(self) -> None:
        store = _make_store()
        store._client.next_query_rows = [
            _row(_success(source_object="orders")),
            _row(_success(source_object="payments", event_id="evt-p")),
        ]

        results = store.get_completed_for_date(DELIVERY_DATE)

        assert len(results) == 2
        assert {r.source_object for r in results} == {"orders", "payments"}

    def test_all_returned_records_are_success(self) -> None:
        store = _make_store()
        store._client.next_query_rows = [
            _row(_success(source_object="orders")),
            _row(_success(source_object="reviews", event_id="evt-r")),
        ]

        results = store.get_completed_for_date(DELIVERY_DATE)

        assert all(r.status is ReplayStatus.SUCCESS for r in results)

    def test_multiple_source_objects_returned(self) -> None:
        store = _make_store()
        store._client.next_query_rows = [
            _row(_success(source_object="orders")),
            _row(_success(source_object="order_items", event_id="evt-oi")),
            _row(_success(source_object="payments", event_id="evt-p")),
            _row(_success(source_object="reviews", event_id="evt-r")),
        ]

        results = store.get_completed_for_date(DELIVERY_DATE)

        assert len(results) == 4

    def test_query_filters_to_success_status(self) -> None:
        store = _make_store()

        store.get_completed_for_date(DELIVERY_DATE)

        query = store._client.query_calls[0]["query"]
        assert "status = 'success'" in query

    def test_query_orders_by_source_object_ascending(self) -> None:
        store = _make_store()

        store.get_completed_for_date(DELIVERY_DATE)

        query = store._client.query_calls[0]["query"]
        assert "ORDER BY source_object ASC" in query

    def test_query_uses_window_function_for_latest_success_per_source(self) -> None:
        store = _make_store()

        store.get_completed_for_date(DELIVERY_DATE)

        query = store._client.query_calls[0]["query"]
        assert "ROW_NUMBER()" in query
        assert "PARTITION BY source_object" in query

    def test_uses_delivery_date_query_parameter(self) -> None:
        store = _make_store()

        store.get_completed_for_date(DELIVERY_DATE)

        params = store._client.query_calls[0]["job_config"].query_parameters
        values = {p.name: p.value for p in params}
        assert values["delivery_date"] == DELIVERY_DATE

    def test_empty_date_returns_empty_tuple(self) -> None:
        store = _make_store()
        store._client.next_query_rows = []

        assert store.get_completed_for_date(DELIVERY_DATE) == ()

    def test_no_successful_events_returns_empty_tuple(self) -> None:
        # Even if the underlying table has RUNNING/FAILED rows for this
        # date, the fake client here simulates the SQL already having
        # filtered to zero rows, exactly as the real WHERE status =
        # 'success' clause would for a date with no successes at all.
        store = _make_store()
        store._client.next_query_rows = []

        assert store.get_completed_for_date(DELIVERY_DATE) == ()

    def test_invalid_delivery_date_rejected(self) -> None:
        store = _make_store()

        with pytest.raises(TypeError):
            store.get_completed_for_date("2017-05-01")  # type: ignore[arg-type]

    def test_returns_replay_state_record_objects(self) -> None:
        store = _make_store()
        record = _success()
        store._client.next_query_rows = [_row(record)]

        results = store.get_completed_for_date(DELIVERY_DATE)

        assert isinstance(results[0], ReplayStateRecord)
        assert results[0].event_id == record.event_id


class TestRowDeserialization:
    def test_unknown_status_value_raises_clearly(self) -> None:
        store = _make_store()
        row = _row(_success())
        row["status"] = "not_a_real_status"
        store._client.next_query_rows = [row]

        with pytest.raises(ValueError):
            store.get_history(DELIVERY_DATE, "orders")

    def test_unknown_stage_value_raises_clearly(self) -> None:
        store = _make_store()
        row = _row(_success())
        row["stage"] = "not_a_real_stage"
        store._client.next_query_rows = [row]

        with pytest.raises(ValueError):
            store.get_history(DELIVERY_DATE, "orders")

    def test_corrupted_success_with_ingestion_stage_raises_clearly(self) -> None:
        # Stored metadata that predates or otherwise violates the
        # SUCCESS-requires-WAREHOUSE invariant must fail loudly when
        # read back, not be silently accepted as valid.
        store = _make_store()
        row = _row(_success())
        row["status"] = "success"
        row["stage"] = "ingestion"
        store._client.next_query_rows = [row]

        with pytest.raises(ValueError):
            store.get_history(DELIVERY_DATE, "orders")


class TestProviderPipelineIndependence:
    def test_module_does_not_reference_pipeline_components(self) -> None:
        source_text = Path(inspect.getfile(brs_module)).read_text(encoding="utf-8")
        import_lines = [line for line in source_text.splitlines() if line.startswith(("import ", "from "))]
        import_block = "\n".join(import_lines)

        assert "OlistSourceSimulator" not in import_block
        assert "OlistSimulatedSourceProvider" not in import_block
        assert "connectors" not in import_block
        assert "GCSStorageManager" not in import_block
        assert "BigQueryRawLoader" not in import_block
        assert "HistoricalReplayRunner" not in import_block