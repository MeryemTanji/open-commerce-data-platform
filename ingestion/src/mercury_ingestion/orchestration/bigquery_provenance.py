"""Mercury's BigQuery implementation of the provenance store (ADR-010 Phase 3C).

``BigQueryProvenanceStore`` implements the generic ``ProvenanceStore``
contract from ``provenance.py`` against two BigQuery operational-
metadata tables, mirroring ``BigQueryReplayStateStore``'s own
conventions exactly: no constructor-time provisioning, explicit
``ensure_resources()``, Application Default Credentials only, and
append-only inserts with query parameterization for every value.

It is strictly a persistence adapter -- it has no knowledge of GCS,
connectors, ``BigQueryRawLoader``, ``HistoricalReplayRunner``, or
``RecoveryExecutor``. Nothing here ever touches a Raw business table.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from google.cloud import bigquery

from mercury_ingestion.orchestration.provenance import (
    ProvenanceStore,
    RawArtifactProvenance,
    WarehouseLoadProvenance,
)

DEFAULT_DATASET_ID = "metadata"
DEFAULT_ARTIFACT_TABLE_ID = "raw_artifact_provenance"
DEFAULT_WAREHOUSE_TABLE_ID = "warehouse_load_provenance"

ARTIFACT_PROVENANCE_SCHEMA: tuple[bigquery.SchemaField, ...] = (
    bigquery.SchemaField("provenance_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("delivery_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("source_object", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("ingestion_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("gcs_uri", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("checksum", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("file_size_bytes", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("record_count", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("recorded_at", "TIMESTAMP", mode="REQUIRED"),
)

WAREHOUSE_LOAD_PROVENANCE_SCHEMA: tuple[bigquery.SchemaField, ...] = (
    bigquery.SchemaField("load_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("provenance_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("delivery_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("source_object", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("destination", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("partition_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("output_rows", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("job_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("recorded_at", "TIMESTAMP", mode="REQUIRED"),
)

_ARTIFACT_SELECT_COLUMNS = (
    "provenance_id, run_id, delivery_date, source_object, ingestion_date, gcs_uri, "
    "checksum, file_size_bytes, record_count, recorded_at"
)
_WAREHOUSE_SELECT_COLUMNS = (
    "load_id, provenance_id, run_id, delivery_date, source_object, destination, "
    "partition_date, output_rows, job_id, recorded_at"
)


def _require_non_blank(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


def _serialize_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class BigQueryProvenanceStore(ProvenanceStore):
    """BigQuery-backed append-only store for artifact/warehouse-load provenance.

    Uses two tables in the same ``metadata`` dataset
    ``BigQueryReplayStateStore`` already uses:
    ``raw_artifact_provenance`` and ``warehouse_load_provenance``.
    Construction only creates a lightweight ``bigquery.Client`` handle
    and performs no network call; call ``ensure_resources()`` explicitly
    to create the tables if they don't already exist.
    """

    def __init__(
        self,
        project_id: str,
        dataset_id: str = DEFAULT_DATASET_ID,
        artifact_table_id: str = DEFAULT_ARTIFACT_TABLE_ID,
        warehouse_table_id: str = DEFAULT_WAREHOUSE_TABLE_ID,
        location: str | None = None,
    ) -> None:
        _require_non_blank(project_id, "project_id")
        _require_non_blank(dataset_id, "dataset_id")
        _require_non_blank(artifact_table_id, "artifact_table_id")
        _require_non_blank(warehouse_table_id, "warehouse_table_id")
        if location is not None:
            _require_non_blank(location, "location")

        self.project_id = project_id
        self.dataset_id = dataset_id
        self.artifact_table_id = artifact_table_id
        self.warehouse_table_id = warehouse_table_id
        self.location = location
        self._client = bigquery.Client(project=project_id, location=location)

    @property
    def _artifact_table_ref(self) -> str:
        return f"{self.project_id}.{self.dataset_id}.{self.artifact_table_id}"

    @property
    def _warehouse_table_ref(self) -> str:
        return f"{self.project_id}.{self.dataset_id}.{self.warehouse_table_id}"

    def ensure_resources(self) -> None:
        """Idempotently ensure the metadata dataset and both provenance tables exist.

        Safe to call repeatedly (``exists_ok=True`` throughout). Never
        touches any Raw dataset or table, and never touches the
        replay-state table either -- only Mercury's own two provenance
        tables. Both tables are partitioned by ``delivery_date`` and
        clustered by ``source_object``, matching
        ``BigQueryReplayStateStore``'s own convention.
        """
        dataset = bigquery.Dataset(f"{self.project_id}.{self.dataset_id}")
        if self.location is not None:
            dataset.location = self.location
        self._client.create_dataset(dataset, exists_ok=True)

        artifact_table = bigquery.Table(self._artifact_table_ref, schema=list(ARTIFACT_PROVENANCE_SCHEMA))
        artifact_table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY, field="delivery_date"
        )
        artifact_table.clustering_fields = ["source_object"]
        self._client.create_table(artifact_table, exists_ok=True)

        warehouse_table = bigquery.Table(self._warehouse_table_ref, schema=list(WAREHOUSE_LOAD_PROVENANCE_SCHEMA))
        warehouse_table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY, field="delivery_date"
        )
        warehouse_table.clustering_fields = ["source_object"]
        self._client.create_table(warehouse_table, exists_ok=True)

    def append_artifact(self, record: RawArtifactProvenance) -> None:
        """Insert one new Raw artifact provenance record. Never updates or deletes.

        Raises:
            RuntimeError: if BigQuery reports any row insertion errors.
        """
        if not isinstance(record, RawArtifactProvenance):
            raise TypeError("record must be a RawArtifactProvenance")

        row = {
            "provenance_id": record.provenance_id,
            "run_id": record.run_id,
            "delivery_date": record.delivery_date.isoformat(),
            "source_object": record.source_object,
            "ingestion_date": record.ingestion_date.isoformat(),
            "gcs_uri": record.gcs_uri,
            "checksum": record.checksum,
            "file_size_bytes": record.file_size_bytes,
            "record_count": record.record_count,
            "recorded_at": _serialize_timestamp(record.recorded_at),
        }
        errors = self._client.insert_rows_json(self._artifact_table_ref, [row], row_ids=[record.provenance_id])
        if errors:
            # Per ADR-011, this persistence-adapter exception message is
            # static and Mercury-authored -- it never embeds `errors`
            # (arbitrary backend/provider-generated response payload) or
            # any record content. Callers (HistoricalReplayRunner,
            # RecoveryExecutor) already wrap this into their own safe
            # orchestration error via exception chaining; this adapter
            # itself must not be the first place arbitrary provider text
            # enters an exception message.
            raise RuntimeError("failed to append artifact provenance")

    def append_warehouse_load(self, record: WarehouseLoadProvenance) -> None:
        """Insert one new warehouse-load provenance record. Never updates or deletes.

        Raises:
            RuntimeError: if BigQuery reports any row insertion errors.
        """
        if not isinstance(record, WarehouseLoadProvenance):
            raise TypeError("record must be a WarehouseLoadProvenance")

        row = {
            "load_id": record.load_id,
            "provenance_id": record.provenance_id,
            "run_id": record.run_id,
            "delivery_date": record.delivery_date.isoformat(),
            "source_object": record.source_object,
            "destination": record.destination,
            "partition_date": record.partition_date.isoformat(),
            "output_rows": record.output_rows,
            "job_id": record.job_id,
            "recorded_at": _serialize_timestamp(record.recorded_at),
        }
        errors = self._client.insert_rows_json(self._warehouse_table_ref, [row], row_ids=[record.load_id])
        if errors:
            # Per ADR-011, static/Mercury-authored -- see append_artifact
            # for the same rationale.
            raise RuntimeError("failed to append warehouse load provenance")

    def get_artifact(self, provenance_id: str) -> RawArtifactProvenance | None:
        """Return the Raw artifact provenance record with this exact ID, or None."""
        _require_non_blank(provenance_id, "provenance_id")

        # self._artifact_table_ref is a pre-validated identifier from
        # constructor config, never user input; provenance_id is bound
        # via ScalarQueryParameter below, never interpolated into the query.
        query = (
            f"SELECT {_ARTIFACT_SELECT_COLUMNS} FROM `{self._artifact_table_ref}` "  # nosec B608
            "WHERE provenance_id = @provenance_id "
            "LIMIT 1"
        )
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("provenance_id", "STRING", provenance_id)]
        )
        rows = list(self._client.query(query, job_config=job_config, location=self.location).result())
        if not rows:
            return None
        return self._row_to_artifact(rows[0])

    def get_artifact_history(self, delivery_date: date, source_object: str) -> tuple[RawArtifactProvenance, ...]:
        """Return every Raw artifact provenance record for this pair, oldest first."""
        if not isinstance(delivery_date, date):
            raise TypeError("delivery_date must be a datetime.date")
        _require_non_blank(source_object, "source_object")

        query = (
            f"SELECT {_ARTIFACT_SELECT_COLUMNS} FROM `{self._artifact_table_ref}` "  # nosec B608
            "WHERE delivery_date = @delivery_date AND source_object = @source_object "
            "ORDER BY recorded_at ASC"
        )
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("delivery_date", "DATE", delivery_date),
                bigquery.ScalarQueryParameter("source_object", "STRING", source_object),
            ]
        )
        rows = self._client.query(query, job_config=job_config, location=self.location).result()
        return tuple(self._row_to_artifact(row) for row in rows)

    def get_artifact_by_uri(
        self, delivery_date: date, source_object: str, gcs_uri: str
    ) -> RawArtifactProvenance | None:
        """Return the Raw artifact provenance record matching this exact URI, or None.

        Most recently recorded match wins if more than one somehow
        exists for the same URI (should not normally happen, given GCS
        create-only immutability, but this keeps the lookup
        deterministic regardless).
        """
        if not isinstance(delivery_date, date):
            raise TypeError("delivery_date must be a datetime.date")
        _require_non_blank(source_object, "source_object")
        _require_non_blank(gcs_uri, "gcs_uri")

        query = (
            f"SELECT {_ARTIFACT_SELECT_COLUMNS} FROM `{self._artifact_table_ref}` "  # nosec B608
            "WHERE delivery_date = @delivery_date AND source_object = @source_object AND gcs_uri = @gcs_uri "
            "ORDER BY recorded_at DESC "
            "LIMIT 1"
        )
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("delivery_date", "DATE", delivery_date),
                bigquery.ScalarQueryParameter("source_object", "STRING", source_object),
                bigquery.ScalarQueryParameter("gcs_uri", "STRING", gcs_uri),
            ]
        )
        rows = list(self._client.query(query, job_config=job_config, location=self.location).result())
        if not rows:
            return None
        return self._row_to_artifact(rows[0])

    def get_warehouse_load_history(
        self, delivery_date: date, source_object: str
    ) -> tuple[WarehouseLoadProvenance, ...]:
        """Return every warehouse-load provenance record for this pair, oldest first."""
        if not isinstance(delivery_date, date):
            raise TypeError("delivery_date must be a datetime.date")
        _require_non_blank(source_object, "source_object")

        query = (
            f"SELECT {_WAREHOUSE_SELECT_COLUMNS} FROM `{self._warehouse_table_ref}` "  # nosec B608
            "WHERE delivery_date = @delivery_date AND source_object = @source_object "
            "ORDER BY recorded_at ASC"
        )
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("delivery_date", "DATE", delivery_date),
                bigquery.ScalarQueryParameter("source_object", "STRING", source_object),
            ]
        )
        rows = self._client.query(query, job_config=job_config, location=self.location).result()
        return tuple(self._row_to_warehouse_load(row) for row in rows)

    def get_latest_warehouse_load(self, delivery_date: date, source_object: str) -> WarehouseLoadProvenance | None:
        """Return the most recently recorded warehouse-load provenance record for this pair, or None."""
        if not isinstance(delivery_date, date):
            raise TypeError("delivery_date must be a datetime.date")
        _require_non_blank(source_object, "source_object")

        query = (
            f"SELECT {_WAREHOUSE_SELECT_COLUMNS} FROM `{self._warehouse_table_ref}` "  # nosec B608
            "WHERE delivery_date = @delivery_date AND source_object = @source_object "
            "ORDER BY recorded_at DESC "
            "LIMIT 1"
        )
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("delivery_date", "DATE", delivery_date),
                bigquery.ScalarQueryParameter("source_object", "STRING", source_object),
            ]
        )
        rows = list(self._client.query(query, job_config=job_config, location=self.location).result())
        if not rows:
            return None
        return self._row_to_warehouse_load(rows[0])

    @staticmethod
    def _row_to_artifact(row: object) -> RawArtifactProvenance:
        return RawArtifactProvenance(
            provenance_id=row["provenance_id"],
            run_id=row["run_id"],
            delivery_date=row["delivery_date"],
            source_object=row["source_object"],
            ingestion_date=row["ingestion_date"],
            gcs_uri=row["gcs_uri"],
            checksum=row["checksum"],
            file_size_bytes=row["file_size_bytes"],
            record_count=row["record_count"],
            recorded_at=row["recorded_at"],
        )

    @staticmethod
    def _row_to_warehouse_load(row: object) -> WarehouseLoadProvenance:
        return WarehouseLoadProvenance(
            load_id=row["load_id"],
            provenance_id=row["provenance_id"],
            run_id=row["run_id"],
            delivery_date=row["delivery_date"],
            source_object=row["source_object"],
            destination=row["destination"],
            partition_date=row["partition_date"],
            output_rows=row["output_rows"],
            job_id=row["job_id"],
            recorded_at=row["recorded_at"],
        )