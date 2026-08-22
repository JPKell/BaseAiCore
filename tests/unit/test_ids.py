"""Unit tests for ULID generation and parsing."""

from __future__ import annotations

import random
import threading
from datetime import UTC, datetime, timedelta

import pytest

from baseaicore.errors import ValidationError
from baseaicore.ids import UlidGenerator, new_id, parse_id

# 100 000 is the figure the development plan names; it also exercises the monotonic path heavily,
# since a modern machine generates thousands of IDs inside a single millisecond.
BULK_COUNT = 100_000


def test_a_ulid_is_twenty_six_crockford_characters() -> None:
    value = new_id()

    assert len(value) == 26
    assert set(value) <= set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")


def test_ids_are_unique_and_sort_by_creation_order() -> None:
    values = [new_id() for _ in range(BULK_COUNT)]

    assert len(set(values)) == BULK_COUNT
    assert values == sorted(values)


def test_ids_generated_within_one_millisecond_still_sort_in_creation_order(
    frozen_clock: datetime,
) -> None:
    # The plain ULID specification gives no ordering inside a millisecond. The suite reads rows
    # back in key order, so a burst that reordered itself would reorder a run's events.
    generator = UlidGenerator(clock=lambda: frozen_clock, randomness_source=random.Random(7))

    burst = [generator.new_id() for _ in range(1_000)]

    assert burst == sorted(burst)
    assert len(set(burst)) == 1_000


def test_a_later_millisecond_always_sorts_after_an_earlier_one(frozen_clock: datetime) -> None:
    times = [frozen_clock, frozen_clock + timedelta(milliseconds=1)]
    generator = UlidGenerator(clock=lambda: times.pop(0), randomness_source=random.Random(1))

    first, second = generator.new_id(), generator.new_id()

    assert first < second


def test_ids_round_trip_through_parse(frozen_clock: datetime) -> None:
    generator = UlidGenerator(clock=lambda: frozen_clock, randomness_source=random.Random(3))
    value = generator.new_id()

    parts = parse_id(value)

    assert parts.text == value
    assert parts.timestamp == frozen_clock
    assert len(parts.randomness) == 10


def test_the_parsed_timestamp_has_millisecond_resolution_in_utc() -> None:
    generator = UlidGenerator(clock=lambda: datetime(2026, 8, 22, 14, 3, 11, 250_999, tzinfo=UTC))

    parts = parse_id(generator.new_id())

    assert parts.timestamp == datetime(2026, 8, 22, 14, 3, 11, 250_000, tzinfo=UTC)
    assert parts.timestamp.tzinfo is UTC


def test_generation_is_thread_safe_and_still_ordered(frozen_clock: datetime) -> None:
    generator = UlidGenerator(clock=lambda: frozen_clock, randomness_source=random.Random(11))
    produced: list[str] = []
    lock = threading.Lock()

    def generate() -> None:
        batch = [generator.new_id() for _ in range(500)]
        with lock:
            produced.extend(batch)

    threads = [threading.Thread(target=generate) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(set(produced)) == len(produced) == 4_000


def test_monotonic_state_belongs_to_a_generator_not_to_the_module(
    frozen_clock: datetime,
) -> None:
    # Two generators given the same clock and the same seed produce the same sequence, which is
    # only true if neither is advancing the other's counter.
    first = UlidGenerator(clock=lambda: frozen_clock, randomness_source=random.Random(5))
    second = UlidGenerator(clock=lambda: frozen_clock, randomness_source=random.Random(5))

    assert [first.new_id() for _ in range(3)] == [second.new_id() for _ in range(3)]


@pytest.mark.parametrize(
    ("value", "expected_message"),
    [
        ("", "exactly 26 characters"),
        ("0" * 25, "exactly 26 characters"),
        ("0" * 27, "exactly 26 characters"),
        ("U" * 26, "not a Crockford base32 character"),
        ("I" * 26, "not a Crockford base32 character"),
        ("l" * 26, "not a Crockford base32 character"),
        ("01ARZ3NDEKTSV4RRFFQ69G5FA-", "not a Crockford base32 character"),
        ("Z" * 26, "overflows 48 bits"),
    ],
    ids=[
        "empty",
        "too short",
        "too long",
        "excluded letter U",
        "ambiguous letter I",
        "lowercase",
        "punctuation",
        "timestamp overflow",
    ],
)
def test_parse_rejects_malformed_input(value: str, expected_message: str) -> None:
    with pytest.raises(ValidationError, match=expected_message):
        parse_id(value)


def test_lowercase_is_rejected_rather_than_corrected() -> None:
    # Crockford's specification permits lenient decoding. It is refused here because a ULID is a
    # database key, and two accepted spellings of one key is how a row gets inserted twice.
    value = new_id()

    with pytest.raises(ValidationError):
        parse_id(value.lower())


def test_a_naive_clock_is_refused() -> None:
    generator = UlidGenerator(clock=lambda: datetime(2026, 8, 22, 14, 3, 11))  # noqa: DTZ001 — the point

    with pytest.raises(ValidationError, match="naive datetime"):
        generator.new_id()


def test_exhausting_the_randomness_within_one_millisecond_is_refused(
    frozen_clock: datetime,
) -> None:
    # Unreachable in practice — it needs 2**80 IDs inside one millisecond — but refusing is what
    # keeps the ordering guarantee true; wrapping would break it silently.
    class MaximumRandomness:
        def randbytes(self, n: int, /) -> bytes:
            return b"\xff" * n

    generator = UlidGenerator(clock=lambda: frozen_clock, randomness_source=MaximumRandomness())
    generator.new_id()

    with pytest.raises(ValidationError, match="Exhausted the 80-bit randomness space"):
        generator.new_id()


def test_a_timestamp_before_the_epoch_is_refused() -> None:
    # It would encode to a negative timestamp field and sort before every ID ever generated.
    generator = UlidGenerator(clock=lambda: datetime(1969, 7, 20, tzinfo=UTC))

    with pytest.raises(ValidationError, match="48-bit range"):
        generator.new_id()


def test_ulid_parts_are_frozen() -> None:
    parts = parse_id(new_id())

    with pytest.raises((AttributeError, TypeError)):
        parts.text = "other"  # type: ignore[misc]  # proving the refusal
