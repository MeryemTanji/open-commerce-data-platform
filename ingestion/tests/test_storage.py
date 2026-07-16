"""Unit tests for mercury_ingestion.common.storage."""

from __future__ import annotations

import dataclasses
import hashlib
from datetime import date
from pathlib import Path

import pytest

from mercury_ingestion.common import storage as storage_module
from mercury_ingestion.common.storage import LocalStorageManager, StorageResult

INGESTION_DATE = date(2026, 7, 14)


def _write_source_file(tmp_path: Path, name: str = "orders.csv", content: bytes = b"id,amount\n1,10\n") -> Path:
    source_file = tmp_path / "source" / name
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(content)
    return source_file


class TestSuccessfulSave:
    def test_returns_storage_result(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path)
        manager = LocalStorageManager(tmp_path / "landing")

        result = manager.save_file(
            source_file=source_file,
            source_system="olist",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        assert isinstance(result, StorageResult)
        assert Path(result.landing_path).exists()
        assert result.file_size_bytes == source_file.stat().st_size

    def test_expected_directory_structure(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path)
        root = tmp_path / "landing"
        manager = LocalStorageManager(root)

        result = manager.save_file(
            source_file=source_file,
            source_system="olist",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        expected = root / "raw" / "olist" / "orders" / "ingestion_date=2026-07-14" / "orders.csv"
        assert Path(result.landing_path) == expected

    def test_destination_directory_is_created(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path)
        root = tmp_path / "landing"
        assert not root.exists()
        manager = LocalStorageManager(root)

        manager.save_file(
            source_file=source_file,
            source_system="olist",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        assert (root / "raw" / "olist" / "orders" / "ingestion_date=2026-07-14").is_dir()

    def test_original_filename_is_preserved(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path, name="weird-name_v2.CSV")
        manager = LocalStorageManager(tmp_path / "landing")

        result = manager.save_file(
            source_file=source_file,
            source_system="olist",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        assert Path(result.landing_path).name == "weird-name_v2.CSV"

    def test_source_bytes_are_unchanged(self, tmp_path: Path) -> None:
        content = b"id,amount\n1,10\n2,20\n"
        source_file = _write_source_file(tmp_path, content=content)
        manager = LocalStorageManager(tmp_path / "landing")

        result = manager.save_file(
            source_file=source_file,
            source_system="olist",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        assert Path(result.landing_path).read_bytes() == content

    def test_checksum_matches_sha256_of_landed_file(self, tmp_path: Path) -> None:
        content = b"id,amount\n1,10\n2,20\n"
        source_file = _write_source_file(tmp_path, content=content)
        manager = LocalStorageManager(tmp_path / "landing")

        result = manager.save_file(
            source_file=source_file,
            source_system="olist",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        expected_checksum = hashlib.sha256(content).hexdigest()
        assert result.checksum == expected_checksum

    def test_file_size_is_correct(self, tmp_path: Path) -> None:
        content = b"x" * 12345
        source_file = _write_source_file(tmp_path, content=content)
        manager = LocalStorageManager(tmp_path / "landing")

        result = manager.save_file(
            source_file=source_file,
            source_system="olist",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        assert result.file_size_bytes == 12345


class TestSourceValidation:
    def test_missing_source_file_raises(self, tmp_path: Path) -> None:
        manager = LocalStorageManager(tmp_path / "landing")

        with pytest.raises(FileNotFoundError):
            manager.save_file(
                source_file=tmp_path / "does_not_exist.csv",
                source_system="olist",
                source_object="orders",
                ingestion_date=INGESTION_DATE,
            )

    def test_source_path_is_a_directory_raises(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "a_directory"
        source_dir.mkdir()
        manager = LocalStorageManager(tmp_path / "landing")

        with pytest.raises(ValueError):
            manager.save_file(
                source_file=source_dir,
                source_system="olist",
                source_object="orders",
                ingestion_date=INGESTION_DATE,
            )

    def test_blank_source_system_raises(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path)
        manager = LocalStorageManager(tmp_path / "landing")

        with pytest.raises(ValueError):
            manager.save_file(
                source_file=source_file,
                source_system="   ",
                source_object="orders",
                ingestion_date=INGESTION_DATE,
            )

    def test_blank_source_object_raises(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path)
        manager = LocalStorageManager(tmp_path / "landing")

        with pytest.raises(ValueError):
            manager.save_file(
                source_file=source_file,
                source_system="olist",
                source_object="",
                ingestion_date=INGESTION_DATE,
            )


class TestUnsafePathSegments:
    UNSAFE_SEGMENTS = [
        ".",
        "..",
        "../orders",
        "platform/orders",
        r"platform\orders",
    ]

    @pytest.mark.parametrize("unsafe_value", UNSAFE_SEGMENTS)
    def test_unsafe_source_system_raises(self, tmp_path: Path, unsafe_value: str) -> None:
        source_file = _write_source_file(tmp_path)
        manager = LocalStorageManager(tmp_path / "landing")

        with pytest.raises(ValueError):
            manager.save_file(
                source_file=source_file,
                source_system=unsafe_value,
                source_object="orders",
                ingestion_date=INGESTION_DATE,
            )

    @pytest.mark.parametrize("unsafe_value", UNSAFE_SEGMENTS)
    def test_unsafe_source_object_raises(self, tmp_path: Path, unsafe_value: str) -> None:
        source_file = _write_source_file(tmp_path)
        manager = LocalStorageManager(tmp_path / "landing")

        with pytest.raises(ValueError):
            manager.save_file(
                source_file=source_file,
                source_system="olist",
                source_object=unsafe_value,
                ingestion_date=INGESTION_DATE,
            )


class TestNoOverwrite:
    def test_destination_already_exists_raises(self, tmp_path: Path) -> None:
        source_file = _write_source_file(tmp_path)
        manager = LocalStorageManager(tmp_path / "landing")

        manager.save_file(
            source_file=source_file,
            source_system="olist",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        with pytest.raises(FileExistsError):
            manager.save_file(
                source_file=source_file,
                source_system="olist",
                source_object="orders",
                ingestion_date=INGESTION_DATE,
            )

    def test_no_overwrite_occurs_after_conflict(self, tmp_path: Path) -> None:
        original_content = b"original content"
        source_file = _write_source_file(tmp_path, content=original_content)
        manager = LocalStorageManager(tmp_path / "landing")

        first_result = manager.save_file(
            source_file=source_file,
            source_system="olist",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )

        # Attempt to land a different file at the same destination path.
        source_file.write_bytes(b"different content, same filename")
        with pytest.raises(FileExistsError):
            manager.save_file(
                source_file=source_file,
                source_system="olist",
                source_object="orders",
                ingestion_date=INGESTION_DATE,
            )

        assert Path(first_result.landing_path).read_bytes() == original_content


class TestStorageResult:
    def test_is_immutable(self) -> None:
        result = StorageResult(landing_path="raw/x", checksum="abc", file_size_bytes=10)

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.file_size_bytes = 20  # type: ignore[misc]

    def test_blank_landing_path_raises(self) -> None:
        with pytest.raises(ValueError):
            StorageResult(landing_path="   ", checksum="abc", file_size_bytes=10)

    def test_blank_checksum_raises(self) -> None:
        with pytest.raises(ValueError):
            StorageResult(landing_path="raw/x", checksum="", file_size_bytes=10)

    def test_negative_file_size_raises(self) -> None:
        with pytest.raises(ValueError):
            StorageResult(landing_path="raw/x", checksum="abc", file_size_bytes=-1)


class TestRootDirectoryHandling:
    def test_root_path_that_is_an_existing_file_is_rejected(self, tmp_path: Path) -> None:
        root_as_file = tmp_path / "root_is_a_file"
        root_as_file.write_text("not a directory")

        with pytest.raises(ValueError):
            LocalStorageManager(root_as_file)

    def test_root_directory_is_not_created_during_init(self, tmp_path: Path) -> None:
        root = tmp_path / "landing"

        LocalStorageManager(root)

        assert not root.exists()

    def test_non_path_root_directory_raises_type_error(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            LocalStorageManager(str(tmp_path / "landing"))  # type: ignore[arg-type]


class TestAtomicCopyFailureCleanup:
    def test_temp_file_is_cleaned_up_if_copy_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source_file = _write_source_file(tmp_path)
        root = tmp_path / "landing"
        manager = LocalStorageManager(root)

        def _raise_copyfile(*_args: object, **_kwargs: object) -> None:
            raise OSError("simulated copy failure")

        monkeypatch.setattr(storage_module.shutil, "copyfile", _raise_copyfile)

        with pytest.raises(OSError):
            manager.save_file(
                source_file=source_file,
                source_system="olist",
                source_object="orders",
                ingestion_date=INGESTION_DATE,
            )

        destination_dir = root / "raw" / "olist" / "orders" / "ingestion_date=2026-07-14"
        assert destination_dir.is_dir()
        assert list(destination_dir.iterdir()) == []

    def test_no_destination_file_left_behind_after_failed_copy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source_file = _write_source_file(tmp_path)
        manager = LocalStorageManager(tmp_path / "landing")

        def _raise_copyfile(*_args: object, **_kwargs: object) -> None:
            raise OSError("simulated copy failure")

        monkeypatch.setattr(storage_module.shutil, "copyfile", _raise_copyfile)

        with pytest.raises(OSError):
            manager.save_file(
                source_file=source_file,
                source_system="olist",
                source_object="orders",
                ingestion_date=INGESTION_DATE,
            )

        # A subsequent, non-monkeypatched save should succeed cleanly,
        # proving no leftover destination file blocks it.
        monkeypatch.undo()
        result = manager.save_file(
            source_file=source_file,
            source_system="olist",
            source_object="orders",
            ingestion_date=INGESTION_DATE,
        )
        assert Path(result.landing_path).exists()