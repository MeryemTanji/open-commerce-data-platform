"""Mercury's seventh concrete ingestion connector: reviews.

This module implements the local, Olist-backed extraction of Nova
Commerce's order-review source, under the ``review_platform`` source
system. It validates the technical structure of the source CSV (file
type, encoding, required columns) and counts logical records; everything
else in the ingestion lifecycle — metadata, immutable landing,
success/failure handling — is provided by ``BaseConnector``.

Dataset grain: one row represents one review. The expected source-level
key is ``review_id``. ``order_id`` is a relationship key back to the
orders source, not the row's unique identity — a single order may
receive more than one review record in the raw extract, and this
connector does not enforce one-review-per-order. This connector also
does not validate ``review_id`` uniqueness. Review-id uniqueness,
review-score validation, timestamp parsing, text-quality rules,
referential integrity to orders, and canonical review modelling are all
downstream Dataform staging concerns, not raw ingestion concerns.

A future API-based review source (or a different file format) can be
added as a separate connector that implements the same two hooks while
reusing Mercury's shared connector lifecycle unchanged.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import final

from mercury_ingestion.common.storage import LocalStorageManager
from mercury_ingestion.connectors.base import BaseConnector

_ENCODING = "utf-8-sig"

REQUIRED_COLUMNS = frozenset(
    {
        "review_id",
        "order_id",
        "review_score",
        "review_comment_title",
        "review_comment_message",
        "review_creation_date",
        "review_answer_timestamp",
    }
)


@final
class ReviewsConnector(BaseConnector):
    """Ingests Nova Commerce's order-reviews CSV (Olist-backed, local file).

    Grain: one row per review. The expected source key is ``review_id``
    — this connector does not validate its uniqueness. ``order_id`` is a
    relationship key back to the orders source, not the row's unique
    identity; this connector does not enforce one-review-per-order.

    This connector performs technical, structural validation only — it
    confirms the file is readable, correctly typed, and has the columns
    downstream layers depend on. It does not judge the quality of the
    business data itself. In particular it does not: reject an
    out-of-range or blank ``review_score``, reject a blank
    ``review_comment_title`` or ``review_comment_message``, validate
    ``review_creation_date`` or ``review_answer_timestamp`` formatting,
    validate uniqueness of ``review_id``, or check ``order_id`` against
    the orders source. Those checks belong to later staging/canonical
    models, not to raw ingestion.
    """

    SOURCE_SYSTEM = "review_platform"
    SOURCE_OBJECT = "reviews"

    def __init__(
        self,
        source_file: Path,
        storage_manager: LocalStorageManager,
        schema_version: str | None = "1.0",
    ) -> None:
        super().__init__(
            source_file=source_file,
            source_system=self.SOURCE_SYSTEM,
            source_object=self.SOURCE_OBJECT,
            storage_manager=storage_manager,
            schema_version=schema_version,
        )

    def validate_source(self) -> None:
        """Validate technical structure only; raise on missing/malformed input.

        Raises:
            FileNotFoundError: if the source file does not exist.
            ValueError: if the source is not a regular file, is not a
                ``.csv`` file, is empty, has no header, or is missing
                required columns.
            UnicodeDecodeError: propagates unchanged if the file cannot be
                decoded as UTF-8; ``BaseConnector`` converts it to FAILED
                metadata like any other exception.
        """
        if not self.source_file.exists():
            raise FileNotFoundError(f"source_file does not exist: {self.source_file}")
        if not self.source_file.is_file():
            raise ValueError(f"source_file is not a regular file: {self.source_file}")
        if self.source_file.suffix.lower() != ".csv":
            raise ValueError(f"source_file must have a .csv extension: {self.source_file}")
        if self.source_file.stat().st_size == 0:
            raise ValueError(f"source_file is empty: {self.source_file}")

        with self.source_file.open(encoding=_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames
            if not fieldnames:
                raise ValueError(f"source_file has no header row: {self.source_file}")

            missing = REQUIRED_COLUMNS - set(fieldnames)
            if missing:
                raise ValueError(
                    "source_file is missing required columns: "
                    f"{', '.join(sorted(missing))}"
                )

    def count_records(self) -> int:
        """Return the number of data rows in the CSV, excluding the header.

        ``csv.DictReader`` skips blank physical lines on its own, so they
        are not counted as review records. A quoted, multiline review
        comment counts as a single logical row, since ``csv.DictReader``
        (via the underlying ``csv.reader``) already resolves embedded
        newlines within quoted fields into one record.
        """
        with self.source_file.open(encoding=_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            return sum(1 for _ in reader)