"""Unit tests for timestamps, RFC 3339 formatting and duration helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from baseaicore.errors import ValidationError
from baseaicore.timeutil import (
    elapsed_ms,
    from_rfc3339,
    monotonic_ns,
    to_rfc3339,
    utc_now,
)

INSTANT = datetime(2026, 8, 22, 14, 3, 11, 250_000, tzinfo=UTC)


def test_utc_now_is_timezone_aware_and_in_utc() -> None:
    # The one place in this package that reads the wall clock; everything else takes a Clock.
    now = utc_now()

    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (INSTANT, "2026-08-22T14:03:11.250Z"),
        (datetime(2026, 1, 1, tzinfo=UTC), "2026-01-01T00:00:00.000Z"),
        (datetime(2026, 8, 22, 14, 3, 11, 250_999, tzinfo=UTC), "2026-08-22T14:03:11.250Z"),
        (datetime(2026, 8, 22, 14, 3, 11, 999_999, tzinfo=UTC), "2026-08-22T14:03:11.999Z"),
        (
            datetime(2026, 8, 22, 16, 3, 11, tzinfo=timezone(timedelta(hours=2))),
            "2026-08-22T14:03:11.000Z",
        ),
    ],
    ids=[
        "milliseconds",
        "midnight",
        "truncates below ms",
        "just under a second",
        "converts offset",
    ],
)
def test_to_rfc3339_always_emits_millisecond_precision_with_z(
    value: datetime, expected: str
) -> None:
    # Fixed precision, not "whatever the platform gives": these strings are hashed and compared
    # byte for byte across machines.
    assert to_rfc3339(value) == expected


def test_to_rfc3339_rejects_a_naive_datetime() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        to_rfc3339(datetime(2026, 8, 22, 14, 3, 11))  # noqa: DTZ001 — the input under test


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-08-22T14:03:11.250Z", INSTANT),
        ("2026-08-22T14:03:11.250+00:00", INSTANT),
        ("2026-08-22T16:03:11.250+02:00", INSTANT),
        ("2026-08-22T09:03:11.250-05:00", INSTANT),
        ("2026-08-22T14:03:11Z", datetime(2026, 8, 22, 14, 3, 11, tzinfo=UTC)),
    ],
    ids=["trailing Z", "zero offset", "positive offset", "negative offset", "no fraction"],
)
def test_from_rfc3339_parses_and_normalizes_to_utc(text: str, expected: datetime) -> None:
    parsed = from_rfc3339(text)

    assert parsed == expected
    assert parsed.tzinfo is UTC


@pytest.mark.parametrize(
    "text",
    ["2026-08-22T14:03:11.250", "2026-08-22", "2026-08-22 14:03:11"],
    ids=["no offset", "date only", "space separator, no offset"],
)
def test_from_rfc3339_rejects_input_without_an_offset(text: str) -> None:
    # Assuming UTC would be wrong exactly on the machines that are not in UTC.
    with pytest.raises(ValidationError, match="offset"):
        from_rfc3339(text)


@pytest.mark.parametrize(
    "text", ["", "not a timestamp", "2026-13-01T00:00:00Z"], ids=["empty", "prose", "month 13"]
)
def test_from_rfc3339_rejects_unparsable_input(text: str) -> None:
    with pytest.raises(ValidationError, match="RFC 3339"):
        from_rfc3339(text)


def test_a_timestamp_round_trips_through_both_directions() -> None:
    assert from_rfc3339(to_rfc3339(INSTANT)) == INSTANT


def test_monotonic_readings_never_go_backwards() -> None:
    readings = [monotonic_ns() for _ in range(100)]

    assert readings == sorted(readings)


@pytest.mark.parametrize(
    ("start_ns", "end_ns", "expected"),
    [(0, 1_000_000, 1.0), (0, 1_500_000, 1.5), (0, 0, 0.0), (0, 1_000, 0.001), (5, 5, 0.0)],
    ids=["one ms", "fractional ms", "no time", "sub-millisecond", "same reading"],
)
def test_elapsed_ms_converts_nanoseconds_to_milliseconds(
    start_ns: int, end_ns: int, expected: float
) -> None:
    # Fractional milliseconds are kept: a sub-millisecond operation took a nonzero time, and
    # rounding it to 0 would be the same lie the suite refuses elsewhere.
    assert elapsed_ms(start_ns, end_ns) == expected


def test_elapsed_ms_defaults_its_end_to_now() -> None:
    assert elapsed_ms(monotonic_ns()) >= 0.0


def test_elapsed_ms_refuses_readings_that_run_backwards() -> None:
    with pytest.raises(ValidationError, match="precedes start reading"):
        elapsed_ms(1_000_000, 0)
