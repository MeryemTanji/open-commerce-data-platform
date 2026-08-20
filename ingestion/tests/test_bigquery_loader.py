"""Unit tests for mercury_ingestion.warehouse.bigquery_loader.

No real GCP credentials, project, dataset, or network access are used.
Only the BigQuery client boundary (``bigquery_loader.bigquery.Client``)
is replaced with an in-memory fake; ``bigquery.LoadJobConfig``,
``bigquery.SchemaField``, and BigQuery's enums are used for real, since
constructing them has no side effects and no network call.
"""

from __future__ import annotations

import inspect
from datetime import date
from pathlib import Path

import pytest
from google.api_core import exceptions as gcs_exceptions
from google.cloud import bigquery

from mercury_ingestion.warehouse import bigquery_loader as bigquery_loader_module
from mercury_ingestion.warehouse.bigquery_loader import BigQueryLoadResult, BigQueryRawLoader
from mercury_ingestion.warehouse.schemas import (
    MASTER_REFERENCE_SOURCE_OBJECTS,
    TRANSACTIONAL_SOURCE_OBJECTS,
    get_raw_schema,
)

PROJECT_ID = "mercury-data-platform-dev"
DATASET_ID = "raw"
GCS_URI = "gs://mercury-data-platform-dev-raw-01/raw/order_platform/orders/ingestion_date=2017-05-10/olist_orders_dataset.csv"


class _FakeLoadJob:
    """Records what it was called with; raises on result() if configured to."""

    def __init__(
        self,
        source_uris: object,
        destination: object,
        job_config: bigquery.LoadJobConfig | None,
        location: str | None,
        output_rows: int,
        job_id: str,
        raise_exc: BaseException | None,
    ) -> None:
        self.source_uris = source_uris
        self.destination = destination
        self.job_config = job_config
        self.location = location
        self.output_rows = output_rows
        self.job_id = job_id
        self._raise_exc = raise_exc
        self.result_called = False

    def result(self) -> "_FakeLoadJob":
        self.result_called = True
        if self._raise_exc is not None:
            raise self._raise_exc
        return self


class _FakeClient:
    """Records construction args and load_table_from_uri() calls."""

    created_calls: list[dict[str, object]] = []

    def __init__(self, project: str | None = None, location: str | None = None, **kwargs: object) -> None:
        self.project = project
        self.location = location
        _FakeClient.created_calls.append({"project": project, "location": location})
        self.load_calls: list[_FakeLoadJob] = []
        self.next_output_rows = 0
        self.next_job_id = "fake-job-id"
        self.next_raise_exc: BaseException | None = None

    def get_dataset(self, *args: object, **kwargs: object) -> None:  # pragma: no cover - must never be called
        raise AssertionError(
            "client.get_dataset() must not be called during construction: that "
            "would perform an unnecessary network round trip"
        )

    def load_table_from_uri(
        self,
        source_uris: object,
        destination: object,
        *,
        job_config: bigquery.LoadJobConfig | None = None,
        location: str | None = None,
        **kwargs: object,
    ) -> _FakeLoadJob:
        job = _FakeLoadJob(
            source_uris=source_uris,
            destination=destination,
            job_config=job_config,
            location=location,
            output_rows=self.next_output_rows,
            job_id=self.next_job_id,
            raise_exc=self.next_raise_exc,
        )
        self.load_calls.append(job)
        return job


@pytest.fixture(autouse=True)
def _fake_bigquery_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClient.created_calls = []
    monkeypatch.setattr(bigquery_loader_module.bigquery, "Client", _FakeClient)


def _make_loader(location: str = "europe-west4") -> BigQueryRawLoader:
    return BigQueryRawLoader(project_id=PROJECT_ID, dataset_id=DATASET_ID, location=location)


class TestConstructor:
    def test_valid_project_dataset_location_accepted(self) -> None:
        loader = _make_loader()

        assert loader.project_id == PROJECT_ID
        assert loader.dataset_id == DATASET_ID
        assert loader.location == "europe-west4"

    def test_blank_project_rejected(self) -> None:
        with pytest.raises(ValueError):
            BigQueryRawLoader(project_id="   ", dataset_id=DATASET_ID)

    def test_blank_dataset_rejected(self) -> None:
        with pytest.raises(ValueError):
            BigQueryRawLoader(project_id=PROJECT_ID, dataset_id="")

    def test_blank_location_rejected(self) -> None:
        with pytest.raises(ValueError):
            BigQueryRawLoader(project_id=PROJECT_ID, dataset_id=DATASET_ID, location="  ")

    def test_default_location_is_europe_west4(self) -> None:
        loader = BigQueryRawLoader(project_id=PROJECT_ID, dataset_id=DATASET_ID)

        assert loader.location == "europe-west4"

    def test_client_constructed_with_expected_project_and_location(self) -> None:
        BigQueryRawLoader(project_id=PROJECT_ID, dataset_id=DATASET_ID, location="us-central1")

        assert _FakeClient.created_calls[-1] == {"project": PROJECT_ID, "location": "us-central1"}

    def test_constructor_performs_no_dataset_lookup(self) -> None:
        # _FakeClient.get_dataset() raises AssertionError if touched; a
        # clean construction proves it was never called.
        _make_loader()


