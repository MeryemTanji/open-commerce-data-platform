"""Unit tests for mercury_ingestion.warehouse.inspection and bigquery_inspector."""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from mercury_ingestion.warehouse import bigquery_inspector as bigquery_inspector_module
from mercury_ingestion.warehouse.bigquery_inspector import BigQueryInspector
from mercury_ingestion.warehouse.inspection import WarehouseInspector, WarehousePartitionObservation

GOOD_DESTINATION = "mercury-data-platform-dev.raw.orders$20170519"


class TestWarehousePartitionObservation:
    def test_valid_present_construction(self) -> None:
        obs = WarehousePartitionObservation(
            source_object="orders", partition_date=date(2017, 5, 19), destination=GOOD_DESTINATION, present=True, row_count=5
        )
        assert obs.row_count == 5

    def test_valid_absent_construction(self) -> None:
        obs = WarehousePartitionObservation(
            source_object="orders", partition_date=date(2017, 5, 19), destination=GOOD_DESTINATION, present=False, row_count=None
        )
        assert obs.present is False

    def test_is_immutable(self) -> None:
        obs = WarehousePartitionObservation(
            source_object="orders", partition_date=date(2017, 5, 19), destination=GOOD_DESTINATION, present=True, row_count=5
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            obs.row_count = 10  # type: ignore[misc]

    def test_blank_source_object_rejected(self) -> None:
        with pytest.raises(ValueError):
            WarehousePartitionObservation(
                source_object="", partition_date=date(2017, 5, 19), destination=GOOD_DESTINATION, present=True, row_count=5
            )

    def test_invalid_partition_date_rejected(self) -> None:
        with pytest.raises(TypeError):
            WarehousePartitionObservation(
                source_object="orders", partition_date="2017-05-19", destination=GOOD_DESTINATION, present=True, row_count=5
            )

    def test_negative_row_count_rejected(self) -> None:
        with pytest.raises(ValueError):
            WarehousePartitionObservation(
                source_object="orders", partition_date=date(2017, 5, 19), destination=GOOD_DESTINATION, present=True, row_count=-1
            )

    def test_zero_row_count_accepted(self) -> None:
        obs = WarehousePartitionObservation(
            source_object="orders", partition_date=date(2017, 5, 19), destination=GOOD_DESTINATION, present=True, row_count=0
        )
        assert obs.row_count == 0

    def test_absent_with_row_count_rejected(self) -> None:
        with pytest.raises(ValueError):
            WarehousePartitionObservation(
                source_object="orders", partition_date=date(2017, 5, 19), destination=GOOD_DESTINATION, present=False, row_count=0
            )


class TestWarehouseInspectorIsAbstract:
    def test_cannot_be_instantiated_directly(self) -> None:
        with pytest.raises(TypeError):
            WarehouseInspector()  # type: ignore[abstract]


class _FakeRow:
    def __init__(self, total_rows: int) -> None:
        self._total_rows = total_rows

    def __getitem__(self, key: str) -> int:
        assert key == "total_rows"
        return self._total_rows


class _FakeQueryJob:
    def __init__(self, rows: list[_FakeRow]) -> None:
        self._rows = rows

    def result(self) -> list[_FakeRow]:
        return self._rows


class _FakeBigQueryClient:
    def __init__(self, project: str | None = None, location: str | None = None, **kwargs: object) -> None:
        self.queries: list[tuple[str, object]] = []
        self.rows_to_return: list[_FakeRow] = []
        self.fail_with: Exception | None = None

    def query(self, query: str, job_config: object = None, **kwargs: object) -> _FakeQueryJob:
        if self.fail_with is not None:
            raise self.fail_with
        self.queries.append((query, job_config))
        return _FakeQueryJob(self.rows_to_return)


@pytest.fixture(autouse=True)
def _fake_bigquery_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bigquery_inspector_module.bigquery, "Client", _FakeBigQueryClient)


class TestBigQueryInspector:
    def test_existing_partition_observation(self) -> None:
        inspector = BigQueryInspector(project_id="mercury-data-platform-dev", dataset_id="raw")
        inspector._client.rows_to_return = [_FakeRow(total_rows=5)]

        observation = inspector.inspect_partition("orders", date(2017, 5, 19))

        assert observation.present is True
        assert observation.row_count == 5
        assert observation.destination == GOOD_DESTINATION

    def test_missing_partition_returns_present_false(self) -> None:
        inspector = BigQueryInspector(project_id="mercury-data-platform-dev", dataset_id="raw")
        inspector._client.rows_to_return = []

        observation = inspector.inspect_partition("orders", date(2017, 5, 19))

        assert observation.present is False
        assert observation.row_count is None
        assert observation.destination == GOOD_DESTINATION

    def test_zero_row_partition_is_present(self) -> None:
        inspector = BigQueryInspector(project_id="mercury-data-platform-dev", dataset_id="raw")
        inspector._client.rows_to_return = [_FakeRow(total_rows=0)]

        observation = inspector.inspect_partition("reviews", date(2017, 5, 19))

        assert observation.present is True
        assert observation.row_count == 0

    def test_query_uses_parameterized_values(self) -> None:
        inspector = BigQueryInspector(project_id="mercury-data-platform-dev", dataset_id="raw")
        inspector._client.rows_to_return = [_FakeRow(total_rows=5)]

        inspector.inspect_partition("orders", date(2017, 5, 19))

        query, job_config = inspector._client.queries[0]
        param_names = {p.name for p in job_config.query_parameters}
        assert param_names == {"table_name", "partition_id"}
        assert "@table_name" in query
        assert "@partition_id" in query

    def test_queries_information_schema_partitions_not_raw_rows(self) -> None:
        inspector = BigQueryInspector(project_id="mercury-data-platform-dev", dataset_id="raw")
        inspector._client.rows_to_return = [_FakeRow(total_rows=5)]

        inspector.inspect_partition("orders", date(2017, 5, 19))

        query, _ = inspector._client.queries[0]
        assert "INFORMATION_SCHEMA.PARTITIONS" in query
        assert "total_rows" in query
        assert "SELECT *" not in query

    def test_blank_source_object_rejected(self) -> None:
        inspector = BigQueryInspector(project_id="mercury-data-platform-dev", dataset_id="raw")
        with pytest.raises(ValueError):
            inspector.inspect_partition("", date(2017, 5, 19))

    def test_invalid_partition_date_rejected(self) -> None:
        inspector = BigQueryInspector(project_id="mercury-data-platform-dev", dataset_id="raw")
        with pytest.raises(TypeError):
            inspector.inspect_partition("orders", "2017-05-19")  # type: ignore[arg-type]

    def test_query_failure_propagates(self) -> None:
        inspector = BigQueryInspector(project_id="mercury-data-platform-dev", dataset_id="raw")
        inspector._client.fail_with = RuntimeError("permission denied")

        with pytest.raises(RuntimeError):
            inspector.inspect_partition("orders", date(2017, 5, 19))

    def test_never_writes_or_creates_resources(self) -> None:
        import inspect

        source_text = inspect.getsource(BigQueryInspector)
        assert "insert_rows" not in source_text
        assert "create_table" not in source_text
        assert "create_dataset" not in source_text
        assert "UPDATE " not in source_text
        assert "DELETE " not in source_text
        assert "MERGE " not in source_text