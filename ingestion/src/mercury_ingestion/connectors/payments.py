"""Mercury's sixth concrete ingestion connector: payments.

This module implements the local, Olist-backed extraction of Nova
Commerce's payment-processing source, under the ``payment_platform``
source system. Its CSV-specific technical validation and record
counting are inherited from ``BaseCsvConnector`` (per ADR-005); this
module supplies only the source identity, required schema, and domain
documentation for the payments source.

Dataset grain: one row represents one payment record associated with an
order. A single order may have more than one payment record (e.g. a
voucher plus a credit-card payment on the same order), so repeated
``order_id`` values are expected. The expected source-level composite
key is ``(order_id, payment_sequential)``. This connector does not
validate that key's uniqueness — composite-key uniqueness, numeric type
casting, payment-value assertions, payment-type validation, installment
validation, reconciliation to order-level totals, and canonical payment
modelling are all downstream Dataform staging concerns, not raw
ingestion concerns.

A future API-based payment source (or a different file format) can be
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
        "order_id",
        "payment_sequential",
        "payment_type",
        "payment_installments",
        "payment_value",
    }
)


@final
class PaymentsConnector(BaseCsvConnector):
    """Ingests Nova Commerce's order-payments CSV (Olist-backed, local file).

    Grain: one row per payment record associated with an order. One
    order may have multiple payment records, so ``order_id`` is expected
    to repeat across rows. The expected source key is
    ``(order_id, payment_sequential)`` — this connector does not
    validate its uniqueness.

    This connector performs technical, structural validation only — it
    confirms the file is readable, correctly typed, and has the columns
    downstream layers depend on. It does not judge the quality of the
    business data itself. In particular it does not: reject negative or
    zero ``payment_value``, reject an unexpected or blank
    ``payment_type``, reject zero, negative, or blank
    ``payment_installments``, validate uniqueness of
    ``(order_id, payment_sequential)``, or reconcile payment totals
    against order-level values. Those checks belong to later
    staging/canonical models, not to raw ingestion.
    """

    SOURCE_SYSTEM = "payment_platform"
    SOURCE_OBJECT = "payments"

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