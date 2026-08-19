"""Mercury's safe operational-error model (ADR-011 Phase 2).

This module exists to enforce one boundary:

    arbitrary exception
            |
            X  must never cross
            |
    durable / display-safe operational metadata

``IngestionMetadata.error_message`` and ``ReplayStateRecord.error_message``
are both plain ``str | None`` fields, and prior to ADR-011 they were
populated directly from ``str(exc)`` -- an arbitrary upstream exception's
text, which could in principle contain source/customer values (e.g. a
future parser reporting "invalid email jane@example.com at row 42").

This module does not attempt to detect or redact PII inside exception
text. Regex-based scrubbing is not a trust boundary Mercury relies on.
Instead, the principle is structural: arbitrary exception prose is never
accepted into persisted metadata in the first place. Callers construct
an ``OperationalError`` from information *they already know* (which
operation was being attempted, on which component, in which broad
category of failure) and a short, Mercury-authored ``safe_message`` --
never from ``str(exc)`` or ``repr(exc)``. The original exception may
still be used for transient debugging (e.g. via normal Python exception
chaining, ``raise ... from exc``), but it is never copied into the safe
representation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

MAX_OPERATIONAL_ERROR_LENGTH = 512
"""Hard cap on the rendered persisted error string.

Since every persisted string is Mercury-authored (never arbitrary
exception text), truncation should never actually be needed in
practice. This bound exists purely as a defensive backstop, so an
accidentally verbose future ``safe_message`` cannot itself become a
source of unbounded control-plane content.
"""


class OperationalErrorCategory(str, Enum):
    """The broad technical failure location a Mercury operation belongs to.

    Categories are chosen by the calling code based on which known
    operation boundary failed -- never inferred by parsing exception
    text. Keeping this list small and stable is deliberate: it exists to
    make failures classifiable and auditable, not to build a general
    error taxonomy.
    """

    SOURCE_VALIDATION_FAILED = "source_validation_failed"
    RECORD_COUNT_FAILED = "record_count_failed"
    STORAGE_WRITE_FAILED = "storage_write_failed"
    INGESTION_FAILED = "ingestion_failed"
    WAREHOUSE_LOAD_FAILED = "warehouse_load_failed"
    STATE_PERSISTENCE_FAILED = "state_persistence_failed"
    UNEXPECTED_INTERNAL_ERROR = "unexpected_internal_error"


def _require_non_blank(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


@dataclass(frozen=True, slots=True)
class OperationalError:
    """A safe, Mercury-authored description of an operational failure.

    Every field here is supplied by Mercury's own code, describing
    something Mercury already knows (which category of failure, which
    component, which operation) plus a short, hand-authored
    ``safe_message``. Nothing here is, or is derived from, arbitrary
    exception text -- there is deliberately no field for exception
    message, exception repr, or exception args.
    """

    category: OperationalErrorCategory
    component: str
    operation: str
    safe_message: str

    def __post_init__(self) -> None:
        if not isinstance(self.category, OperationalErrorCategory):
            raise TypeError("category must be an OperationalErrorCategory")
        _require_non_blank(self.component, "component")
        _require_non_blank(self.operation, "operation")
        _require_non_blank(self.safe_message, "safe_message")

    def to_safe_string(self) -> str:
        """Render this error as the single bounded string persisted into
        ``IngestionMetadata.error_message`` / ``ReplayStateRecord.error_message``.

        Structured context that already exists as separate fields
        elsewhere (e.g. ``ReplayStateRecord.source_object``,
        ``.delivery_date``, ``.stage``) is deliberately not repeated
        here -- this string only needs to carry what those structured
        fields cannot: the failure category, which component/operation
        it came from, and a short human-readable description.
        """
        rendered = (
            f"category={self.category.value} component={self.component} "
            f"operation={self.operation} message={self.safe_message}"
        )
        return rendered[:MAX_OPERATIONAL_ERROR_LENGTH]