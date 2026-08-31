# BaseAiCore — Development Plan

**Sequence position:** first component built in the suite. Nothing else can start meaningfully before Phase 1 completes.
**Target:** `baseaicore 0.4.0` by the end of Phase 4 (version numbering starts at 0.1 and increments per phase).

---

## Phase 1 — Measurement, identity, time and cost primitives

**Goal:** a script can build a canonical model identity, represent an unavailable measurement safely,
generate a sortable ID, and cost a call against a dated price observation — with `baseaicore` as the
only installed suite package.

**Prerequisites:** repository created; CI template; [Coding](../../standards/coding-standards.md) and [Testing](../../standards/testing-standards.md) standards adopted.

**Work**
* Repository skeleton: `pyproject.toml` (hatchling, `src/` layout, `requires-python = ">=3.12"`,
  zero runtime dependencies), ruff/mypy/pytest configuration, `.importlinter`, CI workflow, README, CHANGELOG, LICENSE (Apache-2.0).
* `measurement.py`: `Unsupported`, `UNSUPPORTED`, `Measurement`, `is_supported`, `supported_values`.
* `identity.py`: `ProviderKind`, `IdentityConfidence`, `ModelIdentity`, `canonical_id`,
  `with_digest`, `normalize_digest`. The canonical-ID format is
  `{kind}/{name}@sha256:<12 hex>` or `…@unknown`, fixed by
  [ADR-0024](../../adr/0024-canonical-id-and-model-references.md) — it is a persisted lookup key in
  three databases, so its golden test is the one that must never be "updated to match" a change.
* `ids.py`: ULID `new_id`, `parse_id` → `UlidParts` (a frozen local type; a zero-dependency package
  cannot return a third-party ULID class).
* `timeutil.py`: `utc_now`, `to_rfc3339`, `from_rfc3339`, `Clock`.
* `hashing.py`: `canonical_json`, `sha256_of`.
* `errors.py`: `SuiteError` and subclasses with stable codes.
* `money.py`: `Money` (exact integer nanos in a named currency), `normalize_currency`. No floats, no
  currency conversion — cross-currency arithmetic raises
  ([ADR-0030](../../adr/0030-model-cost-and-pricing.md) §2–3).
* `cost.py`: `TokenCount`, `TokenUsage` (disjoint billable token counts), `PricingSource`,
  `TokenRates` (per **million** tokens, as quoted), `ModelPricing` (a dated, sourced, windowed price
  observation with a `pricing_hash` that excludes `observed_at`), `CostEstimate`, `estimate_cost`.
  Cost is derived from stored usage, never stored as the primary fact, so a price correction
  re-costs history instead of corrupting it (ADR-0030 §1). An absent rate against a non-zero count
  yields `UNSUPPORTED` with a reason — a local model is not a free model (ADR-0030 §6).

**Files/subsystems**
```text
src/baseaicore/{__init__,__about__,measurement,identity,ids,timeutil,hashing,errors,money,cost}.py
tests/unit/{test_measurement,test_identity,test_ids,test_timeutil,test_hashing,test_errors,
            test_money,test_cost}.py
tests/test_packaging.py
```

**Tests**
* Every refused operation on `UNSUPPORTED` raises `TypeError`; singleton survives copy/pickle.
* Identity equality/hash/canonical-ID goldens, including a name containing `/`, `:` and `@`, and
  unicode.
* `normalize_digest`: bare hex, `sha256:`-prefixed, uppercase, wrong length, non-hex, empty and
  `None`, each to the documented result — a value that will not normalize yields `None`, hence a
  `name_only` identity, never a malformed one.
