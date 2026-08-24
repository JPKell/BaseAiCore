# API Reference

Generated from the public docstrings in `baseaicore.__all__` by [`scripts/generate_api_reference.py`](../scripts/generate_api_reference.py). Do not hand-edit — regenerate instead.

`baseaicore 0.4.0` — 55 public symbols.

### `CapabilityId`

Defined in `baseaicore.capability`.

A syntactically validated vocabulary term identifying a capability, generic or specialized.

Immutable and hashable, so it can be a dictionary key or a set member. Two identifiers are
equal, and hash equal, if and only if their ``value`` strings are equal.

This type has no opinion on which terms exist or what they mean — it only proves that a
string is a legal capability ID and computes the two syntactic relationships (root,
specialization) that hold regardless of vocabulary contents. Whether ``coding.python`` is a
real, current vocabulary term is SetSpec's question, not this one's.

Attributes:
    value: The full dotted identifier, exactly as constructed, e.g. ``"coding"`` or
        ``"content.article_draft"``. This is the string form; there is no separate
        serialization because a capability ID has no representation that is not the string it
        was built from.

| Member | Kind | Summary |
|---|---|---|
| `inherits_from` | method(self, other: 'CapabilityId') -> 'bool' | Return whether ``other`` names this identifier or one of its ancestors. |
| `is_specialization` | property | Whether this identifier narrows a root with at least one further segment. |
| `root` | property | The first, most general segment — itself a legal ``CapabilityId`` value. |

### `Clock`

Defined in `baseaicore.timeutil`.

Value: `Clock` (`TypeAliasType`)

### `Comparability`

Defined in `baseaicore.subject`.

The four possible outcomes of a comparability check.

``COMPARABLE`` alone means safe to merge or average directly. ``SEPARATE`` and ``WARN`` are
both "yes, but": ``SEPARATE`` means the two measurements may be shown side by side as an
explicit, never-merged comparison (a runtime-profile or quantization study, or two results
from different benchmark versions); ``WARN`` means direct comparison is allowed but the result
carries a caveat the UI must show (a cross-machine quality comparison, or a ``name_only``
identity across a gap in time). ``INDETERMINATE`` means this check was not given enough
information to answer at all — never treated as ``COMPARABLE`` by default.

### `ComparabilityVerdict`

Defined in `baseaicore.subject`.

The result of a comparability check: a categorical outcome plus why.

The reason is not decoration — it is what a UI shows next to the outcome, and what a
regression-detection job logs when it refuses to compare two results.

Attributes:
    comparability: The categorical outcome.
    reason: One human-readable sentence naming the matrix row that produced this outcome.

### `ConfigurationError`

Defined in `baseaicore.errors`.

Configuration is absent, malformed, or internally contradictory.

### `ConflictError`

Defined in `baseaicore.errors`.

The operation contradicts existing state — a uniqueness violation or a lost update.

### `CostEstimate`

Defined in `baseaicore.cost`.

What a call is estimated to have cost, and everything needed to judge that estimate.

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

| Member | Kind | Summary |
|---|---|---|
| `is_complete` | property | Report whether every used token class could be priced, making the total a real amount. |

### `DependencyUnavailableError`

Defined in `baseaicore.errors`.

A required external dependency — a provider, a database, a device — is unreachable.

### `GpuProfile`

Defined in `baseaicore.machine`.

Static identity of one GPU, as a collector reported it.

Immutable. Only ``name``, ``uuid`` and — when the UUID is missing — ``index`` contribute to the
machine fingerprint; see :func:`compute_machine_fingerprint` and this module's policy table for
why the driver and toolkit versions do not.

Attributes:
    index: The device's enumeration position, ``0``-based. Also the value FreeWeight and
        LoadCoach attribute a per-device measurement to
        (ADR-0027).
    uuid: The device's stable hardware identifier, unchanged across reboots and across
        re-enumeration. This is the GPU's real identity; ``index`` is only where it happened to
        be enumerated this boot. ``None`` when the collector could not read one.
    name: The marketing name, e.g. ``"NVIDIA GeForce RTX 5060 Ti"``.
    vram_total_bytes: Total device memory. Total, never used — used memory is telemetry.
    driver_version: The installed driver version. A drift signal, not identity.
    cuda_version: The CUDA/ROCm toolkit version. A drift signal, not identity.
    compute_capability: The device's compute capability, e.g. ``"12.0"``.
    vendor: Who makes the device.

### `GpuVendor`

