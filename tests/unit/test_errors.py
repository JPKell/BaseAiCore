"""Unit tests for the base error hierarchy. Error codes are a public contract (spec §11)."""

from __future__ import annotations

import pickle

import pytest

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

# The golden code table. These strings appear in API error envelopes, stored event rows and CLI
# exit-code mapping, so changing one is a breaking change for three applications — this test is
# the thing that makes that visible in a diff.
EXPECTED_CODES = [
    (SuiteError, "INTERNAL_ERROR"),
    (ConfigurationError, "CONFIGURATION_ERROR"),
    (ValidationError, "VALIDATION_ERROR"),
    (NotFoundError, "NOT_FOUND"),
    (ConflictError, "CONFLICT"),
    (UnsupportedOperationError, "UNSUPPORTED_OPERATION"),
    (UnsupportedPlatformError, "UNSUPPORTED_PLATFORM"),
    (DependencyUnavailableError, "DEPENDENCY_UNAVAILABLE"),
]


EXPECTED_CODE_IDS = [error_type.__name__ for error_type, _ in EXPECTED_CODES]


@pytest.mark.parametrize(("error_type", "code"), EXPECTED_CODES, ids=EXPECTED_CODE_IDS)
def test_each_error_carries_its_documented_code(error_type: type[SuiteError], code: str) -> None:
    assert error_type.code == code
    assert error_type("boom").code == code


@pytest.mark.parametrize(("error_type", "_code"), EXPECTED_CODES, ids=EXPECTED_CODE_IDS)
def test_every_error_is_a_suite_error(error_type: type[SuiteError], _code: str) -> None:
    assert issubclass(error_type, SuiteError)
    assert issubclass(error_type, Exception)


def test_details_default_to_an_empty_mapping_not_none() -> None:
    assert SuiteError("boom").details == {}


def test_details_are_copied_so_later_mutation_cannot_change_a_raised_error() -> None:
    supplied = {"field": "name"}

    error = ValidationError("boom", details=supplied)
    supplied["field"] = "something else"

    assert error.details == {"field": "name"}


def test_str_is_the_message_alone() -> None:
    assert str(ValidationError("name must not be empty")) == "name must not be empty"


def test_repr_names_the_class_code_message_and_details() -> None:
    text = repr(NotFoundError("no such model", details={"model": "qwen"}))

    assert "NotFoundError" in text
    assert "NOT_FOUND" in text
    assert "no such model" in text
    assert "qwen" in text


def test_chaining_preserves_the_cause() -> None:
    try:
        try:
            raise ValueError("underlying")
        except ValueError as exc:
            raise ValidationError("wrapped") from exc
    except ValidationError as caught:
        assert isinstance(caught.__cause__, ValueError)
        assert str(caught.__cause__) == "underlying"


def test_an_error_survives_pickling_with_its_message_and_details() -> None:
    # The default Exception reduction replays `args`, which drops `details`; an error crossing a
    # process boundary must keep the half a machine reads.
    original = ConflictError("duplicate", details={"key": "abc"})

    restored = pickle.loads(pickle.dumps(original))  # noqa: S301 — our own bytes, not input

    assert restored.message == "duplicate"
    assert restored.code == "CONFLICT"
    assert restored.details == {"key": "abc"}
    assert type(restored) is ConflictError
