# Changelog

All notable changes to `baseaicore` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/), pre-1.0 per
`docs/standards/packaging-and-release-standards.md` §3.

## [Unreleased]

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
