"""Mercury's Olist historical source-delivery simulator.

Per ADR-007 and the ingestion-framework design, the Olist dataset is a
collection of static historical CSV files. To make Mercury behave like a
real data platform with different source-refresh patterns, this module
derives two kinds of simulated deliveries from those immutable files:

- **Initial / one-off master-reference loads** for sources with no
  reliable temporal information (customers, products, sellers,
  geolocations) — copied byte-for-byte unchanged.
- **Daily incremental transactional loads** for sources with defensible
  temporal information (orders, order items, payments, reviews) —
  filtered by business date and written out as their own CSV files.

This module is strictly upstream of ingestion::

    Immutable Olist CSVs
            |
    OlistSourceSimulator
            |
    Generated source delivery CSVs
            |
    Existing connectors -> StorageManager -> Raw Landing

It has no knowledge of connectors, storage backends, ingestion metadata,
or Dataform, and never modifies anything under ``source_directory``.
"""

from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

_ENCODING = "utf-8-sig"

# Stable source_object identity -> immutable Olist source filename.
SOURCE_FILENAMES: dict[str, str] = {
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "geolocations": "olist_geolocation_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
}

# Sources with no reliable temporal information (ADR-007): treated as a
# static initial/master load, copied byte-for-byte unchanged.
INITIAL_SOURCE_OBJECTS: tuple[str, ...] = ("customers", "products", "sellers", "geolocations")

# Sources with defensible temporal information (ADR-007): replayed as
# daily incremental deliveries filtered by business date.
DAILY_SOURCE_OBJECTS: tuple[str, ...] = ("orders", "order_items", "payments", "reviews")

_ORDER_TIMESTAMP_FIELD = "order_purchase_timestamp"
_REVIEW_TIMESTAMP_FIELD = "review_creation_date"
_ORDER_ID_FIELD = "order_id"

_TIMESTAMP_FORMATS: tuple[str, ...] = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d")

# Minimal technical fields the simulation algorithm itself depends on to
# determine delivery membership -- not the complete connector schema.
# Orders needs both its identity and its purchase timestamp; Order Items
# and Payments only need order_id to join against the day's Orders;
# Reviews only needs its own creation timestamp.
_ORDERS_REQUIRED_SIMULATION_FIELDS = frozenset({_ORDER_ID_FIELD, _ORDER_TIMESTAMP_FIELD})
_ORDER_ID_REQUIRED_SIMULATION_FIELDS = frozenset({_ORDER_ID_FIELD})
_REVIEWS_REQUIRED_SIMULATION_FIELDS = frozenset({_REVIEW_TIMESTAMP_FIELD})