Defined in `baseaicore.machine`.

Who makes the device, which decides which telemetry interface can read it.

``UNKNOWN`` is the honest default rather than a guess: a device the collector could not
attribute is not an NVIDIA device by assumption. It is not part of the machine fingerprint —
the GPU's name already pins the model, and a collector that improved its vendor detection must
not thereby re-identify the machine.

### `IdentityConfidence`

Defined in `baseaicore.identity`.

How firmly an identity pins down a specific set of weights.

Stored alongside every measurement. A ``NAME_ONLY`` result carries a permanent caveat: the
provider exposed no digest, so it can never be proven later to describe the same weights —
a tag such as ``qwen3.5:latest`` can be repointed at any time. LoadCoach reduces evidence
confidence for it and FreeWeight shows it in the UI
(ADR-0017).

### `MachineProfile`

Defined in `baseaicore.machine`.

The static identity of one machine, persisted once per fingerprint.

Immutable. Every field other than ``machine_fingerprint`` is optional in the sense that a
collector may be unable to read it: strings that were not reported are ``None`` and quantities
that were not reported are :data:`~baseaicore.measurement.UNSUPPORTED`, and both hash as
``"unsupported"`` so a machine that cannot describe itself fully still has one stable identity.

``machine_fingerprint`` is the *recorded* fingerprint, not a derived property. It is neither
computed nor re-verified in ``__post_init__``, and that is deliberate: a profile read back from
a database years later must reconstruct exactly as it was written, including the case where the
inclusion policy has since changed. SweatMeter computes it once, with
:func:`compute_machine_fingerprint`, at the moment it collects the fields.

Attributes:
    machine_fingerprint: The identity this profile was stored under.
    hostname: The machine's hostname. Part of the fingerprint — see the module docstring's note
        on hostname churn.
    os_name: e.g. ``"Linux"``.
    os_version: e.g. ``"Ubuntu 26.04 LTS"``. A drift signal, not identity.
    kernel: The kernel release string. A drift signal, not identity.
    architecture: e.g. ``"x86_64"``.
    cpu_model: The CPU's model string.
    physical_cores: Physical core count.
    logical_cores: Logical core count, hyperthreads included.
    ram_bytes: Total system memory.
    gpus: Every visible GPU. A tuple, and never summed across
        (ADR-0027).
    storage: Attached storage devices. Provenance only; excluded from the fingerprint.
    python_version: The interpreter that produced the measurement. Application environment
        rather than machine identity, so it is recorded here and excluded from the fingerprint.
    observed_at: When this snapshot was taken. Timezone-aware, UTC.

### `Measurement`

Defined in `baseaicore.measurement`.

Value: `Measurement` (`TypeAliasType`)

### `MeasurementSubject`

Defined in `baseaicore.subject`.

What one measurement was actually measured against: weights, runtime, machine.

A measurement is never stored without its full subject (`Canonical Model Identity` §5, Rule
3). The subject deliberately excludes the benchmark version and the dataset hash — those
describe the *test*, not the *thing being tested* — which is why
:meth:`is_comparable_with` takes them as separate arguments rather than storing them here.

Attributes:
    identity: Which weights were measured.
    runtime_profile_hash: :attr:`~baseaicore.runtime.RuntimeProfile.profile_hash` of the
        profile the model was served under.
    machine_fingerprint: :func:`~baseaicore.machine.compute_machine_fingerprint` of the
        machine the measurement ran on.

| Member | Kind | Summary |
|---|---|---|
| `is_comparable_with` | method(self, other: 'MeasurementSubject', *, metric_kind: 'MetricKind', benchmark_version: 'str | None' = None, other_benchmark_version: 'str | None' = None, dataset_hashes: 'Mapping[str, str] | None' = None, other_dataset_hashes: 'Mapping[str, str] | None' = None) -> 'ComparabilityVerdict' | Decide whether a measurement on this subject may be compared with one on ``other``. |

### `MetricKind`

Defined in `baseaicore.subject`.

The class of metric being compared, because comparability differs by class.

A quality metric survives a machine change — the same weights answer the same question the
same way. Performance, memory and energy metrics do not: they measure the hardware as much as
the model (`Canonical Model Identity §5`, row 3).

### `ModelCapabilityFlag`

Defined in `baseaicore.descriptor`.

A capability a provider *claims* a model has, distinct from a measured capability.

FreeWeight's benchmark results record what a model can *demonstrably* do; this flag records
only what the provider *says* it can do. The two are never conflated
(canonical model identity §3).

