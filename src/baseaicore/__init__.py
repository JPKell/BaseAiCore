"""BaseAiCore — the domain vocabulary every component of the Local AI Suite agrees on.

Layer 1: pure domain types with no I/O, no configuration, no logging and no third-party
dependencies. If two components would otherwise invent the same concept twice, and that concept is
pure vocabulary, it belongs here.

What is exported below is the public API. Anything not listed in ``__all__`` is private and may
change without a version bump, whatever its module happens to be named.

Phase 1 (this release) ships measurement, identity, IDs, time, hashing, errors, money and cost.
Descriptors, runtime profiles, measurement subjects, machine profiles and capability IDs arrive in
later phases — see ``docs/packages/baseaicore/development-plan.md``.

    >>> from baseaicore import ModelIdentity, ProviderKind
    >>> identity = ModelIdentity(ProviderKind.OLLAMA, "qwen3.5:9b-q8_0")
    >>> identity.canonical_id
    'ollama/qwen3.5:9b-q8_0@unknown'
"""

from __future__ import annotations

from baseaicore.__about__ import __version__
from baseaicore.cost import (
    TOKENS_PER_RATE_UNIT,
    CostEstimate,
    ModelPricing,
    PricingSource,
    TokenCount,
    TokenRates,
    TokenUsage,
    estimate_cost,
)
from baseaicore.errors import (
    ConfigurationError,
    ConflictError,
    DependencyUnavailableError,
    NotFoundError,
    SuiteError,
    UnsupportedOperationError,
    UnsupportedPlatformError,
    ValidationError,
)
from baseaicore.hashing import canonical_json, sha256_of
from baseaicore.identity import (
    IdentityConfidence,
    ModelIdentity,
    ProviderKind,
    normalize_digest,
)
from baseaicore.ids import RandomnessSource, UlidGenerator, UlidParts, new_id, parse_id
from baseaicore.measurement import (
    UNSUPPORTED,
    Measurement,
    Unsupported,
    is_supported,
    supported_values,
)
from baseaicore.money import NANOS_PER_UNIT, Money, normalize_currency
from baseaicore.timeutil import (
    Clock,
    elapsed_ms,
    from_rfc3339,
    monotonic_ns,
    to_rfc3339,
    utc_now,
)

__all__ = [
    "NANOS_PER_UNIT",
    "TOKENS_PER_RATE_UNIT",
    "UNSUPPORTED",
    "Clock",
    "ConfigurationError",
    "ConflictError",
    "CostEstimate",
    "DependencyUnavailableError",
    "IdentityConfidence",
    "Measurement",
    "ModelIdentity",
    "ModelPricing",
    "Money",
    "NotFoundError",
    "PricingSource",
    "ProviderKind",
    "RandomnessSource",
    "SuiteError",
    "TokenCount",
    "TokenRates",
    "TokenUsage",
    "UlidGenerator",
    "UlidParts",
    "Unsupported",
    "UnsupportedOperationError",
    "UnsupportedPlatformError",
    "ValidationError",
    "__version__",
    "canonical_json",
    "elapsed_ms",
    "estimate_cost",
    "from_rfc3339",
    "is_supported",
    "monotonic_ns",
    "new_id",
    "normalize_currency",
    "normalize_digest",
    "parse_id",
    "sha256_of",
    "supported_values",
    "to_rfc3339",
    "utc_now",
]
