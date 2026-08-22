"""Performance budgets from spec §15.

Marked ``performance`` and therefore deselected by default (``pyproject.toml`` ``addopts``):
these assert wall-clock budgets, which are only meaningful on the dedicated nightly hardware and
are noise on a shared CI runner. Gold standard G19 is that every budget has a test, not that every
budget is checked on every push.

Each budget is measured as a per-operation mean over a batch, so one scheduler hiccup cannot fail
a run on its own.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from baseaicore.cost import (
    ModelPricing,
    PricingSource,
    TokenRates,
    TokenUsage,
    estimate_cost,
)
from baseaicore.hashing import canonical_json
from baseaicore.identity import ModelIdentity, ProviderKind
from baseaicore.ids import new_id
from baseaicore.money import Money
from baseaicore.timeutil import elapsed_ms, monotonic_ns

pytestmark = pytest.mark.performance

ITERATIONS = 10_000
AT = datetime(2026, 8, 22, 14, 0, tzinfo=UTC)

_PRICING = ModelPricing(
    identity=ModelIdentity(ProviderKind.OPENAI_COMPATIBLE, "gpt-oss-120b"),
    rates=TokenRates(
        currency="USD",
        input_per_million_tokens=Money.from_decimal("USD", "3.00"),
        output_per_million_tokens=Money.from_decimal("USD", "15.00"),
        cache_write_per_million_tokens=Money.from_decimal("USD", "3.75"),
        cache_read_per_million_tokens=Money.from_decimal("USD", "0.30"),
    ),
    source=PricingSource.PROVIDER_PUBLISHED,
    observed_at=AT,
)
_USAGE = TokenUsage(
    input_tokens=1_500, output_tokens=200, cache_write_tokens=10, cache_read_tokens=40
)
_TEN_KB_STRUCTURE = {
    f"key_{index:04d}": [index, float(index), f"value_{index}"] for index in range(300)
}


def mean_microseconds(operation: Callable[[], object]) -> float:
    """Return the mean duration of ``operation`` over ``ITERATIONS`` calls, in microseconds."""
    start = monotonic_ns()
    for _ in range(ITERATIONS):
        operation()
    return elapsed_ms(start) * 1_000 / ITERATIONS


def test_identity_construction_and_canonical_id_is_within_budget() -> None:
    def build() -> str:
        return ModelIdentity(ProviderKind.OLLAMA, "qwen3.5:9b-q8_0").canonical_id

    assert mean_microseconds(build) <= 5.0


def test_new_id_is_within_budget() -> None:
    assert mean_microseconds(new_id) <= 2.0


def test_pricing_hash_is_within_budget() -> None:
    # Measured on a fresh record each time, so the instance cache never hides the real cost.
    def compute() -> str:
        return ModelPricing(
            identity=_PRICING.identity,
            rates=_PRICING.rates,
            source=_PRICING.source,
            observed_at=_PRICING.observed_at,
        ).pricing_hash

    assert mean_microseconds(compute) <= 50.0


def test_estimate_cost_is_within_budget() -> None:
    assert mean_microseconds(lambda: estimate_cost(_USAGE, _PRICING, at=AT)) <= 20.0


def test_canonical_json_on_a_ten_kilobyte_structure_is_within_budget() -> None:
    assert len(canonical_json(_TEN_KB_STRUCTURE)) >= 10_000
    assert mean_microseconds(lambda: canonical_json(_TEN_KB_STRUCTURE)) <= 2_000.0