### `ModelDescriptor`

Defined in `baseaicore.descriptor`.

Descriptive facts about a model, as reported by a provider at a point in time.

Refreshable, unlike :class:`~baseaicore.identity.ModelIdentity`: a provider's own account of a
model's architecture can be re-read at any time, and each reading is its own descriptor rather
than a mutation of the last one.

The architecture fields (``layers``, ``kv_heads``, ``head_dim``, …) are load-bearing:
FreeWeight's KV-cache benchmark computes a theoretical bytes-per-token from them and compares
it against the observed VRAM slope. A field the provider did not report makes that benchmark
return :data:`~baseaicore.measurement.UNSUPPORTED`, never a wrong number built from a guess.

Attributes:
    identity: The weights this descriptor describes.
    observed_at: When this snapshot was read from the provider. Timezone-aware, UTC.
    family: The model family name, e.g. ``"qwen3.5"``.
    architecture: The architecture name, e.g. ``"transformer"``, ``"mamba"``.
    parameter_count: Total parameter count.
    active_parameter_count: MoE active parameters per token; equal to ``parameter_count`` for
        a dense model.
    expert_count: Number of experts, for a mixture-of-experts model.
    quantization: Weight quantization, e.g. ``"Q8_0"``.
    weight_format: File format, e.g. ``"gguf"``, ``"safetensors"``.
    size_bytes: On-disk size of the weights.
    max_context: The context length the model *advertises*. Not the context a provider is
        actually configured to serve — that is a runtime concern, ``served_context``
        (ADR-0023 §4).
    embedding_dim: Hidden/embedding dimension.
    layers: Transformer layer count.
    attention_heads: Attention head count.
    kv_heads: Key/value head count (equal to ``attention_heads`` without grouped-query
        attention).
    head_dim: Dimension of each attention head.
    vocab_size: Tokenizer vocabulary size.
    rope_config: RoPE scaling configuration, in the provider's own shape.
    sliding_window: Sliding-attention window size, if the architecture uses one.
    declared_capabilities: What the provider claims this model can do.
    license_text: The model's license, if the provider exposes one.
    raw: The untouched provider response. Preserved for diagnostics and for extracting fields
        the normalizer does not yet know about. Nothing above ModelRack may read this for
        business logic (canonical model identity §3).

### `ModelIdentity`

Defined in `baseaicore.identity`.

Immutable name of one set of weights as exposed by one kind of provider.

Two identities are equal — and hash equal — if and only if all three fields are equal. That
equality is stable across processes, machines and Python versions, because it is built from
plain strings and nothing else.

Explicitly excluded, and each for a reason: the endpoint URL and hostname (deployment detail),
the file path (machine-local), quantization and parameter count (descriptive metadata that the
name usually encodes but the descriptor owns), any measurement, and any user-assigned label.

Attributes:
    provider_kind: Which kind of provider serves these weights.
    provider_model_name: Exactly as the provider names it, case and punctuation preserved, so
        it round-trips back to the provider unchanged. It may legitimately contain ``/``,
        ``:`` and ``@`` (``hf.co/user/repo:q4``), which is why the canonical ID is never
        parsed to recover it and never used as a URL path segment.
    artifact_digest: ``"sha256:"`` + 64 lowercase hex characters when the provider exposes
        one, else ``None``. The only field that survives a retag, and therefore the only thing
        that makes a comparison across two weeks honest. Pass it through
        :func:`normalize_digest` first.

| Member | Kind | Summary |
|---|---|---|
| `canonical_id` | property | Return the stable, human-readable identity string. |
| `identity_confidence` | property | Whether this identity pins the exact weights or only the name they were served under. |
| `with_digest` | method(self, digest: 'str') -> 'ModelIdentity' | Return the same identity with its artifact digest set. |

### `ModelPricing`

Defined in `baseaicore.cost`.

One observation of what one model costs, with provenance and a validity window.

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

| Member | Kind | Summary |
|---|---|---|
| `is_effective_at` | method(self, when: 'datetime') -> 'bool' | Report whether this price applies at a given instant. |
| `pricing_hash` | property | Return a stable 16-character identifier for **the price**, not for the reading of it. |

### `Money`

Defined in `baseaicore.money`.

An exact amount in one currency, stored as whole nanos.

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

