"""Unit tests for mercury_ingestion.common.artifact_inspection and gcs_artifact_inspector."""

from __future__ import annotations

import dataclasses

import pytest
from google.api_core import exceptions as gcs_exceptions
from google.cloud import storage as gcs

from mercury_ingestion.common.artifact_inspection import RawArtifactInspector, RawArtifactObservation
from mercury_ingestion.common.gcs_artifact_inspector import GCSArtifactInspector

GOOD_URI = "gs://bucket/raw/orders/ingestion_date=2017-05-20/orders.csv"


class TestRawArtifactObservation:
    def test_valid_present_construction(self) -> None:
        obs = RawArtifactObservation(gcs_uri=GOOD_URI, present=True, checksum="abc", file_size_bytes=100)
        assert obs.present is True

    def test_valid_absent_construction(self) -> None:
        obs = RawArtifactObservation(gcs_uri=GOOD_URI, present=False, checksum=None, file_size_bytes=None)
        assert obs.present is False

    def test_is_immutable(self) -> None:
        obs = RawArtifactObservation(gcs_uri=GOOD_URI, present=True, checksum="abc", file_size_bytes=100)
        with pytest.raises(dataclasses.FrozenInstanceError):
            obs.checksum = "other"  # type: ignore[misc]

    def test_non_gs_uri_rejected(self) -> None:
        with pytest.raises(ValueError):
            RawArtifactObservation(gcs_uri="https://example.com/x.csv", present=False, checksum=None, file_size_bytes=None)

    def test_blank_checksum_rejected_when_present(self) -> None:
        with pytest.raises(ValueError):
            RawArtifactObservation(gcs_uri=GOOD_URI, present=True, checksum="   ", file_size_bytes=100)

    def test_negative_file_size_rejected(self) -> None:
        with pytest.raises(ValueError):
            RawArtifactObservation(gcs_uri=GOOD_URI, present=True, checksum="abc", file_size_bytes=-1)

    def test_absent_with_checksum_rejected(self) -> None:
        with pytest.raises(ValueError):
            RawArtifactObservation(gcs_uri=GOOD_URI, present=False, checksum="abc", file_size_bytes=None)

    def test_absent_with_file_size_rejected(self) -> None:
        with pytest.raises(ValueError):
            RawArtifactObservation(gcs_uri=GOOD_URI, present=False, checksum=None, file_size_bytes=100)

    def test_present_with_missing_checksum_is_legitimate(self) -> None:
        obs = RawArtifactObservation(gcs_uri=GOOD_URI, present=True, checksum=None, file_size_bytes=100)
        assert obs.checksum is None


class TestRawArtifactInspectorIsAbstract:
    def test_cannot_be_instantiated_directly(self) -> None:
        with pytest.raises(TypeError):
            RawArtifactInspector()  # type: ignore[abstract]


class _FakeBlob:
    def __init__(self, exists: bool, checksum: str | None, size: int | None) -> None:
        self._exists = exists
        self.metadata = {"mercury_sha256": checksum} if checksum else {}
        self.size = size

    def reload(self) -> None:
        if not self._exists:
            raise gcs_exceptions.NotFound("not found")


class _FakeBucket:
    def __init__(self, blob: _FakeBlob) -> None:
        self._blob = blob

    def blob(self, object_name: str) -> _FakeBlob:
        return self._blob


class _FakeGcsClient:
    def __init__(self, blob: _FakeBlob | None = None, project: str | None = None) -> None:
        self._blob = blob or _FakeBlob(exists=False, checksum=None, size=None)

    def bucket(self, bucket_name: str) -> _FakeBucket:
        return _FakeBucket(self._blob)


@pytest.fixture()
def _fake_gcs_client(monkeypatch: pytest.MonkeyPatch):
    holder = {"blob": _FakeBlob(exists=False, checksum=None, size=None)}

    class _ClientFactory:
        def __call__(self, project: str | None = None) -> _FakeGcsClient:
            return _FakeGcsClient(blob=holder["blob"])

    monkeypatch.setattr(gcs, "Client", _ClientFactory())
    return holder


class TestGCSArtifactInspector:
    def test_existing_object_observation(self, _fake_gcs_client) -> None:
        _fake_gcs_client["blob"] = _FakeBlob(exists=True, checksum="abc123", size=100)
        inspector = GCSArtifactInspector()

        observation = inspector.inspect(GOOD_URI)

        assert observation.present is True
        assert observation.checksum == "abc123"
        assert observation.file_size_bytes == 100

    def test_missing_object_returns_present_false(self, _fake_gcs_client) -> None:
        _fake_gcs_client["blob"] = _FakeBlob(exists=False, checksum=None, size=None)
        inspector = GCSArtifactInspector()

        observation = inspector.inspect(GOOD_URI)

        assert observation.present is False
        assert observation.checksum is None
        assert observation.file_size_bytes is None

    def test_existing_object_without_checksum_metadata(self, _fake_gcs_client) -> None:
        _fake_gcs_client["blob"] = _FakeBlob(exists=True, checksum=None, size=50)
        inspector = GCSArtifactInspector()

        observation = inspector.inspect(GOOD_URI)

        assert observation.present is True
        assert observation.checksum is None

    def test_malformed_uri_rejected(self, _fake_gcs_client) -> None:
        inspector = GCSArtifactInspector()
        with pytest.raises(ValueError):
            inspector.inspect("not-a-gs-uri")

    def test_blank_uri_rejected(self, _fake_gcs_client) -> None:
        inspector = GCSArtifactInspector()
        with pytest.raises(ValueError):
            inspector.inspect("")

    def test_bucket_only_uri_without_object_rejected(self, _fake_gcs_client) -> None:
        inspector = GCSArtifactInspector()
        with pytest.raises(ValueError):
            inspector.inspect("gs://bucket-only")

    def test_other_api_failure_propagates(self, _fake_gcs_client) -> None:
        class _RaisingBlob(_FakeBlob):
            def reload(self) -> None:
                raise gcs_exceptions.Forbidden("permission denied")

        _fake_gcs_client["blob"] = _RaisingBlob(exists=True, checksum=None, size=None)
        inspector = GCSArtifactInspector()

        with pytest.raises(gcs_exceptions.Forbidden):
            inspector.inspect(GOOD_URI)

    def test_never_downloads_object_content(self) -> None:
        import inspect

        source_text = inspect.getsource(GCSArtifactInspector)
        assert "download" not in source_text.lower()
        assert "signed_url" not in source_text.lower()
        assert "public_url" not in source_text.lower()