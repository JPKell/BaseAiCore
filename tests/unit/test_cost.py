"""Unit tests for token usage, pricing observations and cost estimation (ADR-0030).

The rule under test throughout: a cost that cannot be known is UNSUPPORTED with a reason, never
zero and never a partial sum. The comparison that decides which model the suite recommends depends
on it.
"""

from __future__ import annotations

import copy
import pickle
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from baseaicore.cost import (
    TOKENS_PER_RATE_UNIT,
    CostEstimate,
    ModelPricing,
    PricingSource,
    TokenRates,
    TokenUsage,
    estimate_cost,
)
from baseaicore.errors import ValidationError
from baseaicore.identity import ModelIdentity, ProviderKind
from baseaicore.measurement import UNSUPPORTED
from baseaicore.money import Money

USD = "USD"
AT = datetime(2026, 8, 22, 14, 0, tzinfo=UTC)
OBSERVED = datetime(2026, 8, 1, tzinfo=UTC)

REMOTE = ModelIdentity(ProviderKind.OPENAI_COMPATIBLE, "gpt-oss-120b")
LOCAL = ModelIdentity(ProviderKind.OLLAMA, "qwen3.5:9b-q8_0")

# A realistic published price list: $3.00 / 1M input, $15.00 / 1M output, $3.75 / 1M cache write,
# $0.30 / 1M cache read.
FULL_RATES = TokenRates(
    currency=USD,
    input_per_million_tokens=Money.from_decimal(USD, "3.00"),
    output_per_million_tokens=Money.from_decimal(USD, "15.00"),
    cache_write_per_million_tokens=Money.from_decimal(USD, "3.75"),
    cache_read_per_million_tokens=Money.from_decimal(USD, "0.30"),
)


def pricing(**overrides: Any) -> ModelPricing:
    """Build a price observation, overriding any field."""
    defaults: dict[str, Any] = {
        "identity": REMOTE,
        "rates": FULL_RATES,
        "source": PricingSource.PROVIDER_PUBLISHED,
        "observed_at": OBSERVED,
    }
    return ModelPricing(**{**defaults, **overrides})


# ---- TokenUsage -----------------------------------------------------------------------------
def test_every_count_defaults_to_unsupported_not_zero() -> None:
    # A provider that reported nothing has told us nothing; a run recorded as using zero tokens
    # averages away real throughput and real cost.
    usage = TokenUsage()

    assert usage.input_tokens is UNSUPPORTED
    assert usage.output_tokens is UNSUPPORTED
    assert usage.cache_write_tokens is UNSUPPORTED
    assert usage.cache_read_tokens is UNSUPPORTED


def test_total_tokens_sums_the_four_disjoint_classes() -> None:
    usage = TokenUsage(
        input_tokens=100, output_tokens=20, cache_write_tokens=5, cache_read_tokens=3
    )

    assert usage.total_tokens == 128


@pytest.mark.parametrize(
    "field_name",
    ["input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens"],
)
def test_total_tokens_is_unsupported_when_any_class_is(field_name: str) -> None:
    # A total that quietly omitted an unreported class would understate the call while looking
    # like a complete figure.
    counts: dict[str, Any] = {
        "input_tokens": 1,
        "output_tokens": 1,
        "cache_write_tokens": 1,
        "cache_read_tokens": 1,
    }
    counts[field_name] = UNSUPPORTED

    assert TokenUsage(**counts).total_tokens is UNSUPPORTED


def test_all_zero_counts_total_zero() -> None:
    usage = TokenUsage(input_tokens=0, output_tokens=0, cache_write_tokens=0, cache_read_tokens=0)

    assert usage.total_tokens == 0


@pytest.mark.parametrize(
    "value", [-1, 1.5, "10", None, True], ids=["negative", "fraction", "str", "none", "bool"]
)
def test_a_count_that_is_not_a_whole_non_negative_number_is_refused(value: Any) -> None:
    with pytest.raises(ValidationError, match="input_tokens"):
        TokenUsage(input_tokens=value)


def test_usage_is_frozen_and_hashable() -> None:
    usage = TokenUsage(input_tokens=1)

    assert {usage: "x"}[TokenUsage(input_tokens=1)] == "x"
    with pytest.raises((AttributeError, TypeError)):
        usage.input_tokens = 2  # type: ignore[misc]  # proving the refusal


# ---- TokenRates -----------------------------------------------------------------------------
def test_rates_default_to_unsupported_which_is_not_free() -> None:
    rates = TokenRates(currency=USD)

    assert rates.rate_for("input") is UNSUPPORTED
    assert rates.rate_for("cache_read") is UNSUPPORTED