| Member | Kind | Summary |
|---|---|---|
| `as_canonical` | method(self) -> 'dict[str, Any]' | Return the mapping form used inside canonical JSON and therefore inside every hash. |
| `to_decimal` | method(self) -> 'Decimal' | Return the amount in whole currency units, exactly. |

### `NANOS_PER_UNIT`

Defined in `baseaicore.money`.

Value: `1000000000` (`int`)

### `NotFoundError`

Defined in `baseaicore.errors`.

A named entity does not exist.

### `PricingSource`

Defined in `baseaicore.cost`.

Where a price came from, and therefore how much weight it carries.

The distinction is not bookkeeping: a rate the provider returned alongside the response and a
rate somebody copied out of a documentation page six months ago are different epistemic
objects, and a consumer deciding whether to show a cost — or to route on it — needs to tell
them apart.

### `ProviderKind`

Defined in `baseaicore.identity`.

The kind of provider serving a model — not the endpoint it is served from.

Kind rather than address, because the same weights served by Ollama and by vLLM behave
differently enough (templating, sampling defaults, KV handling) that their measurements are
not interchangeable, while a port or hostname change is a deployment detail that must not
fragment a model's history.

Adding a member is a backwards-compatible change; renaming one is not, because the value is
persisted and appears in every canonical ID.

### `RandomnessSource`

Defined in `baseaicore.ids`.

The randomness a :class:`UlidGenerator` draws its 80 random bits from.

Satisfied by :class:`random.SystemRandom` (the default), by :class:`random.Random` seeded for
a reproducible test, and by anything else offering the same method.

| Member | Kind | Summary |
|---|---|---|
| `randbytes` | method(self, n: 'int', /) -> 'bytes' | Return ``n`` random bytes. |

### `RuntimeProfile`

Defined in `baseaicore.runtime`.

How a provider is asked to load and serve a model. Hashes to a stable key.

Every field is optional: ``RuntimeProfile()`` with everything at its default means "provider
defaults" and is itself a legal, hashable profile — there is no "no profile" state
(ADR-0023 §1).

Immutable and hashable. ``profile_hash`` is computed lazily and cached on the instance.

Attributes:
    context_size: Requested context window, in tokens.
    kv_cache_precision: KV-cache quantization, e.g. ``"f16"``, ``"q8_0"``, ``"q4_0"``.
    gpu_layers: Number of layers offloaded to GPU.
    flash_attention: Whether flash attention is requested.
    threads: CPU thread count requested.
    batch_size: Requested batch size.
    keep_alive: How long the provider is asked to keep the model loaded, e.g. ``"5m"``.
    provider_options: Anything provider-specific that does not have its own field. Hashed
        deterministically like every other field, nested mappings included, so two profiles
        differing only in one nested option hash differently.

| Member | Kind | Summary |
|---|---|---|
| `profile_hash` | property | Return a stable 16-character identifier for this runtime profile. |

### `StorageDevice`

Defined in `baseaicore.machine`.

A storage device attached to the machine.

Recorded as provenance — a benchmark that loaded weights from a spinning disk explains its own
cold-start timings — and deliberately excluded from the machine fingerprint, because plugging
in a disk does not make a machine a different machine.

Attributes:
    name: The device name as the OS exposes it, e.g. ``"nvme0n1"``.
    size_bytes: Total capacity.
    model: The device's model string, if the OS exposes one.
    rotational: ``True`` for a spinning disk, ``False`` for solid state, ``None`` when the
        collector could not tell. ``None`` rather than a default of ``False``: guessing here
        would attribute a cold-load time to the wrong cause.

### `SuiteError`

Defined in `baseaicore.errors`.

Base for every error raised anywhere in the suite.

Carries a stable ``code`` and an optional ``details`` mapping. ``details`` is structured
context for the caller to log or render — it is never formatted into the message, because a
message is for humans and ``details`` is for machines, and mixing the two produces log lines
that cannot be aggregated.

``details`` must never contain a secret, a prompt or generated content
(security standards); it travels into API error envelopes.

Attributes:
    code: Stable machine-readable identifier, shared by every instance of the class.
    message: The human-readable description passed at construction.
    details: A shallow copy of the mapping passed at construction, or an empty mapping. The
        copy exists so a caller mutating its own dict afterwards cannot change a raised error.

### `TOKENS_PER_RATE_UNIT`

Defined in `baseaicore`.

Value: `1000000` (`int`)

### `TokenCount`

Defined in `baseaicore.cost`.

Value: `TokenCount` (`TypeAliasType`)

### `TokenRates`

