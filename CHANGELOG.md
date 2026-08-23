# Changelog

All notable changes to `baseaicore` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/), pre-1.0 per
`docs/standards/packaging-and-release-standards.md` §3.

## [Unreleased]

## [0.2.0] — 2026-08-22

Phase 2 of the [development plan](docs/packages/baseaicore/development-plan.md): the model
descriptor, the runtime profile and the measurement subject — the suite can now describe a model,
describe how it is being run, and decide whether two measurements are comparable.

### Added
- `descriptor`: `ModelCapabilityFlag` and `ModelDescriptor` — refreshable architecture metadata
  (family, quantization, layer/head counts, …) kept separate from `ModelIdentity`. Every optional
  numeric field accepts `UNSUPPORTED`; `raw` is preserved untouched
  ([Canonical Model Identity](docs/architecture/canonical-model-identity.md) §3).
- `runtime`: `RuntimeProfile` and its `profile_hash` — SHA-256 over the canonical JSON of every
  non-`None` field, stable across processes and independent of field-construction order
  ([ADR-0023](docs/adr/0023-runtime-profile-resolution.md)).
- `subject`: `MetricKind`, `Comparability`, `ComparabilityVerdict` and `MeasurementSubject` with
  `is_comparable_with`, implementing the full comparability matrix from
  [Canonical Model Identity §5](docs/architecture/canonical-model-identity.md). Benchmark version
  and dataset hashes are not subject fields; omitting them yields `indeterminate`, never
  `comparable` by default.

### Notes
- 100 % line and branch coverage on the new modules; `mypy --strict`, `ruff` and `import-linter`
  clean across the repository.
- Not yet exported from `baseaicore.__init__`: curating the public surface is Phase 4 work, so
  these three modules are implemented but still imported directly
  (`from baseaicore.descriptor import ModelDescriptor`, etc.) rather than from the package root.
- Machine profile and capability IDs arrive in Phases 3–4.

## [0.1.0] — 2026-08-22

Phase 1 of the [development plan](docs/packages/baseaicore/development-plan.md): measurement,
identity, IDs, time, hashing, errors — plus money and cost, brought forward into this phase.

### Added
- `measurement`: the `Unsupported` sentinel and its `UNSUPPORTED` singleton, the `Measurement`
  type, `is_supported` and `supported_values`. Every numeric, truthiness and ordering operation on
  the sentinel raises, so `value or 0` cannot turn an absent measurement into a real-looking
  number ([ADR-0016](docs/adr/0016-unavailable-is-not-zero.md)).
- `identity`: `ProviderKind`, `IdentityConfidence`, `ModelIdentity`, `normalize_digest`. The
  canonical-ID format `{kind}/{name}@sha256:<12 hex>` is fixed by golden tests
  ([ADR-0024](docs/adr/0024-canonical-id-and-model-references.md)).
- `money`: `Money` as exact integer nanos in a named currency, and `normalize_currency`. No floats;
  cross-currency arithmetic and comparison raise rather than assuming an exchange rate.
- `cost`: `TokenUsage`, `PricingSource`, `TokenRates`, `ModelPricing`, `CostEstimate` and
  `estimate_cost`. A price is a dated, sourced observation with a validity window and a stable
  `pricing_hash`; an unknown price costs `UNSUPPORTED` with a reason, never zero
  ([ADR-0030](docs/adr/0030-model-cost-and-pricing.md), new in this release).
- `ids`: `UlidGenerator`, `new_id`, `parse_id`, `UlidParts` — monotonic within a millisecond and
  thread-safe, with no third-party ULID dependency.
- `timeutil`: `utc_now`, `to_rfc3339`, `from_rfc3339`, the `Clock` type, `monotonic_ns` and
  `elapsed_ms`. Timestamps and durations are separate and never interchanged.
- `hashing`: `canonical_json` and `sha256_of`, byte-identical across processes and platforms.
- `errors`: `SuiteError` and its seven subclasses, each with a stable `code`.

### Notes
- Zero runtime dependencies, asserted by a test rather than by convention.
- 100 % line and branch coverage; `mypy --strict`, `ruff` and `import-linter` clean.
- Descriptors, runtime profiles, measurement subjects, machine profiles and capability IDs arrive
  in Phases 2–4 and are not exported yet.

## [0.0.0]

### Added
- Repository scaffold generated from the suite's development plan (no functional code yet).
