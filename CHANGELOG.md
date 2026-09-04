# Changelog

All notable changes to `baseaicore` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/), pre-1.0 per
packaging and release standards §3.

## [Unreleased]

### Fixed
- The `UNSUPPORTED` example in `README.md` and `docs/quickstart.md` ran its first line and stopped:
  `UNSUPPORTED or 0` raises, as the comment beside it says, so the two lines demonstrating
  `is_supported` and `supported_values` were unreachable to anyone who pasted the block. The
  refusal is now shown inside a `try`, so the example demonstrates the same thing and runs to
  completion. No behaviour changed. Found by executing every documented snippet in the suite,
  not by reading them.

## [0.4.1] — 2026-09-02

Phase 5 of the [development plan](docs/packages/baseaicore/development-plan.md): the two types the
PromptCadence and Adapter arcs need before any of their code exists, added so additively that no
existing consumer notices. Every pre-existing test and every golden passes unchanged; no signature
changed; `0.4.1` lands inside every existing `>=0.4,<0.5` pin, so no downstream repository needs a
coordinated release to gain them. This release also carries the CI and packaging work done since
`0.4.0`, listed below.

### Added
- `DataClassification`: an ordered three-level vocabulary — `PUBLIC < INTERNAL < CONFIDENTIAL` —
  caller-declared, with the lattice join being the built-in `max()` (ADR-0046).
  Ordering is by **rank**, never by the member's string value: alphabetically
  `"confidential" < "internal" < "public"`, which is exactly backwards, so the four ordering
  operators are defined rather than inherited and comparing against a non-member **raises** rather
  than falling back to string ordering. Not an `IntEnum`, so `PUBLIC` is never falsy. Every ordered
  pair is golden-tested; adding a level is a new ADR, because the ordering is the contract.
- `AdapterIdentity(name, artifact_digest, source_digest=None)`: a LoRA adapter named by the sha256
  of the **served** artifact, so renaming the file changes nothing and changing its content makes a
  new subject. `artifact_digest` is required — a malformed one is refused, never degraded to
  `name_only` — and `source_digest` is lineage, excluded from equality, hashing and comparability.
  Exposes `digest_short` and `canonical_suffix`.
- `verify_adapter_base_compatibility(...) -> IdentityConfidence`: base compatibility checked by
  digest and **failing closed**. A mismatch is a refusal, a declared digest against a base that
  exposes none cannot be verified and is also a refusal, and a name-only declaration returns
  `NAME_ONLY` — reusing the existing confidence machinery rather than a parallel flag.
- `MeasurementSubject.adapter`: a keyword-only optional adapter axis, and
  `MeasurementSubject.canonical_subject_id`, which appends the adapter's `+name@sha256:…` suffix.
  **With no adapter it is byte-for-byte the model identity's canonical ID** — asserted against
  every row of ADR-0024's golden table, which is the additive proof (ADR-0058).
- `requirements/ci.lock` and `requirements/release.lock`: exact, hash-verified pins for this
  repository's own CI and release pipeline, required by Packaging and Release Standards §4 and
  Security Standards §11. `requirements/README.md` documents what they are for, what they are
  deliberately *not* for (a consumer still resolves the ranges in `pyproject.toml`), and how to
  regenerate them.

### Changed
- `MeasurementSubject.is_comparable_with` gains one matrix row: a differing `adapter` — including
  one bare subject and one adapted — yields `separate`, exactly as a differing runtime profile
  does. Adapter evidence is measured, never inherited, so those are different subjects. Two
  adapter-free subjects are unaffected, which is why every measurement taken before this release
  compares exactly as it did.
- CI and the release workflow install the locked sets instead of re-resolving on every run, and
  build with `--no-isolation` so the build backend comes from `release.lock` too. The Python 3.14
  early-warning job still resolves from ranges, because pinning versions that have no 3.14 wheels
  would defeat the point of an early warning.
