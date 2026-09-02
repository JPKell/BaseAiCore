"""Unit tests for the adapter axis.

The canonical suffixes below are fixed by ADR-0058. They become part of a persisted subject key in
three databases the moment adapters are served, so a change that makes one fail is the change that
is wrong, not the test.
"""

from __future__ import annotations

import copy
import pickle

import pytest

from baseaicore.adapter import AdapterIdentity, verify_adapter_base_compatibility
from baseaicore.errors import ValidationError
from baseaicore.identity import IdentityConfidence, ModelIdentity, ProviderKind

BASE_DIGEST = "sha256:1f3a9c4e2b70a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f607182930"
ADAPTER_DIGEST = "sha256:9e2b41d07c55a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f607182930"
SOURCE_DIGEST = "sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"

# ---- Golden canonical suffixes (ADR-0058) ----------------------------------------------------
GOLDEN_SUFFIXES = [
    ("factcheck", ADAPTER_DIGEST, "+factcheck@sha256:9e2b41d07c55"),
    ("house-voice", ADAPTER_DIGEST, "+house-voice@sha256:9e2b41d07c55"),
    ("sql_expert2", BASE_DIGEST, "+sql_expert2@sha256:1f3a9c4e2b70"),
]


@pytest.mark.parametrize(("name", "digest", "expected"), GOLDEN_SUFFIXES)
def test_the_canonical_suffix_matches_its_golden_value(
    name: str, digest: str, expected: str
) -> None:
    assert AdapterIdentity(name, digest).canonical_suffix == expected


def test_the_suffix_keeps_the_algorithm_prefix_and_twelve_hex_characters() -> None:
    # The same truncation rule ADR-0024 §1 fixed for a model identity, reused rather than
    # re-derived, so one string cannot be shortened two ways.
    adapter = AdapterIdentity("factcheck", ADAPTER_DIGEST)

    assert adapter.digest_short == "sha256:9e2b41d07c55"
    assert len(adapter.digest_short.removeprefix("sha256:")) == 12


def test_str_is_the_suffix_without_its_plus_so_a_log_line_stays_greppable() -> None:
    assert f"{AdapterIdentity('factcheck', ADAPTER_DIGEST)}" == "factcheck@sha256:9e2b41d07c55"


def test_the_suffix_is_computed_once_and_returned_unchanged() -> None:
    adapter = AdapterIdentity("factcheck", ADAPTER_DIGEST)

    assert adapter.canonical_suffix == adapter.canonical_suffix


# ---- Identity semantics ----------------------------------------------------------------------


def test_identity_is_the_served_artifact_so_lineage_does_not_split_a_subject() -> None:
    # source_digest records where the adapter came from; it never participates in identity,
    # because the artifact served is what produced the behaviour (ADR-0058 rule 1).
    without_lineage = AdapterIdentity("factcheck", ADAPTER_DIGEST)
    with_lineage = AdapterIdentity("factcheck", ADAPTER_DIGEST, SOURCE_DIGEST)

    assert without_lineage == with_lineage
    assert hash(without_lineage) == hash(with_lineage)
    assert with_lineage.source_digest == SOURCE_DIGEST


def test_a_different_artifact_is_a_different_adapter_even_under_the_same_name() -> None:
    # Content addressing: a rename is safe, a content change is a new subject.
    assert AdapterIdentity("factcheck", ADAPTER_DIGEST) != AdapterIdentity("factcheck", BASE_DIGEST)


def test_the_name_is_part_of_identity_because_it_is_part_of_the_canonical_string() -> None:
    # Two equal values that render differently would be incoherent.
    first = AdapterIdentity("factcheck", ADAPTER_DIGEST)
    second = AdapterIdentity("fact-check", ADAPTER_DIGEST)

    assert first != second
    assert first.canonical_suffix != second.canonical_suffix


def test_equality_and_hashing_survive_copying_and_pickling() -> None:
    adapter = AdapterIdentity("factcheck", ADAPTER_DIGEST, SOURCE_DIGEST)

    for revived in (copy.deepcopy(adapter), pickle.loads(pickle.dumps(adapter))):  # noqa: S301 — our bytes
        assert revived == adapter
        assert hash(revived) == hash(adapter)


