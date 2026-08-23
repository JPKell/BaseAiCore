"""BaseAiCore — the domain vocabulary every component of the Local AI Suite agrees on.

Layer 1: pure domain types with no I/O, no configuration, no logging and no third-party
dependencies. If two components would otherwise invent the same concept twice, and that concept is
pure vocabulary, it belongs here.

What is exported below is the public API, complete as of Phase 4
(``docs/packages/baseaicore/development-plan.md``): measurement, identity, IDs, time, hashing,
errors, money and cost; model descriptor, runtime profile and measurement subject; machine profile
and fingerprint; capability identifiers. Anything not listed in ``__all__`` is private and may
change without a version bump, whatever its module happens to be named.

    >>> from baseaicore import ModelIdentity, ProviderKind
    >>> identity = ModelIdentity(ProviderKind.OLLAMA, "qwen3.5:9b-q8_0")
    >>> identity.canonical_id
    'ollama/qwen3.5:9b-q8_0@unknown'
"""

from __future__ import annotations

from baseaicore.__about__ import __version__
from baseaicore.capability import CapabilityId
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
from baseaicore.descriptor import ModelCapabilityFlag, ModelDescriptor
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
from baseaicore.machine import (
    GpuProfile,
    GpuVendor,
    MachineProfile,
    StorageDevice,
    compute_machine_fingerprint,
)
from baseaicore.measurement import (
    UNSUPPORTED,
    Measurement,
    Unsupported,
    is_supported,
    supported_values,
)
from baseaicore.money import NANOS_PER_UNIT, Money, normalize_currency
from baseaicore.runtime import RuntimeProfile
from baseaicore.subject import Comparability, ComparabilityVerdict, MeasurementSubject, MetricKind
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
    "CapabilityId",
    "Clock",
    "Comparability",
    "ComparabilityVerdict",
    "ConfigurationError",
    "ConflictError",
    "CostEstimate",
    "DependencyUnavailableError",
    "GpuProfile",
    "GpuVendor",
    "IdentityConfidence",
    "MachineProfile",
    "Measurement",
    "MeasurementSubject",
    "MetricKind",
    "ModelCapabilityFlag",
    "ModelDescriptor",
    "ModelIdentity",
    "ModelPricing",
    "Money",
    "NotFoundError",
    "PricingSource",
    "ProviderKind",
    "RandomnessSource",
    "RuntimeProfile",
    "StorageDevice",
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
    "compute_machine_fingerprint",
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
