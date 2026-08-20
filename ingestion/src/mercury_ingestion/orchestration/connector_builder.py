"""Mercury's shared connector-construction helper (ADR-010 Phase 3B).

Both ``HistoricalReplayRunner`` (ADR-009 daily replay) and
``RecoveryExecutor`` (ADR-010 Phase 3B recovery) need to resolve a
``SourceDelivery`` into a constructed, ready-to-run connector. This
module is the single place that mapping and construction logic lives --
``CONNECTOR_MAP`` is declared here once, and both callers use
``build_connector()`` rather than each maintaining (or duplicating)
their own copy.

This module performs no I/O itself: constructing a connector has no
side effects beyond ``BaseConnector.__init__``'s own lightweight field
assignment and validation.
"""

from __future__ import annotations

from mercury_ingestion.common.storage import StorageManager
from mercury_ingestion.connectors.base import BaseConnector
from mercury_ingestion.connectors.customers import CustomerConnector
from mercury_ingestion.connectors.geolocations import GeolocationConnector
from mercury_ingestion.connectors.order_items import OrderItemsConnector
from mercury_ingestion.connectors.orders import OrdersConnector
from mercury_ingestion.connectors.payments import PaymentsConnector
from mercury_ingestion.connectors.products import ProductsConnector
from mercury_ingestion.connectors.reviews import ReviewsConnector
from mercury_ingestion.connectors.sellers import SellersConnector
from mercury_ingestion.sources.base import SourceDelivery

# Maps each stable Mercury source_object to its existing concrete
# connector class. Deliberately explicit rather than derived, so the
# mapping stays reviewable and never silently drifts from the actual
# connector set. This is the single copy of this mapping in the
# codebase -- both HistoricalReplayRunner and RecoveryExecutor resolve
# connectors through build_connector() below rather than each
# maintaining their own map.
CONNECTOR_MAP: dict[str, type[BaseConnector]] = {
    "customers": CustomerConnector,
    "orders": OrdersConnector,
    "order_items": OrderItemsConnector,
    "products": ProductsConnector,
    "sellers": SellersConnector,
    "payments": PaymentsConnector,
    "reviews": ReviewsConnector,
    "geolocations": GeolocationConnector,
}


def build_connector(delivery: SourceDelivery, storage_manager: StorageManager) -> BaseConnector:
    """Resolve a SourceDelivery into a constructed, ready-to-run connector.

    Raises:
        ValueError: if ``delivery.source_object`` has no known connector.
    """
    connector_class = CONNECTOR_MAP.get(delivery.source_object)
    if connector_class is None:
        raise ValueError(f"unsupported source_object: {delivery.source_object!r}")
    return connector_class(source_file=delivery.path, storage_manager=storage_manager)