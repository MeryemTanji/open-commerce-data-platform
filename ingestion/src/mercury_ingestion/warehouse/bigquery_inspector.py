"""BigQuery implementation of Mercury's read-only warehouse inspection (ADR-010 Phase 3C).

``BigQueryInspector`` reads partition existence and row count from
``INFORMATION_SCHEMA.PARTITIONS`` -- BigQuery's own partition metadata
catalog -- never from a query against Raw business columns. It performs
no writes, no table creation, and no dataset creation.
"""

from __future__ import annotations

from datetime import date

from google.cloud import bigquery

from mercury_ingestion.warehouse.inspection import WarehouseInspector, WarehousePartitionObservation


def _require_non_blank(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


class BigQueryInspector(WarehouseInspector):
    """Reads BigQuery transactional partition metadata via ``INFORMATION_SCHEMA.PARTITIONS``.

    Authentication relies entirely on Application Default Credentials --
    this class never accepts explicit credentials. Construction only
    creates a lightweight ``bigquery.Client`` handle and performs no
    network call.
    """

    def __init__(self, project_id: str, dataset_id: str) -> None:
        _require_non_blank(project_id, "project_id")
        _require_non_blank(dataset_id, "dataset_id")
        self.project_id = project_id
        self.dataset_id = dataset_id
        self._client = bigquery.Client(project=project_id)

    def inspect_partition(self, source_object: str, partition_date: date) -> WarehousePartitionObservation:
        """Return partition existence/row-count metadata for one source/date.

        Raises:
            ValueError: if ``source_object`` is blank.
            TypeError: if ``partition_date`` is not a ``datetime.date``.
            google.api_core.exceptions.GoogleAPICallError: any BigQuery
                query failure propagates unchanged -- a genuine
                inspection-infrastructure failure, distinct from a
                partition that legitimately does not exist.
        """
        _require_non_blank(source_object, "source_object")
        if not isinstance(partition_date, date):
            raise TypeError("partition_date must be a datetime.date")

        partition_id = partition_date.strftime("%Y%m%d")
        destination = f"{self.project_id}.{self.dataset_id}.{source_object}${partition_id}"

        # self.project_id/self.dataset_id are pre-validated constructor
        # config, never user input; table_name/partition_id are bound
        # via ScalarQueryParameter below, never interpolated into the query.
        query = (
            "SELECT total_rows FROM "
            f"`{self.project_id}.{self.dataset_id}`.INFORMATION_SCHEMA.PARTITIONS "  # nosec B608
            "WHERE table_name = @table_name AND partition_id = @partition_id"
        )
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("table_name", "STRING", source_object),
                bigquery.ScalarQueryParameter("partition_id", "STRING", partition_id),
            ]
        )
        rows = list(self._client.query(query, job_config=job_config).result())

        if not rows:
            return WarehousePartitionObservation(
                source_object=source_object,
                partition_date=partition_date,
                destination=destination,
                present=False,
                row_count=None,
            )

        total_rows = rows[0]["total_rows"]
        return WarehousePartitionObservation(
            source_object=source_object,
            partition_date=partition_date,
            destination=destination,
            present=True,
            row_count=int(total_rows),
        )