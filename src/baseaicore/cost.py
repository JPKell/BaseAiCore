"""Domain module — token usage, model pricing observations, and cost estimation.

Imports no framework and performs no I/O: this module defines what a price *is* and how to apply
one, and never goes to find one. There is no bundled price catalogue and no provider lookup —
acquisition belongs to ModelRack and the applications, which record a :class:`PricingSource` when
they hand a record over (ADR-0030).

Three ideas hold this module together, and each exists because model prices move for reasons the
user does not control:

1. **Cost is derived, never stored as the primary fact.** A run stores its :class:`TokenUsage` and
   the :attr:`ModelPricing.pricing_hash` that was applied. When a provider corrects a price, when a
   price list is read for the first time long after a run, or when a costing bug is found, history
   is re-costed from the counts. Had the money figure been the stored fact, the correction would
   have had nowhere to go.
2. **A price is a dated, sourced observation with a window** — not a property of the model. The
   same weights cost different amounts on the batch tier, in another region, under yesterday's
   price list. :class:`ModelPricing` carries all of that, so a figure in a table can always answer
   "from which price, read when, from where, valid over what window?".
3. **An unknown price is** :data:`~baseaicore.measurement.UNSUPPORTED`, **never zero.** A model
   running on the user's own hardware has no token price; it is not free, it costs electricity and
   time that SweatMeter measures and this module does not price. Zeroing it would make it win
   every "cheapest model" comparison in the suite by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from baseaicore.errors import ValidationError
from baseaicore.hashing import sha256_of
from baseaicore.measurement import UNSUPPORTED, Unsupported, is_supported
from baseaicore.money import Money, normalize_currency

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from baseaicore.identity import ModelIdentity

__all__ = [
    "CostEstimate",
    "ModelPricing",
    "PricingSource",
    "TokenCount",
    "TokenRates",
    "TokenUsage",
    "estimate_cost",
]

TOKENS_PER_RATE_UNIT: Final = 1_000_000
"""Prices are quoted per this many tokens, and stored that way rather than pre-divided.

Providers publish "per million tokens"; dividing at storage time would turn an exact quoted figure
into a repeating fraction before anything had been counted (ADR-0030 §2).
"""

_PRICING_HASH_LENGTH = 16

type TokenCount = int | Unsupported
"""A whole number of tokens, or :data:`~baseaicore.measurement.UNSUPPORTED` if none was reported.