* Digest upgrade produces a new equal-except-digest identity; confidence flips to `DIGEST`.
* ULIDs sort by creation order, are unique across 100 000 generations, and round-trip.
* `from_rfc3339` rejects naive input; `to_rfc3339` always emits millisecond precision with `Z`.
* `canonical_json` byte-identical across repeats; `UNSUPPORTED` serializes to `"unsupported"`; float formatting stable.
* `Money`: exact addition and subtraction, multiplication by a count, ordering, and a
  `ValidationError` from every operator when the currencies differ; `Decimal` round-trip; rounding
  exactly at the half (banker's); malformed currency codes rejected.
* `TokenUsage`: `total_tokens` is `UNSUPPORTED` when any component is; negative counts rejected.
* `pricing_hash` is stable across processes, identical for two records differing only in
  `observed_at`, and different when the tier, the region or any rate changes.
* `estimate_cost`: golden totals for a realistic price list; the total equals the sum of its
  components exactly; an unpriced rate with a **non-zero** count yields an `UNSUPPORTED` total and a
  reason naming the rate; the same rate with a **zero** count yields zero and no reason; an
  unreported token count yields `UNSUPPORTED`; pricing outside its stated window yields
  `UNSUPPORTED`; a naive `at` raises.
* Packaging test: clean-venv install, import, and an assertion that no third-party module is imported.

**Acceptance criteria**
1. `pip install baseaicore && python -c "from baseaicore import ModelIdentity, UNSUPPORTED; …"` works.
2. `UNSUPPORTED or 0` raises rather than yielding `0`.
3. Golden canonical IDs match the values recorded in this plan's test fixtures.
4. A model with no price list costs `UNSUPPORTED`, never `0` — asserted, and asserted again for the
   per-token-class case where only one rate is missing.
5. `mypy --strict`, `ruff`, `lint-imports` all clean; coverage ≥ 95 %.

**Known risks:** ULID implementation correctness (monotonicity within a millisecond); canonical float
formatting differing across platforms; cost arithmetic that rounds each component and then disagrees
with its own total.
**Likely failure modes:** a sentinel that is accidentally falsy in some path; identity strings that
are not URL-safe; ULID collisions under concurrency; a price silently applied outside the window it
was quoted for; cached-token counts double-billed because a provider reports them inside the prompt
count (guarded here by defining `TokenUsage` as disjoint, and caught in ModelRack's conformance suite).
**Gold standards:** zero dependencies; 100 % coverage of this module set; deterministic outputs;
unavailable is never zero, in money as well as in measurement.
**Deferred:** descriptors, runtime profiles, machine profiles, capability IDs; non-token billing
units and price acquisition (both out of scope for this package entirely — ADR-0030).

---

## Phase 2 — Model descriptor, runtime profile and measurement subject

**Goal:** the suite can describe a model, describe how it is being run, and decide whether two measurements are comparable.

**Prerequisites:** Phase 1.

**Work**
* `descriptor.py`: `ModelCapabilityFlag`, `ModelDescriptor` with all architecture fields, `raw` passthrough.
* `runtime.py`: `RuntimeProfile`, `profile_hash` (canonical JSON of non-`None` fields → SHA-256[:16]).
* `subject.py`: `MeasurementSubject`, `MetricKind` (`QUALITY`, `PERFORMANCE`, `MEMORY`, `ENERGY`), `ComparabilityVerdict` (`comparable`, `separate`, `warn`, `indeterminate`) with reasons, implementing the comparability matrix. Benchmark version and dataset hashes are **not** subject fields, so the two matrix rows that turn on them take explicit arguments and yield `indeterminate` when they are not supplied — never `comparable` by default.

**Files/subsystems**
```text
src/baseaicore/{descriptor,runtime,subject}.py
tests/unit/{test_descriptor,test_runtime,test_subject}.py
```

**Tests**
* `profile_hash` stable across field ordering and across processes; `None` fields excluded; nested `provider_options` hashed deterministically.
* Descriptor accepts `UNSUPPORTED` for every optional numeric field; `raw` is preserved untouched.
* Every cell of the comparability matrix from [Canonical Model Identity §5](../../architecture/canonical-model-identity.md) has a test, including quality-across-machines (warn) vs performance-across-machines (separate), and the `indeterminate` result when benchmark arguments are omitted.

**Acceptance criteria**
1. Two `RuntimeProfile`s differing only in `context_size` produce different hashes; identical ones produce the same hash in separate processes.
2. `MeasurementSubject.is_comparable_with` returns the documented verdict and a human-readable reason for every matrix cell.
3. Coverage ≥ 95 %; strict typing clean.

**Known risks:** the comparability rules are judgement calls — encode them as data (a table) so they can be reviewed and changed without rewriting logic.
**Likely failure modes:** hash instability from dict ordering or float repr; verdicts that are correct in code but unexplainable in the UI.
**Gold standards:** the matrix in the architecture document and the table in code are the same table.
**Deferred:** machine profile, capability IDs.

---

## Phase 3 — Machine profile and fingerprint

**Goal:** a machine can be identified stably, and that identity survives a driver upgrade.

**Prerequisites:** Phase 1.

**Work**
* `machine.py`: `GpuVendor`, `GpuProfile`, `StorageDevice`, `MachineProfile`, `compute_machine_fingerprint`.
* Documented inclusion/exclusion policy in the module docstring, with the rationale.

**Files/subsystems**
```text
src/baseaicore/machine.py
tests/unit/test_machine.py
```

**Tests**
* Golden fingerprint for a fixed profile.
* Fingerprint unchanged when driver version, CUDA version, storage or Python version change.
* Fingerprint changes when CPU model, core counts, RAM size or the GPU set changes.
* `UNSUPPORTED` fields hash as `"unsupported"` and still yield a stable fingerprint.
* GPU ordering does not affect the fingerprint (sorted before hashing).

**Acceptance criteria**
1. The exclusion policy is enforced by tests, not only documented.
2. A machine that cannot report its CPU model still produces a stable fingerprint.
3. Coverage ≥ 95 %.

**Known risks:** hostname changes (DHCP, container) fragmenting history — documented, and a `--machine-fingerprint-override` escape hatch is specified for consumers.
**Likely failure modes:** GPU UUID unavailable, making two identical GPUs indistinguishable — handled by including the index and count in that case, with a test.
**Gold standards:** fingerprint stability proven by tests, not asserted in prose.
**Deferred:** collecting the values (SweatMeter's job).

---

## Phase 4 — Capability identifiers and API freeze for 0.4

**Goal:** the vocabulary type exists, the public API is complete for the suite's first consumers, and the package is published.

**Prerequisites:** Phases 1–3.

**Work**
* `capability.py`: `CapabilityId` with syntax validation, `root`, `is_specialization`,
  `inherits_from`. (The vocabulary *contents* and their version live in SetSpec.)
* `__init__.py`: curate the public export surface; everything not exported is private.
* `py.typed` marker; complete docstrings; README with a quickstart; API reference generated from docstrings.
* Publish `0.4.0` to TestPyPI, then PyPI, via Trusted Publishing.

**Files/subsystems**
```text
src/baseaicore/{capability.py,py.typed}
src/baseaicore/__init__.py            # explicit __all__
docs/{quickstart.md,api.md}
```

**Tests**
* Valid IDs: `coding`, `coding.python`, `content.article_draft`. Invalid: empty, leading dot, double dot, uppercase, spaces, trailing dot, over-long.
* `inherits_from` semantics for roots and specializations.
* Public API test: `__all__` matches the documented surface; importing a private module in a test fails the boundary check.
* Install-check job: wheel installs, imports, `py.typed` is present, and mypy sees the types from a consumer project.

**Acceptance criteria**
1. All Phase 1–3 acceptance criteria still pass.
2. `baseaicore 0.4.0` is installable from PyPI and type-checks from a downstream project.
3. Every §20 acceptance criterion in the [spec](spec.md) is met.
4. A downstream consumer (SetSpec, next) can build on it without needing any change here.

**Known risks:** freezing the API before ModelRack and FreeWeight exercise it. Mitigated by `0.x` versioning and by treating the first FreeWeight phase as the real API review.
**Likely failure modes:** a missing `py.typed` silently disabling downstream type checking (covered by a test); an over-broad `__all__` committing us to internals.
**Gold standards:** clean, minimal public API; zero dependencies; deterministic serialization; 95 %+ coverage; documented behaviour.
**Deferred:** LoRA identity, non-token billing units, richer comparability verdicts — all listed as
future extensions in the spec. (Cost types shipped in Phase 1.)