Defined in `baseaicore.cost`.

Per-million-token prices for each billable token class, in one currency.

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

| Member | Kind | Summary |
|---|---|---|
| `as_canonical` | method(self) -> 'dict[str, Any]' | Return the mapping form used inside :attr:`ModelPricing.pricing_hash`. |
| `rate_for` | method(self, token_class: 'str') -> 'Money | Unsupported' | Return the rate for one token class. |

### `TokenUsage`

Defined in `baseaicore.cost`.

The billable token counts of one model call.

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

| Member | Kind | Summary |
|---|---|---|
| `as_counts` | method(self) -> 'dict[str, TokenCount]' | Return the four counts keyed by token class, in the suite's canonical class order. |
| `total_tokens` | property | Return the total across all four classes. |

### `UNSUPPORTED`

Defined in `baseaicore.measurement`.

Value: `UNSUPPORTED` (`Unsupported`)

### `UlidGenerator`

Defined in `baseaicore.ids`.

A thread-safe source of monotonically increasing ULIDs.

Within a single millisecond the plain ULID specification gives no ordering, because each ID
gets fresh randomness. This generator instead increments the previous randomness by one when
the clock has not advanced, so IDs created in a burst still sort in creation order. That
matters because the suite uses ULIDs as primary keys and reads rows back "in order created" —
an unordered burst would reorder the events of a single run.

Thread safety: every call takes an internal lock, so one generator may be shared across
threads. Two *different* generators make no ordering promise about each other within a
millisecond; ordering is a property of a generator, not of the ULID format.

Lifecycle: cheap to construct and safe to discard. Consumers that want reproducible IDs in a
test construct their own with a frozen clock and a seeded randomness source.

| Member | Kind | Summary |
|---|---|---|
| `new_id` | method(self) -> 'str' | Generate the next ULID. |

### `UlidParts`

Defined in `baseaicore.ids`.

The decoded components of a ULID.

A local frozen value type rather than a third-party ULID object: a zero-dependency package
cannot return a class its consumers would have to install something to name.

Attributes:
    timestamp: The creation instant, timezone-aware in UTC, to millisecond resolution. This is
        the wall-clock time of the generating machine when the ID was made — it is a label,
        not a measurement, and two IDs from different machines order by their clocks.
    randomness: The 80 random bits, as 10 bytes. Exposed for tests and for collision analysis;
        it carries no meaning.
    text: The canonical 26-character rendering the parts were decoded from.

### `Unsupported`

Defined in `baseaicore.measurement`.

Sentinel for a measurement this environment genuinely cannot provide.

Boolean, numeric and ordering coercion all raise :class:`TypeError` on purpose. The failure
this guards against is ``value or 0`` / ``value + x`` quietly turning "not measurable" into a
real-looking number — the most damaging bug class in a measurement system, because the result
is indistinguishable from a real reading once it reaches an average, a chart or a routing
decision (ADR-0016).

Equality and hashing are *not* refused. They are identity-based and total: ``UNSUPPORTED ==
UNSUPPORTED`` is ``True``, ``UNSUPPORTED == 0`` is ``False``, and the sentinel can sit inside
a frozen dataclass that needs ``__eq__`` and ``__hash__``. Refusing them would make every
value object containing a measurement unhashable, which buys no safety: an equality test
cannot fabricate a number.

Invariants:
    * There is exactly one instance, process-wide. ``Unsupported()`` returns it, and it
      survives ``copy``, ``deepcopy`` and ``pickle`` as the same object, so ``is`` comparison
      is safe after a round trip through a queue or a cache.
    * It is immutable and therefore thread-safe.

Serialization is the caller's job and is fixed by ADR-0016: the JSON form is the string
``"unsupported"`` (:func:`baseaicore.hashing.canonical_json` emits it), storage is ``NULL``
plus a reason, and the UI renders an em dash with that reason. Never ``null``, never ``0``.

### `UnsupportedOperationError`

Defined in `baseaicore.errors`.

The operation is understood but this implementation refuses to perform it.

Distinct from :class:`UnsupportedPlatformError`: the refusal is about the operation, not the
machine it would run on.

### `UnsupportedPlatformError`

Defined in `baseaicore.errors`.

This platform cannot provide what was asked for.

Defined here and raised elsewhere: nothing in ``baseaicore`` branches on platform (spec §16).
SweatMeter and the applications raise it when an OS lacks a sensor or an interface.

### `ValidationError`

Defined in `baseaicore.errors`.

