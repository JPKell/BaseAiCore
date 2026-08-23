"""Unit tests for measurement-subject comparability (`Canonical Model Identity` §5).

Every row of the matrix has at least one test here, named for the row it exercises. The rule under
test throughout: a verdict is never `comparable` unless every fact needed to justify it was
actually supplied — omitted benchmark or dataset information yields `indeterminate`, never a
default "yes".
"""

from __future__ import annotations

from typing import Any

import pytest

from baseaicore.errors import ValidationError
from baseaicore.identity import ModelIdentity, ProviderKind
from baseaicore.subject import Comparability, ComparabilityVerdict, MeasurementSubject, MetricKind

DIGESTED = ModelIdentity(
    ProviderKind.OLLAMA,
    "qwen3.5:9b-q8_0",
    "sha256:1f3a9c4e2b70a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f607182930",
)
NAME_ONLY = ModelIdentity(ProviderKind.OLLAMA, "qwen3.5:9b-q8_0")
OTHER_MODEL = ModelIdentity(ProviderKind.OLLAMA, "llama4:70b-q4_0")

PROFILE_A = "profilehash-a"
PROFILE_B = "profilehash-b"
MACHINE_A = "machinefingerprint-a"
MACHINE_B = "machinefingerprint-b"


def subject(
    *,
    identity: ModelIdentity = DIGESTED,
    runtime_profile_hash: str = PROFILE_A,
    machine_fingerprint: str = MACHINE_A,
) -> MeasurementSubject:
    """Build a measurement subject, overriding any field."""
    return MeasurementSubject(
        identity=identity,
        runtime_profile_hash=runtime_profile_hash,
        machine_fingerprint=machine_fingerprint,
    )


# ---- Construction ------------------------------------------------------------------------------
@pytest.mark.parametrize("field_name", ["runtime_profile_hash", "machine_fingerprint"])
@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_hash_field_is_rejected(field_name: str, blank: str) -> None:
    defaults: dict[str, Any] = {
        "identity": DIGESTED,
        "runtime_profile_hash": PROFILE_A,
        "machine_fingerprint": MACHINE_A,
    }
    with pytest.raises(ValidationError, match=field_name):
        MeasurementSubject(**{**defaults, field_name: blank})


# ---- Row 1: same subject, same benchmark version, same dataset hash -----------------------------
def test_same_subject_same_benchmark_same_dataset_is_comparable() -> None:
    verdict = subject().is_comparable_with(
        subject(),
        metric_kind=MetricKind.QUALITY,
        benchmark_version="v1",
        other_benchmark_version="v1",
        dataset_hashes={"main": "abc123"},
        other_dataset_hashes={"main": "abc123"},
    )

    assert verdict == ComparabilityVerdict(Comparability.COMPARABLE, verdict.reason)


def test_dataset_hash_equality_does_not_depend_on_key_order() -> None:
    verdict = subject().is_comparable_with(
        subject(),
        metric_kind=MetricKind.QUALITY,
        benchmark_version="v1",
        other_benchmark_version="v1",
        dataset_hashes={"main": "abc123", "extra": "def456"},
        other_dataset_hashes={"extra": "def456", "main": "abc123"},
    )

    assert verdict.comparability is Comparability.COMPARABLE


# ---- Row 2: same subject, different benchmark version -------------------------------------------
def test_same_subject_different_benchmark_version_is_separate_never_averaged() -> None:
    verdict = subject().is_comparable_with(
        subject(),
        metric_kind=MetricKind.QUALITY,
        benchmark_version="v1",
        other_benchmark_version="v2",
        dataset_hashes={"main": "abc123"},
        other_dataset_hashes={"main": "abc123"},
    )

    assert verdict.comparability is Comparability.SEPARATE
    assert "benchmark version" in verdict.reason


def test_same_subject_same_benchmark_version_different_dataset_hash_is_separate() -> None:
    verdict = subject().is_comparable_with(
        subject(),
        metric_kind=MetricKind.QUALITY,
        benchmark_version="v1",
        other_benchmark_version="v1",
        dataset_hashes={"main": "abc123"},
        other_dataset_hashes={"main": "zzz999"},
    )

    assert verdict.comparability is Comparability.SEPARATE
    assert "dataset" in verdict.reason


# ---- Row 3: same identity + runtime profile, different machine ----------------------------------
def test_cross_machine_quality_comparison_warns_rather_than_blocks() -> None:
    verdict = subject(machine_fingerprint=MACHINE_A).is_comparable_with(
        subject(machine_fingerprint=MACHINE_B), metric_kind=MetricKind.QUALITY
    )

    assert verdict.comparability is Comparability.WARN
    assert "machine" in verdict.reason


@pytest.mark.parametrize(
    "metric_kind", [MetricKind.PERFORMANCE, MetricKind.MEMORY, MetricKind.ENERGY]
)
def test_cross_machine_non_quality_metrics_are_separate(metric_kind: MetricKind) -> None:
    verdict = subject(machine_fingerprint=MACHINE_A).is_comparable_with(
        subject(machine_fingerprint=MACHINE_B), metric_kind=metric_kind
    )

    assert verdict.comparability is Comparability.SEPARATE
    assert "machine" in verdict.reason


