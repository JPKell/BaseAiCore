# Quickstart

`baseaicore` has zero runtime dependencies. Everything below runs with nothing installed beyond
the package itself.

```bash
pip install baseaicore
```

## 1. Identify a model

A `ModelIdentity` answers exactly one question — which weights, served by which kind of
provider — and nothing else. Its `canonical_id` is a stable, human-readable string safe to log,
store and use as a lookup key.

```python
from baseaicore import ModelIdentity, ProviderKind, normalize_digest

identity = ModelIdentity(
    ProviderKind.OLLAMA,
    "qwen3.5:9b-q8_0",
    normalize_digest("1f3a9c4e2b70a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f607182930"),
)
print(identity.canonical_id)        # ollama/qwen3.5:9b-q8_0@sha256:1f3a9c4e2b70
print(identity.identity_confidence)  # IdentityConfidence.DIGEST
```

`normalize_digest` accepts whatever shape a provider happens to report (bare hex, `sha256:`
prefixed, uppercase, padded) and returns `None` when the value cannot be trusted — which yields a
`name_only` identity, never a malformed one.

## 2. Describe how it was run

`RuntimeProfile` records the load/serve options that can change a measurement's meaning
(context size, GPU layers, quantization, …) and hashes to a stable key so two runs can be told
apart — or recognized as the same — without comparing every field by hand.

```python
from baseaicore import RuntimeProfile

profile = RuntimeProfile(context_size=8192, gpu_layers=999, flash_attention=True)
print(profile.profile_hash)  # stable across processes; independent of field-construction order
```

## 3. Decide whether two measurements are comparable

A `MeasurementSubject` is keyed by the *hashes*, not the objects themselves — the same
`runtime_profile_hash` and `machine_fingerprint` that get stored alongside every result.

```python
from baseaicore import MeasurementSubject, MetricKind

other_profile = RuntimeProfile(context_size=4096)
subject_a = MeasurementSubject(identity, profile.profile_hash, "fingerprint-a")
subject_b = MeasurementSubject(identity, other_profile.profile_hash, "fingerprint-a")

verdict = subject_a.is_comparable_with(subject_b, metric_kind=MetricKind.QUALITY)
print(verdict.comparability, verdict.reason)  # Comparability.SEPARATE, "different runtime profile"
```

A quality metric survives a runtime-profile change (`comparable`); a performance metric across the
same change does not (`separate`) — the matrix is documented in
Canonical Model Identity §5 and enforced by tests, not
by convention.

## 4. Name a capability

`CapabilityId` validates the *shape* of a vocabulary term — the terms themselves, and their
version, come from SetSpec.

```python
from baseaicore import CapabilityId

capability = CapabilityId("coding.python")
print(capability.root)               # "coding"
print(capability.is_specialization)  # True

general = CapabilityId("coding")
print(capability.inherits_from(general))  # True: a Python-coding result also satisfies "coding"
print(general.inherits_from(capability))  # False: the reverse does not hold
```

## 5. Never let an absent measurement look like a zero

```python
from baseaicore import UNSUPPORTED, is_supported, supported_values

UNSUPPORTED or 0                       # raises TypeError -- not 0
is_supported(UNSUPPORTED)              # False
supported_values([12.5, UNSUPPORTED, 9.0])  # [12.5, 9.0]
```

The same rule governs money: a price is a dated, sourced observation, not a property of the model,
and a model with no price costs *unknown*, never *free*.

```python
from baseaicore import ModelPricing, Money, PricingSource, TokenRates, TokenUsage, estimate_cost, utc_now

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
print(estimate.total)         # 7.5 USD
print(estimate.pricing_hash)  # which price produced that figure -- store this, not the money
```

## 6. Fingerprint the machine

The fingerprint is computed directly from the identity-bearing fields; a `MachineProfile` then
carries that already-computed value alongside the rest of the snapshot, so it never has to be
re-derived to prove it was not tampered with in storage.

```python
from baseaicore import GpuProfile, GpuVendor, MachineProfile, compute_machine_fingerprint

gpu = GpuProfile(index=0, name="NVIDIA GeForce RTX 4090", uuid="GPU-1234", vendor=GpuVendor.NVIDIA)

fingerprint = compute_machine_fingerprint(
    hostname="workbench",
    os_name="Linux",
    architecture="x86_64",
    cpu_model="AMD Ryzen 9 7950X",
    physical_cores=16,
    logical_cores=32,
    ram_bytes=64 * 1024**3,
    gpus=[gpu],
)

profile = MachineProfile(
    machine_fingerprint=fingerprint,
    hostname="workbench",
    os_name="Linux",
    os_version="Ubuntu 26.04 LTS",
    kernel="6.8.0",
    architecture="x86_64",
    cpu_model="AMD Ryzen 9 7950X",
    physical_cores=16,
    logical_cores=32,
    ram_bytes=64 * 1024**3,
    gpus=(gpu,),
)
```

A driver upgrade, a CUDA-toolkit bump or a storage change never changes this value; a different
CPU, core count, RAM size or GPU set always does — both directions are asserted by tests, not only
documented.

## Where to go next

* [API reference](api.md) — every public symbol, generated from its docstring.
* [Specification](packages/baseaicore/spec.md) — purpose, scope, contracts, acceptance criteria.
* [Development plan](packages/baseaicore/development-plan.md) — the phased build history.