- CI installs the built distribution rather than an editable checkout, per Packaging Standards §4.
  Coverage is therefore configured by importable name with a `paths` mapping, so it measures the
  package wherever it is installed; the previous source-path configuration silently reported 0%
  against a non-editable install.
- The `security` job now runs `pip-audit` against both lockfiles. It previously ran bare, which
  audited an environment containing only `pip-audit` itself and could never have reported anything.

### Security
- `pytest` moved from `>=8,<9` to `>=9.0.3,<10`, excluding PYSEC-2026-1845 (vulnerable
  `/tmp/pytest-of-{user}` handling, local denial of service or privilege escalation, affecting
  pytest through 9.0.2). Found by auditing the new lockfile; the suite passes unchanged on
  pytest 9.

## [0.4.0] — 2026-08-22

Phase 4 of the [development plan](docs/packages/baseaicore/development-plan.md): capability
identifiers and the API freeze — the vocabulary type exists, the public API is complete for the
suite's first consumers, and the package is ready to publish. This completes BaseAiCore's
development plan.

### Added
- `capability`: `CapabilityId`, a syntactically validated vocabulary term (`root[.specialization]*`,
  lowercase `[a-z][a-z0-9_]*` segments joined by `.`, at most 64 characters), with `root`,
  `is_specialization` and `inherits_from` implementing the specialization-inheritance relationship
  ([spec §7](docs/packages/baseaicore/spec.md)). The vocabulary's *contents* and their version
  remain SetSpec's; this package owns only the shape.
- `docs/quickstart.md`: a guided, executable walk through every public type.
- `docs/api.md`: an API reference generated from the live public docstrings by the new
  `scripts/generate_api_reference.py` (stdlib-only, matching the zero-dependency policy).

### Changed
- `baseaicore.__init__` now curates and exports the **complete** public surface: the Phase 2–3
  types (`ModelDescriptor`, `ModelCapabilityFlag`, `RuntimeProfile`, `MeasurementSubject`,
  `MetricKind`, `Comparability`, `ComparabilityVerdict`, `GpuProfile`, `GpuVendor`,
  `MachineProfile`, `StorageDevice`, `compute_machine_fingerprint`) and the new `CapabilityId` are
  all importable directly from `baseaicore`, ending the "import from the submodule" stopgap that
  0.1.0–0.3.0 documented.
- README and `docs/packages/baseaicore/spec.md` updated to reflect the completed development plan.

### Notes
- `inherits_from` is reflexive by design: `x.inherits_from(x)` is `True`, so a task profile
  requiring exactly one capability is satisfied by evidence recorded against that capability
  itself, with no special case at the call site. A specialization inherits from every ancestor
  along its dotted path; a root never inherits from its own specialization.
- The 64-character length ceiling is this package's own choice, not one fixed by an ADR or the
  spec — the spec only requires that "over-long" be refused with one documented, tested meaning.
- A public-API boundary test (`tests/test_packaging.py`) now asserts that a module-private helper
  (e.g. `errors._rebuild_error`) is *not* reachable from the package root, proving the curation
  claim rather than trusting it.
- 100 % line and branch coverage; `mypy --strict`, `ruff` and `import-linter` clean across the
  repository.
- Not yet done: publishing `0.4.0` to TestPyPI and PyPI via Trusted Publishing. That is a tag-push
  (`git tag -a v0.4.0 && git push --tags`), which triggers `.github/workflows/release.yml` — a
  real, externally visible action this change does not take on its own
  (Packaging and Release Standards §6).

## [0.3.0] — 2026-08-22

Phase 3 of the [development plan](docs/packages/baseaicore/development-plan.md): machine identity —
a machine can be identified stably, and that identity survives a driver upgrade.

