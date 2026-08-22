"""Unit tests for the Unsupported sentinel — ADR-0016's guarantee, asserted."""

from __future__ import annotations

import copy
import pickle
from collections.abc import Callable

import pytest

from baseaicore.measurement import (
    UNSUPPORTED,
    Measurement,
    Unsupported,
    is_supported,
    supported_values,
)

# Every operation that could turn "not measurable" into a real-looking number. Each is expressed
# as a callable so the failure message names the idiom that would have produced the bad value.
REFUSED_OPERATIONS: list[tuple[str, Callable[[Unsupported], object]]] = [
    ("bool(x)", bool),
    ("if x:", lambda x: "yes" if x else "no"),
    ("x or 0", lambda x: x or 0),
    ("not x", lambda x: not x),
    ("int(x)", int),
    ("float(x)", float),
    ("complex(x)", complex),
    ("round(x)", round),
    ("[0][x]", lambda x: [0][x]),
    ("x + 1", lambda x: x + 1),
    ("1 + x", lambda x: 1 + x),
    ("x - 1", lambda x: x - 1),
    ("1 - x", lambda x: 1 - x),
    ("x * 2", lambda x: x * 2),
    ("2 * x", lambda x: 2 * x),
    ("x / 2", lambda x: x / 2),
    ("2 / x", lambda x: 2 / x),
    ("x // 2", lambda x: x // 2),
    ("2 // x", lambda x: 2 // x),
    ("x % 2", lambda x: x % 2),
    ("2 % x", lambda x: 2 % x),
    ("x ** 2", lambda x: x**2),
    ("2 ** x", lambda x: 2**x),
    ("-x", lambda x: -x),
    ("+x", lambda x: +x),
    ("abs(x)", abs),
    ("x < 1", lambda x: x < 1),
    ("x <= 1", lambda x: x <= 1),
    ("x > 1", lambda x: x > 1),
    ("x >= 1", lambda x: x >= 1),
    ("1 < x", lambda x: 1 < x),  # noqa: SIM300 — the reflected operator is the point
    ("1 >= x", lambda x: 1 >= x),  # noqa: SIM300 — the reflected operator is the point
    ("sum([x])", lambda x: sum([x])),
    # A list holding both a number and the sentinel is exactly what a caller building an
    # aggregate has, and what the type checker is right to object to before runtime does.
    ("max([1, x])", lambda x: max([1, x])),  # type: ignore[type-var]  # mixing is the point
    ("sorted([1, x])", lambda x: sorted([1, x])),  # type: ignore[type-var]  # same
]


@pytest.mark.parametrize(
    ("idiom", "operation"), REFUSED_OPERATIONS, ids=[idiom for idiom, _ in REFUSED_OPERATIONS]
)
def test_every_numeric_and_truthiness_operation_raises(
    idiom: str, operation: Callable[[Unsupported], object]
) -> None:
    with pytest.raises(TypeError, match="UNSUPPORTED is not a number"):
        operation(UNSUPPORTED)
    assert idiom  # the id in the failure message is the point of the parameter


def test_the_error_message_names_the_safe_alternative() -> None:
    with pytest.raises(TypeError) as caught:
        bool(UNSUPPORTED)

    assert "is_supported(value)" in str(caught.value)
    assert "ADR-0016" in str(caught.value)


def test_equality_is_identity_based_and_does_not_raise() -> None:
    assert UNSUPPORTED == UNSUPPORTED  # noqa: PLR0124 — reflexivity is exactly what is asserted
    # mypy is right that these never overlap; asserting it is how we know the runtime agrees
    # rather than raising, which is what makes the sentinel usable inside a frozen dataclass.
    assert UNSUPPORTED != 0  # type: ignore[comparison-overlap]  # the non-overlap is the point
    assert UNSUPPORTED != None  # noqa: E711 — `is not None` is not the test  # type: ignore[comparison-overlap]
    assert (UNSUPPORTED == 0.0) is False  # type: ignore[comparison-overlap]  # as above


def test_it_is_hashable_so_value_objects_containing_it_can_be() -> None:
    assert hash(UNSUPPORTED) == hash(Unsupported())
    assert len({UNSUPPORTED, Unsupported(), UNSUPPORTED}) == 1


def test_construction_returns_the_one_singleton() -> None:
    assert Unsupported() is UNSUPPORTED
    assert Unsupported() is Unsupported()


@pytest.mark.parametrize(
    "round_trip",
    [
        copy.copy,
        copy.deepcopy,
        lambda value: pickle.loads(pickle.dumps(value)),  # noqa: S301 — our own bytes, not input
    ],
    ids=["copy", "deepcopy", "pickle"],
)
def test_the_singleton_survives_copying_as_the_same_object(
    round_trip: Callable[[Unsupported], Unsupported],
) -> None:
    assert round_trip(UNSUPPORTED) is UNSUPPORTED


def test_repr_is_the_name_it_is_imported_under() -> None:
    assert repr(UNSUPPORTED) == "UNSUPPORTED"


def test_str_is_the_suite_wide_serialized_form() -> None:
    assert str(UNSUPPORTED) == "unsupported"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, True), (0.0, True), (-1, True), (1.5, True), (UNSUPPORTED, False)],
)
def test_is_supported_distinguishes_a_real_number_from_the_sentinel(
    value: Measurement, expected: bool
) -> None:
    assert is_supported(value) is expected


def test_supported_values_filters_and_preserves_order() -> None:
    assert supported_values([3, UNSUPPORTED, 1, UNSUPPORTED, 2.5]) == [3, 1, 2.5]


def test_supported_values_of_all_unsupported_is_empty_not_zero() -> None:
    # An empty result is the caller's signal that the metric is unsupported, not that it is zero.
    assert supported_values([UNSUPPORTED, UNSUPPORTED]) == []


def test_supported_values_keeps_a_genuine_zero() -> None:
    # A measured zero is real data and must survive the filter that removes absent ones.
    assert supported_values([0, UNSUPPORTED]) == [0]