A value failed a domain rule: wrong shape, wrong range, or a broken invariant.

This is the error every constructor in this package raises. It names the field and the
expectation, never just "invalid".

### `__version__`

Defined in `baseaicore.__about__`.

Value: `'0.4.0'` (`str`)

### `canonical_json(value: 'Any') -> 'str'`

Defined in `baseaicore.hashing`.

Serialize a structure to canonical JSON: sorted keys, no whitespace, stable numbers.

The guarantee is byte-identity, not readability. Keys are sorted, separators are minimal,
non-ASCII characters are emitted as themselves (the result is UTF-8 text, and
:func:`sha256_of` encodes it as UTF-8), and every value type that could serialize two ways is
either normalized to one form or refused.

Accepted values and their canonical forms:

* ``dict``/``Mapping`` — keys must be strings, and are sorted by code point.
* ``list``/``tuple`` and other non-string sequences — order is preserved, because order is
  meaning. A caller that wants order-independence sorts before calling.
* ``str``, ``int``, ``bool``, ``None`` — as JSON.
* ``float`` — Python's shortest round-tripping repr, which is platform-stable. ``-0.0`` is
  normalized to ``0.0``; ``nan`` and ``±inf`` are refused, since they are not JSON and a
  ``nan`` reaching a hash is a fabricated measurement in disguise.
* :data:`~baseaicore.measurement.UNSUPPORTED` — the string ``"unsupported"``, fixed by
  ADR-0016 §4. Never ``null``, never ``0``.
* :class:`~enum.Enum` — its value, serialized by these same rules.
* :class:`~datetime.datetime` — RFC 3339 with millisecond precision (:func:`to_rfc3339`), so
  it must be timezone-aware.

Everything else is refused, including :class:`~decimal.Decimal` (``Decimal("3.0")`` and
``Decimal("3.00")`` are equal but serialize differently, so hashing one would depend on how it
was typed — see ADR-0030; convert to
:class:`~baseaicore.money.Money` or to a string first), ``bytes``, ``set`` and arbitrary
objects.

Strings are **not** Unicode-normalized. Two visually identical names in NFC and NFD hash
differently, which is deliberate: a provider's model name must round-trip byte-exactly
(canonical model identity §2), and silently normalizing it here would
make the hash disagree with the equality of the object it came from.

Args:
    value: The structure to serialize.

Returns:
    Canonical JSON text. Byte-identical for equal inputs.

Raises:
    ValidationError: If the structure contains an unserializable type, a non-string mapping
        key, a non-finite float, a naive datetime, or a reference cycle.

Security:
    Never call this on a structure containing a secret. Its output is what gets hashed,
    logged, stored and exported, and it makes no attempt to redact
    (security standards).

### `compute_machine_fingerprint(*, hostname: 'str | None', os_name: 'str | None', architecture: 'str | None', cpu_model: 'str | None', physical_cores: 'Measurement', logical_cores: 'Measurement', ram_bytes: 'Measurement', gpus: 'Sequence[GpuProfile]') -> 'str'`

Defined in `baseaicore.machine`.

Compute the stable identity of a machine from the hardware that changes measurements.

The digest is taken over the canonical JSON of a document with one key per identity input, so
it is byte-stable across processes, machines and Python versions
(:func:`~baseaicore.hashing.sha256_of`). Only the arguments below participate: everything the
module docstring lists as excluded is absent from the signature entirely, which is the strongest
form the exclusion policy can take — a driver upgrade cannot change this result because the
driver version is not reachable from here.

Two normalizations exist purely to stop one machine from having two identities:

* **Unreported is one value.** A string argument that is ``None``, empty or only whitespace
  hashes as the literal ``"unsupported"``, exactly as
  :data:`~baseaicore.measurement.UNSUPPORTED` does for the numeric arguments (Machine Identity
  §3). One collector reporting a missing CPU model as ``None`` and another reporting it as
  ``""`` must not produce two fingerprints for one machine. The accepted consequence is that a
  machine whose CPU model genuinely reads ``"unsupported"`` is indistinguishable from one that
  could not report it.
* **Surrounding whitespace is stripped**, because ``/proc/cpuinfo`` and ``nvidia-smi`` fields
  routinely carry it and the machine must not get a second identity depending on which reader
  ran. This is the opposite of the rule for a *model* name, which round-trips back to a
  provider byte-exactly and is therefore never touched
  (:func:`~baseaicore.hashing.canonical_json`); a hostname in a fingerprint is never sent
  anywhere, so only its identity matters.

