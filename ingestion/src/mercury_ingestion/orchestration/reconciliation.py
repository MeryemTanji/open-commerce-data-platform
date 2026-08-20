"""Mercury's provenance-backed reconciliation layer (ADR-010 Phase 3C).

``RecoveryReconciler`` answers one narrow question for a
``RECONCILE``-decided logical source delivery: has this source *already*
physically succeeded end-to-end, provably, even though Mercury's control
plane lost track of that success? It never executes anything -- no
connector, no GCS write, no BigQuery load, no replay-state append. It
only reads durable provenance and current physical metadata and decides
``CONFIRMED`` or ``BLOCKED``.

The governing rule (ADR-010 Phase 3C): Mercury may repair missing
control-plane completion state only when existing durable provenance
and current physical state *prove* that the expected immutable Raw
artifact was successfully materialized into the expected BigQuery Raw
partition. When proof is incomplete or contradictory, Mercury must not
guess -- every missing or mismatched fact returns ``BLOCKED`` with a
specific, finite, technical reason, never a free-form message.

This module never reads Raw business/customer content: it inspects only
provenance records (technical metadata Mercury itself already recorded)
and read-only artifact/warehouse *metadata* observations (existence,
checksum, size, row count) via ``RawArtifactInspector``/
``WarehouseInspector``. An inability to inspect (permission denied,
service unavailable, ...) is a genuine infrastructure failure and is
never silently converted into a normal ``BLOCKED`` evidence result --
that distinction is the caller's responsibility (see
``RecoveryExecutor``), since this module's own ``reconcile()`` lets such
exceptions propagate unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum

from mercury_ingestion.common.artifact_inspection import RawArtifactInspector
from mercury_ingestion.orchestration.provenance import ProvenanceStore
from mercury_ingestion.warehouse.inspection import WarehouseInspector

_INGESTION_DATE_SEGMENT_PATTERN = re.compile(r"(?:^|/)ingestion_date=(\d{4}-\d{2}-\d{2})(?:/|$)")


def _extract_ingestion_date_from_uri(gcs_uri: str) -> date | None:
    """Extract the ``ingestion_date=YYYY-MM-DD`` path segment from a ``gs://`` URI.

    Requires an exact, fully-delimited path segment (bounded by ``/`` or
    the start/end of the string on both sides) -- never a substring
    match anywhere else in the URI (e.g. a filename or query-like
    component that merely happens to contain the same characters).

    Returns ``None`` if the segment is missing or its date portion is
    not a valid calendar date -- this function never raises. A missing
    or malformed segment is contradictory/incomplete evidence for the
    caller to handle as a normal ``BLOCKED`` reconciliation outcome, not
    an infrastructure failure.

    This module never derives ``ingestion_date`` from ``delivery_date``
    (e.g. no "+1 day" arithmetic) -- it only ever reads whatever date is
    already encoded in the URI, for internal provenance-consistency
    comparison against ``RawArtifactProvenance.ingestion_date``.
    """
    match = _INGESTION_DATE_SEGMENT_PATTERN.search(gcs_uri)
    if match is None:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _require_non_blank(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


class ReconciliationOutcome(str, Enum):
    """Whether reconciliation could prove end-to-end physical completion."""

    CONFIRMED = "confirmed"
    BLOCKED = "blocked"


class ReconciliationReason(str, Enum):
    """A finite, technical, PII-safe reason code -- never a free-form message."""

    CONFIRMED = "confirmed"
    NO_WAREHOUSE_LOAD_PROVENANCE = "no_warehouse_load_provenance"
    NO_ARTIFACT_PROVENANCE = "no_artifact_provenance"
    PROVENANCE_IDENTITY_MISMATCH = "provenance_identity_mismatch"
    GCS_ARTIFACT_MISSING = "gcs_artifact_missing"
    GCS_CHECKSUM_MISSING = "gcs_checksum_missing"
    GCS_CHECKSUM_MISMATCH = "gcs_checksum_mismatch"
    GCS_SIZE_MISMATCH = "gcs_size_mismatch"
    GCS_INGESTION_DATE_MISMATCH = "gcs_ingestion_date_mismatch"
    BIGQUERY_PARTITION_MISSING = "bigquery_partition_missing"
    BIGQUERY_DESTINATION_MISMATCH = "bigquery_destination_mismatch"
    BIGQUERY_ROW_COUNT_MISMATCH = "bigquery_row_count_mismatch"


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """The outcome of attempting to reconcile one logical source delivery.

    For ``CONFIRMED``, ``provenance_id``/``load_id`` identify the exact
    evidence chain that proved completion. For ``BLOCKED``, they are
    typically ``None`` -- the reason code alone is sufficient and safe;
    no free-form detail is ever attached.
    """

    delivery_date: date
    source_object: str
    outcome: ReconciliationOutcome
    reason: ReconciliationReason
    provenance_id: str | None = None
    load_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.delivery_date, date):
            raise TypeError("delivery_date must be a datetime.date")
        _require_non_blank(self.source_object, "source_object")
        if not isinstance(self.outcome, ReconciliationOutcome):
            raise TypeError("outcome must be a ReconciliationOutcome")
        if not isinstance(self.reason, ReconciliationReason):
            raise TypeError("reason must be a ReconciliationReason")
        if self.provenance_id is not None:
            _require_non_blank(self.provenance_id, "provenance_id")
        if self.load_id is not None:
            _require_non_blank(self.load_id, "load_id")

        if self.outcome is ReconciliationOutcome.CONFIRMED:
            if self.reason is not ReconciliationReason.CONFIRMED:
                raise ValueError("CONFIRMED outcome must use reason=CONFIRMED")
            if self.provenance_id is None or self.load_id is None:
                raise ValueError("CONFIRMED outcome must identify both provenance_id and load_id")
        else:
            if self.reason is ReconciliationReason.CONFIRMED:
                raise ValueError("BLOCKED outcome must not use reason=CONFIRMED")


def _blocked(delivery_date: date, source_object: str, reason: ReconciliationReason) -> ReconciliationResult:
    return ReconciliationResult(delivery_date=delivery_date, source_object=source_object, outcome=ReconciliationOutcome.BLOCKED, reason=reason)


class RecoveryReconciler:
    """Pure evidence-evaluation layer: decides CONFIRMED or BLOCKED, never executes anything.

    Depends only on the generic ``ProvenanceStore``, ``RawArtifactInspector``,
    and ``WarehouseInspector`` abstractions -- never a concrete backend,
    never a connector, never ``StorageManager``, never ``BigQueryRawLoader``.
    """

    def __init__(
        self,
        provenance_store: ProvenanceStore,
        raw_artifact_inspector: RawArtifactInspector,
        warehouse_inspector: WarehouseInspector,
    ) -> None:
        if not isinstance(provenance_store, ProvenanceStore):
            raise TypeError("provenance_store must be a ProvenanceStore")
        if not isinstance(raw_artifact_inspector, RawArtifactInspector):
            raise TypeError("raw_artifact_inspector must be a RawArtifactInspector")
        if not isinstance(warehouse_inspector, WarehouseInspector):
            raise TypeError("warehouse_inspector must be a WarehouseInspector")

        self.provenance_store = provenance_store
        self.raw_artifact_inspector = raw_artifact_inspector
        self.warehouse_inspector = warehouse_inspector

    def reconcile(self, delivery_date: date, source_object: str) -> ReconciliationResult:
        """Attempt to prove end-to-end physical completion for one logical source delivery.

        Every check below is evaluated in order, and the first
        unmet condition returns ``BLOCKED`` with its specific reason --
        no partial/best-effort confirmation is ever produced. Only when
        every fact matches does this return ``CONFIRMED``.

        Raises:
            Whatever the underlying ``ProvenanceStore``/
            ``RawArtifactInspector``/``WarehouseInspector`` raises for a
            genuine infrastructure failure (as opposed to a legitimate
            "not found"/"absent" observation) -- this method does not
            catch or convert those into a normal ``BLOCKED`` result.
        """
        if not isinstance(delivery_date, date):
            raise TypeError("delivery_date must be a datetime.date")
        _require_non_blank(source_object, "source_object")

        # Durable warehouse provenance must exist.
        warehouse_provenance = self.provenance_store.get_latest_warehouse_load(delivery_date, source_object)
        if warehouse_provenance is None:
            return _blocked(delivery_date, source_object, ReconciliationReason.NO_WAREHOUSE_LOAD_PROVENANCE)

        # The artifact provenance it links to must resolve.
        artifact_provenance = self.provenance_store.get_artifact(warehouse_provenance.provenance_id)
        if artifact_provenance is None:
            return _blocked(delivery_date, source_object, ReconciliationReason.NO_ARTIFACT_PROVENANCE)

        # Cross-record identity must agree.
        if (
            warehouse_provenance.delivery_date != delivery_date
            or warehouse_provenance.source_object != source_object
            or warehouse_provenance.partition_date != delivery_date
            or artifact_provenance.delivery_date != delivery_date
            or artifact_provenance.source_object != source_object
        ):
            return _blocked(delivery_date, source_object, ReconciliationReason.PROVENANCE_IDENTITY_MISMATCH)

        # GCS identity: inspect exactly the recorded artifact URI.
        artifact_observation = self.raw_artifact_inspector.inspect(artifact_provenance.gcs_uri)
        if not artifact_observation.present:
            return _blocked(delivery_date, source_object, ReconciliationReason.GCS_ARTIFACT_MISSING)
        if artifact_observation.checksum is None:
            return _blocked(delivery_date, source_object, ReconciliationReason.GCS_CHECKSUM_MISSING)
        if artifact_observation.checksum != artifact_provenance.checksum:
            return _blocked(delivery_date, source_object, ReconciliationReason.GCS_CHECKSUM_MISMATCH)
        if artifact_observation.file_size_bytes != artifact_provenance.file_size_bytes:
            return _blocked(delivery_date, source_object, ReconciliationReason.GCS_SIZE_MISMATCH)

        # Internal provenance-consistency check: the ingestion_date
        # recorded in provenance must match the date actually encoded
        # in the artifact's own URI. This is never a delivery_date + 1
        # derivation (that rule belongs solely to
        # OlistSimulatedSourceProvider) -- it only compares two already-
        # recorded facts against each other.
        uri_ingestion_date = _extract_ingestion_date_from_uri(artifact_provenance.gcs_uri)
        if uri_ingestion_date is None or uri_ingestion_date != artifact_provenance.ingestion_date:
            return _blocked(delivery_date, source_object, ReconciliationReason.GCS_INGESTION_DATE_MISMATCH)

        # Warehouse identity: inspect the recorded partition.
        partition_observation = self.warehouse_inspector.inspect_partition(source_object, delivery_date)
        if not partition_observation.present:
            return _blocked(delivery_date, source_object, ReconciliationReason.BIGQUERY_PARTITION_MISSING)
        if partition_observation.destination != warehouse_provenance.destination:
            return _blocked(delivery_date, source_object, ReconciliationReason.BIGQUERY_DESTINATION_MISMATCH)
        if (
            partition_observation.row_count != warehouse_provenance.output_rows
            or warehouse_provenance.output_rows != artifact_provenance.record_count
        ):
            return _blocked(delivery_date, source_object, ReconciliationReason.BIGQUERY_ROW_COUNT_MISMATCH)

        return ReconciliationResult(
            delivery_date=delivery_date,
            source_object=source_object,
            outcome=ReconciliationOutcome.CONFIRMED,
            reason=ReconciliationReason.CONFIRMED,
            provenance_id=artifact_provenance.provenance_id,
            load_id=warehouse_provenance.load_id,
        )