def test_an_adapter_identity_is_frozen() -> None:
    adapter = AdapterIdentity("factcheck", ADAPTER_DIGEST)

    with pytest.raises((AttributeError, TypeError)):
        adapter.name = "other"  # type: ignore[misc]  # proving the refusal


# ---- Refusals --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "",
        "a",  # one character: the shape requires at least two
        "Factcheck",  # uppercase
        "1factcheck",  # must start with a letter
        "-factcheck",  # must start with a letter
        "fact check",  # no spaces
        "fact.check",  # no dots
        "f" * 65,  # over the 64-character limit
    ],
)
def test_a_name_outside_the_manifest_shape_is_refused(name: str) -> None:
    with pytest.raises(ValidationError, match="Adapter name must match"):
        AdapterIdentity(name, ADAPTER_DIGEST)


@pytest.mark.parametrize(
    "digest",
    [
        "",
        "1f3a9c4e2b70",  # a short digest, not a full one
        "sha256:NOTHEX" + "0" * 58,
        "SHA256:" + "a" * 64,  # not normalized: uppercase prefix
        "sha256:" + "A" * 64,  # not normalized: uppercase hex
        "a" * 64,  # not normalized: bare hex, prefix missing
        "sha256:" + "a" * 63,  # one hex character short
    ],
)
def test_an_artifact_digest_that_is_not_already_normalized_is_refused(digest: str) -> None:
    # An adapter is content-addressed, so a digest that will not normalize is a refusal — never a
    # name_only adapter, which is the degradation a *model* identity is allowed.
    with pytest.raises(ValidationError, match="artifact_digest must be"):
        AdapterIdentity("factcheck", digest)


def test_an_unusable_source_digest_is_refused_rather_than_stored_malformed() -> None:
    with pytest.raises(ValidationError, match="source_digest must be"):
        AdapterIdentity("factcheck", ADAPTER_DIGEST, "not-a-digest")


# ---- Base compatibility (ADR-0058 rule 5) ----------------------------------------------------

SERVED_BASE = ModelIdentity(ProviderKind.LLAMACPP, "qwen3.5-9b-q8", BASE_DIGEST)
SERVED_BASE_WITHOUT_DIGEST = ModelIdentity(ProviderKind.LLAMACPP, "qwen3.5-9b-q8")


def test_a_matching_declared_digest_verifies_at_full_confidence() -> None:
    confidence = verify_adapter_base_compatibility(
        SERVED_BASE, declared_base_name="qwen3.5-9b-q8", declared_base_digest=BASE_DIGEST
    )

    assert confidence is IdentityConfidence.DIGEST


def test_a_name_only_declaration_is_accepted_with_visibly_reduced_confidence() -> None:
    # A PEFT adapter_config.json names its base by name, which is not a proof. The suite already
    # knows how to display, store and discount name_only, so the uncertainty rides that rail
    # rather than a parallel flag.
    confidence = verify_adapter_base_compatibility(SERVED_BASE, declared_base_name="qwen3.5-9b-q8")

    assert confidence is IdentityConfidence.NAME_ONLY


def test_a_mismatched_base_digest_is_refused_and_never_attempted() -> None:
    with pytest.raises(ValidationError, match="fails closed"):
        verify_adapter_base_compatibility(
            SERVED_BASE, declared_base_name="qwen3.5-9b-q8", declared_base_digest=ADAPTER_DIGEST
        )


def test_a_declared_digest_against_an_unidentifiable_base_is_refused() -> None:
    # Fail closed: the claim cannot be checked, so it is not accepted at a lower confidence.
    with pytest.raises(ValidationError, match="cannot be verified"):
        verify_adapter_base_compatibility(
            SERVED_BASE_WITHOUT_DIGEST,
            declared_base_name="qwen3.5-9b-q8",
            declared_base_digest=BASE_DIGEST,
        )


def test_a_mismatched_base_name_with_no_digest_is_refused() -> None:
    with pytest.raises(ValidationError, match="the name is the only"):
        verify_adapter_base_compatibility(SERVED_BASE, declared_base_name="llama4-8b")
