"""Local filesystem implementation of Mercury's Raw Landing storage.

This module preserves source files unchanged in an immutable, date-
partitioned landing zone and returns the technical facts (path, checksum,
size) needed to build ingestion metadata elsewhere. It intentionally does
not parse file content, count records, validate business rules, or talk to
any cloud service — those concerns belong to other components.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import uuid4

_CHUNK_SIZE = 1024 * 1024  # 1 MiB, used for streaming checksum computation


def _require_non_blank(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


def _require_safe_path_segment(value: str, field_name: str) -> None:
    """Ensure ``value`` is safe to use as a single directory name.

    This rejects blank values, the special "." and ".." segments, and any
    value containing a path separator, so a caller cannot use
    ``source_system``/``source_object`` to escape the intended directory
    level or traverse into another part of the filesystem.
    """
    _require_non_blank(value, field_name)
    if value in (".", ".."):
        raise ValueError(f"{field_name} cannot be '.' or '..': {value!r}")
    if "/" in value or "\\" in value:
        raise ValueError(f"{field_name} cannot contain a path separator: {value!r}")


@dataclass(frozen=True, slots=True)
class StorageResult:
    """Technical outcome of landing a single file.

    This is deliberately narrow: it reports where the file landed and how
    to verify it, not what the file contains.
    """

    landing_path: str
    checksum: str
    file_size_bytes: int

    def __post_init__(self) -> None:
        _require_non_blank(self.landing_path, "landing_path")
        _require_non_blank(self.checksum, "checksum")
        if self.file_size_bytes < 0:
            raise ValueError("file_size_bytes cannot be negative")


def _sha256_of(path: Path) -> str:
    """Compute the SHA-256 checksum of a file by streaming its contents."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class LocalStorageManager:
    """Local-disk implementation of the Raw Landing storage capability.

    Files are landed under::

        <root_directory>/raw/<source_system>/<source_object>/ingestion_date=YYYY-MM-DD/<original_filename>

    The root directory is not created until a file is actually saved, so
    constructing a manager has no side effects on the filesystem.

    Notes:
        This is the local filesystem implementation of Mercury's Raw
        Landing storage capability. A future implementation will target Google Cloud Storage while preserving the same storage contract and expected behavior where practical. Version 1 assumes a single writer for a given destination path and does not implement distributed concurrency control (e.g. locking or lease coordination across processes).
    """

    def __init__(self, root_directory: Path) -> None:
        if not isinstance(root_directory, Path):
            raise TypeError("root_directory must be a pathlib.Path")
        if root_directory.exists() and not root_directory.is_dir():
            raise ValueError(f"root_directory exists and is not a directory: {root_directory}")

        self.root_directory = root_directory

    def save_file(
        self,
        source_file: Path,
        source_system: str,
        source_object: str,
        ingestion_date: date,
    ) -> StorageResult:
        """Copy ``source_file`` unchanged into the Raw Landing zone.

        Raises:
            FileNotFoundError: if ``source_file`` does not exist.
            ValueError: if ``source_file`` is not a regular file, or if
                ``source_system``/``source_object`` are blank.
            FileExistsError: if the destination file already exists.
        """
        if not source_file.exists():
            raise FileNotFoundError(f"source_file does not exist: {source_file}")
        if not source_file.is_file():
            raise ValueError(f"source_file is not a regular file: {source_file}")

        _require_safe_path_segment(source_system, "source_system")
        _require_safe_path_segment(source_object, "source_object")

        destination_dir = self._build_destination_dir(source_system, source_object, ingestion_date)
        destination_file = destination_dir / source_file.name

        if destination_file.exists():
            raise FileExistsError(f"destination file already exists: {destination_file}")

        destination_dir.mkdir(parents=True, exist_ok=True)
        self._copy_atomically(source_file, destination_file)

        checksum = _sha256_of(destination_file)
        file_size_bytes = destination_file.stat().st_size

        return StorageResult(
            landing_path=str(destination_file),
            checksum=checksum,
            file_size_bytes=file_size_bytes,
        )

    def _build_destination_dir(
        self,
        source_system: str,
        source_object: str,
        ingestion_date: date,
    ) -> Path:
        return (
            self.root_directory
            / "raw"
            / source_system
            / source_object
            / f"ingestion_date={ingestion_date.isoformat()}"
        )

    @staticmethod
    def _copy_atomically(source_file: Path, destination_file: Path) -> None:
        """Copy to a temp file in the destination directory, then rename.

        This avoids ever exposing a partially written file at
        ``destination_file``: readers either see nothing or the complete
        file. The temporary file is removed if the copy fails.
        """
        temp_file = destination_file.with_name(f".{destination_file.name}.tmp-{uuid4().hex}")
        try:
            shutil.copyfile(source_file, temp_file)
            temp_file.replace(destination_file)
        except BaseException:
            temp_file.unlink(missing_ok=True)
            raise