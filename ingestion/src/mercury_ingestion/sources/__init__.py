"""Mercury's source-delivery abstraction package (ADR-009).

Contains the ``SourceDeliveryProvider`` contract and its concrete
``OlistSimulatedSourceProvider`` implementation, which adapts the
existing ``OlistSourceSimulator`` without reimplementing its logic. This
package has no knowledge of connectors, storage, GCS, BigQuery, or
orchestration -- it only makes source deliveries available.
"""

from mercury_ingestion.sources.base import SourceDelivery, SourceDeliveryBatch, SourceDeliveryProvider
from mercury_ingestion.sources.simulated_olist import OlistSimulatedSourceProvider

__all__ = [
    "OlistSimulatedSourceProvider",
    "SourceDelivery",
    "SourceDeliveryBatch",
    "SourceDeliveryProvider",
]