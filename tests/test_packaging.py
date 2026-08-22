"""Packaging and public-API contract tests.

These prove the two claims the whole suite rests on: ``baseaicore`` imports nothing but the
standard library (gold standards G2 and G16), and its public surface is exactly what the spec
says it is.
"""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

import pytest

import baseaicore

# The public API, from spec §7. A symbol added here without a spec and changelog entry is an
# accidental commitment; a symbol removed is a breaking change for eight downstream repositories.
EXPECTED_PUBLIC_API = {
    # Measurement
    "UNSUPPORTED",
    "Measurement",
    "Unsupported",
    "is_supported",
    "supported_values",
    # Identity
    "IdentityConfidence",
    "ModelIdentity",
    "ProviderKind",
    "normalize_digest",
    # Money and cost
    "NANOS_PER_UNIT",
    "TOKENS_PER_RATE_UNIT",
    "CostEstimate",
    "ModelPricing",
    "Money",
    "PricingSource",
    "TokenCount",
    "TokenRates",
    "TokenUsage",
    "estimate_cost",
    "normalize_currency",
    # Errors
    "ConfigurationError",
    "ConflictError",
    "DependencyUnavailableError",
    "NotFoundError",
    "SuiteError",
    "UnsupportedOperationError",
    "UnsupportedPlatformError",
    "ValidationError",
    # Identity and time
    "Clock",
    "RandomnessSource",
    "UlidGenerator",
    "UlidParts",
    "elapsed_ms",
    "from_rfc3339",
    "monotonic_ns",
    "new_id",
    "parse_id",
    "to_rfc3339",
    "utc_now",
    # Hashing
    "canonical_json",
    "sha256_of",
    # Metadata
    "__version__",
}


@pytest.mark.contract
def test_the_public_api_is_exactly_what_the_spec_documents() -> None:
    assert set(baseaicore.__all__) == EXPECTED_PUBLIC_API


@pytest.mark.contract
def test_every_exported_name_actually_resolves() -> None:
    missing = [name for name in baseaicore.__all__ if not hasattr(baseaicore, name)]

    assert missing == []


@pytest.mark.contract
def test_all_lists_each_name_once() -> None:
    # Ordering is enforced by ruff's RUF022 (constants, then classes, then functions); this test
    # covers the thing a linter cannot see — a name exported twice from two modules.
    assert len(baseaicore.__all__) == len(set(baseaicore.__all__))


@pytest.mark.contract
def test_importing_the_package_pulls_in_no_third_party_module() -> None:
    """Assert the zero-dependency claim by measuring what an import adds to ``sys.modules``.

    The delta is measured inside a subprocess rather than in this one, because pytest, coverage
    and the plugins have already imported half the world by the time a test runs.
    """
    program = (
        "import json, sys;"
        "before = set(sys.modules);"
        "import baseaicore;"
        "added = {name.split('.')[0] for name in set(sys.modules) - before};"
        "print(json.dumps(sorted(added)))"
    )

    result = subprocess.run(  # noqa: S603 — our own interpreter, no shell, literal argument list
        [sys.executable, "-c", program], capture_output=True, text=True, check=True
    )
    added = json.loads(result.stdout)

    third_party = [
        name
        for name in added
        if name != "baseaicore" and not name.startswith("_") and name not in sys.stdlib_module_names
    ]
    assert third_party == [], f"baseaicore imported non-stdlib modules: {third_party}"


@pytest.mark.contract
def test_the_distribution_declares_no_runtime_dependencies() -> None:
    """Assert the dependency budget from gold standard G16 §1.1: BaseAiCore is allowed zero."""
    requirements = importlib.metadata.requires("baseaicore") or []

    runtime = [requirement for requirement in requirements if "extra ==" not in requirement]
    assert runtime == [], f"baseaicore declares runtime dependencies: {runtime}"


@pytest.mark.contract
def test_the_py_typed_marker_ships_so_consumers_get_the_types() -> None:
    # A missing marker silently disables type checking in every downstream project.
    marker = Path(baseaicore.__file__).parent / "py.typed"

    assert marker.is_file()


@pytest.mark.contract
def test_the_version_is_a_release_number_the_metadata_agrees_with() -> None:
    assert baseaicore.__version__ == importlib.metadata.version("baseaicore")


def test_the_five_line_script_from_the_spec_works() -> None:
    """Spec §20 acceptance criterion 2, as a test rather than as a promise."""
    from baseaicore import (  # noqa: PLC0415 — importing it here is what the script does
        UNSUPPORTED,
        ModelIdentity,
        ProviderKind,
        is_supported,
    )

    identity = ModelIdentity(ProviderKind.OLLAMA, "qwen3.5:9b-q8_0")

    assert identity.canonical_id == "ollama/qwen3.5:9b-q8_0@unknown"
    assert is_supported(UNSUPPORTED) is False


def test_the_cost_acceptance_criterion_holds_end_to_end() -> None:
    """Development plan Phase 1, acceptance criterion 4: no price means no cost, not a free one."""
    from baseaicore import (  # noqa: PLC0415 — importing it here is what the script does
        UNSUPPORTED,
        ModelIdentity,
        ModelPricing,
        PricingSource,
        ProviderKind,
        TokenRates,
        TokenUsage,
        estimate_cost,
        utc_now,
    )

    now = utc_now()
    unpriced = ModelPricing(
        identity=ModelIdentity(ProviderKind.OLLAMA, "qwen3.5:9b-q8_0"),
        rates=TokenRates(currency="USD"),
        source=PricingSource.USER_OVERRIDE,
        observed_at=now,
    )

    estimate = estimate_cost(TokenUsage(input_tokens=1_000, output_tokens=200), unpriced, at=now)

    assert estimate.total is UNSUPPORTED
    assert estimate.unpriced_reasons != ()