def test_rates_normalize_their_currency() -> None:
    assert TokenRates(currency="usd").currency == USD


def test_a_rate_in_another_currency_is_refused() -> None:
    # A price list assembled from two currencies is the realistic way this goes wrong.
    with pytest.raises(ValidationError, match=r"EUR.*USD|USD.*EUR"):
        TokenRates(currency=USD, input_per_million_tokens=Money("EUR", 1))


def test_a_negative_rate_is_refused() -> None:
    # A negative Money is a legitimate credit; a negative *price* never is.
    with pytest.raises(ValidationError, match="must not be negative"):
        TokenRates(currency=USD, input_per_million_tokens=Money(USD, -1))


@pytest.mark.parametrize("rate", [3.0, "3.00", 0], ids=["float", "str", "bare int"])
def test_a_rate_that_is_not_money_is_refused(rate: Any) -> None:
    with pytest.raises(ValidationError, match="must be Money or UNSUPPORTED"):
        TokenRates(currency=USD, input_per_million_tokens=rate)


def test_rate_for_rejects_an_unknown_token_class() -> None:
    with pytest.raises(ValidationError, match="Unknown token class"):
        FULL_RATES.rate_for("reasoning")


# ---- ModelPricing ---------------------------------------------------------------------------
def test_pricing_hash_is_sixteen_hex_characters() -> None:
    value = pricing().pricing_hash

    assert len(value) == 16
    assert set(value) <= set("0123456789abcdef")


def test_pricing_hash_ignores_when_the_price_was_read() -> None:
    # It identifies the price, not the reading of it: re-polling an unchanged list must not look
    # like a change, or a catalogue accumulates one row per poll.
    first = pricing(observed_at=OBSERVED)
    second = pricing(observed_at=OBSERVED + timedelta(days=180))

    assert first.pricing_hash == second.pricing_hash


@pytest.mark.parametrize(
    "overrides",
    [
        {"identity": LOCAL},
        {"identity": REMOTE.with_digest("a" * 64)},
        {"source": PricingSource.USER_OVERRIDE},
        {"price_tier": "batch"},
        {"region": "eu-west-1"},
        {"effective_from": AT},
        {"effective_until": AT},
        {"rates": TokenRates(currency=USD, input_per_million_tokens=Money(USD, 1))},
        {"rates": TokenRates(currency="EUR")},
    ],
    ids=[
        "identity",
        "digest",
        "source",
        "tier",
        "region",
        "window start",
        "window end",
        "rates",
        "currency",
    ],
)
def test_pricing_hash_changes_when_any_priced_dimension_changes(overrides: dict[str, Any]) -> None:
    assert pricing(**overrides).pricing_hash != pricing().pricing_hash


