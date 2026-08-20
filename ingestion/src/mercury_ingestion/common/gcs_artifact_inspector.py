"""GCS implementation of Mercury's read-only Raw artifact inspection (ADR-010 Phase 3C).

``GCSArtifactInspector`` reads only technical object metadata (existence,
size, and the ``mercury_sha256`` custom metadata ``GCSStorageManager``
attaches on upload) via ``blob.reload()``, which is a metadata-only GET
against GCS -- it never downloads object content, generates a signed or
public URL, or mutates the object in any way.
"""

from __future__ import annotations

from urllib.parse import urlparse

from google.api_core import exceptions as gcs_exceptions
from google.cloud import storage as gcs

from mercury_ingestion.common.artifact_inspection import RawArtifactInspector, RawArtifactObservation

_MERCURY_SHA256_KEY = "mercury_sha256"


def _require_non_blank(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


class GCSArtifactInspector(RawArtifactInspector):
    """Reads Raw artifact technical metadata directly from GCS.

    Authentication relies entirely on Application Default Credentials --
    this class never accepts explicit credentials. Construction performs
    no network call.
    """

    def __init__(self, project_id: str | None = None) -> None:
        if project_id is not None:
            _require_non_blank(project_id, "project_id")
        self.project_id = project_id
        self._client = gcs.Client(project=project_id)

    def inspect(self, gcs_uri: str) -> RawArtifactObservation:
        """Return technical metadata for the object at ``gcs_uri``.

        Raises:
            ValueError: if ``gcs_uri`` is blank or not a well-formed
                ``gs://bucket/object`` URI.
            google.api_core.exceptions.GoogleAPICallError: any backend
                failure other than "not found" (permission denied,
                service unavailable, ...) propagates unchanged -- that
                is a genuine inspection-infrastructure failure, not a
                normal "artifact missing" observation.
        """
        _require_non_blank(gcs_uri, "gcs_uri")
        bucket_name, object_name = _parse_gcs_uri(gcs_uri)

        blob = self._client.bucket(bucket_name).blob(object_name)
        try:
            blob.reload()
        except gcs_exceptions.NotFound:
            return RawArtifactObservation(gcs_uri=gcs_uri, present=False, checksum=None, file_size_bytes=None)

        metadata = blob.metadata or {}
        checksum = metadata.get(_MERCURY_SHA256_KEY)
        return RawArtifactObservation(
            gcs_uri=gcs_uri,
            present=True,
            checksum=checksum,
            file_size_bytes=blob.size,
        )


def _parse_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"gcs_uri must start with 'gs://': {gcs_uri!r}")
    parsed = urlparse(gcs_uri)
    bucket_name = parsed.netloc
    object_name = parsed.path.lstrip("/")
    if not bucket_name or not object_name:
        raise ValueError(f"gcs_uri must be a well-formed gs://bucket/object URI: {gcs_uri!r}")
    return bucket_name, object_name