"""ADR-011 Phase 2 security regression tests.

These tests inject a synthetic sentinel value into an exception at each
of Mercury's exception-to-metadata boundaries and assert the sentinel
never appears in any persisted/raised operational-error text. Per
ADR-011 Section 13, a deliberately distinctive, obviously-fake value is
used (never real customer data) so a failing assertion is unambiguous.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Callable

import pytest
from google.api_core import exceptions as gcs_exceptions

from mercury_ingestion.common.metadata import IngestionStatus
from mercury_ingestion.common.operational_errors import MAX_OPERATIONAL_ERROR_LENGTH, OperationalErrorCategory
from mercury_ingestion.common.storage import LocalStorageManager, StorageManager, StorageResult
from mercury_ingestion.connectors.base import BaseConnector, ConnectorRunResult
from mercury_ingestion.orchestration.provenance import (
    ProvenanceStore,
    RawArtifactProvenance,
    WarehouseLoadProvenance,
)
from mercury_ingestion.orchestration.replay import HistoricalReplayError, HistoricalReplayRunner
from mercury_ingestion.orchestration.state import ReplayStateRecord, ReplayStateStore, ReplayStatus
from mercury_ingestion.sources.base import SourceDelivery, SourceDeliveryBatch, SourceDeliveryProvider
from mercury_ingestion.warehouse import bigquery_loader as bigquery_loader_module
from mercury_ingestion.warehouse.bigquery_loader import BigQueryRawLoader

# A deliberately distinctive, obviously-fake sentinel -- never real
# customer data -- injected into exception text at each boundary.
SENTINEL = "sensitive-test-email@example.invalid"


def _assert_sentinel_absent(value: str | None) -> None:
    assert value is not None
    assert SENTINEL not in value


# --- Connector-level fixtures ------------------------------------------------


class _SentinelValidationConnector(BaseConnector):
    """A connector whose validate_source() raises an exception containing SENTINEL."""

    def validate_source(self) -> None:
        raise ValueError(f"invalid record encountered: {SENTINEL}")

    def count_records(self) -> int:  # pragma: no cover - never reached
        return 0


class _SentinelCountConnector(BaseConnector):
    """A connector whose count_records() raises an exception containing SENTINEL."""

    def validate_source(self) -> None:
        pass

    def count_records(self) -> int:
        raise RuntimeError(f"failed while scanning row containing {SENTINEL}")


class _PassthroughConnector(BaseConnector):
    """A connector whose validate_source/count_records both succeed trivially."""

    def validate_source(self) -> None:
        pass

    def count_records(self) -> int:
        return 1


class _SentinelStorageManager(StorageManager):
    """A StorageManager whose save_file() raises an exception containing SENTINEL."""

    def save_file(
        self, source_file: Path, source_system: str, source_object: str, ingestion_date: date
    ) -> StorageResult:
        raise RuntimeError(f"upload rejected, payload contained {SENTINEL}")


def _write_source_file(tmp_path: Path) -> Path:
    source_file = tmp_path / "source.csv"
    source_file.write_text("id\n1\n", encoding="utf-8")
    return source_file


# --- HistoricalReplayRunner-level fixtures ----------------------------------


class _FakeBQJob:
    def __init__(self, output_rows: int, job_id: str, raise_exc: BaseException | None) -> None:
        self.output_rows = output_rows
        self.job_id = job_id
        self._raise_exc = raise_exc

    def result(self) -> "_FakeBQJob":
        if self._raise_exc is not None:
            raise self._raise_exc
        return self


class _FakeBigQueryClient:
    def __init__(self, project: str | None = None, location: str | None = None, **kwargs: object) -> None:
        self.load_calls: list[dict[str, object]] = []
        self.raise_for_destination: dict[str, BaseException] = {}
        self._job_counter = 0

    def load_table_from_uri(
        self,
        source_uris: object,
        destination: object,
        *,
        job_config: object = None,
        location: str | None = None,
        **kwargs: object,
    ) -> _FakeBQJob:
        self._job_counter += 1
        self.load_calls.append({"source_uris": source_uris, "destination": destination})
        raise_exc = self.raise_for_destination.get(str(destination))
        return _FakeBQJob(output_rows=1, job_id=f"job-{self._job_counter}", raise_exc=raise_exc)


@pytest.fixture(autouse=True)
def _fake_bigquery_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bigquery_loader_module.bigquery, "Client", _FakeBigQueryClient)


def _make_bigquery_loader() -> BigQueryRawLoader:
    return BigQueryRawLoader(project_id="mercury-data-platform-dev", dataset_id="raw")


class _FakeGcsStorageManager(StorageManager):
    def __init__(self, local_root: Path, bucket_name: str = "mercury-data-platform-dev-raw-01") -> None:
        self.local_root = local_root
        self.bucket_name = bucket_name
        self._landed_objects: set[str] = set()

    def save_file(self, source_file: Path, source_system: str, source_object: str, ingestion_date: date) -> StorageResult:
        object_name = f"raw/{source_system}/{source_object}/ingestion_date={ingestion_date.isoformat()}/{source_file.name}"
        if object_name in self._landed_objects:
            raise FileExistsError(f"destination object already exists: gs://{self.bucket_name}/{object_name}")
        content = source_file.read_bytes()
        destination_path = self.local_root / object_name
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_bytes(content)
        self._landed_objects.add(object_name)
        return StorageResult(
            landing_path=f"gs://{self.bucket_name}/{object_name}",
            checksum=hashlib.sha256(content).hexdigest(),
            file_size_bytes=len(content),
        )


class _InMemoryReplayStateStore(ReplayStateStore):
    def __init__(self) -> None:
        self.events: list[ReplayStateRecord] = []
        self.fail_when: Callable[[ReplayStateRecord], bool] | None = None

    def append(self, record: ReplayStateRecord) -> None:
        if self.fail_when is not None and self.fail_when(record):
            raise RuntimeError(f"simulated state-store failure containing {SENTINEL}")
        self.events.append(record)

    def get_history(self, delivery_date: date, source_object: str) -> tuple[ReplayStateRecord, ...]:
        matches = [e for e in self.events if e.delivery_date == delivery_date and e.source_object == source_object]
        return tuple(sorted(matches, key=lambda e: e.recorded_at))

    def get_latest(self, delivery_date: date, source_object: str) -> ReplayStateRecord | None:
        history = self.get_history(delivery_date, source_object)
        return history[-1] if history else None

    def get_latest_for_date(self, delivery_date: date) -> tuple[ReplayStateRecord, ...]:
        by_source: dict[str, ReplayStateRecord] = {}
        for event in self.events:
            if event.delivery_date != delivery_date:
                continue
            current = by_source.get(event.source_object)
            if current is None or event.recorded_at >= current.recorded_at:
                by_source[event.source_object] = event
        return tuple(by_source[key] for key in sorted(by_source))

    def get_completed_for_date(self, delivery_date: date) -> tuple[ReplayStateRecord, ...]:
        by_source: dict[str, ReplayStateRecord] = {}
        for event in self.events:
            if event.delivery_date != delivery_date or event.status is not ReplayStatus.SUCCESS:
                continue
            current = by_source.get(event.source_object)
            if current is None or event.recorded_at >= current.recorded_at:
                by_source[event.source_object] = event
        return tuple(by_source[key] for key in sorted(by_source))


class _InMemoryProvenanceStore(ProvenanceStore):
    """A minimal, always-succeeding ProvenanceStore for security-regression tests
    that only need HistoricalReplayRunner to be constructible -- not provenance
    behavior itself, which has its own dedicated tests elsewhere."""

    def __init__(self) -> None:
        self.artifacts: list[RawArtifactProvenance] = []
        self.warehouse_loads: list[WarehouseLoadProvenance] = []

    def append_artifact(self, record: RawArtifactProvenance) -> None:
        self.artifacts.append(record)

    def append_warehouse_load(self, record: WarehouseLoadProvenance) -> None:
        self.warehouse_loads.append(record)

    def get_artifact(self, provenance_id: str) -> RawArtifactProvenance | None:
        return next((a for a in self.artifacts if a.provenance_id == provenance_id), None)

    def get_artifact_history(self, delivery_date: date, source_object: str) -> tuple[RawArtifactProvenance, ...]:
        return tuple(a for a in self.artifacts if a.delivery_date == delivery_date and a.source_object == source_object)

    def get_artifact_by_uri(self, delivery_date: date, source_object: str, gcs_uri: str) -> RawArtifactProvenance | None:
        return next(
            (
                a
                for a in self.artifacts
                if a.delivery_date == delivery_date and a.source_object == source_object and a.gcs_uri == gcs_uri
            ),
            None,
        )

    def get_warehouse_load_history(self, delivery_date: date, source_object: str) -> tuple[WarehouseLoadProvenance, ...]:
        return tuple(
            w for w in self.warehouse_loads if w.delivery_date == delivery_date and w.source_object == source_object
        )

    def get_latest_warehouse_load(self, delivery_date: date, source_object: str) -> WarehouseLoadProvenance | None:
        history = self.get_warehouse_load_history(delivery_date, source_object)
        return history[-1] if history else None


class _SingleSourceProvider(SourceDeliveryProvider):
    """Always returns the same four-source daily batch, regardless of date."""

    def __init__(self, source_file: Path) -> None:
        self._source_file = source_file

    def get_initial_delivery(self) -> SourceDeliveryBatch:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_daily_delivery(self, delivery_date: date) -> SourceDeliveryBatch:
        return SourceDeliveryBatch(
            deliveries=(
                SourceDelivery(
                    source_object="orders", path=self._source_file, delivery_date=delivery_date, record_count=1
                ),
                SourceDelivery(
                    source_object="order_items", path=self._source_file, delivery_date=delivery_date, record_count=1
                ),
                SourceDelivery(
                    source_object="payments", path=self._source_file, delivery_date=delivery_date, record_count=1
                ),
                SourceDelivery(
                    source_object="reviews", path=self._source_file, delivery_date=delivery_date, record_count=1
                ),
            ),
            delivery_date=delivery_date,
        )


def _write_orders_source_file(tmp_path: Path) -> Path:
    header = [
        "order_id",
        "customer_id",
        "order_status",
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]
    content = ",".join(header) + "\no1,c1,delivered,2017-05-01 10:00:00,,,,\n"
    source_file = tmp_path / "orders.csv"
    source_file.write_text(content, encoding="utf-8-sig")
    return source_file


class TestConnectorLevelSanitization:
    def test_validation_exception_sentinel_never_in_metadata(self, tmp_path: Path) -> None:
        connector = _SentinelValidationConnector(
            source_file=_write_source_file(tmp_path),
            source_system="test_system",
            source_object="test_object",
            storage_manager=LocalStorageManager(tmp_path / "landing"),
        )

        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED
        _assert_sentinel_absent(result.metadata.error_message)
        assert OperationalErrorCategory.SOURCE_VALIDATION_FAILED.value in result.metadata.error_message

    def test_count_records_exception_sentinel_never_in_metadata(self, tmp_path: Path) -> None:
        connector = _SentinelCountConnector(
            source_file=_write_source_file(tmp_path),
            source_system="test_system",
            source_object="test_object",
            storage_manager=LocalStorageManager(tmp_path / "landing"),
        )

        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED
        _assert_sentinel_absent(result.metadata.error_message)
        assert OperationalErrorCategory.RECORD_COUNT_FAILED.value in result.metadata.error_message

    def test_storage_write_exception_sentinel_never_in_metadata(self, tmp_path: Path) -> None:
        connector = _PassthroughConnector(
            source_file=_write_source_file(tmp_path),
            source_system="test_system",
            source_object="test_object",
            storage_manager=_SentinelStorageManager(),
        )

        result = connector.run()

        assert result.metadata.status is IngestionStatus.FAILED
        _assert_sentinel_absent(result.metadata.error_message)
        assert OperationalErrorCategory.STORAGE_WRITE_FAILED.value in result.metadata.error_message


class TestHistoricalReplayRunnerSanitization:
    def test_warehouse_load_exception_sentinel_never_in_replay_state(self, tmp_path: Path) -> None:
        source_file = _write_orders_source_file(tmp_path)
        provider = _SingleSourceProvider(source_file)
        storage_manager = _FakeGcsStorageManager(tmp_path / "bucket")
        bigquery_loader = _make_bigquery_loader()
        replay_state_store = _InMemoryReplayStateStore()
        runner = HistoricalReplayRunner(
            source_provider=provider,
            storage_manager=storage_manager,
            bigquery_loader=bigquery_loader,
            replay_state_store=replay_state_store,
            provenance_store=_InMemoryProvenanceStore(),
        )
        day = date(2017, 5, 1)
        sentinel_exc = gcs_exceptions.ServiceUnavailable(f"upstream error: {SENTINEL}")
        bigquery_loader._client.raise_for_destination["mercury-data-platform-dev.raw.orders$20170501"] = sentinel_exc

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        for event in replay_state_store.events:
            if event.error_message is not None:
                _assert_sentinel_absent(event.error_message)

        orders_failure = next(
            e for e in replay_state_store.events if e.source_object == "orders" and e.status is ReplayStatus.FAILED
        )
        assert OperationalErrorCategory.WAREHOUSE_LOAD_FAILED.value in orders_failure.error_message

    def test_state_store_failure_sentinel_never_in_raised_error(self, tmp_path: Path) -> None:
        source_file = _write_orders_source_file(tmp_path)
        provider = _SingleSourceProvider(source_file)
        storage_manager = _FakeGcsStorageManager(tmp_path / "bucket")
        bigquery_loader = _make_bigquery_loader()
        replay_state_store = _InMemoryReplayStateStore()
        replay_state_store.fail_when = lambda record: record.source_object == "orders"
        runner = HistoricalReplayRunner(
            source_provider=provider,
            storage_manager=storage_manager,
            bigquery_loader=bigquery_loader,
            replay_state_store=replay_state_store,
            provenance_store=_InMemoryProvenanceStore(),
        )
        day = date(2017, 5, 1)

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        _assert_sentinel_absent(str(exc_info.value))
        assert exc_info.value.stage == "state_store"

    def test_state_store_failure_still_chains_original_exception(self, tmp_path: Path) -> None:
        # The safe-message requirement must not come at the cost of
        # losing the original exception -- it remains available via
        # normal Python exception chaining for transient debugging.
        source_file = _write_orders_source_file(tmp_path)
        provider = _SingleSourceProvider(source_file)
        storage_manager = _FakeGcsStorageManager(tmp_path / "bucket")
        bigquery_loader = _make_bigquery_loader()
        replay_state_store = _InMemoryReplayStateStore()
        replay_state_store.fail_when = lambda record: record.source_object == "orders"
        runner = HistoricalReplayRunner(
            source_provider=provider,
            storage_manager=storage_manager,
            bigquery_loader=bigquery_loader,
            replay_state_store=replay_state_store,
            provenance_store=_InMemoryProvenanceStore(),
        )
        day = date(2017, 5, 1)

        with pytest.raises(HistoricalReplayError) as exc_info:
            runner.run_day(day)

        assert exc_info.value.__cause__ is not None
        assert SENTINEL not in str(exc_info.value)
        # The chained cause is the real underlying exception -- its raw
        # text is not embedded in the raised message, but it remains
        # reachable for a debugger/developer via __cause__.
        assert isinstance(exc_info.value.__cause__, RuntimeError)

    def test_unexpected_ingestion_exception_sentinel_never_leaks(self, tmp_path: Path) -> None:
        # Simulates a genuine programming-contract violation: a
        # connector's run() somehow lets an exception escape rather than
        # returning FAILED metadata. This is intentionally invoked via a
        # broken connector mapping rather than relying on any real
        # connector actually violating its own contract.
        from mercury_ingestion.orchestration import replay as replay_module

        class _RaisingConnector(BaseConnector):
            def __init__(self, source_file: Path, storage_manager: StorageManager, schema_version: str | None = None) -> None:
                super().__init__(
                    source_file=source_file,
                    source_system="order_platform",
                    source_object="orders",
                    storage_manager=storage_manager,
                    schema_version=schema_version,
                )

            def validate_source(self) -> None:  # pragma: no cover - never reached
                pass

            def count_records(self) -> int:  # pragma: no cover - never reached
                return 0

            def run(self, ingestion_date: date | None = None) -> ConnectorRunResult:
                # Simulates a connector implementation that violates
                # BaseConnector's own contract by letting an exception
                # escape run() directly, instead of returning FAILED
                # metadata as BaseConnector.run() always does.
                raise RuntimeError(f"unexpected internal failure: {SENTINEL}")

        original_map = dict(replay_module.CONNECTOR_MAP)
        replay_module.CONNECTOR_MAP["orders"] = _RaisingConnector  # type: ignore[assignment]
        try:
            source_file = _write_orders_source_file(tmp_path)
            provider = _SingleSourceProvider(source_file)
            storage_manager = _FakeGcsStorageManager(tmp_path / "bucket")
            bigquery_loader = _make_bigquery_loader()
            replay_state_store = _InMemoryReplayStateStore()
            runner = HistoricalReplayRunner(
                source_provider=provider,
                storage_manager=storage_manager,
                bigquery_loader=bigquery_loader,
                replay_state_store=replay_state_store,
                provenance_store=_InMemoryProvenanceStore(),
            )
            day = date(2017, 5, 1)

            with pytest.raises(HistoricalReplayError) as exc_info:
                runner.run_day(day)

            _assert_sentinel_absent(str(exc_info.value))
            for event in replay_state_store.events:
                if event.error_message is not None:
                    _assert_sentinel_absent(event.error_message)
            assert exc_info.value.__cause__ is not None
            assert SENTINEL in str(exc_info.value.__cause__)  # cause still carries full detail
        finally:
            replay_module.CONNECTOR_MAP.clear()
            replay_module.CONNECTOR_MAP.update(original_map)

    def test_ordinary_connector_failure_propagated_into_replay_state_is_safe(self, tmp_path: Path) -> None:
        # End-to-end: an ordinary (non-exceptional) connector FAILED
        # result copies IngestionMetadata.error_message into replay
        # state -- confirms that value is safe by construction, since
        # BaseConnector itself never persists raw exception text either.
        missing_file = tmp_path / "does_not_exist.csv"
        provider = _SingleSourceProvider(missing_file)
        storage_manager = _FakeGcsStorageManager(tmp_path / "bucket")
        bigquery_loader = _make_bigquery_loader()
        replay_state_store = _InMemoryReplayStateStore()
        runner = HistoricalReplayRunner(
            source_provider=provider,
            storage_manager=storage_manager,
            bigquery_loader=bigquery_loader,
            replay_state_store=replay_state_store,
            provenance_store=_InMemoryProvenanceStore(),
        )
        day = date(2017, 5, 1)

        with pytest.raises(HistoricalReplayError):
            runner.run_day(day)

        for event in replay_state_store.events:
            if event.status is ReplayStatus.FAILED:
                assert str(missing_file) not in (event.error_message or "")


class TestOperationalErrorMetadataShape:
    def test_ingestion_metadata_error_message_is_bounded(self, tmp_path: Path) -> None:
        connector = _SentinelValidationConnector(
            source_file=_write_source_file(tmp_path),
            source_system="test_system",
            source_object="test_object",
            storage_manager=LocalStorageManager(tmp_path / "landing"),
        )

        result = connector.run()

        assert len(result.metadata.error_message) <= MAX_OPERATIONAL_ERROR_LENGTH