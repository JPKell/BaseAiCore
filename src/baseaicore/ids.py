"""Domain module — ULID generation and parsing, with no third-party dependency.

Imports no framework and performs no I/O beyond reading the injected clock.

A ULID is a 128-bit identifier rendered as 26 Crockford base32 characters: 48 bits of millisecond
timestamp followed by 80 bits of randomness. It sorts lexicographically in creation order, which
is what makes it usable as a primary key in the suite's databases without a separate created-at
index, and it is opaque enough to appear in a URL.

This module implements it rather than depending on a ULID library because ``baseaicore`` has zero
third-party runtime dependencies (gold standard G16), and because a shared identifier type that
came from an external package would put that package in every consumer's dependency tree.
"""

from __future__ import annotations

import random
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Protocol

from baseaicore.errors import ValidationError
from baseaicore.timeutil import utc_now

if TYPE_CHECKING:
    from baseaicore.timeutil import Clock

__all__ = ["RandomnessSource", "UlidGenerator", "UlidParts", "new_id", "parse_id"]

# Crockford base32: the digits and uppercase letters, excluding I, L, O and U — I/L/O because they
# are confusable with 1 and 0 when a human transcribes an ID, U to avoid accidental obscenities.
_ALPHABET: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE_MAP: Final = {character: index for index, character in enumerate(_ALPHABET)}
# Two characters per table entry: encoding 10 bits at a time roughly halves the per-ID cost of the
# rendering loop, which is what keeps `new_id()` inside the 2 µs budget in spec §15. 1 024 entries
# is 32 KB of interned strings, built once at import.
_ENCODE_PAIRS: Final = tuple(first + second for first in _ALPHABET for second in _ALPHABET)

_ULID_LENGTH = 26
_TIMESTAMP_CHARS = 10
_RANDOMNESS_BYTES = 10
_TIMESTAMP_BITS = 48
_RANDOMNESS_BITS = 80
_MAX_TIMESTAMP_MS = (1 << _TIMESTAMP_BITS) - 1
_MAX_RANDOMNESS = (1 << _RANDOMNESS_BITS) - 1
_ENCODE_PAIR_COUNT = _ULID_LENGTH // 2


class RandomnessSource(Protocol):
    """The randomness a :class:`UlidGenerator` draws its 80 random bits from.

    Satisfied by :class:`random.SystemRandom` (the default), by :class:`random.Random` seeded for
    a reproducible test, and by anything else offering the same method.
    """

    def randbytes(self, n: int, /) -> bytes:
        """Return ``n`` random bytes."""
        ...


@dataclass(frozen=True, slots=True)
class UlidParts:
    """The decoded components of a ULID.

    A local frozen value type rather than a third-party ULID object: a zero-dependency package
    cannot return a class its consumers would have to install something to name.

    Attributes:
        timestamp: The creation instant, timezone-aware in UTC, to millisecond resolution. This is
            the wall-clock time of the generating machine when the ID was made — it is a label,
            not a measurement, and two IDs from different machines order by their clocks.
        randomness: The 80 random bits, as 10 bytes. Exposed for tests and for collision analysis;
            it carries no meaning.
        text: The canonical 26-character rendering the parts were decoded from.
    """

    timestamp: datetime
    randomness: bytes
    text: str


class UlidGenerator:
    """A thread-safe source of monotonically increasing ULIDs.

    Within a single millisecond the plain ULID specification gives no ordering, because each ID
    gets fresh randomness. This generator instead increments the previous randomness by one when
    the clock has not advanced, so IDs created in a burst still sort in creation order. That
    matters because the suite uses ULIDs as primary keys and reads rows back "in order created" —
    an unordered burst would reorder the events of a single run.

    Thread safety: every call takes an internal lock, so one generator may be shared across
    threads. Two *different* generators make no ordering promise about each other within a
    millisecond; ordering is a property of a generator, not of the ULID format.

    Lifecycle: cheap to construct and safe to discard. Consumers that want reproducible IDs in a
    test construct their own with a frozen clock and a seeded randomness source.
    """

    __slots__ = ("_clock", "_lock", "_previous_ms", "_previous_randomness", "_randomness_source")

    def __init__(
        self,
        *,
        clock: Clock = utc_now,
        randomness_source: RandomnessSource | None = None,
    ) -> None:
        """Build a generator.

        Args:
            clock: Returns the current timezone-aware time. Injected so that monotonicity within a
                millisecond is testable without racing a real clock.
            randomness_source: Where the 80 random bits come from — typically a seeded
                :class:`random.Random` for reproducible tests. Defaults to
                :class:`random.SystemRandom`, which draws from the OS entropy pool. A predictable
                source is acceptable for IDs (they are not secrets) but is never the default,
                because a guessable ID in a URL invites enumeration.
        """
        self._clock: Clock = clock
        self._randomness_source: RandomnessSource = (
            randomness_source if randomness_source is not None else random.SystemRandom()
        )
        self._lock = threading.Lock()
        self._previous_ms: int = -1
        self._previous_randomness: int = 0

    def new_id(self) -> str:
        """Generate the next ULID.

        Returns:
            A 26-character Crockford base32 ULID. Greater than every ID this generator has already
            returned, when compared as a string.

        Raises:
            ValidationError: If the clock reports a time outside the 48-bit millisecond range the
                format can hold (before 1970 or after the year 10889), or if the clock is naive.
        """
        now = self._clock()
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            raise ValidationError(
                "The clock returned a naive datetime; a ULID timestamp must be unambiguous. "
                "Return a timezone-aware UTC datetime, as utc_now() does.",
                details={"field": "clock"},
            )
        timestamp_ms = int(now.timestamp() * 1_000)
        if not 0 <= timestamp_ms <= _MAX_TIMESTAMP_MS:
            # In practice only the lower bound is reachable: the 48-bit field runs to the year
            # 10889, which is past datetime's own maximum. A clock reading before the epoch is
            # reachable, and would produce an ID that sorts before every other one ever made.
            raise ValidationError(
                f"Timestamp {timestamp_ms} ms is outside the 48-bit range a ULID can represent; "
                "it must be at or after 1970-01-01 UTC.",
                details={"timestamp_ms": timestamp_ms},
            )

        with self._lock:
            if timestamp_ms == self._previous_ms:
                randomness = self._previous_randomness + 1
                if randomness > _MAX_RANDOMNESS:
                    # 2**80 IDs inside one millisecond is unreachable; refusing beats wrapping,
                    # which would silently break the ordering guarantee this class exists for.
                    raise ValidationError(
                        "Exhausted the 80-bit randomness space within a single millisecond.",
                        details={"timestamp_ms": timestamp_ms},
                    )
            else:
                randomness = int.from_bytes(
                    self._randomness_source.randbytes(_RANDOMNESS_BYTES), "big"
                )
                self._previous_ms = timestamp_ms
            self._previous_randomness = randomness

        return _encode(timestamp_ms, randomness)


