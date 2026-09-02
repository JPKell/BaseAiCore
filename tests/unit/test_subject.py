"""Unit tests for measurement-subject comparability (`Canonical Model Identity` §5).

Every row of the matrix has at least one test here, named for the row it exercises. The rule under
test throughout: a verdict is never `comparable` unless every fact needed to justify it was
actually supplied — omitted benchmark or dataset information yields `indeterminate`, never a
default "yes".
"""

from __future__ import annotations

import urllib.parse
from typing import Any

import pytest

from baseaicore.adapter import AdapterIdentity
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


# ---- The adapter axis (Phase 5, ADR-0058) ----------------------------------------------------
#
# The additive claim under test: with no adapter, a subject's canonical string is byte-for-byte
# the model identity's canonical ID. Its exhaustive form — over every row of ADR-0024's golden
# table — is in test_identity.py, beside the table it must not disturb.

DIGEST = "sha256:1f3a9c4e2b70a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f607182930"
ADAPTER_DIGEST = "sha256:9e2b41d07c55a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f607182930"
FACTCHECK = AdapterIdentity("factcheck", ADAPTER_DIGEST)
HOUSE_VOICE = AdapterIdentity("house-voice", DIGEST)


def test_a_bare_subject_serializes_byte_identically_to_the_canonical_id() -> None:
    # The additive claim of ADR-0058, at this level: an absent adapter adds nothing to the string.
    # The exhaustive form of this proof, over every row of ADR-0024's own golden table, lives in
    # test_identity.py beside that table.
    identity = ModelIdentity(ProviderKind.OLLAMA, "qwen3.5:9b-q8_0", DIGEST)
    subject = MeasurementSubject(identity, "profile-hash", "machine-fp")

    assert subject.canonical_subject_id == identity.canonical_id
    assert subject.adapter is None


GOLDEN_ADAPTER_SUBJECT_IDS = [
    (
        ModelIdentity(ProviderKind.LLAMACPP, "qwen3.5-9b-q8", DIGEST),
        FACTCHECK,
        "llamacpp/qwen3.5-9b-q8@sha256:1f3a9c4e2b70+factcheck@sha256:9e2b41d07c55",
    ),
    (
        ModelIdentity(ProviderKind.LLAMACPP, "qwen3.5-9b-q8", None),
        FACTCHECK,
        "llamacpp/qwen3.5-9b-q8@unknown+factcheck@sha256:9e2b41d07c55",
    ),
    (
        ModelIdentity(ProviderKind.LLAMACPP, "hf.co/user/repo:q4@main", None),
        HOUSE_VOICE,
        "llamacpp/hf.co/user/repo:q4@main@unknown+house-voice@sha256:1f3a9c4e2b70",
    ),
]


@pytest.mark.parametrize(("identity", "adapter", "expected"), GOLDEN_ADAPTER_SUBJECT_IDS)
def test_an_adapter_bearing_subject_matches_its_golden_canonical_string(
    identity: ModelIdentity, adapter: AdapterIdentity, expected: str
) -> None:
    subject = MeasurementSubject(identity, "profile-hash", "machine-fp", adapter=adapter)

    assert subject.canonical_subject_id == expected


def test_the_plus_is_percent_encoded_where_the_string_is_a_query_parameter_value() -> None:
    # ADR-0024 §3 is unchanged: this string is never a URL path segment. Where it appears as a
    # query-parameter value, a bare "+" would decode to a space under form encoding and resolve to
    # a different subject, or to none — so it is encoded as %2B.
    subject = MeasurementSubject(
        ModelIdentity(ProviderKind.LLAMACPP, "qwen3.5-9b-q8", DIGEST),
        "profile-hash",
        "machine-fp",
        adapter=FACTCHECK,
    )

    encoded = urllib.parse.quote(subject.canonical_subject_id, safe="")

    assert encoded == (
        "llamacpp%2Fqwen3.5-9b-q8%40sha256%3A1f3a9c4e2b70%2Bfactcheck%40sha256%3A9e2b41d07c55"
    )
    assert "%2B" in encoded
    assert "+" not in encoded


def test_the_adapter_field_is_keyword_only_so_positional_construction_is_unchanged() -> None:
    # Three positional arguments is what every existing caller writes, and it still means what it
    # always meant.
    subject = MeasurementSubject(
        ModelIdentity(ProviderKind.OLLAMA, "m", DIGEST), "profile-hash", "machine-fp"
    )

    assert subject.adapter is None
    with pytest.raises(TypeError):
        MeasurementSubject(  # type: ignore[misc]  # proving the refusal
            ModelIdentity(ProviderKind.OLLAMA, "m", DIGEST),
            "profile-hash",
            "machine-fp",
            FACTCHECK,
        )


def _subject(adapter: AdapterIdentity | None) -> MeasurementSubject:
    return MeasurementSubject(
        ModelIdentity(ProviderKind.LLAMACPP, "qwen3.5-9b-q8", DIGEST),
        "profile-hash",
        "machine-fp",
        adapter=adapter,
    )


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (None, FACTCHECK),
        (FACTCHECK, None),
        (FACTCHECK, HOUSE_VOICE),
    ],
    ids=["bare-vs-adapted", "adapted-vs-bare", "two-adapters"],
)
def test_a_differing_adapter_makes_two_subjects_separate_never_merged(
    left: AdapterIdentity | None, right: AdapterIdentity | None
) -> None:
    # Evidence measured on (base, adapterA) applies to that subject and to nothing else — not to
    # the bare base, not to (base, adapterB). ADR-0059.
    verdict = _subject(left).is_comparable_with(
        _subject(right),
        metric_kind=MetricKind.QUALITY,
        benchmark_version="1.0.0",
        other_benchmark_version="1.0.0",
        dataset_hashes={"d": "h"},
        other_dataset_hashes={"d": "h"},
    )

    assert verdict.comparability is Comparability.SEPARATE
    assert "adapter" in verdict.reason


def test_the_same_adapter_compares_exactly_as_the_bare_subject_does() -> None:
    verdict = _subject(FACTCHECK).is_comparable_with(
        _subject(FACTCHECK),
        metric_kind=MetricKind.QUALITY,
        benchmark_version="1.0.0",
        other_benchmark_version="1.0.0",
        dataset_hashes={"d": "h"},
        other_dataset_hashes={"d": "h"},
    )

    assert verdict.comparability is Comparability.COMPARABLE


def test_two_subjects_differing_only_in_adapter_lineage_are_the_same_subject() -> None:
    # source_digest is lineage, not identity, so it must not split a subject or its evidence.
    with_lineage = AdapterIdentity("factcheck", ADAPTER_DIGEST, "sha256:" + "ab" * 32)

    verdict = _subject(FACTCHECK).is_comparable_with(
        _subject(with_lineage),
        metric_kind=MetricKind.QUALITY,
        benchmark_version="1.0.0",
        other_benchmark_version="1.0.0",
        dataset_hashes={"d": "h"},
        other_dataset_hashes={"d": "h"},
    )

    assert verdict.comparability is Comparability.COMPARABLE
