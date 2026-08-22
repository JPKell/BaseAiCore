"""Domain module — exact money in a named currency.

Imports no framework and performs no I/O.

Money here is an exact integer count of **nanos** — billionths of one currency unit — never a
float. Token prices are quoted per million tokens and run to tiny fractions of a currency unit
(``$0.019`` per million tokens is 19 nanos per token), and floats neither sum associatively nor
compare reliably at that scale. A cost column that disagrees with the sum of its own rows is the
same class of defect as a fabricated measurement
([ADR-0030](../../docs/adr/0030-model-cost-and-pricing.md) §2).

There is no currency conversion in this module and there never will be: converting requires an
exchange rate, which is time-varying external data outside the user's control. Every cross-
currency operation raises instead (ADR-0030 §3).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any, Final

from baseaicore.errors import ValidationError

__all__ = ["NANOS_PER_UNIT", "Money", "normalize_currency"]

NANOS_PER_UNIT: Final = 1_000_000_000
"""Nanos in one currency unit. ``Money("USD", NANOS_PER_UNIT)`` is one US dollar."""

_CURRENCY_CODE_LENGTH = 3


def normalize_currency(value: str) -> str:
    """Normalize a currency code to ISO 4217 alpha-3 form.

    Only the *shape* is validated — three ASCII letters, uppercased. The ISO 4217 code list itself
    changes over time (codes are added, withdrawn and reused), and compiling a snapshot of it into
    a zero-dependency domain package would ship a list that silently rejects a legitimate currency
    the day after a release. Shape validation catches the realistic errors — a symbol, a name, a
    typo, an empty string — without pretending to know every code in the world.

    Args:
        value: A currency code in any case, with or without surrounding whitespace.

    Returns:
        The uppercased three-letter code.

    Raises:
        ValidationError: If the value is not exactly three ASCII letters.
    """
    candidate = value.strip().upper()
    is_alpha3 = (
        len(candidate) == _CURRENCY_CODE_LENGTH and candidate.isascii() and candidate.isalpha()
    )
    if not is_alpha3:
        raise ValidationError(
            f"Currency must be an ISO 4217 alpha-3 code such as 'USD' or 'EUR'; got {value!r}. "
            "Symbols ('$'), names ('dollars') and empty strings are not codes.",
            details={"field": "currency", "value": value},
        )
    return candidate


@dataclass(frozen=True, slots=True, order=False)
class Money:
    """An exact amount in one currency, stored as whole nanos.

    Invariants:
        * ``currency`` is a normalized alpha-3 code (see :func:`normalize_currency`).
        * ``nanos`` is an ``int``. It may be negative — a credit, a refund or a difference is a
          legitimate amount — even though a *price* may not be (:class:`~baseaicore.cost.TokenRates`
          enforces that separately, because the constraint belongs to prices, not to money).

    Arithmetic is exact and closed within one currency. ``+`` and ``-`` take another
    :class:`Money`, ``*`` takes a whole count, and the ordering operators compare amounts.
    Every one of them raises :class:`~baseaicore.errors.ValidationError` when the currencies
    differ, rather than converting: see the module docstring and ADR-0030 §3.

    Immutable, hashable and safe to share across threads.
    """

    currency: str
    nanos: int

    def __post_init__(self) -> None:
        """Validate and normalize the fields.

        Raises:
            ValidationError: If ``currency`` is not an alpha-3 code, or ``nanos`` is not an
                integer. A float ``nanos`` is refused rather than truncated — accepting it would
                reintroduce exactly the imprecision this type exists to eliminate.
        """
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        if isinstance(self.nanos, bool) or not isinstance(self.nanos, int):
            raise ValidationError(
                f"Money.nanos must be a whole number of nanos (billionths of one currency unit); "
                f"got {self.nanos!r}. Build from a decimal amount with Money.from_decimal().",
                details={"field": "nanos", "value": repr(self.nanos)},
            )

    @classmethod
    def zero(cls, currency: str) -> Money:
        """Return zero in ``currency``.

        A genuine zero — "this cost nothing" — which is a different statement from
        :data:`~baseaicore.measurement.UNSUPPORTED`, "the price is not known here". Use this only
        when the amount really is nothing, such as a token class with a count of zero.

        Args:
            currency: The currency code.

        Returns:
            ``Money(currency, 0)``.
        """
        return cls(currency=currency, nanos=0)

    @classmethod
    def from_decimal(cls, currency: str, amount: Decimal | int | str) -> Money:
        """Build an amount from a decimal figure, rounding to whole nanos.

        This is the parsing boundary: a price read from a provider's documentation, a
        configuration file or a user's input arrives as a decimal figure and becomes exact here.

        Args:
            currency: The currency code.
            amount: The amount in whole currency units — ``Decimal("3.00")`` is three dollars, not
                three nanos. Strings and ints are accepted and converted exactly; a ``float`` is
                refused, because ``0.07`` is not ``0.07`` and the error would be baked in at the
                one point it could still have been avoided.

        Returns:
            The amount, rounded half-to-even to the nearest nano. Sub-nano precision in a price is
            below the resolution of any provider's billing.

        Raises:
            ValidationError: If ``amount`` is a float, is not a parsable decimal, or is not finite.
        """
        if isinstance(amount, float):
            raise ValidationError(
                f"Money.from_decimal refuses float input ({amount!r}): binary floats cannot hold "
                "decimal money exactly. Pass a Decimal or a string, e.g. Decimal('3.00') or "
                "'3.00'.",
                details={"field": "amount", "value": repr(amount)},
            )
        try:
            exact = Decimal(amount)
        except ArithmeticError as exc:
            raise ValidationError(
                f"Not a parsable decimal amount: {amount!r}.",
                details={"field": "amount", "value": repr(amount)},
            ) from exc
        if not exact.is_finite():
            raise ValidationError(
                f"Money amounts must be finite; got {amount!r}.",
                details={"field": "amount", "value": repr(amount)},
            )
        nanos = int((exact * NANOS_PER_UNIT).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
        return cls(currency=currency, nanos=nanos)

    def to_decimal(self) -> Decimal:
        """Return the amount in whole currency units, exactly.

        For display and for handing to something that speaks decimals. It is deliberately *not*
        the stored form: two equal ``Decimal`` values can carry different exponents and therefore
        serialize differently, which would make any hash over a price depend on how the number was
        typed (ADR-0030 "alternatives considered").

        Returns:
            The amount as a :class:`~decimal.Decimal` with nine decimal places.
        """
        return Decimal(self.nanos) / Decimal(NANOS_PER_UNIT)

    def __add__(self, other: Money) -> Money:
        """Return the sum, in the shared currency."""
        self._require_same_currency(other, "add")
        return Money(currency=self.currency, nanos=self.nanos + other.nanos)

    def __sub__(self, other: Money) -> Money:
        """Return the difference, in the shared currency."""
        self._require_same_currency(other, "subtract")
        return Money(currency=self.currency, nanos=self.nanos - other.nanos)

    def __mul__(self, count: int) -> Money:
        """Return this amount repeated ``count`` times.

        Multiplication is by a whole count only — an amount times a fraction is a rate
        calculation, and rate calculations state their own rounding rule
        (:func:`baseaicore.cost.estimate_cost` does).

        Raises:
            ValidationError: If ``count`` is not an integer.
        """
        if isinstance(count, bool) or not isinstance(count, int):
            raise ValidationError(
                f"Money can only be multiplied by a whole count; got {count!r}. Scaling by a "
                "fraction is a rate calculation and must state its rounding rule.",
                details={"field": "count", "value": repr(count)},
            )
        return Money(currency=self.currency, nanos=self.nanos * count)

    __rmul__ = __mul__

    def __neg__(self) -> Money:
        """Return the amount with its sign flipped."""
        return Money(currency=self.currency, nanos=-self.nanos)

    def __lt__(self, other: Money) -> bool:
        """Report whether this amount is less than ``other``, in the shared currency."""
        self._require_same_currency(other, "compare")
        return self.nanos < other.nanos

    def __le__(self, other: Money) -> bool:
        """Report whether this amount is at most ``other``, in the shared currency."""
        self._require_same_currency(other, "compare")
        return self.nanos <= other.nanos

    def __gt__(self, other: Money) -> bool:
        """Report whether this amount is greater than ``other``, in the shared currency."""
        self._require_same_currency(other, "compare")
        return self.nanos > other.nanos

    def __ge__(self, other: Money) -> bool:
        """Report whether this amount is at least ``other``, in the shared currency."""
        self._require_same_currency(other, "compare")
        return self.nanos >= other.nanos

    def __str__(self) -> str:
        """Return the amount and its currency, e.g. ``0.000003 USD``, without trailing zeros."""
        text = f"{self.to_decimal():.9f}".rstrip("0")
        if text.endswith("."):
            text += "0"
        return f"{text} {self.currency}"

    def as_canonical(self) -> dict[str, Any]:
        """Return the mapping form used inside canonical JSON and therefore inside every hash.

        Returns:
            ``{"currency": ..., "nanos": ...}``. Two equal amounts always produce the same mapping,
            which is what :func:`baseaicore.hashing.canonical_json` needs and what a ``Decimal``
            could not guarantee.
        """
        return {"currency": self.currency, "nanos": self.nanos}

    def _require_same_currency(self, other: Money, operation: str) -> None:
        """Raise unless ``other`` is Money in this currency."""
        if not isinstance(other, Money):
            raise ValidationError(
                f"Cannot {operation} {type(other).__name__!r} and Money; the other operand must "
                "be Money in the same currency.",
                details={"operation": operation, "other_type": type(other).__name__},
            )
        if other.currency != self.currency:
            raise ValidationError(
                f"Cannot {operation} {self.currency} and {other.currency}: that needs an exchange "
                "rate, which changes over time and is not something this package will assume. "
                "Convert deliberately, at a rate you obtained and recorded (ADR-0030 §3).",
                details={
                    "operation": operation,
                    "currency": self.currency,
                    "other_currency": other.currency,
                },
            )
