"""Unit tests for canonical model identity.

The golden canonical IDs below are fixed by ADR-0024. They are a persisted, indexed lookup key in
three databases; if a change makes one of them fail, the change is wrong, not the test.
"""

from __future__ import annotations

import copy
import pickle

import pytest

from baseaicore.errors import ValidationError
from baseaicore.identity import (
    IdentityConfidence,
    ModelIdentity,
    ProviderKind,
    normalize_digest,
)

DIGEST = "sha256:1f3a9c4e2b70a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f607182930"

# ---- Golden canonical IDs (ADR-0024 §1) -----------------------------------------------------
GOLDEN_CANONICAL_IDS = [
    (ProviderKind.OLLAMA, "qwen3.5:9b-q8_0", DIGEST, "ollama/qwen3.5:9b-q8_0@sha256:1f3a9c4e2b70"),
    (ProviderKind.OLLAMA, "qwen3.5:9b-q8_0", None, "ollama/qwen3.5:9b-q8_0@unknown"),
    # A model name legitimately containing every separator the canonical ID itself uses. This is
    # why the string is lossy by design and never parsed back into its parts.
    (
        ProviderKind.LLAMACPP,
        "hf.co/user/repo:q4@main",
        None,
        "llamacpp/hf.co/user/repo:q4@main@unknown",
    ),
    (
        ProviderKind.OPENAI_COMPATIBLE,
        "gpt-oss-120b",
        None,
        "openai_compatible/gpt-oss-120b@unknown",
    ),
    (ProviderKind.VLLM, "模型/qwen-中文:q4", None, "vllm/模型/qwen-中文:q4@unknown"),
    (ProviderKind.FAKE, "fake-model", DIGEST, "fake/fake-model@sha256:1f3a9c4e2b70"),
]


@pytest.mark.parametrize(
    ("kind", "name", "digest", "expected"), GOLDEN_CANONICAL_IDS, ids=lambda v: str(v)[:40]
)
def test_canonical_id_matches_its_golden_value(
    kind: ProviderKind, name: str, digest: str | None, expected: str
) -> None:
    assert ModelIdentity(kind, name, digest).canonical_id == expected


def test_canonical_id_keeps_the_algorithm_prefix_and_twelve_hex_characters() -> None:
    # ADR-0024 §1 rejected both `digest[:12]` ("sha256:1f3a") and a bare 12 hex characters.
    identity = ModelIdentity(ProviderKind.OLLAMA, "m", DIGEST)

    _, _, digest_short = identity.canonical_id.rpartition("@")

    assert digest_short == "sha256:1f3a9c4e2b70"
    assert len(digest_short.removeprefix("sha256:")) == 12


def test_str_is_the_canonical_id_so_log_interpolation_stays_greppable() -> None:
    identity = ModelIdentity(ProviderKind.OLLAMA, "qwen3.5:9b-q8_0")

    assert f"{identity}" == "ollama/qwen3.5:9b-q8_0@unknown"


def test_the_canonical_id_is_computed_once_and_returned_unchanged() -> None:
    identity = ModelIdentity(ProviderKind.OLLAMA, "m", DIGEST)

    assert identity.canonical_id == identity.canonical_id
    assert identity.canonical_id == "ollama/m@sha256:1f3a9c4e2b70"


def test_the_canonical_id_cache_is_invisible_to_equality_and_repr() -> None:
    first = ModelIdentity(ProviderKind.OLLAMA, "m")
    second = ModelIdentity(ProviderKind.OLLAMA, "m")
    _ = first.canonical_id  # populate the cache on one of the pair only

    assert first == second
    assert hash(first) == hash(second)
    assert repr(first) == repr(second)
    assert "cache" not in repr(first)


# ---- Equality, hashing and immutability -----------------------------------------------------
def test_two_identities_are_equal_when_all_three_fields_are() -> None:
    assert ModelIdentity(ProviderKind.OLLAMA, "m", DIGEST) == ModelIdentity(
        ProviderKind.OLLAMA, "m", DIGEST
    )


@pytest.mark.parametrize(
    "other",
    [
        ModelIdentity(ProviderKind.VLLM, "m", DIGEST),
        ModelIdentity(ProviderKind.OLLAMA, "other", DIGEST),
        ModelIdentity(ProviderKind.OLLAMA, "m", None),
    ],
    ids=["different kind", "different name", "different digest"],
)
def test_a_difference_in_any_field_breaks_equality(other: ModelIdentity) -> None:
    assert ModelIdentity(ProviderKind.OLLAMA, "m", DIGEST) != other


def test_identities_are_usable_as_dictionary_keys() -> None:
    key = ModelIdentity(ProviderKind.OLLAMA, "m", DIGEST)

    assert {key: "value"}[ModelIdentity(ProviderKind.OLLAMA, "m", DIGEST)] == "value"


def test_an_identity_is_frozen() -> None:
    identity = ModelIdentity(ProviderKind.OLLAMA, "m")

    with pytest.raises((AttributeError, TypeError)):
        identity.provider_model_name = "other"  # type: ignore[misc]  # proving the refusal


@pytest.mark.parametrize(
    "round_trip",
    [copy.copy, copy.deepcopy, lambda v: pickle.loads(pickle.dumps(v))],  # noqa: S301 — our bytes
    ids=["copy", "deepcopy", "pickle"],
)
def test_an_identity_round_trips_equal(round_trip: object) -> None:
    original = ModelIdentity(ProviderKind.OLLAMA, "m", DIGEST)

    restored = round_trip(original)  # type: ignore[operator]  # parametrized callables

    assert restored == original
    assert restored.canonical_id == original.canonical_id


