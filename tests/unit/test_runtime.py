"""Unit tests for `RuntimeProfile.profile_hash`.

The rule under test throughout: the same runtime settings hash the same everywhere, `None` never
leaks into the hash as a value, and two profiles that differ in any one field hash differently —
that difference is what makes a differing runtime profile a hard separation between measurements
(ADR-0023 §1).
"""

from __future__ import annotations

import subprocess
import sys

from baseaicore.runtime import RuntimeProfile


def test_default_profile_is_legal_and_hashable() -> None:
    # RuntimeProfile() means "provider defaults"; there is no "no profile" state (ADR-0023 §1).
    profile = RuntimeProfile()

    assert isinstance(profile.profile_hash, str)
    assert len(profile.profile_hash) == 16


def test_identical_profiles_built_separately_hash_the_same() -> None:
    first = RuntimeProfile(context_size=32_768, kv_cache_precision="q8_0", gpu_layers=999)
    second = RuntimeProfile(context_size=32_768, kv_cache_precision="q8_0", gpu_layers=999)

    assert first.profile_hash == second.profile_hash


def test_the_hash_is_computed_once_and_returned_unchanged() -> None:
    profile = RuntimeProfile(context_size=8192)

    assert profile.profile_hash == profile.profile_hash


def test_differing_context_size_produces_a_different_hash() -> None:
    small = RuntimeProfile(context_size=8192)
    large = RuntimeProfile(context_size=32_768)

    assert small.profile_hash != large.profile_hash


def test_none_fields_are_excluded_rather_than_hashed_as_null() -> None:
    # A profile built before a field existed must hash identically to one that explicitly leaves
    # that field unset — adding an optional field is additive, never a silent hash break.
    explicit_default = RuntimeProfile(context_size=8192, threads=None)
    never_mentioned = RuntimeProfile(context_size=8192)

    assert explicit_default.profile_hash == never_mentioned.profile_hash


def test_every_settable_field_changes_the_hash_when_changed_alone() -> None:
    baseline = RuntimeProfile(
        context_size=8192,
        kv_cache_precision="f16",
        gpu_layers=10,
        flash_attention=False,
        threads=4,
        batch_size=512,
        keep_alive="5m",
    )
    variants = [
        RuntimeProfile(
            context_size=16_384,
            kv_cache_precision="f16",
            gpu_layers=10,
            flash_attention=False,
            threads=4,
            batch_size=512,
            keep_alive="5m",
        ),
        RuntimeProfile(
            context_size=8192,
            kv_cache_precision="q8_0",
            gpu_layers=10,
            flash_attention=False,
            threads=4,
            batch_size=512,
            keep_alive="5m",
        ),
        RuntimeProfile(
            context_size=8192,
            kv_cache_precision="f16",
            gpu_layers=20,
            flash_attention=False,
            threads=4,
            batch_size=512,
            keep_alive="5m",
        ),
        RuntimeProfile(
            context_size=8192,
            kv_cache_precision="f16",
            gpu_layers=10,
            flash_attention=True,
            threads=4,
            batch_size=512,
            keep_alive="5m",
        ),
        RuntimeProfile(
            context_size=8192,
            kv_cache_precision="f16",
            gpu_layers=10,
            flash_attention=False,
            threads=8,
            batch_size=512,
            keep_alive="5m",
        ),
        RuntimeProfile(
            context_size=8192,
            kv_cache_precision="f16",
            gpu_layers=10,
            flash_attention=False,
            threads=4,
            batch_size=1024,
            keep_alive="5m",
        ),
        RuntimeProfile(
            context_size=8192,
            kv_cache_precision="f16",
            gpu_layers=10,
            flash_attention=False,
            threads=4,
            batch_size=512,
            keep_alive="10m",
        ),
    ]

    for variant in variants:
        assert variant.profile_hash != baseline.profile_hash


def test_nested_provider_options_are_hashed_deterministically() -> None:
    first = RuntimeProfile(provider_options={"a": 1, "b": {"c": 2}})
    second = RuntimeProfile(
        provider_options={"b": {"c": 2}, "a": 1}
    )  # different construction order

    assert first.profile_hash == second.profile_hash


def test_differing_nested_provider_options_produce_a_different_hash() -> None:
    first = RuntimeProfile(provider_options={"num_gpu": 1})
    second = RuntimeProfile(provider_options={"num_gpu": 2})

    assert first.profile_hash != second.profile_hash


def test_the_hash_cache_is_invisible_to_equality_and_repr() -> None:
    first = RuntimeProfile(context_size=8192)
    second = RuntimeProfile(context_size=8192)
    _ = first.profile_hash  # populate the cache on `first` only

    assert first == second
    assert repr(first) == repr(second)


def test_profile_hash_is_stable_across_processes() -> None:
    # It is stored beside runs in FreeWeight and LoadCoach; a per-process hash would be worthless.
    program = (
        "from baseaicore.runtime import RuntimeProfile;"
        "print(RuntimeProfile(context_size=32768, kv_cache_precision='q8_0').profile_hash)"
    )

    result = subprocess.run(  # noqa: S603 — our own interpreter, no shell, literal argument list
        [sys.executable, "-c", program], capture_output=True, text=True, check=True
    )

    assert (
        result.stdout.strip()
        == RuntimeProfile(context_size=32_768, kv_cache_precision="q8_0").profile_hash
    )
