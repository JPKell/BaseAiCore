"""Domain module — timezone-aware timestamps, RFC 3339 formatting, and duration helpers.

Imports no framework and performs no I/O beyond reading the system clock in :func:`utc_now` and
the monotonic counter in :func:`monotonic_ns`.

Two kinds of time live here and are never interchanged
(``docs/standards/coding-standards.md`` §5): a **timestamp** is a timezone-aware
:class:`datetime.datetime` in UTC and answers "when did this happen?"; a **duration** comes from
:func:`time.perf_counter_ns` and answers "how long did it take?". Subtracting two wall-clock
timestamps to time an operation is a defect — the wall clock can step backwards during an NTP
correction, and a benchmark that reports a negative duration is worse than one that reports none.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from baseaicore.errors import ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "Clock",
    "elapsed_ms",
    "from_rfc3339",
    "monotonic_ns",
    "to_rfc3339",
    "utc_now",
]

type Clock = Callable[[], datetime]
"""The injectable clock type used suite-wide.

Domain and service code takes a ``Clock`` parameter defaulting to :func:`utc_now` rather than
calling :func:`datetime.datetime.now` directly, so every time-dependent behaviour is testable
without patching the interpreter (``docs/standards/coding-standards.md`` §5).
"""

_NANOSECONDS_PER_MILLISECOND = 1_000_000


def utc_now() -> datetime:
    """Return the current time as a timezone-aware datetime in UTC.

    Returns:
        The current instant with ``tzinfo`` set to :data:`datetime.UTC`. Never naive: a naive
        datetime crossing a package boundary is ambiguous, and the suite's storage, exports and
        comparisons all assume UTC.
    """
    return datetime.now(UTC)


def to_rfc3339(value: datetime) -> str:
    """Format a timestamp as RFC 3339 with millisecond precision and a trailing ``Z``.

    Millisecond precision is fixed rather than "whatever the platform provides" so that the same
    instant produces the same string on every machine — the strings appear in canonical JSON, in
    hashes and in exported payloads, where a platform-dependent number of digits would break
    byte-for-byte comparison. Sub-millisecond detail belongs in a duration, not a timestamp.

    Args:
        value: A timezone-aware datetime in any timezone; it is converted to UTC first.

    Returns:
        A string of the form ``2026-08-22T14:03:11.250Z``.

    Raises:
        ValidationError: If ``value`` is naive. A naive datetime has no defensible UTC reading,
            and guessing one would silently shift every downstream timestamp by the local offset.
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValidationError(
            "to_rfc3339 requires a timezone-aware datetime; got a naive one. Build it with "
            "utc_now() or attach a timezone with .replace(tzinfo=UTC) if you know it is UTC.",
            details={"field": "value", "expected": "timezone-aware datetime"},
        )
    in_utc = value.astimezone(UTC)
    milliseconds = in_utc.microsecond // 1_000
    return f"{in_utc.strftime('%Y-%m-%dT%H:%M:%S')}.{milliseconds:03d}Z"


def from_rfc3339(text: str) -> datetime:
    """Parse an RFC 3339 timestamp into a timezone-aware datetime in UTC.

    Args:
        text: An RFC 3339 timestamp with an explicit offset or a trailing ``Z``. Any offset is
            accepted and normalized to UTC, so a value written by a client in another timezone
            round-trips to the same instant.

    Returns:
        The instant, with ``tzinfo`` set to :data:`datetime.UTC`.

    Raises:
        ValidationError: If ``text`` is not a parsable timestamp, or if it carries no offset.
            Naive input is rejected rather than assumed to be UTC: the assumption is wrong
            exactly when it matters, on a machine that is not in UTC.
    """
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError(
            f"Not a parsable RFC 3339 timestamp: {text!r}. Expected a form such as "
            "'2026-08-22T14:03:11.250Z'.",
            details={"field": "text", "value": text},
        ) from exc
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise ValidationError(
            f"Timestamp {text!r} carries no UTC offset. Append 'Z' if it is UTC, or the real "
            "offset if it is not — this function will not guess.",
            details={"field": "text", "value": text, "expected": "explicit UTC offset"},
        )
    return parsed.astimezone(UTC)


def monotonic_ns() -> int:
    """Return a monotonic counter reading in nanoseconds, for measuring durations.

    Returns:
        A reading from :func:`time.perf_counter_ns`. It has no meaning on its own — only the
        difference between two readings taken in the same process is defined — and it is immune
        to wall-clock adjustments, which is why every duration in the suite comes from here
        rather than from two :func:`utc_now` calls.
    """
    return time.perf_counter_ns()


def elapsed_ms(start_ns: int, end_ns: int | None = None) -> float:
    """Return the milliseconds elapsed between two :func:`monotonic_ns` readings.

    Args:
        start_ns: The earlier reading.
        end_ns: The later reading. Defaults to a reading taken now.

    Returns:
        The elapsed time in milliseconds, as a float. Fractional milliseconds are preserved —
        a sub-millisecond operation genuinely took a nonzero time, and rounding it to ``0``
        would be the same lie this suite refuses elsewhere.

    Raises:
        ValidationError: If the end reading precedes the start reading, which means the two
            readings did not come from the same monotonic counter and no duration can be derived.
    """
    end = monotonic_ns() if end_ns is None else end_ns
    if end < start_ns:
        raise ValidationError(
            f"End reading {end} precedes start reading {start_ns}. Both must come from "
            "monotonic_ns() in the same process; a wall-clock timestamp cannot be used here.",
            details={"start_ns": start_ns, "end_ns": end},
        )
    return (end - start_ns) / _NANOSECONDS_PER_MILLISECOND
