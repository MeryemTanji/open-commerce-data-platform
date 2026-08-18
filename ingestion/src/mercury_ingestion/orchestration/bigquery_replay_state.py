"""Mercury's BigQuery implementation of the replay-state store (ADR-010).

``BigQueryReplayStateStore`` implements the generic ``ReplayStateStore``
contract from ``state.py`` against a BigQuery operational-metadata
table. It is strictly a persistence adapter: it has no knowledge of
Olist simulation, connectors, GCS Raw Landing, ``BigQueryRawLoader``, or
``HistoricalReplayRunner``. ``HistoricalReplayRunner`` depends only on
the generic ``ReplayStateStore`` abstraction, never on this concrete
BigQuery implementation.

Every ``append()`` call inserts one new row; the table is never
updated, deleted from, or truncated. Queries use BigQuery query
parameters for values (delivery date, source object) while dataset and
table identifiers are built from already-validated constructor
configuration, since BigQuery parameters cannot parameterize
identifiers.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from google.cloud import bigquery

from mercury_ingestion.orchestration.state import (
    ReplayStage,
    ReplayStateRecord,
    ReplayStateStore,
    ReplayStatus,
)

DEFAULT_DATASET_ID = "metadata"
DEFAULT_TABLE_ID = "historical_replay_state"

# Explicit Raw-style schema: every column typed deliberately, no
# autodetection. Enum values are stored as their plain string .value.
REPLAY_STATE_SCHEMA: tuple[bigquery.SchemaField, ...] = (
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("event_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("delivery_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("source_object", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("stage", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("started_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("completed_at", "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("error_message", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("recorded_at", "TIMESTAMP", mode="REQUIRED"),
)

_SELECT_COLUMNS = (
    "run_id, event_id, delivery_date, source_object, status, stage, "
    "started_at, completed_at, error_message, recorded_at"
)


def _require_non_blank(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


def _serialize_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class BigQueryReplayStateStore(ReplayStateStore):
    """BigQuery-backed append-only store for historical replay state.

    Authentication relies entirely on Application Default Credentials,
    matching ``BigQueryRawLoader``. Construction only creates a
    lightweight ``bigquery.Client`` handle and performs no network call
    -- no dataset or table existence check. Call ``ensure_resources()``
    explicitly to create the metadata dataset/table if they don't
    already exist; construction alone never provisions anything.
    """

    def __init__(
        self,
        project_id: str,
        dataset_id: str = DEFAULT_DATASET_ID,
        table_id: str = DEFAULT_TABLE_ID,
        location: str | None = None,
    ) -> None:
        _require_non_blank(project_id, "project_id")
        _require_non_blank(dataset_id, "dataset_id")
        _require_non_blank(table_id, "table_id")
        if location is not None:
            _require_non_blank(location, "location")

        self.project_id = project_id
        self.dataset_id = dataset_id
        self.table_id = table_id
        self.location = location
        self._client = bigquery.Client(project=project_id, location=location)

    @property
    def _table_ref(self) -> str:
        return f"{self.project_id}.{self.dataset_id}.{self.table_id}"

    def ensure_resources(self) -> None:
        """Idempotently ensure the metadata dataset and replay-state table exist.

        Safe to call repeatedly: uses ``exists_ok=True`` throughout, so
        an already-existing dataset/table is left untouched rather than
        recreated or overwritten. This never touches any Raw dataset or
        table -- it only manages Mercury's own operational-metadata
        table (``metadata.historical_replay_state`` by default).

        The table is partitioned by ``delivery_date`` (DAY granularity)
        since replay-state queries are always anchored to a delivery
        date or date range, and clustered by ``source_object`` since
        most lookups also filter to one specific source.
        """
        dataset = bigquery.Dataset(f"{self.project_id}.{self.dataset_id}")
        if self.location is not None:
            dataset.location = self.location
        self._client.create_dataset(dataset, exists_ok=True)

        table = bigquery.Table(self._table_ref, schema=list(REPLAY_STATE_SCHEMA))
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY, field="delivery_date"
        )
        table.clustering_fields = ["source_object"]
        self._client.create_table(table, exists_ok=True)

    def append(self, record: ReplayStateRecord) -> None:
        """Insert one new replay-state event.

        Never updates, deletes, merges over, or truncates existing rows
        -- this is a pure insert. ``record.event_id`` is passed as the
        streaming-insert row ID, which BigQuery uses on a best-effort
        basis to deduplicate accidental retries of the exact same
        insert; event ID uniqueness itself is the caller's
        responsibility at event-creation time, not a BigQuery
        constraint.

        Raises:
            RuntimeError: if BigQuery reports any row insertion errors.
        """
        if not isinstance(record, ReplayStateRecord):
            raise TypeError("record must be a ReplayStateRecord")

        row = {
            "run_id": record.run_id,
            "event_id": record.event_id,
            "delivery_date": record.delivery_date.isoformat(),
            "source_object": record.source_object,
            "status": record.status.value,
            "stage": record.stage.value,
            "started_at": _serialize_timestamp(record.started_at),
            "completed_at": _serialize_timestamp(record.completed_at) if record.completed_at is not None else None,
            "error_message": record.error_message,
            "recorded_at": _serialize_timestamp(record.recorded_at),
        }

        errors = self._client.insert_rows_json(self._table_ref, [row], row_ids=[record.event_id])
        if errors:
            raise RuntimeError(f"failed to append replay state event {record.event_id!r}: {errors}")

    def get_history(self, delivery_date: date, source_object: str) -> tuple[ReplayStateRecord, ...]:
        """Return every event for (delivery_date, source_object), oldest first."""
        if not isinstance(delivery_date, date):
            raise TypeError("delivery_date must be a datetime.date")
        _require_non_blank(source_object, "source_object")

        query = (
            f"SELECT {_SELECT_COLUMNS} FROM `{self._table_ref}` "
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
        return tuple(self._row_to_record(row) for row in rows)

    def get_latest(self, delivery_date: date, source_object: str) -> ReplayStateRecord | None:
        """Return the most recent event for (delivery_date, source_object), or None."""
        if not isinstance(delivery_date, date):
            raise TypeError("delivery_date must be a datetime.date")
        _require_non_blank(source_object, "source_object")

        query = (
            f"SELECT {_SELECT_COLUMNS} FROM `{self._table_ref}` "
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
        return self._row_to_record(rows[0])

    def get_latest_for_date(self, delivery_date: date) -> tuple[ReplayStateRecord, ...]:
        """Return the latest ATTEMPT event per source_object present on delivery_date.

        This can regress relative to an earlier success -- a source
        whose most recent event is ``FAILED`` is correctly returned with
        that ``FAILED`` event here, even if an earlier attempt for the
        same source succeeded. Use ``get_completed_for_date`` to ask
        about logical completion instead.
        """
        if not isinstance(delivery_date, date):
            raise TypeError("delivery_date must be a datetime.date")

        query = (
            "WITH ranked AS ("
            f"SELECT {_SELECT_COLUMNS}, "
            "ROW_NUMBER() OVER (PARTITION BY source_object ORDER BY recorded_at DESC) AS rn "
            f"FROM `{self._table_ref}` "
            "WHERE delivery_date = @delivery_date"
            ") "
            f"SELECT {_SELECT_COLUMNS} FROM ranked WHERE rn = 1 ORDER BY source_object ASC"
        )
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("delivery_date", "DATE", delivery_date)]
        )
        rows = self._client.query(query, job_config=job_config, location=self.location).result()
        return tuple(self._row_to_record(row) for row in rows)

    def get_completed_for_date(self, delivery_date: date) -> tuple[ReplayStateRecord, ...]:
        """Return the logical completion record per source_object for delivery_date.

        Restricts to ``status = 'success'`` *before* ranking, so a
        source's most recent successful event is returned even when a
        later, different-run attempt subsequently failed -- that later
        failure is simply excluded from consideration here, not allowed
        to hide the earlier success. A source with zero successful
        events (never attempted, still running, or every attempt
        failed) is absent from the result entirely.
        """
        if not isinstance(delivery_date, date):
            raise TypeError("delivery_date must be a datetime.date")

        query = (
            "WITH successful AS ("
            f"SELECT {_SELECT_COLUMNS} FROM `{self._table_ref}` "
            "WHERE delivery_date = @delivery_date AND status = 'success'"
            "), ranked AS ("
            f"SELECT {_SELECT_COLUMNS}, "
            "ROW_NUMBER() OVER (PARTITION BY source_object ORDER BY recorded_at DESC) AS rn "
            "FROM successful"
            ") "
            f"SELECT {_SELECT_COLUMNS} FROM ranked WHERE rn = 1 ORDER BY source_object ASC"
        )
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("delivery_date", "DATE", delivery_date)]
        )
        rows = self._client.query(query, job_config=job_config, location=self.location).result()
        return tuple(self._row_to_record(row) for row in rows)

    @staticmethod
    def _row_to_record(row: object) -> ReplayStateRecord:
        """Convert one BigQuery result row into a ReplayStateRecord.

        Unknown ``status``/``stage`` values raise ``ValueError`` via the
        enum constructors rather than being silently accepted --
        corrupted metadata must fail loudly when read, not be treated
        as valid.
        """
        return ReplayStateRecord(
            run_id=row["run_id"],
            event_id=row["event_id"],
            delivery_date=row["delivery_date"],
            source_object=row["source_object"],
            status=ReplayStatus(row["status"]),
            stage=ReplayStage(row["stage"]),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            error_message=row["error_message"],
            recorded_at=row["recorded_at"],
        )