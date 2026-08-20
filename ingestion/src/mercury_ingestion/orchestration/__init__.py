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
executes nothing on its own; and the Phase 3B recovery execution layer
(``RecoveryExecutionOutcome``, ``ValidatedRawArtifact``,
``RecoveryItemExecutionResult``, ``RecoveryExecutionResult``,
``RecoveryExecutor``), which actually performs the physical work a
``RecoveryPlan`` decided on, reusing the same connectors and
``BigQueryRawLoader`` ``HistoricalReplayRunner`` already uses. Neither
recovery layer is yet wired into ``HistoricalReplayRunner`` itself; each
is exported here because it is an independently usable, standalone
public type, consistent with how every other meaningful type in this
package is already exposed. Internal helpers (e.g.
``HistoricalReplayRunner``'s private phase methods) are deliberately not
re-exported here.
"""

from mercury_ingestion.orchestration.bigquery_replay_state import BigQueryReplayStateStore
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
    "BigQueryReplayStateStore",
    "CONNECTOR_MAP",
    "HistoricalReplayDayResult",
    "HistoricalReplayError",
    "HistoricalReplayInitialResult",
    "HistoricalReplayRangeResult",
    "HistoricalReplayRunner",
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
    "ReplayStage",
    "ReplayStateRecord",
    "ReplayStateStore",
    "ReplayStatus",
    "ValidatedRawArtifact",
    "is_date_complete",
]