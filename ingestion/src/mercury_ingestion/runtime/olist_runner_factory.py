"""Construct Mercury's Olist historical replay runner.

This module owns dependency composition only. It connects the existing
Olist simulator, source provider, Raw storage, BigQuery loader,
replay-state store, provenance store, and HistoricalReplayRunner.

It does not execute ingestion, generate source deliveries, parse command
arguments, or own environment configuration.
"""

from __future__ import annotations

from pathlib import Path

from mercury_ingestion.common.gcs_storage import GCSStorageManager
from mercury_ingestion.orchestration.bigquery_provenance import (
    BigQueryProvenanceStore,
)
from mercury_ingestion.orchestration.bigquery_replay_state import (
    BigQueryReplayStateStore,
)
from mercury_ingestion.orchestration.replay import (
    HistoricalReplayRunner,
)
from mercury_ingestion.simulation.olist import OlistSourceSimulator
from mercury_ingestion.sources.simulated_olist import (
    OlistSimulatedSourceProvider,
)
from mercury_ingestion.warehouse.bigquery_loader import (
    BigQueryRawLoader,
)


def build_olist_replay_runner(
    *,
    source_directory: Path,
    simulation_directory: Path,
    project_id: str,
    raw_bucket_name: str,
    raw_dataset_id: str,
    metadata_dataset_id: str,
    location: str,
) -> HistoricalReplayRunner:
    """Construct a cloud-backed runner using existing Mercury components.

    Resource provisioning remains outside this factory. The
    ``ensure_resources`` calls only confirm that the operational tables
    required by replay-state and provenance persistence are available.
    """

    simulator = OlistSourceSimulator(
        source_directory=source_directory,
        output_directory=simulation_directory,
    )

    source_provider = OlistSimulatedSourceProvider(simulator)

    storage_manager = GCSStorageManager(
        bucket_name=raw_bucket_name,
        project_id=project_id,
    )

    bigquery_loader = BigQueryRawLoader(
        project_id=project_id,
        dataset_id=raw_dataset_id,
        location=location,
    )

    replay_state_store = BigQueryReplayStateStore(
        project_id=project_id,
        dataset_id=metadata_dataset_id,
        location=location,
    )

    provenance_store = BigQueryProvenanceStore(
        project_id=project_id,
        dataset_id=metadata_dataset_id,
        location=location,
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