# ---- Row 4: same identity, different runtime profile ---------------------------------------------
def test_same_identity_different_runtime_profile_is_an_explicit_comparison_only() -> None:
    verdict = subject(runtime_profile_hash=PROFILE_A).is_comparable_with(
        subject(runtime_profile_hash=PROFILE_B), metric_kind=MetricKind.PERFORMANCE
    )

    assert verdict.comparability is Comparability.SEPARATE
    assert "runtime profile" in verdict.reason


def test_different_runtime_profile_outranks_different_machine() -> None:
    # Both the profile and the machine differ; the profile row governs (table order).
    verdict = subject(
        runtime_profile_hash=PROFILE_A, machine_fingerprint=MACHINE_A
    ).is_comparable_with(
        subject(runtime_profile_hash=PROFILE_B, machine_fingerprint=MACHINE_B),
        metric_kind=MetricKind.QUALITY,
    )

    assert verdict.comparability is Comparability.SEPARATE
    assert "runtime profile" in verdict.reason


# ---- Row 5: different identity (family/quantization relationship unknown to a subject) ----------
def test_different_identity_is_indeterminate_not_separate() -> None:
    # A subject does not carry `family`, so it cannot tell a quantization sibling from an
    # unrelated model — indeterminate is the honest answer, never a guessed verdict.
    verdict = subject(identity=DIGESTED).is_comparable_with(
        subject(identity=OTHER_MODEL), metric_kind=MetricKind.QUALITY
    )

    assert verdict.comparability is Comparability.INDETERMINATE
    assert "identity" in verdict.reason


# ---- Row 6: name_only identity across a gap in time ----------------------------------------------
def test_name_only_identity_otherwise_comparable_warns_instead() -> None:
    verdict = subject(identity=NAME_ONLY).is_comparable_with(
        subject(identity=NAME_ONLY),
        metric_kind=MetricKind.QUALITY,
        benchmark_version="v1",
        other_benchmark_version="v1",
        dataset_hashes={"main": "abc123"},
        other_dataset_hashes={"main": "abc123"},
    )

    assert verdict.comparability is Comparability.WARN
    assert "name_only" in verdict.reason


def test_digest_identity_otherwise_comparable_stays_comparable() -> None:
    verdict = subject(identity=DIGESTED).is_comparable_with(
        subject(identity=DIGESTED),
        metric_kind=MetricKind.QUALITY,
        benchmark_version="v1",
        other_benchmark_version="v1",
        dataset_hashes={"main": "abc123"},
        other_dataset_hashes={"main": "abc123"},
    )

    assert verdict.comparability is Comparability.COMPARABLE


# ---- Benchmark/dataset arguments omitted -> indeterminate, never comparable by default -----------
def test_omitting_benchmark_version_yields_indeterminate() -> None:
    verdict = subject().is_comparable_with(subject(), metric_kind=MetricKind.QUALITY)

    assert verdict.comparability is Comparability.INDETERMINATE
    assert "benchmark_version" in verdict.reason


def test_omitting_only_the_others_benchmark_version_yields_indeterminate() -> None:
    verdict = subject().is_comparable_with(
        subject(), metric_kind=MetricKind.QUALITY, benchmark_version="v1"
    )

    assert verdict.comparability is Comparability.INDETERMINATE


def test_omitting_dataset_hashes_yields_indeterminate_even_with_matching_benchmark_version() -> (
    None
):
    verdict = subject().is_comparable_with(
        subject(),
        metric_kind=MetricKind.QUALITY,
        benchmark_version="v1",
        other_benchmark_version="v1",
    )

    assert verdict.comparability is Comparability.INDETERMINATE
    assert "dataset_hashes" in verdict.reason


def test_omitting_only_the_others_dataset_hashes_yields_indeterminate() -> None:
    verdict = subject().is_comparable_with(
        subject(),
        metric_kind=MetricKind.QUALITY,
        benchmark_version="v1",
        other_benchmark_version="v1",
        dataset_hashes={"main": "abc123"},
    )

    assert verdict.comparability is Comparability.INDETERMINATE


def test_indeterminate_never_becomes_comparable_by_a_missing_argument() -> None:
    # Every combination of omitted benchmark/dataset arguments must stop short of `comparable`.
    always_indeterminate: list[dict[str, Any]] = [
        {},
        {"benchmark_version": "v1"},
        {"other_benchmark_version": "v1"},
        {"benchmark_version": "v1", "other_benchmark_version": "v1"},
        {
            "benchmark_version": "v1",
            "other_benchmark_version": "v1",
            "dataset_hashes": {"main": "abc123"},
        },
    ]
    for kwargs in always_indeterminate:
        verdict = subject().is_comparable_with(subject(), metric_kind=MetricKind.QUALITY, **kwargs)
        assert verdict.comparability is Comparability.INDETERMINATE, kwargs
