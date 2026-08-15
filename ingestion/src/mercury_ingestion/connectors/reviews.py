"""Mercury's seventh concrete ingestion connector: reviews.

This module implements the local, Olist-backed extraction of Nova
Commerce's order-review source, under the ``review_platform`` source
system. Its CSV-specific technical validation and record counting are
inherited from ``BaseCsvConnector`` (per ADR-005); this module supplies
only the source identity, required schema, and domain documentation for
the reviews source.

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
added as a separate connector that reuses Mercury's shared connector
lifecycle unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import final

from mercury_ingestion.common.storage import LocalStorageManager
from mercury_ingestion.connectors.csv_base import BaseCsvConnector

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
class ReviewsConnector(BaseCsvConnector):
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
            required_columns=REQUIRED_COLUMNS,
            storage_manager=storage_manager,
            schema_version=schema_version,
        )