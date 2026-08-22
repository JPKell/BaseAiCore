"""Unit tests for exact money (ADR-0030, sections 2 and 3)."""

from __future__ import annotations

import copy
import pickle
from decimal import Decimal
from typing import Any

import pytest

from baseaicore.errors import ValidationError
from baseaicore.money import NANOS_PER_UNIT, Money, normalize_currency

USD = "USD"


# ---- Currency codes -------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("supplied", "expected"),
    [("USD", "USD"), ("usd", "USD"), ("  eur  ", "EUR"), ("gBp", "GBP")],
    ids=["already normal", "lowercase", "whitespace", "mixed case"],
)
def test_normalize_currency_uppercases_a_three_letter_code(supplied: str, expected: str) -> None:
    assert normalize_currency(supplied) == expected


@pytest.mark.parametrize(
    "supplied",
    ["", "US", "USDD", "$", "dollars", "US1", "US ", "€", "  "],
    ids=[
        "empty",
        "too short",
        "too long",
        "symbol",
        "name",
        "digit",
        "letter and space",
        "non-ascii symbol",
        "whitespace only",
    ],
)
def test_normalize_currency_refuses_anything_that_is_not_a_code(supplied: str) -> None:
    with pytest.raises(ValidationError, match="ISO 4217"):
        normalize_currency(supplied)


def test_a_currency_that_is_three_letters_is_accepted_without_a_code_list() -> None:
    # Shape only, deliberately: the ISO 4217 list changes, and a snapshot compiled into a
    # zero-dependency package would reject a legitimate currency the day after a release.
    assert normalize_currency("xyz") == "XYZ"


# ---- Construction ---------------------------------------------------------------------------
def test_money_normalizes_its_currency_on_construction() -> None:
    assert Money("usd", 5).currency == USD


def test_a_currency_unit_is_a_billion_nanos() -> None:
    assert Money.from_decimal(USD, "1.00").nanos == NANOS_PER_UNIT


def test_money_may_be_negative_because_a_credit_is_a_real_amount() -> None:
    assert Money(USD, -5).nanos == -5


@pytest.mark.parametrize(
    "nanos", [1.5, 1.0, "5", None, True], ids=["float", "whole float", "str", "none", "bool"]
)
def test_non_integer_nanos_are_refused(nanos: Any) -> None:
    # Accepting a float here would reintroduce exactly the imprecision the type exists to remove.
    with pytest.raises(ValidationError, match="whole number of nanos"):
        Money(USD, nanos)


# ---- from_decimal / to_decimal --------------------------------------------------------------
@pytest.mark.parametrize(
    ("amount", "expected_nanos"),
    [
        (Decimal("3.00"), 3_000_000_000),
        ("3.00", 3_000_000_000),
        (3, 3_000_000_000),
        (Decimal("0.000000001"), 1),
        (Decimal("-1.5"), -1_500_000_000),
        (Decimal("0"), 0),
        (Decimal("0.019"), 19_000_000),
    ],
    ids=["decimal", "string", "int", "one nano", "negative", "zero", "cheap rate"],
)
def test_from_decimal_converts_exactly(amount: Any, expected_nanos: int) -> None:
    assert Money.from_decimal(USD, amount).nanos == expected_nanos


@pytest.mark.parametrize(
    ("amount", "expected_nanos"),
    [
        (Decimal("0.0000000005"), 0),  # ties to even: 0.5 -> 0
        (Decimal("0.0000000015"), 2),  # ties to even: 1.5 -> 2
        (Decimal("0.0000000025"), 2),  # ties to even: 2.5 -> 2
        (Decimal("0.0000000006"), 1),  # above the half rounds up
        (Decimal("0.0000000004"), 0),  # below the half rounds down
    ],
    ids=["half to even down", "half to even up", "half to even stays", "above half", "below half"],
)
def test_from_decimal_rounds_half_to_even(amount: Decimal, expected_nanos: int) -> None:
    # Half-up would bias every sum of thousands of costs upward.
    assert Money.from_decimal(USD, amount).nanos == expected_nanos


def test_from_decimal_refuses_a_float() -> None:
    # 0.07 is not 0.07; refusing at the parse boundary is the last point the error is avoidable.
    with pytest.raises(ValidationError, match="refuses float input"):
        Money.from_decimal(USD, 0.07)  # type: ignore[arg-type]  # the refusal is the contract


@pytest.mark.parametrize("amount", ["not a number", "1.2.3"], ids=["prose", "malformed"])
def test_from_decimal_refuses_an_unparsable_amount(amount: str) -> None:
    with pytest.raises(ValidationError, match="parsable decimal"):
        Money.from_decimal(USD, amount)


@pytest.mark.parametrize("amount", ["nan", "inf", "-inf"], ids=["nan", "inf", "-inf"])
def test_from_decimal_refuses_non_finite_amounts(amount: str) -> None:
    with pytest.raises(ValidationError, match="finite"):
        Money.from_decimal(USD, amount)


def test_decimal_round_trips_exactly() -> None:
    amount = Decimal("12.345678901")

    assert Money.from_decimal(USD, amount).to_decimal() == amount


def test_to_decimal_is_in_whole_currency_units() -> None:
    assert Money(USD, 3_000_000_000).to_decimal() == Decimal(3)


def test_zero_is_a_real_amount_not_an_absent_one() -> None:
    # "This cost nothing" is a different statement from "the price is unknown"; only the first
    # one is a Money.
    assert Money.zero("eur") == Money("EUR", 0)