The whole-number restriction of :data:`~baseaicore.measurement.Measurement`: there is no such
thing as half a token, and a provider that reports nothing must not be recorded as reporting zero
(ADR-0016).
"""

# The billable token classes, in the order they appear on every type here and in every result.
# One tuple, used by the validators, the hash and the estimator, so a fifth class can never be
# added to one of them and forgotten in another.
_TOKEN_CLASSES: Final = ("input", "output", "cache_write", "cache_read")


class PricingSource(StrEnum):
    """Where a price came from, and therefore how much weight it carries.

    The distinction is not bookkeeping: a rate the provider returned alongside the response and a
    rate somebody copied out of a documentation page six months ago are different epistemic
    objects, and a consumer deciding whether to show a cost — or to route on it — needs to tell
    them apart.
    """

    PROVIDER_RESPONSE = "provider_response"
    """Reported by the provider with the response it applies to. The strongest available."""

    PROVIDER_PUBLISHED = "provider_published"
    """Read from the provider's published price list, which may since have changed."""

    USER_OVERRIDE = "user_override"
    """Supplied by the user — a negotiated rate, or a correction to a published one."""

    CATALOG = "catalog"
    """From a third-party price catalogue. Convenient, unattributable, and often stale."""

    ESTIMATE = "estimate"
    """Inferred rather than observed — a comparable model's price, or an order-of-magnitude guess.
    Anything computed from this is a projection and must be labelled as one wherever it is shown."""


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """The billable token counts of one model call.

    **The four counts are disjoint.** ``input_tokens`` counts only tokens billed at the input
    rate, *excluding* any billed at a cache rate. Providers disagree about this — one reports
    cached tokens inside its prompt-token figure, another reports them beside it — and reconciling
    that is the provider adapter's job in ModelRack, the only layer that knows each provider's
    convention. Storing a provider's raw overlapping figures here would double-bill every cached
    call (ADR-0030 §Consequences).

    Reasoning or "thinking" tokens are not a separate field: every provider that exposes them
    bills them at its output rate, so they belong in ``output_tokens``. A provider that prices
    them separately is a revisit trigger, not a field to add speculatively.

    Every count defaults to :data:`~baseaicore.measurement.UNSUPPORTED` rather than ``0``: a
    provider that reported nothing has told us nothing, and a run recorded as having used zero
    tokens is a run that will average away real throughput and real cost.

    Attributes:
        input_tokens: Tokens billed at the input rate, excluding cached ones.
        output_tokens: Tokens generated, including reasoning tokens.
        cache_write_tokens: Tokens billed at the cache-creation rate.
        cache_read_tokens: Tokens billed at the (usually much lower) cache-hit rate.
    """

    input_tokens: TokenCount = UNSUPPORTED
    output_tokens: TokenCount = UNSUPPORTED
    cache_write_tokens: TokenCount = UNSUPPORTED
    cache_read_tokens: TokenCount = UNSUPPORTED

    def __post_init__(self) -> None:
        """Validate every count.

        Raises:
            ValidationError: If a count is negative, fractional, or a bool. A negative token count
                is a parsing error in the adapter, and silently accepting it would produce a
                negative cost that looks like a credit.
        """
        for name in _TOKEN_CLASSES:
            field_name = f"{name}_tokens"
            value = getattr(self, field_name)
            if value is UNSUPPORTED:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValidationError(
                    f"{field_name} must be a whole number of tokens or UNSUPPORTED; got "
                    f"{value!r}. Use UNSUPPORTED when the provider reported no count — never 0.",
                    details={"field": field_name, "value": repr(value)},
                )
            if value < 0:
                raise ValidationError(
                    f"{field_name} must not be negative; got {value}.",
                    details={"field": field_name, "value": value},
                )

    @property
    def total_tokens(self) -> TokenCount:
        """Return the total across all four classes.

        Returns:
            The sum, or :data:`~baseaicore.measurement.UNSUPPORTED` if *any* class is unsupported.
            A total that quietly omitted an unreported class would understate the call while
            looking like a complete figure — the same defect as a partial cost presented as a
            total.
        """
        total = 0
        for value in self.as_counts().values():
            if is_supported(value):
                total += value
            else:
                return UNSUPPORTED
        return total

    def as_counts(self) -> dict[str, TokenCount]:
        """Return the four counts keyed by token class, in the suite's canonical class order."""
        return {
            "input": self.input_tokens,
            "output": self.output_tokens,
            "cache_write": self.cache_write_tokens,
            "cache_read": self.cache_read_tokens,
        }


