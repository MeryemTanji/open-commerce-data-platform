"""Mercury's BigQuery Raw warehouse-loading capability.

Per ADR-008, ``BigQueryRawLoader`` begins strictly after Raw Landing has
already succeeded: it receives a ``gs://`` URI for an already-preserved
source artifact and materializes it as a queryable BigQuery Raw
table or partition. It has no knowledge of connectors, source
simulation, or GCS upload/delete/rename — those all happen upstream of
this module, and this module never touches the GCS object itself beyond
referencing its URI in a load job.

Loading strategy (ADR-007 / ADR-008):

- **Master/reference** sources (customers, products, sellers,
  geolocations) load into an unpartitioned table with whole-table
  ``WRITE_TRUNCATE``, making replay idempotent.
- **Transactional** sources (orders, order_items, payments, reviews)
  load into a daily partitioned table, targeting one explicit
  business/source-date partition via a ``$YYYYMMDD`` decorator, with
  ``WRITE_TRUNCATE`` scoped to that partition only.

Every Raw column is loaded as ``STRING`` per the explicit schemas in
``schemas.py`` — no autodetection, no business typing, no platform
metadata columns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from google.cloud import bigquery

from mercury_ingestion.warehouse.schemas import (
    SUPPORTED_SOURCE_OBJECTS,
    TRANSACTIONAL_SOURCE_OBJECTS,
    get_raw_schema,
)

DEFAULT_LOCATION = "europe-west4"


def _require_non_blank(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


@dataclass(frozen=True, slots=True)
class BigQueryLoadResult:
    """Outcome of a single successful ``BigQueryRawLoader.load()`` call.

    Deliberately narrow: it reports what was loaded, where it landed in
    BigQuery, and the job that did it — nothing business-specific.

    ``partition_date`` is the business/source date used to route this
    load to its BigQuery transactional partition — distinct from
    ``ingestion_date`` elsewhere in Mercury (connectors, ``IngestionRunner``,
    the storage layer), which is the processing/landing date. The two
    happen to carry the same value for every current caller, but they
    are conceptually different dates, so this loader names its own
    concept correctly rather than borrowing the ingestion-side term.
    """

    source_object: str
    source_uri: str
    destination: str
    partition_date: date
    output_rows: int
    job_id: str

    def __post_init__(self) -> None:
        _require_non_blank(self.source_object, "source_object")
        _require_non_blank(self.source_uri, "source_uri")
        _require_non_blank(self.destination, "destination")
        _require_non_blank(self.job_id, "job_id")
        if not isinstance(self.partition_date, date):
            raise TypeError("partition_date must be a datetime.date")
        if self.output_rows < 0:
            raise ValueError("output_rows cannot be negative")


class BigQueryRawLoader:
    """Loads an already-landed GCS Raw CSV artifact into a BigQuery Raw table.

    Authentication relies entirely on Application Default Credentials —
    this class never accepts explicit credentials or a service-account
    file. Construction only creates a lightweight ``bigquery.Client``
    handle and performs no network call (no dataset existence check);
    the ``raw`` dataset is assumed to already exist and is never created
    here.
    """

    def __init__(self, project_id: str, dataset_id: str, location: str = DEFAULT_LOCATION) -> None:
        _require_non_blank(project_id, "project_id")
        _require_non_blank(dataset_id, "dataset_id")
        _require_non_blank(location, "location")

        self.project_id = project_id
        self.dataset_id = dataset_id
        self.location = location
        self._client = bigquery.Client(project=project_id, location=location)

    def load(self, source_object: str, gcs_uri: str, partition_date: date) -> BigQueryLoadResult:
        """Load one Raw artifact into its BigQuery Raw table or partition.

        The GCS artifact itself is never downloaded, deleted, moved, or
        rewritten -- the loader only submits a BigQuery load job
        referencing ``gcs_uri`` and waits for it to complete.

        ``partition_date`` is the business/source date used to route a
        transactional load to its explicit ``$YYYYMMDD`` partition. It
        is unrelated to any processing/landing "ingestion date" concept
        used elsewhere in Mercury -- callers currently pass the same
        date value either way, but this parameter's own name reflects
        what this loader actually does with it.

        Raises:
            ValueError: if ``source_object`` is blank or unsupported, or
                if ``gcs_uri`` is blank or not a ``gs://`` URI.
            TypeError: if ``partition_date`` is not a ``datetime.date``.
            google.api_core.exceptions.GoogleAPICallError: any BigQuery
                job failure propagates unchanged.
        """
        _require_non_blank(source_object, "source_object")
        if source_object not in SUPPORTED_SOURCE_OBJECTS:
            raise ValueError(f"unsupported source_object: {source_object!r}")
        _require_non_blank(gcs_uri, "gcs_uri")
        if not gcs_uri.startswith("gs://"):
            raise ValueError(f"gcs_uri must start with 'gs://': {gcs_uri!r}")
        if not isinstance(partition_date, date):
            raise TypeError("partition_date must be a datetime.date")

        is_transactional = source_object in TRANSACTIONAL_SOURCE_OBJECTS
        destination = self._build_destination(source_object, partition_date, is_transactional)
        schema = list(get_raw_schema(source_object))

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            autodetect=False,
            schema=schema,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
            # Reviews may contain quoted, embedded-newline text; applied
            # to every load rather than scoped only to reviews, since it
            # is safe for single-line CSV values too.
            allow_quoted_newlines=True,
            time_partitioning=(
                bigquery.TimePartitioning(type_=bigquery.TimePartitioningType.DAY)
                if is_transactional
                else None
            ),
        )

        job = self._client.load_table_from_uri(
            gcs_uri,
            destination,
            job_config=job_config,
            location=self.location,
        )
        job.result()

        return BigQueryLoadResult(
            source_object=source_object,
            source_uri=gcs_uri,
            destination=destination,
            partition_date=partition_date,
            output_rows=job.output_rows or 0,
            job_id=job.job_id,
        )

    def _build_destination(self, source_object: str, partition_date: date, is_transactional: bool) -> str:
        table = f"{self.project_id}.{self.dataset_id}.{source_object}"
        if is_transactional:
            return f"{table}${partition_date.strftime('%Y%m%d')}"
        return table