# ---- Arithmetic -----------------------------------------------------------------------------
def test_addition_and_subtraction_are_exact() -> None:
    assert Money(USD, 7) + Money(USD, 5) == Money(USD, 12)
    assert Money(USD, 7) - Money(USD, 12) == Money(USD, -5)


def test_summing_a_tenth_ten_times_is_exactly_one() -> None:
    # The float version of this assertion is false, which is why nanos exist.
    tenth = Money.from_decimal(USD, "0.1")

    total = Money.zero(USD)
    for _ in range(10):
        total = total + tenth

    assert total == Money.from_decimal(USD, "1.00")


def test_multiplication_by_a_whole_count() -> None:
    assert Money(USD, 7) * 3 == Money(USD, 21)
    assert 3 * Money(USD, 7) == Money(USD, 21)


@pytest.mark.parametrize(
    "count", [1.5, 2.0, "3", None], ids=["fraction", "whole float", "str", "none"]
)
def test_multiplication_by_anything_but_a_whole_count_is_refused(count: Any) -> None:
    # Scaling by a fraction is a rate calculation, and rate calculations state their rounding.
    with pytest.raises(ValidationError, match="whole count"):
        Money(USD, 7) * count


def test_negation() -> None:
    assert -Money(USD, 7) == Money(USD, -7)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [(1, 2, True), (2, 1, False), (2, 2, False)],
    ids=["less", "greater", "equal"],
)
def test_strict_ordering_within_one_currency(left: int, right: int, expected: bool) -> None:
    assert (Money(USD, left) < Money(USD, right)) is expected
    assert (Money(USD, left) >= Money(USD, right)) is not expected


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [(1, 2, True), (2, 1, False), (2, 2, True)],
    ids=["less", "greater", "equal"],
)
def test_inclusive_ordering_within_one_currency(left: int, right: int, expected: bool) -> None:
    assert (Money(USD, left) <= Money(USD, right)) is expected
    assert (Money(USD, left) > Money(USD, right)) is not expected


def test_amounts_sort() -> None:
    amounts = [Money(USD, 3), Money(USD, 1), Money(USD, 2)]

    assert sorted(amounts) == [Money(USD, 1), Money(USD, 2), Money(USD, 3)]


def test_min_picks_the_cheaper_amount() -> None:
    assert min(Money(USD, 5), Money(USD, 3)) == Money(USD, 3)


# ---- Cross-currency refusal (ADR-0030 §3) ---------------------------------------------------
CROSS_CURRENCY_OPERATIONS = [
    ("add", lambda a, b: a + b),
    ("subtract", lambda a, b: a - b),
    ("less than", lambda a, b: a < b),
    ("less or equal", lambda a, b: a <= b),
    ("greater than", lambda a, b: a > b),
    ("greater or equal", lambda a, b: a >= b),
]


CROSS_CURRENCY_IDS = [name for name, _ in CROSS_CURRENCY_OPERATIONS]


@pytest.mark.parametrize(("name", "operation"), CROSS_CURRENCY_OPERATIONS, ids=CROSS_CURRENCY_IDS)
def test_every_operator_refuses_to_cross_currencies(name: str, operation: Any) -> None:
    # Converting needs an exchange rate: time-varying external data this layer will not assume.
    with pytest.raises(ValidationError, match="exchange rate"):
        operation(Money(USD, 1), Money("EUR", 1))
    assert name


def test_the_cross_currency_message_names_both_currencies() -> None:
    with pytest.raises(ValidationError) as caught:
        Money(USD, 1) + Money("EUR", 1)

    assert caught.value.details["currency"] == USD
    assert caught.value.details["other_currency"] == "EUR"


@pytest.mark.parametrize(("name", "operation"), CROSS_CURRENCY_OPERATIONS, ids=CROSS_CURRENCY_IDS)
def test_every_operator_refuses_a_non_money_operand(name: str, operation: Any) -> None:
    with pytest.raises(ValidationError, match="must be Money"):
        operation(Money(USD, 1), 5)
    assert name


def test_equality_across_currencies_is_false_rather_than_an_error() -> None:
    # Equality cannot fabricate a number, so it stays total; only the operators that would need a
    # conversion refuse.
    assert Money(USD, 1) != Money("EUR", 1)


# ---- Representation and identity ------------------------------------------------------------
@pytest.mark.parametrize(
    ("money", "expected"),
    [
        (Money(USD, 3_000_000_000), "3.0 USD"),
        (Money(USD, 250), "0.00000025 USD"),
        (Money(USD, 0), "0.0 USD"),
        (Money("EUR", -1_500_000_000), "-1.5 EUR"),
    ],
    ids=["whole", "tiny", "zero", "negative"],
)
def test_str_shows_the_amount_and_its_currency(money: Money, expected: str) -> None:
    assert str(money) == expected


def test_as_canonical_is_the_stable_mapping_form() -> None:
    assert Money(USD, 250).as_canonical() == {"currency": USD, "nanos": 250}


def test_money_is_hashable_and_frozen() -> None:
    amount = Money(USD, 5)

    assert {amount: "x"}[Money(USD, 5)] == "x"
    with pytest.raises((AttributeError, TypeError)):
        amount.nanos = 6  # type: ignore[misc]  # proving the refusal


@pytest.mark.parametrize(
    "round_trip",
    [copy.copy, copy.deepcopy, lambda v: pickle.loads(pickle.dumps(v))],  # noqa: S301 — our bytes
    ids=["copy", "deepcopy", "pickle"],
)
def test_money_round_trips_equal(round_trip: Any) -> None:
    assert round_trip(Money(USD, 250)) == Money(USD, 250)