class TestInputValidation:
    def test_unsupported_source_object_rejected(self) -> None:
        loader = _make_loader()

        with pytest.raises(ValueError):
            loader.load(source_object="unknown_source", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

    def test_blank_source_object_rejected(self) -> None:
        loader = _make_loader()

        with pytest.raises(ValueError):
            loader.load(source_object="   ", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

    def test_blank_gcs_uri_rejected(self) -> None:
        loader = _make_loader()

        with pytest.raises(ValueError):
            loader.load(source_object="orders", gcs_uri="", partition_date=date(2017, 5, 10))

    def test_non_gs_uri_rejected(self) -> None:
        loader = _make_loader()

        with pytest.raises(ValueError):
            loader.load(source_object="orders", gcs_uri="https://example.com/x.csv", partition_date=date(2017, 5, 10))

    def test_invalid_partition_date_type_rejected(self) -> None:
        loader = _make_loader()

        with pytest.raises(TypeError):
            loader.load(source_object="orders", gcs_uri=GCS_URI, partition_date="2017-05-10")  # type: ignore[arg-type]


class TestMasterReferenceDestination:
    @pytest.mark.parametrize("source_object", sorted(MASTER_REFERENCE_SOURCE_OBJECTS))
    def test_destination_is_whole_table_no_partition_decorator(self, source_object: str) -> None:
        loader = _make_loader()

        result = loader.load(source_object=source_object, gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        assert result.destination == f"{PROJECT_ID}.{DATASET_ID}.{source_object}"
        assert "$" not in result.destination


class TestTransactionalDestination:
    @pytest.mark.parametrize("source_object", sorted(TRANSACTIONAL_SOURCE_OBJECTS))
    def test_destination_has_yyyymmdd_partition_decorator(self, source_object: str) -> None:
        loader = _make_loader()

        result = loader.load(source_object=source_object, gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        assert result.destination == f"{PROJECT_ID}.{DATASET_ID}.{source_object}$20170510"

    def test_partition_decorator_date_format_is_exact(self) -> None:
        loader = _make_loader()

        result = loader.load(source_object="orders", gcs_uri=GCS_URI, partition_date=date(2017, 1, 5))

        assert result.destination.endswith("$20170105")


class TestWriteDisposition:
    def test_every_load_uses_write_truncate(self) -> None:
        loader = _make_loader()

        loader.load(source_object="orders", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        job_config = loader._client.load_calls[-1].job_config
        assert job_config.write_disposition == bigquery.WriteDisposition.WRITE_TRUNCATE

    def test_master_reference_targets_whole_table(self) -> None:
        loader = _make_loader()

        loader.load(source_object="customers", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        destination = loader._client.load_calls[-1].destination
        assert destination == f"{PROJECT_ID}.{DATASET_ID}.customers"

    def test_transactional_targets_decorated_partition(self) -> None:
        loader = _make_loader()

        loader.load(source_object="orders", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        destination = loader._client.load_calls[-1].destination
        assert destination == f"{PROJECT_ID}.{DATASET_ID}.orders$20170510"


class TestTableCreation:
    def test_create_if_needed_is_configured(self) -> None:
        loader = _make_loader()

        loader.load(source_object="orders", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        job_config = loader._client.load_calls[-1].job_config
        assert job_config.create_disposition == bigquery.CreateDisposition.CREATE_IF_NEEDED


class TestExplicitSchema:
    def test_autodetect_is_disabled(self) -> None:
        loader = _make_loader()

        loader.load(source_object="orders", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        job_config = loader._client.load_calls[-1].job_config
        assert job_config.autodetect is False

    @pytest.mark.parametrize(
        "source_object", sorted(MASTER_REFERENCE_SOURCE_OBJECTS | TRANSACTIONAL_SOURCE_OBJECTS)
    )
    def test_correct_explicit_schema_provided(self, source_object: str) -> None:
        loader = _make_loader()

        loader.load(source_object=source_object, gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        job_config = loader._client.load_calls[-1].job_config
        assert list(job_config.schema) == list(get_raw_schema(source_object))


class TestCsvConfiguration:
    def test_source_format_is_csv(self) -> None:
        loader = _make_loader()

        loader.load(source_object="orders", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        job_config = loader._client.load_calls[-1].job_config
        assert job_config.source_format == bigquery.SourceFormat.CSV

    def test_skip_leading_rows_is_one(self) -> None:
        loader = _make_loader()

        loader.load(source_object="orders", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        job_config = loader._client.load_calls[-1].job_config
        assert job_config.skip_leading_rows == 1

    def test_quoted_newlines_are_allowed(self) -> None:
        loader = _make_loader()

        loader.load(source_object="reviews", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        job_config = loader._client.load_calls[-1].job_config
        assert job_config.allow_quoted_newlines is True

    def test_quoted_newlines_allowed_for_non_review_sources_too(self) -> None:
        loader = _make_loader()

        loader.load(source_object="customers", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        job_config = loader._client.load_calls[-1].job_config
        assert job_config.allow_quoted_newlines is True


class TestPartitionConfiguration:
    @pytest.mark.parametrize("source_object", sorted(TRANSACTIONAL_SOURCE_OBJECTS))
    def test_transactional_sources_use_daily_time_partitioning_no_field(self, source_object: str) -> None:
        loader = _make_loader()

        loader.load(source_object=source_object, gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        job_config = loader._client.load_calls[-1].job_config
        assert job_config.time_partitioning is not None
        assert job_config.time_partitioning.type_ == bigquery.TimePartitioningType.DAY
        assert job_config.time_partitioning.field is None

    @pytest.mark.parametrize("source_object", sorted(MASTER_REFERENCE_SOURCE_OBJECTS))
    def test_master_reference_sources_have_no_partitioning(self, source_object: str) -> None:
        loader = _make_loader()

        loader.load(source_object=source_object, gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        job_config = loader._client.load_calls[-1].job_config
        assert job_config.time_partitioning is None


class TestJobExecution:
    def test_load_table_from_uri_called_with_expected_arguments(self) -> None:
        loader = _make_loader()

        loader.load(source_object="orders", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        job = loader._client.load_calls[-1]
        assert job.source_uris == GCS_URI
        assert job.destination == f"{PROJECT_ID}.{DATASET_ID}.orders$20170510"
        assert isinstance(job.job_config, bigquery.LoadJobConfig)
        assert job.location == "europe-west4"

    def test_job_result_is_called(self) -> None:
        loader = _make_loader()

        loader.load(source_object="orders", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        assert loader._client.load_calls[-1].result_called is True


class TestResult:
    def test_result_contains_expected_fields(self) -> None:
        loader = _make_loader()
        loader._client.next_output_rows = 42
        loader._client.next_job_id = "job-abc-123"

        result = loader.load(source_object="orders", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        assert isinstance(result, BigQueryLoadResult)
        assert result.source_object == "orders"
        assert result.source_uri == GCS_URI
        assert result.destination == f"{PROJECT_ID}.{DATASET_ID}.orders$20170510"
        assert result.partition_date == date(2017, 5, 10)
        assert result.output_rows == 42
        assert result.job_id == "job-abc-123"


class TestZeroRows:
    def test_zero_output_rows_is_a_successful_result(self) -> None:
        loader = _make_loader()
        loader._client.next_output_rows = 0

        result = loader.load(source_object="orders", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

        assert result.output_rows == 0

    def test_zero_output_rows_does_not_raise(self) -> None:
        loader = _make_loader()
        loader._client.next_output_rows = 0

        # Should not raise -- a header-only delivery is a valid, successful load.
        loader.load(source_object="reviews", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))


class TestProviderFailures:
    def test_unrelated_provider_exception_propagates_unchanged(self) -> None:
        loader = _make_loader()
        loader._client.next_raise_exc = gcs_exceptions.Forbidden("403 caller lacks permission")

        with pytest.raises(gcs_exceptions.Forbidden):
            loader.load(source_object="orders", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))

    def test_service_unavailable_is_not_converted_to_generic_exception(self) -> None:
        loader = _make_loader()
        loader._client.next_raise_exc = gcs_exceptions.ServiceUnavailable("503 backend unavailable")

        with pytest.raises(gcs_exceptions.ServiceUnavailable):
            loader.load(source_object="orders", gcs_uri=GCS_URI, partition_date=date(2017, 5, 10))


class TestNoStorageInteraction:
    def test_module_never_references_gcs_storage_manager(self) -> None:
        source_text = Path(inspect.getfile(bigquery_loader_module)).read_text(encoding="utf-8")

        assert "GCSStorageManager" not in source_text
        assert "LocalStorageManager" not in source_text
        assert "StorageManager" not in source_text

    def test_module_never_calls_blob_or_bucket_apis(self) -> None:
        source_text = Path(inspect.getfile(bigquery_loader_module)).read_text(encoding="utf-8")

        assert ".blob(" not in source_text
        assert ".bucket(" not in source_text
        assert "upload_from_filename" not in source_text
        assert "delete(" not in source_text

    def test_loader_has_no_storage_manager_attribute(self) -> None:
        loader = _make_loader()

        assert not hasattr(loader, "storage_manager")