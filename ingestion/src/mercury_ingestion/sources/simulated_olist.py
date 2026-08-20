"""Mercury's Olist-simulation-backed SourceDeliveryProvider (ADR-009).

``OlistSimulatedSourceProvider`` adapts the existing ``OlistSourceSimulator``
into the ``SourceDeliveryProvider`` contract. It never reimplements
Olist simulation, CSV parsing, or temporal-selection logic — all of that
already lives in ``OlistSourceSimulator`` and stays there unmodified.

Per ADR-009, source generation and replay must be independently
executable: if the expected simulated delivery is already fully
materialized on disk, this provider returns it as-is rather than
regenerating it (which would fail anyway, since the simulator's own
immutability contract raises ``FileExistsError`` on an existing
delivery). If a delivery directory exists but is missing one or more
expected files, that is treated as a corrupt/partial delivery and
rejected clearly rather than silently completed, silently returned as a
partial batch, or silently regenerated over.

This provider also owns Mercury's Olist-specific historical-simulation
timing policy: for one business date ``D``, the simulated data is
treated as becoming available for ingestion on ``D + 1`` day, modeling
what a real daily API delivery would look like (data for a business day
typically only becomes available for processing the following day).
This is *only* a simulation-timing convention -- ``OlistSourceSimulator``
itself remains entirely unaware of it (its own ``simulation_date``
concept, and the ``daily/<simulation_date>/`` directory it generates,
are untouched by this policy), and no other Mercury component may
derive this offset itself. A future real API-backed
``SourceDeliveryProvider`` supplies its own genuine ingestion date and
has no reason to inherit this Olist-only rule.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

from mercury_ingestion.simulation.olist import (
    DAILY_SOURCE_OBJECTS,
    INITIAL_SOURCE_OBJECTS,
    SOURCE_FILENAMES,
    DailySimulationResult,
    InitialSimulationResult,
    OlistSourceSimulator,
)
from mercury_ingestion.sources.base import SourceDelivery, SourceDeliveryBatch, SourceDeliveryProvider

_ENCODING = "utf-8-sig"


def _count_csv_records(path: Path) -> int:
    """Count logical CSV data rows (excluding header) without modifying the file.

    Uses the same CSV-aware, encoding-consistent approach established
    throughout Mercury's ingestion framework, so quoted multiline fields
    (e.g. in an already-generated Reviews delivery) are counted
    correctly rather than by naive physical line counting.
    """
    with path.open(encoding=_ENCODING, newline="") as handle:
        reader = csv.DictReader(handle)
        return sum(1 for _ in reader)


class OlistSimulatedSourceProvider(SourceDeliveryProvider):
    """Adapts an ``OlistSourceSimulator`` into ``SourceDeliveryBatch`` results."""

    def __init__(self, simulator: OlistSourceSimulator) -> None:
        if not isinstance(simulator, OlistSourceSimulator):
            raise TypeError("simulator must be an OlistSourceSimulator")
        self.simulator = simulator

    def get_initial_delivery(self) -> SourceDeliveryBatch:
        """Return the initial delivery, generating it only if not already present."""
        destination_dir = self.simulator.output_directory / "initial"
        if destination_dir.exists():
            return self._adapt_existing(destination_dir, INITIAL_SOURCE_OBJECTS, delivery_date=None)

        result = self.simulator.generate_initial_load()
        return self._adapt_initial_result(result)

    def get_daily_delivery(self, delivery_date: date) -> SourceDeliveryBatch:
        """Return one day's delivery, generating it only if not already present.

        The returned batch's ``ingestion_date`` is always
        ``delivery_date + 1 day`` (Mercury's Olist historical-simulation
        timing convention), regardless of whether this call regenerates
        the delivery or adapts an already-materialized one -- the two
        paths must never diverge in their timing semantics.
        """
        destination_dir = self.simulator.output_directory / "daily" / delivery_date.isoformat()
        ingestion_date = self._daily_ingestion_date(delivery_date)
        if destination_dir.exists():
            return self._adapt_existing(
                destination_dir, DAILY_SOURCE_OBJECTS, delivery_date=delivery_date, ingestion_date=ingestion_date
            )

        result = self.simulator.generate_daily_load(delivery_date)
        return self._adapt_daily_result(result)

    @staticmethod
    def _daily_ingestion_date(delivery_date: date) -> date:
        """Mercury's single definition of the Olist daily-simulation timing rule.

        Business data for ``delivery_date`` is treated as becoming
        available for ingestion the following calendar day -- this is
        an Olist-historical-simulation convention only, defined exactly
        once, here.
        """
        return delivery_date + timedelta(days=1)

    def _adapt_initial_result(self, result: InitialSimulationResult) -> SourceDeliveryBatch:
        deliveries = tuple(
            SourceDelivery(
                source_object=simulated_file.source_object,
                path=simulated_file.path,
                delivery_date=None,
                record_count=simulated_file.record_count,
            )
            for simulated_file in result.files
        )
        return SourceDeliveryBatch(deliveries=deliveries, delivery_date=None)

    def _adapt_daily_result(self, result: DailySimulationResult) -> SourceDeliveryBatch:
        deliveries = tuple(
            SourceDelivery(
                source_object=simulated_file.source_object,
                path=simulated_file.path,
                delivery_date=result.simulation_date,
                record_count=simulated_file.record_count,
            )
            for simulated_file in result.files
        )
        return SourceDeliveryBatch(
            deliveries=deliveries,
            delivery_date=result.simulation_date,
            ingestion_date=self._daily_ingestion_date(result.simulation_date),
        )

    def _adapt_existing(
        self,
        destination_dir: Path,
        expected_source_objects: tuple[str, ...],
        delivery_date: date | None,
        ingestion_date: date | None = None,
    ) -> SourceDeliveryBatch:
        """Adapt an already-generated, on-disk delivery without regenerating it.

        Raises:
            ValueError: if ``destination_dir`` exists but is not a
                directory, or is missing one or more of the expected
                source files -- a partial delivery is never silently
                completed, returned, or regenerated over.
        """
        if not destination_dir.is_dir():
            raise ValueError(f"expected a delivery directory at {destination_dir}, found a non-directory path")

        deliveries: list[SourceDelivery] = []
        missing: list[str] = []
        for source_object in expected_source_objects:
            file_path = destination_dir / SOURCE_FILENAMES[source_object]
            if not file_path.is_file():
                missing.append(source_object)
                continue
            deliveries.append(
                SourceDelivery(
                    source_object=source_object,
                    path=file_path,
                    delivery_date=delivery_date,
                    record_count=_count_csv_records(file_path),
                )
            )

        if missing:
            raise ValueError(
                f"existing delivery at {destination_dir} is incomplete; missing required "
                f"source(s): {', '.join(sorted(missing))}"
            )

        return SourceDeliveryBatch(deliveries=tuple(deliveries), delivery_date=delivery_date, ingestion_date=ingestion_date)