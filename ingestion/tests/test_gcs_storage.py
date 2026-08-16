"""Unit tests for mercury_ingestion.common.gcs_storage.

No real GCP credentials, project, bucket, or network access are used.
The Google Cloud Storage client boundary (``gcs_storage.gcs.Client``) is
replaced with an in-memory fake so these tests run fully offline.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest
from google.api_core import exceptions as gcs_exceptions

from mercury_ingestion.common import gcs_storage as gcs_storage_module
from mercury_ingestion.common.gcs_storage import GCSStorageManager, _build_object_name
from mercury_ingestion.common.storage import StorageManager, StorageResult

BUCKET_NAME = "mercury-data-platform-dev-raw-01"
INGESTION_DATE = date(2026, 8, 16)


class _FakeBlob:
    """Records upload calls and can be told to raise on upload."""

    def __init__(self, name: str, bucket: "_FakeBucket") -> None:
        self.name = name
        self._bucket = bucket

    def upload_from_filename(self, filename: str, **kwargs: object) -> None:
        self._bucket.upload_calls.append({"filename": filename, "kwargs": kwargs, "blob_name": self.name})
        if self._bucket.raise_exc is not None:
            raise self._bucket.raise_exc

    def exists(self) -> None:  # pragma: no cover - should never be called
        raise AssertionError(
            "blob.exists() must not be called: uploads use if_generation_match=0, "
            "not a check-then-upload sequence"
        )


class _FakeBucket:
    """Records blob() calls; raises if bucket-metadata methods are touched."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.blob_calls: list[str] = []
        self.upload_calls: list[dict[str, object]] = []
        self.raise_exc: BaseException | None = None

    def blob(self, object_name: str) -> _FakeBlob:
        self.blob_calls.append(object_name)
        return _FakeBlob(object_name, self)

    def exists(self) -> None:  # pragma: no cover - should never be called
        raise AssertionError(
            "bucket.exists() must not be called during construction: that would "
            "perform an unnecessary network round trip"
        )

    def reload(self) -> None:  # pragma: no cover - should never be called
        raise AssertionError(
            "bucket.reload() must not be called during construction: that would "
            "fetch bucket metadata unnecessarily"
        )


class _FakeClient:
    """Records how it was constructed and which buckets were requested."""

    created_with_project: list[str | None] = []

    def __init__(self, project: str | None = None) -> None:
        self.project = project
        self.bucket_calls: list[str] = []
        _FakeClient.created_with_project.append(project)

    def bucket(self, bucket_name: str) -> _FakeBucket:
        self.bucket_calls.append(bucket_name)
        return _FakeBucket(bucket_name)


@pytest.fixture(autouse=True)
def _fake_gcs_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClient.created_with_project = []
    monkeypatch.setattr(gcs_storage_module.gcs, "Client", _FakeClient)


def _write_source_file(tmp_path: Path, name: str = "olist_orders_dataset.csv", content: bytes = b"id,amount\n1,10\n") -> Path:
    source_file = tmp_path / "source" / name
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(content)
    return source_file


class TestConstructor:
    def test_valid_bucket_name_is_accepted(self) -> None:
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        assert manager.bucket_name == BUCKET_NAME

    def test_blank_bucket_name_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            GCSStorageManager(bucket_name="   ")

    def test_project_id_is_optional(self) -> None:
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        assert manager.project_id is None

    def test_blank_project_id_is_rejected_when_supplied(self) -> None:
        with pytest.raises(ValueError):
            GCSStorageManager(bucket_name=BUCKET_NAME, project_id="   ")

    def test_client_is_constructed_with_expected_project(self) -> None:
        GCSStorageManager(bucket_name=BUCKET_NAME, project_id="my-project")

        assert _FakeClient.created_with_project[-1] == "my-project"

    def test_client_is_constructed_with_none_project_by_default(self) -> None:
        GCSStorageManager(bucket_name=BUCKET_NAME)

        assert _FakeClient.created_with_project[-1] is None

    def test_construction_does_not_perform_bucket_metadata_lookup(self) -> None:
        # _FakeBucket.exists()/reload() raise AssertionError if called; a
        # clean construction proves neither was touched.
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        assert manager._bucket.blob_calls == []

    def test_construction_calls_client_bucket_exactly_once(self) -> None:
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        assert manager._client.bucket_calls == [BUCKET_NAME]


class TestStorageManagerRelationship:
    def test_is_instance_of_storage_manager(self) -> None:
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        assert isinstance(manager, StorageManager)

    def test_is_subclass_of_storage_manager(self) -> None:
        assert issubclass(GCSStorageManager, StorageManager)