# ---- Confidence -----------------------------------------------------------------------------
def test_a_digest_makes_the_identity_exact() -> None:
    assert (
        ModelIdentity(ProviderKind.OLLAMA, "m", DIGEST).identity_confidence
        is IdentityConfidence.DIGEST
    )


def test_no_digest_means_name_only_confidence() -> None:
    assert (
        ModelIdentity(ProviderKind.OLLAMA, "m").identity_confidence is IdentityConfidence.NAME_ONLY
    )


# ---- Digest normalization (ADR-0024 §2) -----------------------------------------------------
BARE_HEX = "1f3a9c4e2b70a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f607182930"


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [
        (BARE_HEX, DIGEST),
        (f"sha256:{BARE_HEX}", DIGEST),
        (BARE_HEX.upper(), DIGEST),
        (f"SHA256:{BARE_HEX.upper()}", DIGEST),
        (f"  {BARE_HEX}  ", DIGEST),
        (None, None),
        ("", None),
        ("   ", None),
        (BARE_HEX[:63], None),
        (BARE_HEX + "0", None),
        ("z" * 64, None),
        (f"md5:{BARE_HEX}", None),
        ("sha256:", None),
    ],
    ids=[
        "bare hex",
        "prefixed",
        "uppercase hex",
        "uppercase prefix",
        "surrounding whitespace",
        "none",
        "empty",
        "whitespace only",
        "too short",
        "too long",
        "not hexadecimal",
        "wrong algorithm",
        "prefix only",
    ],
)
def test_normalize_digest_produces_the_documented_result(
    supplied: str | None, expected: str | None
) -> None:
    assert normalize_digest(supplied) == expected


def test_an_unnormalizable_digest_yields_a_name_only_identity_not_a_malformed_one() -> None:
    # The ADR-0024 §2 contract: ModelRack discards what will not normalize, with a reason, and
    # stores a name_only identity. Nothing downstream ever sees a half-valid digest.
    reported = "not-a-digest"

    normalized = normalize_digest(reported)
    identity = ModelIdentity(ProviderKind.OLLAMA, "m", normalized)

    assert normalized is None
    assert identity.identity_confidence is IdentityConfidence.NAME_ONLY


# ---- Construction validation ----------------------------------------------------------------
@pytest.mark.parametrize("name", ["", "   ", "\t\n"], ids=["empty", "spaces", "whitespace"])
def test_an_empty_model_name_is_refused(name: str) -> None:
    with pytest.raises(ValidationError, match="provider_model_name"):
        ModelIdentity(ProviderKind.OLLAMA, name)


@pytest.mark.parametrize(
    "digest",
    [BARE_HEX, DIGEST.upper(), "sha256:abc", f"md5:{BARE_HEX}"],
    ids=["unprefixed", "uppercase", "too short", "wrong algorithm"],
)
def test_a_digest_that_is_not_already_normalized_is_refused(digest: str) -> None:
    # Constructing from a raw provider value must fail loudly: silently normalizing here would
    # hide the case ADR-0024 §2 requires ModelRack to record a reason for.
    with pytest.raises(ValidationError, match="artifact_digest"):
        ModelIdentity(ProviderKind.OLLAMA, "m", digest)


def test_the_refusal_message_points_at_normalize_digest() -> None:
    with pytest.raises(ValidationError) as caught:
        ModelIdentity(ProviderKind.OLLAMA, "m", BARE_HEX)

    assert "normalize_digest()" in str(caught.value)
    assert caught.value.details["field"] == "artifact_digest"


# ---- Digest upgrade -------------------------------------------------------------------------
def test_with_digest_returns_an_identity_equal_except_for_the_digest() -> None:
    original = ModelIdentity(ProviderKind.OLLAMA, "qwen3.5:9b-q8_0")

    upgraded = original.with_digest(BARE_HEX)

    assert upgraded.provider_kind == original.provider_kind
    assert upgraded.provider_model_name == original.provider_model_name
    assert upgraded.artifact_digest == DIGEST
    assert upgraded.identity_confidence is IdentityConfidence.DIGEST
    assert original.artifact_digest is None  # the original is untouched


def test_with_digest_normalizes_what_the_provider_reported() -> None:
    upgraded = ModelIdentity(ProviderKind.OLLAMA, "m").with_digest(f"SHA256:{BARE_HEX.upper()}")

    assert upgraded.artifact_digest == DIGEST


def test_with_digest_refuses_a_value_that_will_not_normalize() -> None:
    # Silently dropping it would leave the caller unable to tell an upgraded identity from one
    # that must be recorded as name_only.
    with pytest.raises(ValidationError, match="normalize_digest"):
        ModelIdentity(ProviderKind.OLLAMA, "m").with_digest("nonsense")


# ---- Provider kinds -------------------------------------------------------------------------
def test_provider_kind_values_are_the_persisted_strings() -> None:
    # These appear in every canonical ID and in three databases; renaming one is a data migration.
    assert [kind.value for kind in ProviderKind] == [
        "ollama",
        "openai_compatible",
        "llamacpp",
        "vllm",
        "fake",
    ]
