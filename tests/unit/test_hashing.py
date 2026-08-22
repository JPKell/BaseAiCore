"""Unit tests for canonical JSON and the hash every fingerprint is built from (gold standard G8)."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

import pytest

from baseaicore.errors import ValidationError
from baseaicore.hashing import canonical_json, sha256_of
from baseaicore.measurement import UNSUPPORTED


class _Colour(StrEnum):
    RED = "red"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"b": 1, "a": 2}, '{"a":2,"b":1}'),
        ({"a": {"z": 1, "y": 2}}, '{"a":{"y":2,"z":1}}'),
        ([3, 1, 2], "[3,1,2]"),
        ((3, 1, 2), "[3,1,2]"),
        ("héllo", '"héllo"'),
        ({"k": None}, '{"k":null}'),
        ({"k": True}, '{"k":true}'),
        ({"k": 1}, '{"k":1}'),
        ({"k": 1.5}, '{"k":1.5}'),
        ({"k": -0.0}, '{"k":0.0}'),
        ({"k": UNSUPPORTED}, '{"k":"unsupported"}'),
        ({"k": _Colour.RED}, '{"k":"red"}'),
        (
            {"k": datetime(2026, 8, 22, 14, 3, 11, 250_000, tzinfo=UTC)},
            '{"k":"2026-08-22T14:03:11.250Z"}',
        ),
    ],
    ids=[
        "keys sorted",
        "nested keys sorted",
        "list order preserved",
        "tuple becomes list",
        "non-ascii kept as-is",
        "none",
        "bool",
        "int",
        "float",
        "negative zero normalized",
        "unsupported sentinel",
        "enum uses its value",
        "datetime is rfc 3339",
    ],
)
def test_canonical_json_produces_the_documented_form(value: Any, expected: str) -> None:
    assert canonical_json(value) == expected


def test_list_order_is_meaning_and_is_never_sorted() -> None:
    # A caller that wants order-independence sorts before calling; doing it here would silently
    # equate two different GPU orderings, two different message sequences, two different anything.
    assert canonical_json([1, 2]) != canonical_json([2, 1])


def test_output_is_byte_identical_across_repeats() -> None:
    value = {"z": [1, {"b": UNSUPPORTED, "a": 2.5}], "a": "é", "n": None}

    assert len({canonical_json(value) for _ in range(50)}) == 1


def test_output_is_byte_identical_across_processes() -> None:
    # Dict iteration order and hash randomization differ per process; a fingerprint that depended
    # on either would be unusable as a cross-machine key.
    program = (
        "from baseaicore.hashing import canonical_json;"
        "from baseaicore.measurement import UNSUPPORTED;"
        "print(canonical_json({'z': 1, 'a': {'d': 4, 'c': UNSUPPORTED}, 'm': [1, 2.5]}))"
    )
    expected = canonical_json({"z": 1, "a": {"d": 4, "c": UNSUPPORTED}, "m": [1, 2.5]})

    results = {
        subprocess.run(  # noqa: S603 — our own interpreter, no shell, literal argument list
            [sys.executable, "-c", program], capture_output=True, text=True, check=True
        ).stdout.strip()
        for _ in range(3)
    }

    assert results == {expected}


def test_int_and_float_are_not_conflated() -> None:
    assert canonical_json(1) == "1"
    assert canonical_json(1.0) == "1.0"


@pytest.mark.parametrize(
    "value",
    [0.1, 1e-9, 1e300, 3.141592653589793, 1 / 3],
    ids=["tenth", "tiny", "huge", "pi", "repeating"],
)
def test_float_formatting_round_trips_exactly(value: float) -> None:
    # Python's repr is the shortest string that round-trips, and it is platform-stable.
    assert float(canonical_json(value)) == value


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "-inf"]
)
def test_non_finite_floats_are_refused(value: float) -> None:
    # They are not JSON, and a nan reaching a hash is a measurement that was never taken.
    with pytest.raises(ValidationError, match="non-finite"):
        canonical_json(value)


def test_decimal_is_refused_with_a_reason() -> None:
    # Decimal("3.0") and Decimal("3.00") are equal but serialize differently, so the hash would
    # depend on how the value was typed (ADR-0030).
    with pytest.raises(ValidationError, match="Decimal is not canonicalizable"):
        canonical_json(Decimal("3.00"))


@pytest.mark.parametrize(
    "value",
    [{"k"}, frozenset({"k"}), complex(1, 2), object()],
    ids=["set", "frozenset", "complex", "arbitrary object"],
)
def test_unserializable_types_are_refused(value: Any) -> None:
    with pytest.raises(ValidationError, match="Cannot canonicalize"):
        canonical_json(value)


@pytest.mark.parametrize(
    "value",
    [b"bytes", bytearray(b"bytes"), memoryview(b"bytes")],
    ids=["bytes", "bytearray", "memoryview"],
)
def test_raw_bytes_are_refused_rather_than_serialized_as_a_list_of_integers(value: Any) -> None:
    # bytes is a Sequence; without an explicit refusal it would quietly become [98, 121, ...].
    with pytest.raises(ValidationError, match="Cannot canonicalize raw bytes"):
        canonical_json(value)


def test_non_string_mapping_keys_are_refused() -> None:
    # json would coerce 1 and "1" to the same key and silently drop one.
    with pytest.raises(ValidationError, match="Mapping keys must be strings"):
        canonical_json({1: "a", "1": "b"})


def test_a_naive_datetime_is_refused() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        canonical_json({"k": datetime(2026, 8, 22)})  # noqa: DTZ001 — the input under test


@pytest.mark.parametrize("build", [list, dict], ids=["list cycle", "dict cycle"])
def test_a_reference_cycle_is_refused_rather_than_hanging(build: Any) -> None:
    container = build()
    if isinstance(container, list):
        container.append(container)
    else:
        container["self"] = container

    with pytest.raises(ValidationError, match="reference cycle"):
        canonical_json(container)


def test_a_repeated_but_acyclic_reference_is_fine() -> None:
    shared = {"a": 1}

    assert canonical_json([shared, shared]) == '[{"a":1},{"a":1}]'


def test_a_str_subclass_is_collapsed_to_plain_str() -> None:
    class Name(str):
        __slots__ = ()

    assert canonical_json({"k": Name("x")}) == '{"k":"x"}'


# ---- sha256_of ------------------------------------------------------------------------------
def test_sha256_of_is_the_digest_of_the_canonical_json() -> None:
    value = {"b": 1, "a": UNSUPPORTED}

    assert sha256_of(value) == hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def test_sha256_of_is_sixty_four_lowercase_hex_characters() -> None:
    digest = sha256_of({"a": 1})

    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")


def test_equal_structures_hash_equal_regardless_of_key_order() -> None:
    assert sha256_of({"a": 1, "b": 2}) == sha256_of({"b": 2, "a": 1})


def test_different_structures_hash_differently() -> None:
    assert sha256_of({"a": 1}) != sha256_of({"a": 2})


def test_unsupported_and_zero_hash_differently() -> None:
    # The whole point of ADR-0016, restated at the hashing layer.
    assert sha256_of({"a": UNSUPPORTED}) != sha256_of({"a": 0})
    assert sha256_of({"a": UNSUPPORTED}) != sha256_of({"a": None})
