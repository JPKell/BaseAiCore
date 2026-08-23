"""Unit tests for the capability identifier type.

Valid and invalid syntax cases are the ones named in the development plan (Phase 4): valid —
``coding``, ``coding.python``, ``content.article_draft``; invalid — empty, leading dot, double
dot, uppercase, spaces, trailing dot, over-long.
"""

from __future__ import annotations

import copy
import pickle

import pytest

from baseaicore.capability import CapabilityId
from baseaicore.errors import ValidationError

# ---- Valid syntax ----------------------------------------------------------------------------
VALID_VALUES = ["coding", "coding.python", "content.article_draft", "a", "gpu4", "a.b.c"]


@pytest.mark.parametrize("value", VALID_VALUES)
def test_a_well_formed_value_constructs_without_error(value: str) -> None:
    assert CapabilityId(value).value == value


# ---- Invalid syntax ---------------------------------------------------------------------------
INVALID_VALUES = [
    ("", "empty"),
    (".coding", "leading dot"),
    ("coding..python", "double dot"),
    ("coding.", "trailing dot"),
    ("Coding", "uppercase"),
    ("coding.Python", "uppercase in specialization"),
    ("coding python", "spaces"),
    ("a" * 65, "over-long"),
    ("_coding", "leading underscore"),
    ("1coding", "leading digit"),
    ("coding-python", "hyphen"),
    ("coding/python", "slash"),
]


@pytest.mark.parametrize(("value", "_reason"), INVALID_VALUES, ids=[r for _, r in INVALID_VALUES])
def test_a_malformed_value_is_refused(value: str, _reason: str) -> None:
    with pytest.raises(ValidationError):
        CapabilityId(value)


def test_the_over_long_value_is_exactly_at_the_documented_boundary() -> None:
    # 64 characters is the documented maximum (module docstring); one over must fail, and the
    # boundary itself must succeed, or "over-long" has no single tested meaning.
    CapabilityId("a" * 64)

    with pytest.raises(ValidationError, match="64"):
        CapabilityId("a" * 65)


def test_the_refusal_message_names_the_field() -> None:
    with pytest.raises(ValidationError) as caught:
        CapabilityId("Coding")

    assert caught.value.details["field"] == "value"
    assert caught.value.details["value"] == "Coding"


# ---- root ---------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "expected_root"),
    [("coding", "coding"), ("coding.python", "coding"), ("content.article_draft", "content")],
)
def test_root_is_the_first_segment(value: str, expected_root: str) -> None:
    assert CapabilityId(value).root == expected_root


# ---- is_specialization ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "expected"),
    [("coding", False), ("coding.python", True), ("content.article_draft", True)],
)
def test_is_specialization_reflects_whether_a_further_segment_exists(
    value: str, expected: bool
) -> None:
    assert CapabilityId(value).is_specialization is expected


# ---- inherits_from --------------------------------------------------------------------------
def test_a_specialization_inherits_from_its_root() -> None:
    assert CapabilityId("coding.python").inherits_from(CapabilityId("coding")) is True


def test_a_root_does_not_inherit_from_its_own_specialization() -> None:
    assert CapabilityId("coding").inherits_from(CapabilityId("coding.python")) is False


def test_every_identifier_inherits_from_itself() -> None:
    assert CapabilityId("coding.python").inherits_from(CapabilityId("coding.python")) is True
    assert CapabilityId("coding").inherits_from(CapabilityId("coding")) is True


def test_unrelated_identifiers_do_not_inherit() -> None:
    assert CapabilityId("coding.python").inherits_from(CapabilityId("content")) is False


def test_a_deep_specialization_inherits_from_every_ancestor() -> None:
    grandchild = CapabilityId("coding.python.async")

    assert grandchild.inherits_from(CapabilityId("coding.python")) is True
    assert grandchild.inherits_from(CapabilityId("coding")) is True


def test_a_shared_prefix_that_is_not_a_dot_boundary_does_not_inherit() -> None:
    # `coding2` shares the literal prefix "coding" but is not a specialization of `coding` — the
    # match must respect the `.` boundary, not just string prefix.
    assert CapabilityId("coding2").inherits_from(CapabilityId("coding")) is False


# ---- Equality, hashing and immutability -------------------------------------------------------
def test_two_identifiers_are_equal_when_their_values_are() -> None:
    assert CapabilityId("coding.python") == CapabilityId("coding.python")


def test_identifiers_are_usable_as_dictionary_keys() -> None:
    key = CapabilityId("coding.python")

    assert {key: "value"}[CapabilityId("coding.python")] == "value"


def test_a_capability_id_is_frozen() -> None:
    identifier = CapabilityId("coding")

    with pytest.raises((AttributeError, TypeError)):
        identifier.value = "other"  # type: ignore[misc]  # proving the refusal


@pytest.mark.parametrize(
    "round_trip",
    [copy.copy, copy.deepcopy, lambda v: pickle.loads(pickle.dumps(v))],  # noqa: S301 — our bytes
    ids=["copy", "deepcopy", "pickle"],
)
def test_a_capability_id_round_trips_equal(round_trip: object) -> None:
    original = CapabilityId("coding.python")

    restored = round_trip(original)  # type: ignore[operator]  # parametrized callables

    assert restored == original


# ---- String form ------------------------------------------------------------------------------
def test_str_is_the_bare_value_so_log_interpolation_stays_greppable() -> None:
    assert f"{CapabilityId('coding.python')}" == "coding.python"
