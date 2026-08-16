"""Mercury's historical source-delivery simulation package.

Contains ``OlistSourceSimulator``, which derives realistic initial and
daily incremental source deliveries from the immutable Olist reference
CSV files (per ADR-007). This package is strictly upstream of
ingestion: it only produces simulated source-delivery CSVs on disk and
has no knowledge of connectors, storage backends, or ingestion
metadata.
"""

from mercury_ingestion.simulation.olist import (
    DailySimulationResult,
    InitialSimulationResult,
    OlistSourceSimulator,
    SimulatedFile,
)

__all__ = [
    "DailySimulationResult",
    "InitialSimulationResult",
    "OlistSourceSimulator",
    "SimulatedFile",
]