_DEFAULT_GENERATOR: Final = UlidGenerator()
"""The process-wide generator behind :func:`new_id`.

A monotonic generator needs state, and monotonicity is only meaningful per generator, so the
convenience function has to be backed by exactly one. It is created at import and never replaced,
which keeps it within the "process-wide immutable" exception to the no-module-state rule
(``docs/standards/coding-standards.md`` §7). Code that needs a controlled clock or reproducible
randomness constructs its own :class:`UlidGenerator` instead of reaching for this one.
"""


def new_id() -> str:
    """Generate a new ULID from the process-wide generator.

    Returns:
        A 26-character Crockford base32 ULID, sorting after every ID this process has already
        generated.
    """
    return _DEFAULT_GENERATOR.new_id()


def parse_id(value: str) -> UlidParts:
    """Decode a ULID into its timestamp and randomness.

    Only the canonical rendering is accepted: exactly 26 uppercase Crockford base32 characters.
    Lowercase input and Crockford's forgiving letter substitutions (``I``/``L`` → ``1``, ``O`` →
    ``0``) are **rejected** rather than corrected, because IDs in this suite are generated by this
    module and used as database keys — accepting two spellings of one key is how a row gets
    inserted twice.

    Args:
        value: The candidate ULID text.

    Returns:
        The decoded :class:`UlidParts`.

    Raises:
        ValidationError: If the length is wrong, a character is outside the alphabet, or the
            timestamp field overflows 48 bits (which a 26-character string can encode but a ULID
            cannot contain).
    """
    if len(value) != _ULID_LENGTH:
        raise ValidationError(
            f"A ULID is exactly {_ULID_LENGTH} characters; got {len(value)} in {value!r}.",
            details={"field": "value", "value": value, "length": len(value)},
        )
    decoded = 0
    for character in value:
        digit = _DECODE_MAP.get(character)
        if digit is None:
            raise ValidationError(
                f"{character!r} is not a Crockford base32 character (0-9 and A-Z excluding I, L, "
                f"O and U); got {value!r}. Lowercase is not accepted.",
                details={"field": "value", "value": value, "character": character},
            )
        decoded = (decoded << 5) | digit

    timestamp_ms = decoded >> _RANDOMNESS_BITS
    if timestamp_ms > _MAX_TIMESTAMP_MS:
        raise ValidationError(
            f"The timestamp field of {value!r} overflows 48 bits, so it is not a valid ULID.",
            details={"field": "value", "value": value},
        )
    randomness = decoded & _MAX_RANDOMNESS
    return UlidParts(
        timestamp=datetime.fromtimestamp(timestamp_ms / 1_000, tz=UTC),
        randomness=randomness.to_bytes(_RANDOMNESS_BYTES, "big"),
        text=value,
    )


def _encode(timestamp_ms: int, randomness: int) -> str:
    """Render a timestamp and randomness as 26 Crockford base32 characters."""
    value = (timestamp_ms << _RANDOMNESS_BITS) | randomness
    # 13 pairs of characters cover 130 bits; the value occupies the low 128, so the leading pair's
    # top two bits are always zero and the rendering is exactly 26 characters.
    pairs = [""] * _ENCODE_PAIR_COUNT
    for position in range(_ENCODE_PAIR_COUNT - 1, -1, -1):
        pairs[position] = _ENCODE_PAIRS[value & 0x3FF]
        value >>= 10
    return "".join(pairs)