GPUs contribute their ``(name, uuid)`` pair, and the entries are sorted before hashing, so the
order a collector happened to enumerate the devices in does not change the machine. When a GPU
reports no UUID, its ``index`` joins its entry: without that, two identical cards in one machine
would produce two identical entries, and the machine would be indistinguishable from a machine
with a differently-sized identical set. The trade-off is explicit — for a GPU with no UUID, and
only for such a GPU, re-enumeration changes the fingerprint.

Args:
    hostname: The machine's hostname, or ``None`` if unreported.
    os_name: The OS name, e.g. ``"Linux"``. Not the OS *version*, which is drift, not identity.
    architecture: The CPU architecture, e.g. ``"x86_64"``.
    cpu_model: The CPU's model string.
    physical_cores: Physical core count, or :data:`~baseaicore.measurement.UNSUPPORTED`.
    logical_cores: Logical core count, or :data:`~baseaicore.measurement.UNSUPPORTED`.
    ram_bytes: Total system memory, or :data:`~baseaicore.measurement.UNSUPPORTED`.
    gpus: Every visible GPU, in any order.

Returns:
    64 lowercase hex characters. Equal inputs always give equal fingerprints; a whole-valued
    ``float`` and the equal ``int`` count as equal inputs, so a collector that computed
    ``ram_bytes`` in floating point does not re-identify the machine.

Raises:
    ValidationError: If a quantity is a non-finite float, via
        :func:`~baseaicore.hashing.canonical_json` — a ``nan`` reaching a fingerprint is a
        measurement that was never taken.

### `elapsed_ms(start_ns: 'int', end_ns: 'int | None' = None) -> 'float'`

Defined in `baseaicore.timeutil`.

Return the milliseconds elapsed between two :func:`monotonic_ns` readings.

Args:
    start_ns: The earlier reading.
    end_ns: The later reading. Defaults to a reading taken now.

Returns:
    The elapsed time in milliseconds, as a float. Fractional milliseconds are preserved —
    a sub-millisecond operation genuinely took a nonzero time, and rounding it to ``0``
    would be the same lie this suite refuses elsewhere.

Raises:
    ValidationError: If the end reading precedes the start reading, which means the two
        readings did not come from the same monotonic counter and no duration can be derived.

### `estimate_cost(usage: 'TokenUsage', pricing: 'ModelPricing', *, at: 'datetime') -> 'CostEstimate'`

Defined in `baseaicore.cost`.

Cost one call's token usage against one price observation.

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

### `from_rfc3339(text: 'str') -> 'datetime'`

Defined in `baseaicore.timeutil`.

Parse an RFC 3339 timestamp into a timezone-aware datetime in UTC.

Args:
    text: An RFC 3339 timestamp with an explicit offset or a trailing ``Z``. Any offset is
        accepted and normalized to UTC, so a value written by a client in another timezone
        round-trips to the same instant.

Returns:
    The instant, with ``tzinfo`` set to :data:`datetime.UTC`.

Raises:
    ValidationError: If ``text`` is not a parsable timestamp, or if it carries no offset.
        Naive input is rejected rather than assumed to be UTC: the assumption is wrong
        exactly when it matters, on a machine that is not in UTC.

### `is_supported(value: 'T | Unsupported') -> 'TypeGuard[T]'`

Defined in `baseaicore.measurement`.

Report whether a value that might be unavailable carries a real one.

Generic in what it guards, so it narrows to whatever the caller's own union holds: a
:data:`Measurement` narrows to ``int | float``, a token count to ``int``, and a
:class:`~baseaicore.money.Money` price to ``Money``. The alternative — hard-coding
``int | float`` — would force a cast at every non-numeric measurement site, and a cast is
exactly the thing that lets an unsupported value slip through untested.

Args:
    value: The value to test.

Returns:
    ``True`` unless ``value`` is :data:`UNSUPPORTED`. The ``True`` branch is narrowed for the
    type checker, so it can be used without a cast.

### `monotonic_ns() -> 'int'`

Defined in `baseaicore.timeutil`.

Return a monotonic counter reading in nanoseconds, for measuring durations.

Returns:
    A reading from :func:`time.perf_counter_ns`. It has no meaning on its own — only the
    difference between two readings taken in the same process is defined — and it is immune
    to wall-clock adjustments, which is why every duration in the suite comes from here
    rather than from two :func:`utc_now` calls.

