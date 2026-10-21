"""Unit tests for the production GCS source-input materializer.

No real GCP credentials, project, bucket, or network access are used.
The Google Cloud Storage client boundary is replaced with an in-memory
fake so these tests run fully offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from google.api_core import exceptions as gcs_exceptions

from mercury_ingestion.runtime import (
    gcs_source_materializer as materializer_module,
)
from mercury_ingestion.runtime.gcs_source_materializer import (
    GCSSourceMaterializer,
)

SOURCE_URI = "gs://mercury-simulation-input/olist/source"
REQUIRED_FILENAMES = (
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
)


class _FakeBlob:
    def __init__(
        self,
        name: str,
        bucket: "_FakeBucket",
    ) -> None:
        self.name = name
        self._bucket = bucket

    def download_to_filename(self, filename: str) -> None:
        self._bucket.download_calls.append(
            {
                "blob_name": self.name,
                "filename": filename,
            }
        )

        if self._bucket.raise_for_blob == self.name:
            raise gcs_exceptions.NotFound("404 object not found")

        content = self._bucket.objects.get(self.name)

        if content is None:
            raise gcs_exceptions.NotFound("404 object not found")

        Path(filename).write_bytes(content)


class _FakeBucket:
    def __init__(
        self,
        name: str,
        objects: dict[str, bytes],
    ) -> None:
        self.name = name
        self.objects = objects
        self.blob_calls: list[str] = []
        self.download_calls: list[dict[str, str]] = []
        self.raise_for_blob: str | None = None

    def blob(self, object_name: str) -> _FakeBlob:
        self.blob_calls.append(object_name)
        return _FakeBlob(object_name, self)

    def exists(self) -> None:  # pragma: no cover
        raise AssertionError(
            "bucket metadata must not be fetched during construction"
        )


class _FakeClient:
    created_with_project: list[str | None] = []
    objects: dict[str, bytes] = {}
    buckets: list[_FakeBucket] = []

    def __init__(
        self,
        project: str | None = None,
    ) -> None:
        self.project = project
        self.bucket_calls: list[str] = []
        _FakeClient.created_with_project.append(project)

    def bucket(self, bucket_name: str) -> _FakeBucket:
        self.bucket_calls.append(bucket_name)

        bucket = _FakeBucket(
            name=bucket_name,
            objects=dict(_FakeClient.objects),
        )
        _FakeClient.buckets.append(bucket)
        return bucket


@pytest.fixture(autouse=True)
def _fake_gcs_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeClient.created_with_project = []
    _FakeClient.buckets = []
    _FakeClient.objects = {
        "olist/source/olist_orders_dataset.csv": (
            b"order_id\norder-1\n"
        ),
        "olist/source/olist_order_items_dataset.csv": (
            b"order_id,item_id\norder-1,1\n"
        ),
    }

    monkeypatch.setattr(
        materializer_module.gcs,
        "Client",
        _FakeClient,
    )


class TestConstruction:
    def test_valid_configuration_is_accepted(self) -> None:
        materializer = GCSSourceMaterializer(
            source_uri=SOURCE_URI,
            required_filenames=REQUIRED_FILENAMES,
        )

        assert materializer.source_uri == SOURCE_URI
        assert materializer.bucket_name == "mercury-simulation-input"
        assert materializer.object_prefix == "olist/source"
        assert materializer.required_filenames == REQUIRED_FILENAMES

    def test_project_id_is_passed_to_client(self) -> None:
        GCSSourceMaterializer(
            source_uri=SOURCE_URI,
            required_filenames=REQUIRED_FILENAMES,
            project_id="mercury-data-platform-dev",
        )

        assert _FakeClient.created_with_project == [
            "mercury-data-platform-dev"
        ]

    @pytest.mark.parametrize(
        "source_uri",
        [
            "",
            "   ",
            "https://example.com/olist",
            "file:///tmp/olist",
            "gs://",
        ],
    )
    def test_invalid_source_uri_is_rejected(
        self,
        source_uri: str,
    ) -> None:
        with pytest.raises(ValueError):
            GCSSourceMaterializer(
                source_uri=source_uri,
                required_filenames=REQUIRED_FILENAMES,
            )

    def test_empty_required_filenames_are_rejected(self) -> None:
        with pytest.raises(ValueError):
            GCSSourceMaterializer(
                source_uri=SOURCE_URI,
                required_filenames=(),
            )

    def test_duplicate_required_filenames_are_rejected(self) -> None:
        with pytest.raises(ValueError):
            GCSSourceMaterializer(
                source_uri=SOURCE_URI,
                required_filenames=(
                    "olist_orders_dataset.csv",
                    "olist_orders_dataset.csv",
                ),
            )

    @pytest.mark.parametrize(
        "filename",
        [
            "../orders.csv",
            "nested/orders.csv",
            "nested\\orders.csv",
            "",
            "   ",
        ],
    )
    def test_unsafe_required_filename_is_rejected(
        self,
        filename: str,
    ) -> None:
        with pytest.raises(ValueError):
            GCSSourceMaterializer(
                source_uri=SOURCE_URI,
                required_filenames=(filename,),
            )

    def test_construction_does_not_download_files(
        self,
    ) -> None:
        GCSSourceMaterializer(
            source_uri=SOURCE_URI,
            required_filenames=REQUIRED_FILENAMES,
        )

        assert _FakeClient.buckets[-1].download_calls == []


class TestMaterialization:
    def test_materializes_required_files(
        self,
        tmp_path: Path,
    ) -> None:
        destination = tmp_path / "source"

        materializer = GCSSourceMaterializer(
            source_uri=SOURCE_URI,
            required_filenames=REQUIRED_FILENAMES,
        )

        result = materializer.materialize(destination)

        assert result == destination
        assert (
            destination / "olist_orders_dataset.csv"
        ).read_bytes() == b"order_id\norder-1\n"
        assert (
            destination / "olist_order_items_dataset.csv"
        ).read_bytes() == (
            b"order_id,item_id\norder-1,1\n"
        )

    def test_downloads_exact_expected_object_names(
        self,
        tmp_path: Path,
    ) -> None:
        materializer = GCSSourceMaterializer(
            source_uri=SOURCE_URI,
            required_filenames=REQUIRED_FILENAMES,
        )

        materializer.materialize(tmp_path / "source")

        assert _FakeClient.buckets[-1].blob_calls == [
            "olist/source/olist_orders_dataset.csv",
            "olist/source/olist_order_items_dataset.csv",
        ]

    def test_destination_directory_is_created(
        self,
        tmp_path: Path,
    ) -> None:
        destination = tmp_path / "nested" / "source"

        materializer = GCSSourceMaterializer(
            source_uri=SOURCE_URI,
            required_filenames=REQUIRED_FILENAMES,
        )

        materializer.materialize(destination)

        assert destination.is_dir()

    def test_existing_destination_file_is_not_overwritten(
        self,
        tmp_path: Path,
    ) -> None:
        destination = tmp_path / "source"
        destination.mkdir()

        existing_file = destination / "olist_orders_dataset.csv"
        existing_file.write_bytes(b"existing-content")

        materializer = GCSSourceMaterializer(
            source_uri=SOURCE_URI,
            required_filenames=REQUIRED_FILENAMES,
        )

        with pytest.raises(FileExistsError):
            materializer.materialize(destination)

        assert existing_file.read_bytes() == b"existing-content"

    def test_missing_source_object_becomes_file_not_found_error(
        self,
        tmp_path: Path,
    ) -> None:
        missing_object = (
            "olist/source/olist_order_items_dataset.csv"
        )

        materializer = GCSSourceMaterializer(
            source_uri=SOURCE_URI,
            required_filenames=REQUIRED_FILENAMES,
        )
        _FakeClient.buckets[-1].raise_for_blob = missing_object

        with pytest.raises(
            FileNotFoundError,
            match="olist_order_items_dataset.csv",
        ):
            materializer.materialize(tmp_path / "source")

    def test_unrelated_google_exception_propagates(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        materializer = GCSSourceMaterializer(
            source_uri=SOURCE_URI,
            required_filenames=REQUIRED_FILENAMES,
        )

        bucket = _FakeClient.buckets[-1]
        blob = bucket.blob(REQUIRED_FILENAMES[0])

        def _raise_forbidden(filename: str) -> None:
            raise gcs_exceptions.Forbidden(
                "403 caller lacks permission"
            )

        monkeypatch.setattr(
            blob,
            "download_to_filename",
            _raise_forbidden,
        )
        monkeypatch.setattr(
            bucket,
            "blob",
            lambda object_name: blob,
        )

        with pytest.raises(gcs_exceptions.Forbidden):
            materializer.materialize(tmp_path / "source")