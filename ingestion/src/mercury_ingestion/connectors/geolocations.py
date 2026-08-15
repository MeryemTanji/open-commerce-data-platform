"""Mercury's eighth concrete ingestion connector: geolocations.

This module implements the local, Olist-backed extraction of Nova
Commerce's public geographic reference data, under the
``public_geographic_source`` source system. Unlike the other seven
connectors, this is not transactional business data — it is external
reference data that may later be used to enrich entities such as
customers and sellers with geographic information.

Its CSV-specific technical validation and record counting are inherited
from ``BaseCsvConnector`` (per ADR-005); this module supplies only the
source identity, required schema, and domain documentation for the
geolocation source.

Dataset grain: one row represents one geographic observation associated
with a ZIP-code prefix — NOT one row per ZIP-code prefix. A single
``geolocation_zip_code_prefix`` may legitimately appear on many rows
with different (or repeated) coordinates and city/state values. No
reliable row-level natural key is established during Raw ingestion: this
connector does not treat ``geolocation_zip_code_prefix`` as a unique
key, and it does not invent a composite key (e.g. zip + lat + lng) to
paper over the absence of one. Every observation, including exact
duplicates, is preserved as received.

Downstream Dataform models are responsible for geographic type casting,
coordinate validation, ZIP normalization, city/state standardization,
duplicate analysis, and deciding an appropriate trusted-location grain
(for example, one row per ZIP-code prefix with a representative
coordinate) before this data is safe to join against customers or
sellers. Joining Raw geolocation directly to customer or seller data on
ZIP prefix, without first resolving this many-observations-per-prefix
grain, risks fanning a single customer or seller row out into multiple
rows and inflating downstream metrics. This connector deliberately does
not implement or prescribe that resolution — it belongs to staging and
canonical warehouse design, after profiling the real source.

A future API-based or alternate geographic reference source can be
added as a separate connector that reuses Mercury's shared connector
lifecycle unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import final

from mercury_ingestion.common.storage import LocalStorageManager
from mercury_ingestion.connectors.csv_base import BaseCsvConnector

REQUIRED_COLUMNS = frozenset(
    {
        "geolocation_zip_code_prefix",
        "geolocation_lat",
        "geolocation_lng",
        "geolocation_city",
        "geolocation_state",
    }
)


@final
class GeolocationConnector(BaseCsvConnector):
    """Ingests Nova Commerce's geolocation CSV (Olist-backed, local file).

    Grain: one row per geographic observation associated with a ZIP-code
    prefix — a given ``geolocation_zip_code_prefix`` is expected to
    repeat across many rows with different or identical coordinates. No
    reliable row-level natural key is established during Raw ingestion;
    this connector neither treats ``geolocation_zip_code_prefix`` as
    unique nor invents a synthetic composite key.

    This connector performs technical, structural validation only — it
    confirms the file is readable, correctly typed, and has the columns
    downstream layers depend on. It does not judge the quality of the
    geographic data itself. In particular it does not: reject repeated
    or duplicate rows, validate latitude/longitude ranges or numeric
    formatting, validate ZIP-prefix formatting, reject blank
    ``geolocation_city``/``geolocation_state``, or resolve inconsistent
    city/state values across rows sharing a ZIP prefix. Those checks,
    and the decision of an appropriate trusted-location grain, belong to
    later staging/canonical models, not to raw ingestion.
    """

    SOURCE_SYSTEM = "public_geographic_source"
    SOURCE_OBJECT = "geolocations"

    def __init__(
        self,
        source_file: Path,
        storage_manager: LocalStorageManager,
        schema_version: str | None = "1.0",
    ) -> None:
        super().__init__(
            source_file=source_file,
            source_system=self.SOURCE_SYSTEM,
            source_object=self.SOURCE_OBJECT,
            required_columns=REQUIRED_COLUMNS,
            storage_manager=storage_manager,
            schema_version=schema_version,
        )