### Added
- `machine`: `GpuVendor`, `GpuProfile`, `StorageDevice`, `MachineProfile` and
  `compute_machine_fingerprint`, implementing
  Machine Identity §1–3. The
  fingerprint is 64 hex characters over the canonical JSON of hostname, OS name, architecture, CPU
  model, core counts, RAM size and the GPU set.
- The inclusion/exclusion policy is documented in the module docstring **and** asserted by tests:
  a driver, CUDA, OS-version, kernel, Python-version or storage change leaves the fingerprint
  untouched; a CPU, core-count, RAM or GPU-set change does not.

### Notes
- Unreported fields hash as the literal `"unsupported"`, whether they arrived as `None` (strings)
  or as `UNSUPPORTED` (quantities), so a machine that cannot report its CPU model still has exactly
  one stable identity (ADR-0016).
- Two normalizations exist solely to stop one machine from having two identities: surrounding
  whitespace is stripped, and a whole-valued `float` quantity hashes as the equal `int`. Both are
  tested. This is deliberately the opposite of the rule for a *model* name, which must round-trip
  to its provider byte-exactly and is therefore never touched.
- GPU entries are sorted before hashing, so enumeration order does not identify a machine. A GPU
  that reports no UUID contributes its index as well, so two identical unidentified cards do not
  collapse into one — the documented trade-off is that re-enumeration re-identifies such a machine.
- `MachineProfile.machine_fingerprint` is the *recorded* fingerprint and is never re-derived: a
  profile read back years later must reconstruct as it was written, including after a policy change.
- The golden fingerprint test joins the canonical-ID golden as a value that must never be "updated
  to match" a change — it is a persisted key in three databases.
- Performance budgets from [spec §15](docs/packages/baseaicore/spec.md) now have tests for
  `compute_machine_fingerprint` (measured ~15 µs against a 100 µs budget) and for
  `RuntimeProfile.profile_hash`, which had been missed in 0.2.0 (gold standard G19).
- 100 % line and branch coverage; `mypy --strict`, `ruff` and `import-linter` clean.
- Not yet exported from `baseaicore.__init__`: curating the public surface is Phase 4 work, so
  these types are imported directly (`from baseaicore.machine import MachineProfile`).

## [0.2.0] — 2026-08-22

Phase 2 of the [development plan](docs/packages/baseaicore/development-plan.md): the model
descriptor, the runtime profile and the measurement subject — the suite can now describe a model,
describe how it is being run, and decide whether two measurements are comparable.

### Added
- `descriptor`: `ModelCapabilityFlag` and `ModelDescriptor` — refreshable architecture metadata
  (family, quantization, layer/head counts, …) kept separate from `ModelIdentity`. Every optional
  numeric field accepts `UNSUPPORTED`; `raw` is preserved untouched
  (Canonical Model Identity §3).
- `runtime`: `RuntimeProfile` and its `profile_hash` — SHA-256 over the canonical JSON of every
  non-`None` field, stable across processes and independent of field-construction order
  (ADR-0023).
- `subject`: `MetricKind`, `Comparability`, `ComparabilityVerdict` and `MeasurementSubject` with
  `is_comparable_with`, implementing the full comparability matrix from
  Canonical Model Identity §5. Benchmark version
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
  number (ADR-0016).
- `identity`: `ProviderKind`, `IdentityConfidence`, `ModelIdentity`, `normalize_digest`. The
  canonical-ID format `{kind}/{name}@sha256:<12 hex>` is fixed by golden tests
  (ADR-0024).
- `money`: `Money` as exact integer nanos in a named currency, and `normalize_currency`. No floats;
  cross-currency arithmetic and comparison raise rather than assuming an exchange rate.
- `cost`: `TokenUsage`, `PricingSource`, `TokenRates`, `ModelPricing`, `CostEstimate` and
  `estimate_cost`. A price is a dated, sourced observation with a validity window and a stable
  `pricing_hash`; an unknown price costs `UNSUPPORTED` with a reason, never zero
  (ADR-0030, new in this release).
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