### `new_id() -> 'str'`

Defined in `baseaicore.ids`.

Generate a new ULID from the process-wide generator.

Returns:
    A 26-character Crockford base32 ULID, sorting after every ID this process has already
    generated.

### `normalize_currency(value: 'str') -> 'str'`

Defined in `baseaicore.money`.

Normalize a currency code to ISO 4217 alpha-3 form.

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

### `normalize_digest(value: 'str | None') -> 'str | None'`

Defined in `baseaicore.identity`.

Normalize a provider-reported artifact digest, or report that it cannot be normalized.

Providers report digests inconsistently: bare hex, ``sha256:``-prefixed, upper or lower case,
sometimes padded with whitespace. ModelRack calls this on every provider response so that
exactly one shape ever reaches storage (ADR-0024 §2).

Args:
    value: Whatever the provider reported, or ``None``.

Returns:
    ``"sha256:"`` followed by 64 lowercase hex characters, or ``None`` if the input was
    ``None``, empty, the wrong length, not hexadecimal, or carried an algorithm prefix other
    than ``sha256:``. Returning ``None`` rather than raising is deliberate: a digest that will
    not normalize must produce a ``name_only`` identity with a recorded reason, not a failed
    model listing and not a malformed identity.

### `parse_id(value: 'str') -> 'UlidParts'`

Defined in `baseaicore.ids`.

Decode a ULID into its timestamp and randomness.

Only the canonical rendering is accepted: exactly 26 uppercase Crockford base32 characters.
Lowercase input and Crockford's forgiving letter substitutions (``I``/``L`` → ``1``, ``O`` →
``0``) are **rejected** rather than corrected, because IDs in this suite are generated by this
module and used as database keys — accepting two spellings of one key is how a row gets
inserted twice.

Args:
    value: The candidate ULID text.

Returns:
    The decoded :class:`UlidParts`.

Raises:
    ValidationError: If the length is wrong, a character is outside the alphabet, or the
        timestamp field overflows 48 bits (which a 26-character string can encode but a ULID
        cannot contain).

### `sha256_of(value: 'Any') -> 'str'`

Defined in `baseaicore.hashing`.

Return the SHA-256 hex digest of a structure's canonical JSON.

This is the hash behind every fingerprint in the suite. Because it goes through
:func:`canonical_json`, two equal structures always produce the same digest and two different
ones effectively never do.

Args:
    value: The structure to hash, subject to :func:`canonical_json`'s accepted types.

Returns:
    64 lowercase hex characters.

Raises:
    ValidationError: Whatever :func:`canonical_json` would raise for the same input.

### `supported_values(values: 'Iterable[Measurement]') -> 'list[int | float]'`

Defined in `baseaicore.measurement`.

Filter an iterable of measurements down to the ones that exist.

The intended use is aggregation. ADR-0016 §6 requires that unsupported values be *excluded*
from a statistic and that the sample count behind that statistic be reported alongside it —
so callers compare ``len(supported_values(xs))`` against ``len(xs)`` and say what they
dropped. A statistic over an empty result is itself unsupported, not zero.

Args:
    values: Measurements in any order; the order is preserved.

Returns:
    A new list containing only the real numbers, in input order. Possibly empty, which is the
    caller's signal that the metric is unsupported rather than zero.

### `to_rfc3339(value: 'datetime') -> 'str'`

Defined in `baseaicore.timeutil`.

Format a timestamp as RFC 3339 with millisecond precision and a trailing ``Z``.

Millisecond precision is fixed rather than "whatever the platform provides" so that the same
instant produces the same string on every machine — the strings appear in canonical JSON, in
hashes and in exported payloads, where a platform-dependent number of digits would break
byte-for-byte comparison. Sub-millisecond detail belongs in a duration, not a timestamp.

Args:
    value: A timezone-aware datetime in any timezone; it is converted to UTC first.

Returns:
    A string of the form ``2026-08-22T14:03:11.250Z``.

Raises:
    ValidationError: If ``value`` is naive. A naive datetime has no defensible UTC reading,
        and guessing one would silently shift every downstream timestamp by the local offset.

### `utc_now() -> 'datetime'`

Defined in `baseaicore.timeutil`.

Return the current time as a timezone-aware datetime in UTC.

Returns:
    The current instant with ``tzinfo`` set to :data:`datetime.UTC`. Never naive: a naive
    datetime crossing a package boundary is ambiguous, and the suite's storage, exports and
    comparisons all assume UTC.
