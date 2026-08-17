"""Mercury's BigQuery Raw warehouse-loading package.

Contains ``BigQueryRawLoader``, which materializes already-landed GCS
Raw source artifacts as queryable BigQuery Raw tables/partitions (per
ADR-008), and the explicit Raw schema registry in ``schemas.py`` (per
ADR-007/ADR-008). This package begins strictly after Raw Landing has
succeeded and has no knowledge of connectors, source simulation, or GCS
upload/delete behavior.
"""

from mercury_ingestion.warehouse.bigquery_loader import BigQueryLoadResult, BigQueryRawLoader
from mercury_ingestion.warehouse.schemas import (
    MASTER_REFERENCE_SOURCE_OBJECTS,
    RAW_SCHEMAS,
    SUPPORTED_SOURCE_OBJECTS,
    TRANSACTIONAL_SOURCE_OBJECTS,
    get_raw_schema,
    is_master_reference,
    is_transactional,
)

__all__ = [
    "BigQueryLoadResult",
    "BigQueryRawLoader",
    "MASTER_REFERENCE_SOURCE_OBJECTS",
    "RAW_SCHEMAS",
    "SUPPORTED_SOURCE_OBJECTS",
    "TRANSACTIONAL_SOURCE_OBJECTS",
    "get_raw_schema",
    "is_master_reference",
    "is_transactional",
]