def test_pricing_hash_is_stable_across_processes() -> None:
    # It is stored beside costs in three databases; a per-process hash would be worthless.
    program = (
        "from datetime import UTC, datetime;"
        "from baseaicore.cost import ModelPricing, PricingSource, TokenRates;"
        "from baseaicore.identity import ModelIdentity, ProviderKind;"
        "from baseaicore.money import Money;"
        "rates = TokenRates(currency='USD',"
        " input_per_million_tokens=Money.from_decimal('USD', '3.00'),"
        " output_per_million_tokens=Money.from_decimal('USD', '15.00'),"
        " cache_write_per_million_tokens=Money.from_decimal('USD', '3.75'),"
        " cache_read_per_million_tokens=Money.from_decimal('USD', '0.30'));"
        "print(ModelPricing(identity=ModelIdentity(ProviderKind.OPENAI_COMPATIBLE, 'gpt-oss-120b'),"
        " rates=rates, source=PricingSource.PROVIDER_PUBLISHED,"
        " observed_at=datetime(2026, 8, 1, tzinfo=UTC)).pricing_hash)"
    )

    result = subprocess.run(  # noqa: S603 — our own interpreter, no shell, literal argument list
        [sys.executable, "-c", program], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == pricing().pricing_hash


@pytest.mark.parametrize("field_name", ["observed_at", "effective_from", "effective_until"])
def test_a_naive_timestamp_on_a_price_is_refused(field_name: str) -> None:
    naive = datetime(2026, 8, 1)  # noqa: DTZ001 — the input under test

    with pytest.raises(ValidationError, match=field_name):
        pricing(**{field_name: naive})


def test_a_window_that_ends_before_it_starts_is_refused() -> None:
    with pytest.raises(ValidationError, match="precedes effective_from"):
        pricing(effective_from=AT, effective_until=AT - timedelta(days=1))


@pytest.mark.parametrize(
    ("window", "when", "expected"),
    [
        ({}, AT, True),
        ({"effective_from": AT}, AT, True),
        ({"effective_from": AT + timedelta(seconds=1)}, AT, False),
        ({"effective_until": AT + timedelta(seconds=1)}, AT, True),
        ({"effective_until": AT}, AT, False),
        (
            {"effective_from": AT - timedelta(days=1), "effective_until": AT + timedelta(days=1)},
            AT,
            True,
        ),
        ({"effective_from": AT + timedelta(days=1)}, AT, False),
    ],
    ids=[
        "no window applies always",
        "start is inclusive",
        "before the start",
        "inside the window",
        "end is exclusive",
        "within both bounds",
        "before a future price",
    ],
)
def test_is_effective_at_treats_the_window_as_half_open(
    window: dict[str, Any], when: datetime, expected: bool
) -> None:
    # Half-open so two consecutive price records with touching boundaries have exactly one
    # applicable price at every instant, rather than two at the seam.
    assert pricing(**window).is_effective_at(when) is expected


def test_an_unstated_bound_never_excludes() -> None:
    # "The provider did not tell us when this expires" is not "this expired".
    assert pricing().is_effective_at(AT + timedelta(days=3650)) is True


def test_is_effective_at_refuses_a_naive_instant() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        pricing().is_effective_at(datetime(2026, 8, 22))  # noqa: DTZ001 — the input under test


@pytest.mark.parametrize(
    "round_trip",
    [copy.copy, copy.deepcopy, lambda v: pickle.loads(pickle.dumps(v))],  # noqa: S301 — our bytes
    ids=["copy", "deepcopy", "pickle"],
)
def test_pricing_round_trips_equal_with_the_same_hash(round_trip: Any) -> None:
    original = pricing(price_tier="batch", region="eu-west-1")

    restored = round_trip(original)

    assert restored == original
    assert restored.pricing_hash == original.pricing_hash


# ---- estimate_cost: the arithmetic ----------------------------------------------------------
def test_a_golden_cost_for_a_realistic_call() -> None:
    # 1 500 000 input at $3.00/M = $4.50; 200 000 output at $15.00/M = $3.00; total $7.50.
    usage = TokenUsage(
        input_tokens=1_500_000, output_tokens=200_000, cache_write_tokens=0, cache_read_tokens=0
    )

    estimate = estimate_cost(usage, pricing(), at=AT)

    assert estimate.input_cost == Money.from_decimal(USD, "4.50")
    assert estimate.output_cost == Money.from_decimal(USD, "3.00")
    assert estimate.total == Money.from_decimal(USD, "7.50")
    assert estimate.is_complete is True
    assert estimate.unpriced_reasons == ()


def test_a_golden_cost_including_both_cache_classes() -> None:
    # 12 000 cache write at $3.75/M = $0.045; 48 000 cache read at $0.30/M = $0.0144.
    usage = TokenUsage(
        input_tokens=2_000, output_tokens=500, cache_write_tokens=12_000, cache_read_tokens=48_000
    )

    estimate = estimate_cost(usage, pricing(), at=AT)

    assert estimate.input_cost == Money.from_decimal(USD, "0.006")
    assert estimate.output_cost == Money.from_decimal(USD, "0.0075")
    assert estimate.cache_write_cost == Money.from_decimal(USD, "0.045")
    assert estimate.cache_read_cost == Money.from_decimal(USD, "0.0144")
    assert estimate.total == Money.from_decimal(USD, "0.0729")


def test_the_total_always_equals_the_sum_of_the_components_shown_beside_it() -> None:
    # Components are rounded first and then summed, so a table never shows rows that do not add up.
    usage = TokenUsage(
        input_tokens=333, output_tokens=777, cache_write_tokens=111, cache_read_tokens=999
    )

    estimate = estimate_cost(usage, pricing(), at=AT)

    assert estimate.total == (
        estimate.input_cost
        + estimate.output_cost
        + estimate.cache_write_cost
        + estimate.cache_read_cost
    )


def test_a_single_token_costs_a_rounded_fraction_of_the_quoted_rate() -> None:
    # $3.00 per million = 3 000 nanos per token; the quoted figure is never pre-divided.
    usage = TokenUsage(input_tokens=1, output_tokens=0, cache_write_tokens=0, cache_read_tokens=0)

    estimate = estimate_cost(usage, pricing(), at=AT)

    assert estimate.input_cost == Money(USD, 3_000)


def test_rounding_a_half_nano_goes_to_even() -> None:
    # A rate of 1 nano per million, over 500 000 tokens, is exactly half a nano.
    rates = TokenRates(currency=USD, input_per_million_tokens=Money(USD, 1))
    usage = TokenUsage(
        input_tokens=TOKENS_PER_RATE_UNIT // 2,
        output_tokens=0,
        cache_write_tokens=0,
        cache_read_tokens=0,
    )

    estimate = estimate_cost(usage, pricing(rates=rates), at=AT)

    assert estimate.input_cost == Money(USD, 0)


def test_rounding_above_the_half_goes_up() -> None:
    rates = TokenRates(currency=USD, input_per_million_tokens=Money(USD, 1))
    usage = TokenUsage(
        input_tokens=(TOKENS_PER_RATE_UNIT // 2) + 1,
        output_tokens=0,
        cache_write_tokens=0,
        cache_read_tokens=0,
    )

    estimate = estimate_cost(usage, pricing(rates=rates), at=AT)

    assert estimate.input_cost == Money(USD, 1)


# ---- estimate_cost: the refusals ------------------------------------------------------------
def test_a_model_with_no_price_list_costs_unsupported_never_zero() -> None:
    # The local-model case, and the single most consequential form the zero-instead-of-unsupported
    # bug could take: a free-looking model wins every "cheapest" comparison in the suite.
    unpriced = pricing(identity=LOCAL, rates=TokenRates(currency=USD))
    usage = TokenUsage(
        input_tokens=1_000, output_tokens=500, cache_write_tokens=0, cache_read_tokens=0
    )

    estimate = estimate_cost(usage, unpriced, at=AT)

    assert estimate.total is UNSUPPORTED
    # Spelled out because this is the assertion the whole ADR exists for.
    assert estimate.total != Money.zero(USD)  # type: ignore[comparison-overlap]  # not free
    assert estimate.is_complete is False
    assert len(estimate.unpriced_reasons) == 2


def test_one_missing_rate_with_a_non_zero_count_refuses_the_whole_total() -> None:
    # A price list that predates a provider's cache pricing. The partial sum is never promoted.
    partial = TokenRates(
        currency=USD,
        input_per_million_tokens=Money.from_decimal(USD, "3.00"),
        output_per_million_tokens=Money.from_decimal(USD, "15.00"),
    )
    usage = TokenUsage(
        input_tokens=1_000, output_tokens=500, cache_write_tokens=0, cache_read_tokens=12_000
    )

    estimate = estimate_cost(usage, pricing(rates=partial), at=AT)

    assert estimate.total is UNSUPPORTED
    assert estimate.input_cost == Money.from_decimal(USD, "0.003")
    assert estimate.cache_read_cost is UNSUPPORTED
    assert "cache_read_per_million_tokens" in estimate.unpriced_reasons[0]
    assert "not free" in estimate.unpriced_reasons[0]


def test_a_missing_rate_with_a_zero_count_costs_exactly_nothing() -> None:
    # The one place a zero is honest: nothing was used, so nothing was billed.
    partial = TokenRates(
        currency=USD,
        input_per_million_tokens=Money.from_decimal(USD, "3.00"),
        output_per_million_tokens=Money.from_decimal(USD, "15.00"),
    )
    usage = TokenUsage(
        input_tokens=1_000, output_tokens=500, cache_write_tokens=0, cache_read_tokens=0
    )

    estimate = estimate_cost(usage, pricing(rates=partial), at=AT)

    assert estimate.cache_read_cost == Money.zero(USD)
    assert estimate.total == Money.from_decimal(USD, "0.0105")
    assert estimate.unpriced_reasons == ()


@pytest.mark.parametrize(
    "field_name",
    ["input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens"],
)
def test_an_unreported_token_count_makes_the_cost_unknowable(field_name: str) -> None:
    counts: dict[str, Any] = {
        "input_tokens": 10,
        "output_tokens": 10,
        "cache_write_tokens": 10,
        "cache_read_tokens": 10,
    }
    counts[field_name] = UNSUPPORTED

    estimate = estimate_cost(TokenUsage(**counts), pricing(), at=AT)

    assert estimate.total is UNSUPPORTED
    assert field_name in estimate.unpriced_reasons[0]
    assert "not zero" in estimate.unpriced_reasons[0]


def test_pricing_outside_its_stated_window_is_not_extrapolated() -> None:
    expired = pricing(
        effective_from=AT - timedelta(days=90), effective_until=AT - timedelta(days=30)
    )
    usage = TokenUsage(
        input_tokens=1_000, output_tokens=500, cache_write_tokens=0, cache_read_tokens=0
    )

    estimate = estimate_cost(usage, expired, at=AT)

    assert estimate.total is UNSUPPORTED
    assert estimate.input_cost is UNSUPPORTED
    assert len(estimate.unpriced_reasons) == 1
    assert "not extrapolated" in estimate.unpriced_reasons[0]


def test_the_window_reason_names_the_window_and_the_instant() -> None:
    expired = pricing(effective_until=AT - timedelta(days=30))

    reason = estimate_cost(TokenUsage(), expired, at=AT).unpriced_reasons[0]

    assert "unstated" in reason
    assert AT.isoformat() in reason


def test_a_naive_instant_is_refused() -> None:
    # Which price applies depends on the instant, so an ambiguous one has no defensible answer.
    with pytest.raises(ValidationError, match="timezone-aware"):
        estimate_cost(TokenUsage(), pricing(), at=datetime(2026, 8, 22))  # noqa: DTZ001 — under test


# ---- CostEstimate provenance ----------------------------------------------------------------
def test_the_estimate_carries_the_provenance_needed_to_judge_it() -> None:
    priced = pricing(source=PricingSource.CATALOG, price_tier="batch")

    estimate = estimate_cost(TokenUsage(), priced, at=AT)

    assert estimate.pricing_hash == priced.pricing_hash
    assert estimate.pricing_source is PricingSource.CATALOG
    assert estimate.priced_at == AT
    assert estimate.currency == USD


def test_re_costing_the_same_usage_at_the_same_instant_reproduces_the_figure() -> None:
    # The property that makes "store usage, derive cost" safe: history re-costs identically.
    usage = TokenUsage(
        input_tokens=1_234, output_tokens=567, cache_write_tokens=0, cache_read_tokens=89
    )

    assert estimate_cost(usage, pricing(), at=AT) == estimate_cost(usage, pricing(), at=AT)


def test_a_corrected_price_re_costs_history_rather_than_corrupting_it() -> None:
    # ADR-0030 §1: the stored fact is the usage, so a price correction is applied by re-costing.
    usage = TokenUsage(
        input_tokens=1_000_000, output_tokens=0, cache_write_tokens=0, cache_read_tokens=0
    )
    corrected = pricing(
        rates=TokenRates(
            currency=USD,
            input_per_million_tokens=Money.from_decimal(USD, "2.50"),
            output_per_million_tokens=Money.from_decimal(USD, "15.00"),
            cache_write_per_million_tokens=Money.from_decimal(USD, "3.75"),
            cache_read_per_million_tokens=Money.from_decimal(USD, "0.30"),
        ),
        source=PricingSource.USER_OVERRIDE,
    )

    before = estimate_cost(usage, pricing(), at=AT)
    after = estimate_cost(usage, corrected, at=AT)

    assert before.total == Money.from_decimal(USD, "3.00")
    assert after.total == Money.from_decimal(USD, "2.50")
    assert after.pricing_hash != before.pricing_hash


def test_estimates_in_different_currencies_never_silently_combine() -> None:
    usage = TokenUsage(
        input_tokens=1_000_000, output_tokens=0, cache_write_tokens=0, cache_read_tokens=0
    )
    in_euros = pricing(
        rates=TokenRates(currency="EUR", input_per_million_tokens=Money.from_decimal("EUR", "2.80"))
    )

    dollars = estimate_cost(usage, pricing(), at=AT)
    euros = estimate_cost(usage, in_euros, at=AT)

    assert isinstance(dollars.total, Money)
    assert isinstance(euros.total, Money)
    with pytest.raises(ValidationError, match="exchange rate"):
        _ = dollars.total + euros.total


def test_a_cost_estimate_is_frozen() -> None:
    estimate = estimate_cost(TokenUsage(), pricing(), at=AT)

    assert isinstance(estimate, CostEstimate)
    with pytest.raises((AttributeError, TypeError)):
        estimate.total = Money.zero(USD)  # type: ignore[misc]  # proving the refusal


def test_pricing_source_values_are_the_persisted_strings() -> None:
    assert [source.value for source in PricingSource] == [
        "provider_response",
        "provider_published",
        "user_override",
        "catalog",
        "estimate",
    ]
