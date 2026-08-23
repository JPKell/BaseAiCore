"""Unit tests for model descriptors: refreshable metadata, kept apart from identity.

The rule under test throughout: every architecture field accepts UNSUPPORTED without complaint,
and `raw` is preserved exactly as given — a descriptor must never fabricate a number it was not
told.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from baseaicore.descriptor import ModelCapabilityFlag, ModelDescriptor
from baseaicore.errors import ValidationError
from baseaicore.identity import ModelIdentity, ProviderKind
from baseaicore.measurement import UNSUPPORTED

OBSERVED_AT = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
IDENTITY = ModelIdentity(ProviderKind.OLLAMA, "qwen3.5:9b-q8_0")


def descriptor(**overrides: Any) -> ModelDescriptor:
    """Build a descriptor, overriding any field."""
    defaults: dict[str, Any] = {"identity": IDENTITY, "observed_at": OBSERVED_AT}
    return ModelDescriptor(**{**defaults, **overrides})


NUMERIC_FIELDS = [
    "parameter_count",
    "active_parameter_count",
    "expert_count",
    "size_bytes",
    "max_context",
    "embedding_dim",
    "layers",
    "attention_heads",
    "kv_heads",
    "head_dim",
    "vocab_size",
    "sliding_window",
]


def test_every_optional_numeric_field_defaults_to_unsupported() -> None:
    built = descriptor()

    for field_name in NUMERIC_FIELDS:
        assert getattr(built, field_name) is UNSUPPORTED, field_name


@pytest.mark.parametrize("field_name", NUMERIC_FIELDS)
def test_every_numeric_field_explicitly_accepts_unsupported(field_name: str) -> None:
    # Not just the default: passing UNSUPPORTED explicitly must not be treated as an error, the
    # way a provider adapter that could not read one field would construct a descriptor.
    built = descriptor(**{field_name: UNSUPPORTED})

    assert getattr(built, field_name) is UNSUPPORTED


@pytest.mark.parametrize("field_name", NUMERIC_FIELDS)
def test_each_numeric_field_accepts_a_real_value_independently_of_the_others(
    field_name: str,
) -> None:
    # Every other numeric field stays UNSUPPORTED — setting one field must not fabricate another.
    built = descriptor(**{field_name: 7})

    assert getattr(built, field_name) == 7
    for other_field in NUMERIC_FIELDS:
        if other_field != field_name:
            assert getattr(built, other_field) is UNSUPPORTED, other_field


def test_raw_defaults_to_an_empty_mapping() -> None:
    assert descriptor().raw == {}


def test_raw_is_preserved_untouched() -> None:
    raw_response = {"nested": {"ollama_field": 42}, "digest": "unrelated-to-identity"}

    built = descriptor(raw=raw_response)

    assert built.raw == raw_response


def test_declared_capabilities_default_to_empty() -> None:
    assert descriptor().declared_capabilities == frozenset()


def test_declared_capabilities_hold_the_provider_claimed_flags() -> None:
    built = descriptor(
        declared_capabilities=frozenset({ModelCapabilityFlag.TOOLS, ModelCapabilityFlag.VISION})
    )

    assert built.declared_capabilities == {ModelCapabilityFlag.TOOLS, ModelCapabilityFlag.VISION}


def test_string_fields_default_to_none() -> None:
    built = descriptor()

    assert built.family is None
    assert built.architecture is None
    assert built.quantization is None
    assert built.weight_format is None
    assert built.rope_config is None
    assert built.license_text is None


def test_naive_observed_at_is_rejected() -> None:
    naive = datetime(2026, 8, 22, 12, 0)  # noqa: DTZ001 — the input under test

    with pytest.raises(ValidationError, match="timezone-aware"):
        descriptor(observed_at=naive)


def test_two_descriptors_of_the_same_identity_are_independent_snapshots() -> None:
    # A refresh never rewrites history: an older snapshot and a newer one coexist as two values.
    first = descriptor(parameter_count=9_200_000_000)
    second = descriptor(
        observed_at=datetime(2026, 8, 23, tzinfo=UTC), parameter_count=9_300_000_000
    )

    assert first.parameter_count == 9_200_000_000
    assert second.parameter_count == 9_300_000_000
    assert first != second
