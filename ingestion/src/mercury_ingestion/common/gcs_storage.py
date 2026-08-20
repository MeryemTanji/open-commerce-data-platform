"""Google Cloud Storage implementation of Mercury's Raw Landing storage.

This module implements ``GCSStorageManager``, the second concrete
``StorageManager`` (see ``storage.py`` and ADR-006). It lands one
immutable Raw source artifact into a GCS bucket and returns the same
``StorageResult`` that ``LocalStorageManager`` returns, so connectors
never need to know which storage backend they are running against.

This module intentionally contains only provider-specific Google Cloud
plumbing — bucket/blob handling, object naming, and precondition-based
atomic upload. It does not parse file content, count records, validate
business rules, load BigQuery, or provision infrastructure. Those
concerns belong to other components.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from google.api_core import exceptions as gcs_exceptions
from google.cloud import storage as gcs

from mercury_ingestion.common.storage import (
    StorageManager,
    StorageResult,
    _require_non_blank,
    _require_safe_path_segment,
    _sha256_of,
)


def _build_object_name(
    source_system: str,
    source_object: str,
    ingestion_date: date,
    filename: str,
) -> str:
    """Build the GCS object name using the shared Raw Landing hierarchy.

    Mirrors ``LocalStorageManager``'s directory layout exactly, but as a
    provider object-name string joined with ``/`` rather than a
    filesystem ``Path`` — GCS object names are not filesystem paths.
    """
    return "/".join(
        (
            "raw",
            source_system,
            source_object,
            f"ingestion_date={ingestion_date.isoformat()}",
            filename,
        )
    )


class GCSStorageManager(StorageManager):
    """Google Cloud Storage implementation of the Raw Landing capability.

    Objects are landed under the same logical hierarchy as
    ``LocalStorageManager``::

        raw/<source_system>/<source_object>/ingestion_date=YYYY-MM-DD/<original_filename>

    Authentication relies entirely on Application Default Credentials —
    this class never accepts explicit credentials, a service-account
    file, or any other auth material. Construction is lightweight and
    performs no network call: it only obtains a local bucket handle via
    ``client.bucket(bucket_name)``, which does not fetch bucket metadata
    or otherwise validate that the bucket exists.

    Uploads are atomic and overwrite-safe via GCS's create-only
    generation precondition (``if_generation_match=0``), never via a
    check-then-upload sequence, which would be racy. Mercury's SHA-256
    checksum is computed from the local source file being uploaded, the
    same integrity contract ``LocalStorageManager`` uses, so
    ``StorageResult.checksum`` means the same thing regardless of which
    ``StorageManager`` implementation produced it. That same checksum is
    also attached to the uploaded object as GCS custom metadata under
    the key ``mercury_sha256`` (the hexadecimal digest only -- nothing
    else), computed before the upload so the object and its checksum
    metadata are created together in one atomic write. This lets a
    later read-only inspector confirm an artifact's integrity from
    object metadata alone, without ever downloading its contents.
    """

    def __init__(self, bucket_name: str, project_id: str | None = None) -> None:
        _require_non_blank(bucket_name, "bucket_name")
        if project_id is not None:
            _require_non_blank(project_id, "project_id")

        self.bucket_name = bucket_name
        self.project_id = project_id
        self._client = gcs.Client(project=project_id)
        self._bucket = self._client.bucket(bucket_name)

    def save_file(
        self,
        source_file: Path,
        source_system: str,
        source_object: str,
        ingestion_date: date,
    ) -> StorageResult:
        """Upload ``source_file`` unchanged into GCS Raw Landing storage.

        Raises:
            FileNotFoundError: if ``source_file`` does not exist.
            ValueError: if ``source_file`` is not a regular file, or if
                ``source_system``/``source_object`` are unsafe path
                segments.
            FileExistsError: if the destination object already exists
                (the ``if_generation_match=0`` precondition failed).
            google.api_core.exceptions.GoogleAPICallError: any other
                provider-side failure (auth, permissions, bucket not
                found, network, service errors) propagates unchanged —
                ``BaseConnector`` already owns translating ingestion
                failures into FAILED metadata.
        """
        if not source_file.exists():
            raise FileNotFoundError(f"source_file does not exist: {source_file}")
        if not source_file.is_file():
            raise ValueError(f"source_file is not a regular file: {source_file}")

        _require_safe_path_segment(source_system, "source_system")
        _require_safe_path_segment(source_object, "source_object")

        object_name = _build_object_name(source_system, source_object, ingestion_date, source_file.name)
        destination_uri = f"gs://{self.bucket_name}/{object_name}"

        # Computed before upload so the object and its mercury_sha256
        # custom metadata are created together in one atomic write,
        # rather than the object existing briefly without it.
        checksum = _sha256_of(source_file)
        file_size_bytes = source_file.stat().st_size

        blob = self._bucket.blob(object_name)
        blob.metadata = {"mercury_sha256": checksum}
        try:
            blob.upload_from_filename(str(source_file), if_generation_match=0)
        except gcs_exceptions.PreconditionFailed as exc:
            raise FileExistsError(f"destination object already exists: {destination_uri}") from exc

        return StorageResult(
            landing_path=destination_uri,
            checksum=checksum,
            file_size_bytes=file_size_bytes,
        )