"""Structured production event utilities for Mercury.

This module defines Mercury's reusable structured-event envelope.

It deliberately does not perform provider-specific logging. Events are
written as compact JSON lines to a supplied text stream, which allows
the same output to work locally, in automated tests, and in Cloud Run
where standard output is collected by Cloud Logging.

The caller remains responsible for constructing a PII-safe terminal
summary. This module adds controlled event metadata without accepting
or exposing raw exception payloads, source records, credentials, or
other unrestricted runtime data.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, TextIO


EVENT_SCHEMA_VERSION = "1.0"

_RESERVED_EVENT_KEYS: frozenset[str] = frozenset(
    {
        "event_schema_version",
        "event_name",
        "occurred_at",
        "command",
        "stage",
    }
)


def _require_non_blank(
    value: str,
    field_name: str,
) -> None:
    """Require a non-empty event metadata value."""

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


def _format_utc_timestamp(value: datetime) -> str:
    """Return a timezone-aware datetime as an ISO-8601 UTC timestamp."""

    if not isinstance(value, datetime):
        raise TypeError("occurred_at must be a datetime")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("occurred_at must be timezone-aware")

    return (
        value.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_terminal_event(
    *,
    summary: Mapping[str, Any],
    event_name: str,
    command: str,
    stage: str,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Add Mercury's observability envelope to a terminal summary.

    The supplied summary is copied rather than mutated.

    Event metadata is controlled by this function. A caller cannot
    replace reserved envelope fields through the summary mapping.

    Args:
        summary: Existing governed, PII-safe terminal summary.
        event_name: Stable machine-readable event name.
        command: Production command that produced the event.
        stage: Logical execution stage represented by the event.
        occurred_at: Optional timezone-aware event timestamp. The
            current UTC time is used when omitted.

    Returns:
        A new JSON-compatible event dictionary.

    Raises:
        TypeError: If required inputs have invalid types.
        ValueError: If metadata is blank, the timestamp is naive, or
            the summary attempts to override reserved event metadata.
    """

    if not isinstance(summary, Mapping):
        raise TypeError("summary must be a mapping")

    _require_non_blank(event_name, "event_name")
    _require_non_blank(command, "command")
    _require_non_blank(stage, "stage")

    conflicting_keys = _RESERVED_EVENT_KEYS.intersection(summary)

    if conflicting_keys:
        formatted_keys = ", ".join(sorted(conflicting_keys))
        raise ValueError(
            "summary contains reserved event metadata: "
            f"{formatted_keys}"
        )

    event_timestamp = (
        datetime.now(timezone.utc)
        if occurred_at is None
        else occurred_at
    )

    return {
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "event_name": event_name,
        "occurred_at": _format_utc_timestamp(event_timestamp),
        "command": command,
        "stage": stage,
        **dict(summary),
    }


def emit_structured_event(
    event: Mapping[str, Any],
    *,
    stream: TextIO | None = None,
) -> None:
    """Write exactly one compact JSON event line.

    Standard output is used by default so Cloud Run can collect the
    event without a provider-specific logging dependency.
    """

    if not isinstance(event, Mapping):
        raise TypeError("event must be a mapping")

    destination = sys.stdout if stream is None else stream

    destination.write(
        json.dumps(
            dict(event),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    destination.write("\n")
    destination.flush()