@dataclass(frozen=True, slots=True)
class TokenRates:
    """Per-million-token prices for each billable token class, in one currency.

    Rates are held as quoted — per :data:`TOKENS_PER_RATE_UNIT` tokens — and never pre-divided
    into a per-token fraction.

    A rate left at :data:`~baseaicore.measurement.UNSUPPORTED` means "this price list does not
    state a rate for this class". That is emphatically not "this class is free": a call that used
    that class cannot be costed, and :func:`estimate_cost` says so rather than dropping the term.

    Attributes:
        currency: The alpha-3 code every stated rate is in. Held once here, and repeated inside
            each :class:`~baseaicore.money.Money` so a rate handed around on its own is still
            self-describing; the two are validated to agree, which is what catches a price list
            assembled from two currencies.
        input_per_million_tokens: Price of a million input tokens.
        output_per_million_tokens: Price of a million generated tokens.
        cache_write_per_million_tokens: Price of a million tokens written to the prompt cache.
        cache_read_per_million_tokens: Price of a million tokens served from the prompt cache.
    """

    currency: str
    input_per_million_tokens: Money | Unsupported = UNSUPPORTED
    output_per_million_tokens: Money | Unsupported = UNSUPPORTED
    cache_write_per_million_tokens: Money | Unsupported = UNSUPPORTED
    cache_read_per_million_tokens: Money | Unsupported = UNSUPPORTED

    def __post_init__(self) -> None:
        """Normalize the currency and validate every stated rate.

        Raises:
            ValidationError: If the currency code is malformed, a rate is not
                :class:`~baseaicore.money.Money`, a rate is in a different currency, or a rate is
                negative. A negative price is always an error, even though a negative
                :class:`~baseaicore.money.Money` (a credit) is not.
        """
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        for name in _TOKEN_CLASSES:
            field_name = f"{name}_per_million_tokens"
            rate = getattr(self, field_name)
            if rate is UNSUPPORTED:
                continue
            if not isinstance(rate, Money):
                raise ValidationError(
                    f"{field_name} must be Money or UNSUPPORTED; got {type(rate).__name__!r}. "
                    "Use UNSUPPORTED when the price list states no rate for this token class — "
                    "never a zero price, which would make the class look free.",
                    details={"field": field_name, "value": repr(rate)},
                )
            if rate.currency != self.currency:
                raise ValidationError(
                    f"{field_name} is in {rate.currency} but these rates are in {self.currency}. "
                    "A price list must be in one currency; converting needs an exchange rate this "
                    "package will not assume (ADR-0030 §3).",
                    details={
                        "field": field_name,
                        "currency": self.currency,
                        "rate_currency": rate.currency,
                    },
                )
            if rate.nanos < 0:
                raise ValidationError(
                    f"{field_name} must not be negative; got {rate}.",
                    details={"field": field_name, "value": str(rate)},
                )

    def rate_for(self, token_class: str) -> Money | Unsupported:
        """Return the rate for one token class.

        Args:
            token_class: One of ``"input"``, ``"output"``, ``"cache_write"``, ``"cache_read"``.

        Returns:
            The rate, or :data:`~baseaicore.measurement.UNSUPPORTED` if this price list states none.

        Raises:
            ValidationError: If ``token_class`` is not one of the four.
        """
        if token_class not in _TOKEN_CLASSES:
            raise ValidationError(
                f"Unknown token class {token_class!r}; expected one of {list(_TOKEN_CLASSES)}.",
                details={"field": "token_class", "value": token_class},
            )
        rate: Money | Unsupported = getattr(self, f"{token_class}_per_million_tokens")
        return rate

    def as_canonical(self) -> dict[str, Any]:
        """Return the mapping form used inside :attr:`ModelPricing.pricing_hash`."""
        return {
            "currency": self.currency,
            **{
                f"{name}_per_million_tokens": (
                    rate.as_canonical() if isinstance(rate, Money) else UNSUPPORTED
                )
                for name in _TOKEN_CLASSES
                for rate in (self.rate_for(name),)
            },
        }


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """One observation of what one model costs, with provenance and a validity window.

    A price is not a property of a model. The same weights legitimately have several prices at
    once — standard tier and batch tier, one region and another, the public list and a negotiated
    agreement — and every one of them can change without notice. This type therefore records not
    just the numbers but where they came from, when they were learned, when the provider says they
    apply, and which tier and region they are for. A catalogue holding all of them is a set of
    observations, not a set of contradictions.

    Attributes:
        identity: The weights these rates apply to.
        rates: The per-million-token prices.
        source: Where the rates came from.
        observed_at: When *we* learned this price. Timezone-aware. Deliberately excluded from
            :attr:`pricing_hash`, so re-reading an unchanged price list does not look like a
            change.
        effective_from: When the provider says the price starts applying, if it says. ``None``
            means "not stated", which is different from "unbounded in principle" only in that we
            know we were not told.
        effective_until: When it stops applying, if stated. ``None`` means not stated.
        price_tier: The provider's own tier name — ``"standard"``, ``"batch"``, ``"priority"``.
            Free text, because every provider names its tiers differently and an enumeration here
            would go stale on their schedule, not ours.
        region: The region the price is for, if it varies by region.
    """

    identity: ModelIdentity
    rates: TokenRates
    source: PricingSource
    observed_at: datetime
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    price_tier: str | None = None
    region: str | None = None

    _pricing_hash_cache: str | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate the timestamps and the window.

        Raises:
            ValidationError: If any timestamp is naive, or the window ends before it starts.
        """
        for field_name in ("observed_at", "effective_from", "effective_until"):
            value = getattr(self, field_name)
            if value is None:
                continue
            if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
                raise ValidationError(
                    f"{field_name} must be timezone-aware; a naive timestamp on a price makes the "
                    "window it applies over depend on the reader's machine.",
                    details={"field": field_name},
                )
        if (
            self.effective_from is not None
            and self.effective_until is not None
            and self.effective_until < self.effective_from
        ):
            raise ValidationError(
                f"effective_until ({self.effective_until.isoformat()}) precedes effective_from "
                f"({self.effective_from.isoformat()}); that window can never contain an instant.",
                details={
                    "effective_from": self.effective_from.isoformat(),
                    "effective_until": self.effective_until.isoformat(),
                },
            )

    def is_effective_at(self, when: datetime) -> bool:
        """Report whether this price applies at a given instant.

        The window is half-open — ``effective_from`` is included, ``effective_until`` is not — so
        two consecutive price records with touching boundaries have exactly one applicable price
        at every instant rather than two at the seam.

        An unstated bound never excludes: a record with no window applies at every instant. "The
        provider did not tell us when this expires" is a different statement from "this expired",
        and inventing an end date would silently stop costing a price list that is still in force.

        Args:
            when: A timezone-aware instant.

        Returns:
            ``True`` if the price applies then.

        Raises:
            ValidationError: If ``when`` is naive.
        """
        if when.tzinfo is None or when.tzinfo.utcoffset(when) is None:
            raise ValidationError(
                "is_effective_at requires a timezone-aware instant; got a naive one.",
                details={"field": "when"},
            )
        if self.effective_from is not None and when < self.effective_from:
            return False
        return not (self.effective_until is not None and when >= self.effective_until)

    @property
    def pricing_hash(self) -> str:
        """Return a stable 16-character identifier for **the price**, not for the reading of it.

        Canonical JSON of the identity, the rates, the source, the window and the tier/region,
        hashed with SHA-256 and truncated to 16 hex characters. ``observed_at`` is deliberately
        excluded, so re-reading an unchanged price list yields the same hash — which is what lets
        a stored cost row name the exact price that produced it, and lets a catalogue deduplicate
        repeated readings instead of accumulating one row per poll.

        The hashed structure is part of the public contract: changing it changes every stored
        hash, so it is a breaking change, not a refactor.

        Returns:
            16 lowercase hex characters. Computed once and cached on the instance.
        """
        cached = self._pricing_hash_cache
        if cached is None:
            cached = sha256_of(
                {
                    "provider_kind": self.identity.provider_kind,
                    "provider_model_name": self.identity.provider_model_name,
                    "artifact_digest": self.identity.artifact_digest,
                    "rates": self.rates.as_canonical(),
                    "source": self.source,
                    "effective_from": self.effective_from,
                    "effective_until": self.effective_until,
                    "price_tier": self.price_tier,
                    "region": self.region,
                }
            )[:_PRICING_HASH_LENGTH]
            object.__setattr__(self, "_pricing_hash_cache", cached)
        return cached


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """What a call is estimated to have cost, and everything needed to judge that estimate.

    Named an estimate because that is what it is. The provider's invoice is authoritative and
    arrives weeks later; nothing computed here is a billed amount, and no API, export or UI in the
    suite presents it as one (ADR-0030 §7).

    :attr:`total` is :data:`~baseaicore.measurement.UNSUPPORTED` unless every token class that
    was actually used could be priced. The per-class components are still reported when they
    could be computed, because "output cost known, cache-read cost unknown" is useful to see —
    but their partial sum is never promoted to a total.

    Attributes:
        currency: The currency of every component and of the total.
        total: The sum of the components, or UNSUPPORTED if any of them is.
        input_cost: Cost of the input tokens, or UNSUPPORTED.
        output_cost: Cost of the generated tokens, or UNSUPPORTED.
        cache_write_cost: Cost of the cache-creation tokens, or UNSUPPORTED.
        cache_read_cost: Cost of the cache-hit tokens, or UNSUPPORTED.
        pricing_hash: Identifies the price record this was computed from.
        pricing_source: Where that price came from, carried through so a consumer can weigh the
            figure without holding the price record.
        priced_at: The instant the price was applied to.
        unpriced_reasons: One human-readable sentence per gap, in token-class order. Empty when
            the total is a real number. These are what the UI shows instead of a zero.
    """

    currency: str
    total: Money | Unsupported
    input_cost: Money | Unsupported
    output_cost: Money | Unsupported
    cache_write_cost: Money | Unsupported
    cache_read_cost: Money | Unsupported
    pricing_hash: str
    pricing_source: PricingSource
    priced_at: datetime
    unpriced_reasons: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        """Report whether every used token class could be priced, making the total a real amount."""
        return is_supported(self.total)


def estimate_cost(usage: TokenUsage, pricing: ModelPricing, *, at: datetime) -> CostEstimate:
    """Cost one call's token usage against one price observation.

    Each class costs ``rate x tokens / 1 000 000``, rounded half-to-even to the nearest nano; the
    components are rounded first and then summed, so the total a caller displays always equals the
    components it displays beside it. The rounding is ours, not the provider's — one more reason
    the result is called an estimate.

    Refusals, and why each one is a refusal rather than a number:

    * The pricing is not effective at ``at`` — every component is UNSUPPORTED. Extrapolating a
      price beyond the window it was quoted for is guessing.
    * A token count is UNSUPPORTED — that component is UNSUPPORTED. The call used an unknown
      number of tokens; no arithmetic recovers it.
    * A count is non-zero and the price list states no rate for it — that component is
      UNSUPPORTED, naming the missing rate. This is the local-model case, and the case of a price
      list that predates a provider's cache pricing.

    The one place a zero is honest: a token class whose count is exactly ``0`` costs exactly
    nothing, whether or not a rate exists for it. Nothing was used, so nothing was billed.

    Args:
        usage: The call's disjoint token counts.
        pricing: The price observation to apply. Callers are responsible for choosing one whose
            identity, tier and region match the call — this function costs what it is given and
            does not second-guess the match.
        at: The instant to price at — normally when the call happened, not when the costing runs,
            so re-costing history later reproduces the same figure.

    Returns:
        A :class:`CostEstimate` whose total is a real amount only if every used class was priced.

    Raises:
        ValidationError: If ``at`` is naive.
    """
    if at.tzinfo is None or at.tzinfo.utcoffset(at) is None:
        raise ValidationError(
            "estimate_cost requires a timezone-aware `at`; got a naive datetime. Which price "
            "applies depends on the instant, so an ambiguous instant has no defensible answer.",
            details={"field": "at"},
        )

    currency = pricing.rates.currency
    effective = pricing.is_effective_at(at)
    components: dict[str, Money | Unsupported] = {}
    reasons: list[str] = []

    if not effective:
        reasons.append(_window_reason(pricing, at))

    for token_class, count in usage.as_counts().items():
        rate = pricing.rates.rate_for(token_class)
        if not effective:
            components[token_class] = UNSUPPORTED
        elif not is_supported(count):
            components[token_class] = UNSUPPORTED
            reasons.append(
                f"{token_class}_tokens was not reported, so its cost cannot be known "
                "(it is not zero)."
            )
        elif count == 0:
            components[token_class] = Money.zero(currency)
        elif isinstance(rate, Money):
            components[token_class] = Money(
                currency=currency,
                nanos=_divide_round_half_even(rate.nanos * count, TOKENS_PER_RATE_UNIT),
            )
        else:
            components[token_class] = UNSUPPORTED
            reasons.append(
                f"The {pricing.source.value} price list states no "
                f"{token_class}_per_million_tokens rate, and this call used {count} "
                f"{token_class} tokens, so its cost is unknown (it is not free)."
            )

    total = _total_of(components.values(), currency)
    return CostEstimate(
        currency=currency,
        total=total,
        input_cost=components["input"],
        output_cost=components["output"],
        cache_write_cost=components["cache_write"],
        cache_read_cost=components["cache_read"],
        pricing_hash=pricing.pricing_hash,
        pricing_source=pricing.source,
        priced_at=at,
        unpriced_reasons=tuple(reasons),
    )


def _window_reason(pricing: ModelPricing, at: datetime) -> str:
    """Explain, in one sentence, why a price does not apply at an instant."""
    start = pricing.effective_from.isoformat() if pricing.effective_from else "unstated"
    end = pricing.effective_until.isoformat() if pricing.effective_until else "unstated"
    return (
        f"The price is effective from {start} until {end}, which does not include "
        f"{at.isoformat()}; it was not extrapolated."
    )


def _total_of(components: Iterable[Money | Unsupported], currency: str) -> Money | Unsupported:
    """Sum the components, or refuse if any one of them is unsupported."""
    total = Money.zero(currency)
    for component in components:
        if not is_supported(component):
            return UNSUPPORTED
        total = total + component
    return total


def _divide_round_half_even(numerator: int, denominator: int) -> int:
    """Divide two non-negative integers, rounding a tie to the even quotient.

    Half-to-even rather than half-up because costs are summed across thousands of calls, and
    half-up biases every one of those sums upward.
    """
    quotient, remainder = divmod(numerator, denominator)
    doubled = remainder * 2
    if doubled > denominator or (doubled == denominator and quotient % 2 == 1):
        quotient += 1
    return quotient
