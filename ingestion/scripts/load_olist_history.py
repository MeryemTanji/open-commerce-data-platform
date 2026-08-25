"""Generate and replay the complete simulated Olist transactional history.

This script is an operational entry point for populating Mercury's Raw layer
from the historical Olist source dataset.

It:

1. determines the complete transactional delivery-date range;
2. generates the local daily Olist simulation;
3. initialises Mercury's cloud-backed replay dependencies;
4. ensures replay-state and provenance resources exist;
5. runs either a one-day smoke test or the complete historical replay.

The Olist-specific ingestion-date rule remains owned by
OlistSimulatedSourceProvider. This script does not derive ingestion dates.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from pathlib import Path

from mercury_ingestion.common.gcs_storage import GCSStorageManager
from mercury_ingestion.orchestration.bigquery_provenance import (
    BigQueryProvenanceStore,
)
from mercury_ingestion.orchestration.bigquery_replay_state import (
    BigQueryReplayStateStore,
)
from mercury_ingestion.orchestration.replay import HistoricalReplayRunner
from mercury_ingestion.simulation.olist import OlistSourceSimulator
from mercury_ingestion.sources.simulated_olist import (
    OlistSimulatedSourceProvider,
)
from mercury_ingestion.warehouse.bigquery_loader import BigQueryRawLoader


PROJECT_ID = "mercury-data-platform-dev"
RAW_DATASET_ID = "raw"
METADATA_DATASET_ID = "metadata"
BUCKET_NAME = "mercury-data-platform-dev-raw-01"
LOCATION = "europe-west4"

SOURCE_DIRECTORY = Path("../data/source/olist")
SIMULATION_DIRECTORY = Path("../data/simulated/olist")

ORDERS_FILE = SOURCE_DIRECTORY / "olist_orders_dataset.csv"
REVIEWS_FILE = SOURCE_DIRECTORY / "olist_order_reviews_dataset.csv"


def _date_range(
    path: Path,
    timestamp_field: str,
) -> tuple[date, date]:
    """Return the minimum and maximum business dates in a source CSV."""

    values: list[date] = []

    with path.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        for row in reader:
            raw_value = row.get(timestamp_field)

            if raw_value is None or not raw_value.strip():
                continue

            values.append(
                datetime.strptime(
                    raw_value.strip(),
                    "%Y-%m-%d %H:%M:%S",
                ).date()
            )

    if not values:
        raise RuntimeError(
            f"no usable timestamps found in {path.name}"
        )

    return min(values), max(values)


def determine_replay_range() -> tuple[date, date]:
    """Determine the complete Olist transactional replay range."""

    orders_start, orders_end = _date_range(
        ORDERS_FILE,
        "order_purchase_timestamp",
    )

    reviews_start, reviews_end = _date_range(
        REVIEWS_FILE,
        "review_creation_date",
    )

    replay_start = min(orders_start, reviews_start)
    replay_end = max(orders_end, reviews_end)

    print()
    print("Olist transactional date ranges")
    print("--------------------------------")
    print(f"Orders : {orders_start} -> {orders_end}")
    print(f"Reviews: {reviews_start} -> {reviews_end}")
    print(f"Replay : {replay_start} -> {replay_end}")
    print()

    return replay_start, replay_end


def build_runner() -> HistoricalReplayRunner:
    """Construct the production-backed historical replay runner."""

    simulator = OlistSourceSimulator(
        source_directory=SOURCE_DIRECTORY,
        output_directory=SIMULATION_DIRECTORY,
    )

    source_provider = OlistSimulatedSourceProvider(simulator)

    storage_manager = GCSStorageManager(
        bucket_name=BUCKET_NAME,
        project_id=PROJECT_ID,
    )

    bigquery_loader = BigQueryRawLoader(
        project_id=PROJECT_ID,
        dataset_id=RAW_DATASET_ID,
        location=LOCATION,
    )

    replay_state_store = BigQueryReplayStateStore(
        project_id=PROJECT_ID,
        dataset_id=METADATA_DATASET_ID,
        location=LOCATION,
    )

    provenance_store = BigQueryProvenanceStore(
        project_id=PROJECT_ID,
        dataset_id=METADATA_DATASET_ID,
        location=LOCATION,
    )

    replay_state_store.ensure_resources()
    provenance_store.ensure_resources()

    return HistoricalReplayRunner(
        source_provider=source_provider,
        storage_manager=storage_manager,
        bigquery_loader=bigquery_loader,
        replay_state_store=replay_state_store,
        provenance_store=provenance_store,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate and replay simulated Olist transactional history."
    )

    parser.add_argument(
        "--full",
        action="store_true",
        help="Replay the complete historical range after generation.",
    )

    args = parser.parse_args()

    replay_start, replay_end = determine_replay_range()

    runner = build_runner()

    print("Generating simulated daily deliveries...")
    runner.generate_range(
        start_date=replay_start,
        end_date=replay_end,
    )
    print("Daily simulation generated successfully.")
    print()

    if args.full:
        print(
            f"Starting FULL historical replay: "
            f"{replay_start} -> {replay_end}"
        )

        result = runner.run_range(
            start_date=replay_start,
            end_date=replay_end,
        )

        print()
        print("Full historical replay finished.")
        print(result)
        return

    print("Running ONE-DAY smoke test only.")
    print(f"Smoke-test delivery date: {replay_start}")
    print()

    result = runner.run_range(
        start_date=replay_start,
        end_date=replay_start,
    )

    print()
    print("Smoke test finished.")
    print(result)
    print()
    print(
        "Inspect GCS, BigQuery Raw, replay state and provenance "
        "before running with --full."
    )


if __name__ == "__main__":
    main()