class TestObjectNaming:
    def test_build_object_name_matches_expected_hierarchy(self) -> None:
        object_name = _build_object_name(
            "order_platform", "orders", INGESTION_DATE, "olist_orders_dataset.csv"
        )

        assert object_name == "raw/order_platform/orders/ingestion_date=2026-08-16/olist_orders_dataset.csv"

    def test_save_file_requests_blob_with_expected_object_name(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path)
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        manager.save_file(
            source_file=source_file,
            source_system="order_platform",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        expected_object_name = "raw/order_platform/orders/ingestion_date=2026-08-16/olist_orders_dataset.csv"
        assert manager._bucket.blob_calls == [expected_object_name]


class TestSourceValidation:
    def test_missing_source_file_raises_file_not_found_error(self, tmp_path: Path) -> None:
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        with pytest.raises(FileNotFoundError):
            manager.save_file(
                source_file=tmp_path / "does_not_exist.csv",
                source_system="order_platform",
                source_object="orders",
                ingestion_date=INGESTION_DATE,
            )

    def test_directory_source_raises_value_error(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "a_directory"
        source_dir.mkdir()
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        with pytest.raises(ValueError):
            manager.save_file(
                source_file=source_dir,
                source_system="order_platform",
                source_object="orders",
                ingestion_date=INGESTION_DATE,
            )

    def test_unsafe_source_system_is_rejected(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path)
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        with pytest.raises(ValueError):
            manager.save_file(
                source_file=source_file,
                source_system="../escape",
                source_object="orders",
                ingestion_date=INGESTION_DATE,
            )

    def test_unsafe_source_object_is_rejected(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path)
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        with pytest.raises(ValueError):
            manager.save_file(
                source_file=source_file,
                source_system="order_platform",
                source_object="platform/orders",
                ingestion_date=INGESTION_DATE,
            )


class TestUploadBehavior:
    def test_upload_is_called_with_if_generation_match_zero(self, tmp_path: Path) -> None:
        # This test must fail if if_generation_match=0 is ever removed:
        # that precondition is what makes the upload overwrite-safe.
        source_file = _write_source_file(tmp_path)
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        manager.save_file(
            source_file=source_file,
            source_system="order_platform",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        upload_call = manager._bucket.upload_calls[0]
        assert upload_call["kwargs"].get("if_generation_match") == 0

    def test_no_existence_check_before_upload(self, tmp_path: Path) -> None:
        # _FakeBlob has no exists() call recorded anywhere in this flow;
        # _FakeBucket.exists()/reload() would raise if touched. A clean
        # save_file() call proves no check-then-upload race exists.
        source_file = _write_source_file(tmp_path)
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        manager.save_file(
            source_file=source_file,
            source_system="order_platform",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )
        # No AssertionError raised means no metadata/existence lookup occurred.


class TestStorageResult:
    def test_returns_correct_gs_uri(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path)
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        result = manager.save_file(
            source_file=source_file,
            source_system="order_platform",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        expected_uri = (
            f"gs://{BUCKET_NAME}/raw/order_platform/orders/"
            "ingestion_date=2026-08-16/olist_orders_dataset.csv"
        )
        assert result.landing_path == expected_uri

    def test_checksum_is_sha256_of_source_file(self, tmp_path: Path) -> None:
        content = b"id,amount\n1,10\n2,20\n"
        source_file = _write_source_file(tmp_path, content=content)
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        result = manager.save_file(
            source_file=source_file,
            source_system="order_platform",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        assert result.checksum == hashlib.sha256(content).hexdigest()

    def test_file_size_is_correct(self, tmp_path: Path) -> None:
        content = b"x" * 4321
        source_file = _write_source_file(tmp_path, content=content)
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        result = manager.save_file(
            source_file=source_file,
            source_system="order_platform",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        assert result.file_size_bytes == 4321

    def test_result_is_a_storage_result(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path)
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        result = manager.save_file(
            source_file=source_file,
            source_system="order_platform",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        assert isinstance(result, StorageResult)


class TestBytePreservation:
    def test_source_file_passed_directly_to_upload_unchanged(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path)
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)

        manager.save_file(
            source_file=source_file,
            source_system="order_platform",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        upload_call = manager._bucket.upload_calls[0]
        assert upload_call["filename"] == str(source_file)


class TestExistingObjectBehavior:
    def test_precondition_failure_becomes_file_exists_error(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path)
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)
        manager._bucket.raise_exc = gcs_exceptions.PreconditionFailed(
            "412 Precondition Failed: generation mismatch"
        )

        with pytest.raises(FileExistsError) as exc_info:
            manager.save_file(
                source_file=source_file,
                source_system="order_platform",
                source_object="orders",
                ingestion_date=INGESTION_DATE,
            )

        expected_uri = (
            f"gs://{BUCKET_NAME}/raw/order_platform/orders/"
            "ingestion_date=2026-08-16/olist_orders_dataset.csv"
        )
        assert expected_uri in str(exc_info.value)


class TestOtherGoogleExceptions:
    def test_unrelated_provider_exception_propagates_unchanged(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path)
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)
        manager._bucket.raise_exc = gcs_exceptions.Forbidden("403 caller lacks permission")

        with pytest.raises(gcs_exceptions.Forbidden):
            manager.save_file(
                source_file=source_file,
                source_system="order_platform",
                source_object="orders",
                ingestion_date=INGESTION_DATE,
            )

    def test_service_unavailable_is_not_translated_to_file_exists_error(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path)
        manager = GCSStorageManager(bucket_name=BUCKET_NAME)
        manager._bucket.raise_exc = gcs_exceptions.ServiceUnavailable("503 backend unavailable")

        with pytest.raises(gcs_exceptions.ServiceUnavailable):
            manager.save_file(
                source_file=source_file,
                source_system="order_platform",
                source_object="orders",
                ingestion_date=INGESTION_DATE,
            )