def _require_non_blank(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


def _require_fields(fieldnames: list[str], required_fields: frozenset[str], source_path: Path) -> None:
    """Ensure the CSV header contains the fields simulation logic depends on.

    This validates only what the simulation algorithm itself needs to
    determine delivery membership -- not the complete source schema a
    connector will later enforce. Checked immediately after reading the
    header, so a header-only file with zero data rows still fails if a
    simulation-critical field is missing (there would otherwise be no
    row on which a missing-field problem could ever surface).
    """
    missing = required_fields - set(fieldnames)
    if missing:
        raise ValueError(
            f"missing required simulation fields in {source_path.name}: {', '.join(sorted(missing))}"
        )


@dataclass(frozen=True, slots=True)
class SimulatedFile:
    """One generated simulated source-delivery CSV.

    Deliberately narrow: it reports the stable ``source_object``
    identity, where the file was written, and how many logical records
    it contains — nothing storage- or ingestion-specific.
    """

    source_object: str
    path: Path
    record_count: int

    def __post_init__(self) -> None:
        _require_non_blank(self.source_object, "source_object")
        if not isinstance(self.path, Path):
            raise TypeError("path must be a pathlib.Path")
        if self.record_count < 0:
            raise ValueError("record_count cannot be negative")


@dataclass(frozen=True, slots=True)
class InitialSimulationResult:
    """Outcome of a single ``generate_initial_load()`` call."""

    files: tuple[SimulatedFile, ...]


@dataclass(frozen=True, slots=True)
class DailySimulationResult:
    """Outcome of a single ``generate_daily_load()`` call."""

    simulation_date: date
    files: tuple[SimulatedFile, ...]


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV's header and data rows without altering any values."""
    with path.open(encoding=_ENCODING, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    return fieldnames, rows


def _count_csv_records(path: Path) -> int:
    """Count logical CSV data rows (excluding header) without modifying the file."""
    with path.open(encoding=_ENCODING, newline="") as handle:
        reader = csv.DictReader(handle)
        return sum(1 for _ in reader)


def _write_csv_subset(output_path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> int:
    """Write a header plus the given rows exactly, returning the row count."""
    with output_path.open("w", encoding=_ENCODING, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return len(rows)


def _parse_date_prefix(value: str | None, source_path: Path, field_name: str, row_number: int) -> date:
    """Parse the business date out of a raw Olist timestamp string.

    Used solely to decide simulated-delivery membership; the original
    timestamp text is never rewritten. Raises ``ValueError`` with the
    file, field, row, and offending value if the timestamp is blank or
    does not match a recognized Olist timestamp format, so a bad
    required timestamp fails loudly rather than silently dropping the
    row from every simulated delivery.
    """
    if value is None or not value.strip():
        raise ValueError(
            f"missing required {field_name} in {source_path.name} at data row "
            f"{row_number}: {value!r}"
        )
    text = value.strip()
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(
        f"malformed {field_name} in {source_path.name} at data row {row_number}: {value!r}"
    )


class OlistSourceSimulator:
    """Derives simulated Olist source deliveries from immutable full CSVs.

    Construction only stores configuration and has no filesystem side
    effects: no directories are created and no source files are read
    until ``generate_initial_load()`` or ``generate_daily_load()`` is
    called. Generated deliveries are immutable once created — rerunning
    either method against an already-generated destination raises
    ``FileExistsError`` rather than overwriting it.
    """

    def __init__(self, source_directory: Path, output_directory: Path) -> None:
        if not isinstance(source_directory, Path):
            raise TypeError("source_directory must be a pathlib.Path")
        if not isinstance(output_directory, Path):
            raise TypeError("output_directory must be a pathlib.Path")

        self.source_directory = source_directory
        self.output_directory = output_directory

    def generate_initial_load(self) -> InitialSimulationResult:
        """Generate the four static initial/master-reference deliveries.

        ``customers``, ``products``, ``sellers``, and ``geolocations``
        are copied byte-for-byte unchanged into
        ``<output_directory>/initial/``. Record counts are determined by
        reading the copied bytes, never by modifying them. The four
        files are staged in a temporary directory and only published via
        a single atomic directory rename once every file has been
        copied and counted, so ``initial/`` only ever becomes visible
        as a complete, four-file delivery -- never partially.

        Raises:
            FileNotFoundError: if a required source file is missing.
            ValueError: if a required source path is not a regular file.
            FileExistsError: if the destination ``initial/`` delivery
                directory already exists.
        """
        source_paths = {obj: self._require_source_file(obj) for obj in INITIAL_SOURCE_OBJECTS}

        destination_dir = self.output_directory / "initial"
        if destination_dir.exists():
            raise FileExistsError(f"initial delivery already exists: {destination_dir}")

        temp_dir = self.output_directory / f".initial.tmp-{uuid4().hex}"
        try:
            temp_dir.mkdir(parents=True, exist_ok=False)
            staged: list[SimulatedFile] = []
            for source_object in INITIAL_SOURCE_OBJECTS:
                filename = SOURCE_FILENAMES[source_object]
                temp_target = temp_dir / filename
                shutil.copyfile(source_paths[source_object], temp_target)
                record_count = _count_csv_records(temp_target)
                staged.append(
                    SimulatedFile(
                        source_object=source_object,
                        path=destination_dir / filename,
                        record_count=record_count,
                    )
                )
        except BaseException:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        # Only now, with every file fully staged, do we publish the
        # complete delivery in one atomic directory rename -- a failure
        # above never leaves a partial initial delivery visible at
        # destination_dir.
        temp_dir.rename(destination_dir)

        return InitialSimulationResult(files=tuple(staged))

    def generate_daily_load(self, simulation_date: date) -> DailySimulationResult:
        """Generate one day's incremental orders/order_items/payments/reviews.

        Orders are selected by ``DATE(order_purchase_timestamp) ==
        simulation_date``. Order Items and Payments are selected by
        belonging to that day's selected Order IDs, not by their own
        timestamps. Reviews are selected independently, by
        ``DATE(review_creation_date) == simulation_date``, and may
        therefore arrive on a different day than their parent Order.

        All four files are always created, even when a source has zero
        matching rows for the day; a zero-record source is written as a
        valid header-only CSV.

        Raises:
            FileNotFoundError: if a required source file is missing.
            ValueError: if a required source path is not a regular file,
                or if a required timestamp field is blank/malformed.
            FileExistsError: if the destination daily delivery already
                exists.
        """
        orders_path = self._require_source_file("orders")
        order_items_path = self._require_source_file("order_items")
        payments_path = self._require_source_file("payments")
        reviews_path = self._require_source_file("reviews")

        destination_dir = self.output_directory / "daily" / simulation_date.isoformat()
        if destination_dir.exists():
            raise FileExistsError(f"daily delivery already exists: {destination_dir}")

        orders_fieldnames, orders_rows, order_ids = self._select_daily_orders(
            orders_path, simulation_date
        )
        order_items_fieldnames, order_items_rows = self._select_by_order_id(
            order_items_path, order_ids
        )
        payments_fieldnames, payments_rows = self._select_by_order_id(payments_path, order_ids)
        reviews_fieldnames, reviews_rows = self._select_daily_reviews(reviews_path, simulation_date)

        selections: tuple[tuple[str, list[str], list[dict[str, str]]], ...] = (
            ("orders", orders_fieldnames, orders_rows),
            ("order_items", order_items_fieldnames, order_items_rows),
            ("payments", payments_fieldnames, payments_rows),
            ("reviews", reviews_fieldnames, reviews_rows),
        )

        temp_dir = self.output_directory / f".daily.tmp-{uuid4().hex}"
        try:
            temp_dir.mkdir(parents=True, exist_ok=False)
            staged: list[SimulatedFile] = []
            for source_object, fieldnames, rows in selections:
                filename = SOURCE_FILENAMES[source_object]
                output_path = temp_dir / filename
                record_count = _write_csv_subset(output_path, fieldnames, rows)
                staged.append(
                    SimulatedFile(
                        source_object=source_object,
                        path=destination_dir / filename,
                        record_count=record_count,
                    )
                )
        except BaseException:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        # Only now, with the full day's delivery fully staged, do we
        # make it visible at destination_dir in one atomic rename -- a
        # failure above never leaves a partial daily delivery behind.
        destination_dir.parent.mkdir(parents=True, exist_ok=True)
        temp_dir.rename(destination_dir)

        return DailySimulationResult(simulation_date=simulation_date, files=tuple(staged))

    def _require_source_file(self, source_object: str) -> Path:
        path = self.source_directory / SOURCE_FILENAMES[source_object]
        if not path.exists():
            raise FileNotFoundError(f"required source file does not exist: {path}")
        if not path.is_file():
            raise ValueError(f"required source path is not a regular file: {path}")
        return path

    def _select_daily_orders(
        self, orders_path: Path, simulation_date: date
    ) -> tuple[list[str], list[dict[str, str]], set[str]]:
        """Return orders header, matched rows, and their order_id set for the day."""
        fieldnames, rows = _read_csv_rows(orders_path)
        _require_fields(fieldnames, _ORDERS_REQUIRED_SIMULATION_FIELDS, orders_path)
        matched_rows: list[dict[str, str]] = []
        order_ids: set[str] = set()
        for row_number, row in enumerate(rows, start=1):
            purchase_date = _parse_date_prefix(
                row.get(_ORDER_TIMESTAMP_FIELD), orders_path, _ORDER_TIMESTAMP_FIELD, row_number
            )
            if purchase_date == simulation_date:
                matched_rows.append(row)
                order_ids.add(row.get(_ORDER_ID_FIELD, ""))
        return fieldnames, matched_rows, order_ids

    def _select_by_order_id(
        self, path: Path, order_ids: set[str]
    ) -> tuple[list[str], list[dict[str, str]]]:
        """Return header and every row (preserving order/duplicates) whose order_id matches."""
        fieldnames, rows = _read_csv_rows(path)
        _require_fields(fieldnames, _ORDER_ID_REQUIRED_SIMULATION_FIELDS, path)
        selected = [row for row in rows if row.get(_ORDER_ID_FIELD) in order_ids]
        return fieldnames, selected

    def _select_daily_reviews(
        self, reviews_path: Path, simulation_date: date
    ) -> tuple[list[str], list[dict[str, str]]]:
        """Return reviews header and rows whose review_creation_date matches the day."""
        fieldnames, rows = _read_csv_rows(reviews_path)
        _require_fields(fieldnames, _REVIEWS_REQUIRED_SIMULATION_FIELDS, reviews_path)
        matched_rows: list[dict[str, str]] = []
        for row_number, row in enumerate(rows, start=1):
            review_date = _parse_date_prefix(
                row.get(_REVIEW_TIMESTAMP_FIELD), reviews_path, _REVIEW_TIMESTAMP_FIELD, row_number
            )
            if review_date == simulation_date:
                matched_rows.append(row)
        return fieldnames, matched_rows