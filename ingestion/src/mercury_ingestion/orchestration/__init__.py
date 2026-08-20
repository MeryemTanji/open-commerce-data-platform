"""Mercury's historical replay orchestration package (ADR-009 / ADR-010).

Contains ``HistoricalReplayRunner``, which coordinates a
``SourceDeliveryProvider`` with the existing connectors,
``IngestionRunner``, a ``StorageManager``, ``BigQueryRawLoader``, and a
``ReplayStateStore`` into a historical-replay workflow. This is distinct
from ``mercury_ingestion.runner.IngestionRunner``, which remains solely
responsible for executing a batch of connectors and is unchanged.

Also exposes the ADR-010 replay-state model (``ReplayStateStore``,
``ReplayStateRecord``, ``ReplayStatus``, ``ReplayStage``,
``is_date_complete``) and its BigQuery-backed implementation
(``BigQueryReplayStateStore``); the Phase 3A recovery planning model
(``RecoveryAction``, ``RecoveryEvidence``, ``RecoveryPlanItem``,
``RecoveryPlan``, ``RecoveryPlanner``), a pure decision policy that
executes nothing on its own; the Phase 3B recovery execution layer
(``RecoveryExecutionOutcome``, ``ValidatedRawArtifact``,
``RecoveryItemExecutionResult``, ``RecoveryExecutionResult``,
``RecoveryExecutor``), which performs the physical work a
``RecoveryPlan`` decided on; and the Phase 3C provenance/reconciliation
layer (``RawArtifactProvenance``, ``WarehouseLoadProvenance``,
``ProvenanceStore``, ``BigQueryProvenanceStore``,
``ReconciliationOutcome``, ``ReconciliationReason``,
``ReconciliationResult``, ``RecoveryReconciler``), which durably records
what was physically produced/loaded and can prove -- never guess -- that
a ``RECONCILE``-decided source has already physically succeeded.
Internal helpers (e.g. ``HistoricalReplayRunner``'s private phase
methods) are deliberately not re-exported here.
"""

from mercury_ingestion.orchestration.bigquery_provenance import BigQueryProvenanceStore
from mercury_ingestion.orchestration.bigquery_replay_state import BigQueryReplayStateStore
from mercury_ingestion.orchestration.provenance import (
    ProvenanceStore,
    RawArtifactProvenance,
    WarehouseLoadProvenance,
)
from mercury_ingestion.orchestration.reconciliation import (
    ReconciliationOutcome,
    ReconciliationReason,
    ReconciliationResult,
    RecoveryReconciler,
)
from mercury_ingestion.orchestration.recovery import (
    RecoveryAction,
    RecoveryEvidence,
    RecoveryPlan,
    RecoveryPlanItem,
    RecoveryPlanner,
)
from mercury_ingestion.orchestration.recovery_execution import (
    RecoveryExecutionError,
    RecoveryExecutionOutcome,
    RecoveryExecutionResult,
    RecoveryExecutor,
    RecoveryItemExecutionResult,
    ValidatedRawArtifact,
)
from mercury_ingestion.orchestration.replay import (
    CONNECTOR_MAP,
    HistoricalReplayDayResult,
    HistoricalReplayError,
    HistoricalReplayInitialResult,
    HistoricalReplayRangeResult,
    HistoricalReplayRunner,
)
from mercury_ingestion.orchestration.state import (
    ReplayStage,
    ReplayStateRecord,
    ReplayStateStore,
    ReplayStatus,
    is_date_complete,
)

__all__ = [
    "BigQueryProvenanceStore",
    "BigQueryReplayStateStore",
    "CONNECTOR_MAP",
    "HistoricalReplayDayResult",
    "HistoricalReplayError",
    "HistoricalReplayInitialResult",
    "HistoricalReplayRangeResult",
    "HistoricalReplayRunner",
    "ProvenanceStore",
    "RawArtifactProvenance",
    "ReconciliationOutcome",
    "ReconciliationReason",
    "ReconciliationResult",
    "RecoveryAction",
    "RecoveryEvidence",
    "RecoveryExecutionError",
    "RecoveryExecutionOutcome",
    "RecoveryExecutionResult",
    "RecoveryExecutor",
    "RecoveryItemExecutionResult",
    "RecoveryPlan",
    "RecoveryPlanItem",
    "RecoveryPlanner",
    "RecoveryReconciler",
    "ReplayStage",
    "ReplayStateRecord",
    "ReplayStateStore",
    "ReplayStatus",
    "ValidatedRawArtifact",
    "WarehouseLoadProvenance",
    "is_date_complete",
]