"""Unit tests for the production Olist replay-runner factory."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from mercury_ingestion.runtime import (
    olist_runner_factory as factory_module,
)
from mercury_ingestion.runtime.olist_runner_factory import (
    build_olist_replay_runner,
)


@pytest.fixture
def dependency_mocks(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Mock]:
    simulator = Mock(name="simulator")
    source_provider = Mock(name="source_provider")
    storage_manager = Mock(name="storage_manager")
    bigquery_loader = Mock(name="bigquery_loader")
    replay_state_store = Mock(name="replay_state_store")
    provenance_store = Mock(name="provenance_store")
    runner = Mock(name="runner")

    classes = {
        "simulator_class": Mock(return_value=simulator),
        "source_provider_class": Mock(
            return_value=source_provider
        ),
        "storage_manager_class": Mock(
            return_value=storage_manager
        ),
        "bigquery_loader_class": Mock(
            return_value=bigquery_loader
        ),
        "replay_state_store_class": Mock(
            return_value=replay_state_store
        ),
        "provenance_store_class": Mock(
            return_value=provenance_store
        ),
        "runner_class": Mock(return_value=runner),
    }

    monkeypatch.setattr(
        factory_module,
        "OlistSourceSimulator",
        classes["simulator_class"],
    )
    monkeypatch.setattr(
        factory_module,
        "OlistSimulatedSourceProvider",
        classes["source_provider_class"],
    )
    monkeypatch.setattr(
        factory_module,
        "GCSStorageManager",
        classes["storage_manager_class"],
    )
    monkeypatch.setattr(
        factory_module,
        "BigQueryRawLoader",
        classes["bigquery_loader_class"],
    )
    monkeypatch.setattr(
        factory_module,
        "BigQueryReplayStateStore",
        classes["replay_state_store_class"],
    )
    monkeypatch.setattr(
        factory_module,
        "BigQueryProvenanceStore",
        classes["provenance_store_class"],
    )
    monkeypatch.setattr(
        factory_module,
        "HistoricalReplayRunner",
        classes["runner_class"],
    )

    return {
        **classes,
        "simulator": simulator,
        "source_provider": source_provider,
        "storage_manager": storage_manager,
        "bigquery_loader": bigquery_loader,
        "replay_state_store": replay_state_store,
        "provenance_store": provenance_store,
        "runner": runner,
    }


def _build() -> object:
    return build_olist_replay_runner(
        source_directory=Path("/workspace/source"),
        simulation_directory=Path("/workspace/simulated"),
        project_id="mercury-data-platform-dev",
        raw_bucket_name="mercury-raw-dev",
        raw_dataset_id="raw",
        metadata_dataset_id="metadata",
        location="europe-west4",
    )


class TestOlistSourceComposition:
    def test_constructs_simulator_with_workspace_paths(
        self,
        dependency_mocks: dict[str, Mock],
    ) -> None:
        _build()

        dependency_mocks[
            "simulator_class"
        ].assert_called_once_with(
            source_directory=Path("/workspace/source"),
            output_directory=Path("/workspace/simulated"),
        )

    def test_wraps_simulator_in_existing_source_provider(
        self,
        dependency_mocks: dict[str, Mock],
    ) -> None:
        _build()

        dependency_mocks[
            "source_provider_class"
        ].assert_called_once_with(
            dependency_mocks["simulator"]
        )


class TestCloudDependencyComposition:
    def test_constructs_raw_storage_manager(
        self,
        dependency_mocks: dict[str, Mock],
    ) -> None:
        _build()

        dependency_mocks[
            "storage_manager_class"
        ].assert_called_once_with(
            bucket_name="mercury-raw-dev",
            project_id="mercury-data-platform-dev",
        )

    def test_constructs_bigquery_raw_loader(
        self,
        dependency_mocks: dict[str, Mock],
    ) -> None:
        _build()

        dependency_mocks[
            "bigquery_loader_class"
        ].assert_called_once_with(
            project_id="mercury-data-platform-dev",
            dataset_id="raw",
            location="europe-west4",
        )

    def test_constructs_replay_state_store(
        self,
        dependency_mocks: dict[str, Mock],
    ) -> None:
        _build()

        dependency_mocks[
            "replay_state_store_class"
        ].assert_called_once_with(
            project_id="mercury-data-platform-dev",
            dataset_id="metadata",
            location="europe-west4",
        )

    def test_constructs_provenance_store(
        self,
        dependency_mocks: dict[str, Mock],
    ) -> None:
        _build()

        dependency_mocks[
            "provenance_store_class"
        ].assert_called_once_with(
            project_id="mercury-data-platform-dev",
            dataset_id="metadata",
            location="europe-west4",
        )


class TestOperationalResources:
    def test_ensures_replay_state_resources(
        self,
        dependency_mocks: dict[str, Mock],
    ) -> None:
        _build()

        dependency_mocks[
            "replay_state_store"
        ].ensure_resources.assert_called_once_with()

    def test_ensures_provenance_resources(
        self,
        dependency_mocks: dict[str, Mock],
    ) -> None:
        _build()

        dependency_mocks[
            "provenance_store"
        ].ensure_resources.assert_called_once_with()


class TestRunnerComposition:
    def test_constructs_runner_from_existing_dependencies(
        self,
        dependency_mocks: dict[str, Mock],
    ) -> None:
        _build()

        dependency_mocks[
            "runner_class"
        ].assert_called_once_with(
            source_provider=dependency_mocks[
                "source_provider"
            ],
            storage_manager=dependency_mocks[
                "storage_manager"
            ],
            bigquery_loader=dependency_mocks[
                "bigquery_loader"
            ],
            replay_state_store=dependency_mocks[
                "replay_state_store"
            ],
            provenance_store=dependency_mocks[
                "provenance_store"
            ],
        )

    def test_returns_constructed_runner(
        self,
        dependency_mocks: dict[str, Mock],
    ) -> None:
        result = _build()

        assert result is dependency_mocks["runner"]