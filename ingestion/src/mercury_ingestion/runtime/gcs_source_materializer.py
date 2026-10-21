"""Materialize durable GCS source input into temporary local storage.

Cloud Run local storage is ephemeral. This component downloads an
explicit set of immutable source files from an approved GCS prefix into
a caller-owned temporary directory.

It does not parse, transform, ingest, or persist source data. Those
responsibilities remain with the existing simulator and ingestion
framework.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from google.api_core import exceptions as gcs_exceptions
from google.cloud import storage as gcs


def _parse_gcs_uri(source_uri: str) -> tuple[str, str]:
    if not isinstance(source_uri, str):
        raise TypeError("source_uri must be a string")

    normalized_uri = source_uri.strip()

    if not normalized_uri:
        raise ValueError("source_uri cannot be blank")

    parsed = urlsplit(normalized_uri)

    if parsed.scheme != "gs" or not parsed.netloc:
        raise ValueError(
            "source_uri must be a valid gs:// URI with a bucket name"
        )

    if parsed.query or parsed.fragment:
        raise ValueError(
            "source_uri must not contain a query or fragment"
        )

    bucket_name = parsed.netloc
    object_prefix = parsed.path.strip("/")

    return bucket_name, object_prefix


def _validate_required_filenames(
    required_filenames: tuple[str, ...],
) -> None:
    if not isinstance(required_filenames, tuple):
        raise TypeError("required_filenames must be a tuple")

    if not required_filenames:
        raise ValueError("required_filenames cannot be empty")

    if len(set(required_filenames)) != len(required_filenames):
        raise ValueError(
            "required_filenames cannot contain duplicates"
        )

    for filename in required_filenames:
        if not isinstance(filename, str):
            raise TypeError(
                "every required filename must be a string"
            )

        if (
            not filename.strip()
            or filename != Path(filename).name
            or "/" in filename
            or "\\" in filename
        ):
            raise ValueError(
                "required filenames must be non-blank base filenames"
            )


class GCSSourceMaterializer:
    """Download explicit GCS source objects into a local directory.

    Authentication relies entirely on Application Default Credentials.
    Construction obtains only a local bucket handle and performs no
    download or bucket-metadata request.
    """

    def __init__(
        self,
        source_uri: str,
        required_filenames: tuple[str, ...],
        project_id: str | None = None,
    ) -> None:
        if project_id is not None:
            if not isinstance(project_id, str):
                raise TypeError("project_id must be a string or None")
            if not project_id.strip():
                raise ValueError(
                    "project_id cannot be blank when supplied"
                )

        _validate_required_filenames(required_filenames)

        bucket_name, object_prefix = _parse_gcs_uri(source_uri)

        self.source_uri = source_uri.strip()
        self.bucket_name = bucket_name
        self.object_prefix = object_prefix
        self.required_filenames = required_filenames
        self.project_id = (
            project_id.strip()
            if project_id is not None
            else None
        )

        self._client = gcs.Client(project=self.project_id)
        self._bucket = self._client.bucket(self.bucket_name)

    def materialize(
        self,
        destination_directory: Path,
    ) -> Path:
        """Download every required source file.

        Existing destination files are never overwritten. If a download
        fails, files created by this invocation are removed so callers
        never receive a partially materialized source directory.
        """
        if not isinstance(destination_directory, Path):
            raise TypeError(
                "destination_directory must be a pathlib.Path"
            )

        if (
            destination_directory.exists()
            and not destination_directory.is_dir()
        ):
            raise ValueError(
                "destination_directory exists and is not a directory"
            )

        destination_files = tuple(
            destination_directory / filename
            for filename in self.required_filenames
        )

        existing_files = tuple(
            path for path in destination_files if path.exists()
        )

        if existing_files:
            raise FileExistsError(
                "required destination file already exists: "
                f"{existing_files[0]}"
            )

        directory_created = not destination_directory.exists()
        destination_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        downloaded_files: list[Path] = []

        try:
            for filename, destination_file in zip(
                self.required_filenames,
                destination_files,
                strict=True,
            ):
                object_name = self._object_name(filename)
                blob = self._bucket.blob(object_name)

                try:
                    blob.download_to_filename(
                        str(destination_file)
                    )
                except gcs_exceptions.NotFound as exc:
                    raise FileNotFoundError(
                        "required source object was not found: "
                        f"gs://{self.bucket_name}/{object_name}"
                    ) from exc

                downloaded_files.append(destination_file)

        except BaseException:
            for downloaded_file in downloaded_files:
                if downloaded_file.exists():
                    downloaded_file.unlink()

            if (
                directory_created
                and destination_directory.exists()
                and not any(destination_directory.iterdir())
            ):
                destination_directory.rmdir()

            raise

        return destination_directory

    def _object_name(self, filename: str) -> str:
        if self.object_prefix:
            return f"{self.object_prefix}/{filename}"

        return filename