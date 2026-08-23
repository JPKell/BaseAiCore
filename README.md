# BaseAiCore

Zero-dependency domain foundation: canonical model identity, machine profile, the Unsupported measurement sentinel, capability IDs, IDs, timestamps and the base error hierarchy.

**Status:** Phases 1–3 shipped (`0.3.0`) — measurement, identity, IDs, time, hashing, errors,
money, cost, model descriptor, runtime profile, measurement subject and the machine profile with
its fingerprint. Capability IDs arrive in Phase 4; see the
[development plan](docs/packages/baseaicore/development-plan.md). The Phase 2–3 types are not yet
exported from `baseaicore.__init__` — import them directly (`from baseaicore.machine import
MachineProfile`) until Phase 4 curates the public surface.

Part of the **Local AI Suite** — see [docs/architecture/executive-summary.md](docs/architecture/executive-summary.md)
for how BaseAiCore fits with the suite's other applications and packages.

## Install

```bash
pip install baseaicore
```

## Quickstart

```python
from baseaicore import ModelIdentity, ProviderKind, normalize_digest

identity = ModelIdentity(
    ProviderKind.OLLAMA,
    "qwen3.5:9b-q8_0",
    normalize_digest("1f3a9c4e2b70a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f607182930"),
)
print(identity.canonical_id)  # ollama/qwen3.5:9b-q8_0@sha256:1f3a9c4e2b70
print(identity.identity_confidence)  # IdentityConfidence.DIGEST
```

A measurement this machine cannot provide refuses to behave like a number, so the idiom that
would fabricate one fails loudly instead of producing a plausible chart:

```python
from baseaicore import UNSUPPORTED, is_supported, supported_values

UNSUPPORTED or 0  # raises TypeError — not 0
is_supported(UNSUPPORTED)  # False
supported_values([12.5, UNSUPPORTED, 9.0])  # [12.5, 9.0], and you know two of three were real
```

The same rule governs money. A price is a dated, sourced observation with a validity window — not a
property of the model — and a model with no price costs *unknown*, never *nothing*:

```python
from baseaicore import (
    ModelPricing,
    Money,
    PricingSource,
    TokenRates,
    TokenUsage,
    estimate_cost,
    utc_now,
)

pricing = ModelPricing(
    identity=identity,
    rates=TokenRates(
        currency="USD",
        input_per_million_tokens=Money.from_decimal("USD", "3.00"),
        output_per_million_tokens=Money.from_decimal("USD", "15.00"),
    ),
    source=PricingSource.PROVIDER_PUBLISHED,
    observed_at=utc_now(),
)
usage = TokenUsage(
    input_tokens=1_500_000, output_tokens=200_000, cache_write_tokens=0, cache_read_tokens=0
)

estimate = estimate_cost(usage, pricing, at=utc_now())
print(estimate.total)  # 7.5 USD
print(estimate.pricing_hash)  # which price produced that figure
```

Store the `TokenUsage` and the `pricing_hash`, not the money: when a provider changes its prices —
which it does on its own schedule, not yours — history re-costs from the counts instead of being
quietly wrong ([ADR-0030](docs/adr/0030-model-cost-and-pricing.md)).

See [docs/packages/baseaicore/spec.md](docs/packages/baseaicore/spec.md) §7 for the full API and
§20 for the acceptance criteria these examples come from.

## Documentation

This repository carries its own copy of the relevant suite documentation under [`docs/`](docs/README.md),
so it can be read and implemented independently of the other eight suite repositories. Start with
[`docs/README.md`](docs/README.md).

| Read this | For |
|---|---|
| [docs/packages/baseaicore/spec.md](docs/packages/baseaicore/spec.md) | Purpose, scope, non-goals, public contracts, configuration, acceptance criteria |
| [docs/packages/baseaicore/development-plan.md](docs/packages/baseaicore/development-plan.md) | The phased build plan: goals, work, tests, acceptance criteria per phase |
| [docs/standards/](docs/standards/) | Coding, testing, security, API, database and packaging standards every phase follows |
| [docs/adr/](docs/adr/README.md) | The architectural decisions this design rests on |

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
pytest -m "not live and not performance"
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full workflow and [`SECURITY.md`](SECURITY.md) for
how to report a vulnerability.

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
