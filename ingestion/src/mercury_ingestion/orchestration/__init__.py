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
(``BigQueryReplayStateStore``), plus the Phase 3A recovery planning
model (``RecoveryAction``, ``RecoveryEvidence``, ``RecoveryPlanItem``,
``RecoveryPlan``, ``RecoveryPlanner``). The recovery planner is a pure
decision policy -- it is not yet wired into ``HistoricalReplayRunner``
and executes nothing on its own; it is exported here because it is an
independently usable, standalone public type, consistent with how every
other meaningful type in this package is already exposed. Internal
helpers (e.g. ``HistoricalReplayRunner``'s private phase methods) are
deliberately not re-exported here.
"""

from mercury_ingestion.orchestration.bigquery_replay_state import BigQueryReplayStateStore
from mercury_ingestion.orchestration.recovery import (
    RecoveryAction,
    RecoveryEvidence,
    RecoveryPlan,
    RecoveryPlanItem,
    RecoveryPlanner,
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
    "RecoveryPlan",
    "RecoveryPlanItem",
    "RecoveryPlanner",
    "ReplayStage",
    "ReplayStateRecord",
    "ReplayStateStore",
    "ReplayStatus",
    "is_date_complete",
]