"""Unit tests for the machine profile and its fingerprint.

The property under test throughout: a machine keeps one identity across every change that is not a
hardware change, and loses it the moment the hardware changes. The exclusion policy in
machine identity and reproducibility §3 is asserted here rather than only
documented, because a fingerprint that quietly started including the driver version would orphan
every stored result on the next `apt upgrade` and nothing else would notice.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from baseaicore.errors import ValidationError
from baseaicore.machine import (
    GpuProfile,
    GpuVendor,
    MachineProfile,
    StorageDevice,
    compute_machine_fingerprint,
)
from baseaicore.measurement import UNSUPPORTED

REFERENCE_GPU = GpuProfile(
    index=0,
    name="NVIDIA GeForce RTX 5060 Ti",
    uuid="GPU-1f3a9c4e-2b70-a1b2-c3d4-e5f607182930",
    vram_total_bytes=16 * 1024**3,
    driver_version="580.65.06",
    cuda_version="13.0",
    compute_capability="12.0",
    vendor=GpuVendor.NVIDIA,
)
"""The reference machine's GPU. Fixed so the golden fingerprint below never moves."""

REFERENCE_IDENTITY: dict[str, Any] = {
    "hostname": "workstation",
    "os_name": "Linux",
    "architecture": "x86_64",
    "cpu_model": "AMD Ryzen 9 9950X 16-Core Processor",
    "physical_cores": 16,
    "logical_cores": 32,
    "ram_bytes": 64 * 1024**3,
    "gpus": (REFERENCE_GPU,),
}
"""Every fingerprint input for the reference machine, as keyword arguments."""

GOLDEN_FINGERPRINT = "6f4b8b54d54736cd0b8fda16eeb97fbc756470512e709f105260169753e8d947"
"""The fingerprint of ``REFERENCE_IDENTITY``.

Like the canonical-ID golden, this value must never be "updated to match" a change. It is a
persisted lookup key: every benchmark result, every piece of routing evidence and every export
carries it, so a change here silently splits one machine's history into two machines. A failure
means the inclusion policy changed, and that is a coordinated, suite-wide event.
"""


def fingerprint_of(profile: MachineProfile) -> str:
    """Recompute a profile's fingerprint from its own fields.

    Deliberately not a method on ``MachineProfile``: the fingerprint stored on a profile is the one
    it was written with, and re-deriving it in production would rewrite history whenever the policy
    changed. Here it exists to prove the exclusions — a field this helper cannot pass on is a field
    that cannot affect the result.
    """
    return compute_machine_fingerprint(
        hostname=profile.hostname,
        os_name=profile.os_name,
        architecture=profile.architecture,
        cpu_model=profile.cpu_model,
        physical_cores=profile.physical_cores,
        logical_cores=profile.logical_cores,
        ram_bytes=profile.ram_bytes,
        gpus=profile.gpus,
    )


def reference_profile(**overrides: Any) -> MachineProfile:
    """Build a complete profile of the reference machine, with the given fields replaced."""
    fields: dict[str, Any] = {
        "machine_fingerprint": GOLDEN_FINGERPRINT,
        "hostname": "workstation",
        "os_name": "Linux",
        "os_version": "Ubuntu 26.04 LTS",
        "kernel": "7.0.0-30-generic",
        "architecture": "x86_64",
        "cpu_model": "AMD Ryzen 9 9950X 16-Core Processor",
        "physical_cores": 16,
        "logical_cores": 32,
        "ram_bytes": 64 * 1024**3,
        "gpus": (REFERENCE_GPU,),
        "storage": (StorageDevice(name="nvme0n1", size_bytes=2 * 1024**4, rotational=False),),
        "python_version": "3.12.7",
        "observed_at": datetime(2026, 8, 22, 14, 3, 11, tzinfo=UTC),
    }
    return MachineProfile(**(fields | overrides))


# --- The golden value, and the shape of the result -------------------------------------------


def test_the_reference_machine_has_its_golden_fingerprint() -> None:
    assert compute_machine_fingerprint(**REFERENCE_IDENTITY) == GOLDEN_FINGERPRINT


def test_the_fingerprint_is_sixty_four_lowercase_hex_characters() -> None:
    fingerprint = compute_machine_fingerprint(**REFERENCE_IDENTITY)

    assert len(fingerprint) == 64
    assert set(fingerprint) <= set("0123456789abcdef")


def test_the_fingerprint_is_stable_across_processes() -> None:
    # It is a persisted key in three databases; a per-process value would be worthless.
    program = (
        "from baseaicore.machine import GpuProfile, compute_machine_fingerprint;"
        "print(compute_machine_fingerprint("
        "hostname='workstation', os_name='Linux', architecture='x86_64',"
        "cpu_model='AMD Ryzen 9 9950X 16-Core Processor',"
        "physical_cores=16, logical_cores=32, ram_bytes=68719476736,"
        "gpus=(GpuProfile(index=0, name='NVIDIA GeForce RTX 5060 Ti',"
        "uuid='GPU-1f3a9c4e-2b70-a1b2-c3d4-e5f607182930'),)))"
    )

    result = subprocess.run(  # noqa: S603 — our own interpreter, no shell, literal argument list
        [sys.executable, "-c", program], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == GOLDEN_FINGERPRINT


def test_the_fingerprint_ignores_the_gpu_fields_that_are_not_identity() -> None:
    # The golden above was computed with a GPU carrying VRAM, driver, CUDA, capability and vendor;
    # a bare (index, name, uuid) triple must land on the same machine.
    bare_gpu = GpuProfile(index=0, name=REFERENCE_GPU.name, uuid=REFERENCE_GPU.uuid)

    assert (
        compute_machine_fingerprint(**{**REFERENCE_IDENTITY, "gpus": (bare_gpu,)})
        == GOLDEN_FINGERPRINT
    )


# --- The exclusion policy: these changes must NOT re-identify the machine ---------------------


@pytest.mark.parametrize(
    ("field_name", "new_value"),
    [
        ("driver_version", "581.00.00"),
        ("cuda_version", "13.1"),
        ("compute_capability", "12.1"),
        ("vendor", GpuVendor.UNKNOWN),
        ("vram_total_bytes", 24 * 1024**3),
    ],
)
def test_a_gpu_field_outside_the_policy_does_not_change_the_fingerprint(
    field_name: str, new_value: Any
) -> None:
    # A driver upgrade must not orphan a machine's entire measurement history (Machine Identity §3).
    upgraded = replace(REFERENCE_GPU, **{field_name: new_value})

    assert (
        compute_machine_fingerprint(**{**REFERENCE_IDENTITY, "gpus": (upgraded,)})
        == GOLDEN_FINGERPRINT
    )


@pytest.mark.parametrize(
    ("field_name", "new_value"),
    [
        ("os_version", "Ubuntu 28.04 LTS"),
        ("kernel", "8.1.0-1-generic"),
        ("python_version", "3.14.0"),
        ("storage", (StorageDevice(name="sda", size_bytes=8 * 1024**4, rotational=True),)),
        ("storage", ()),
        ("observed_at", datetime(2027, 1, 1, tzinfo=UTC)),
    ],
)
def test_a_profile_field_outside_the_policy_does_not_change_the_fingerprint(
    field_name: str, new_value: Any
) -> None:
    # Plugging in a disk, upgrading the OS or changing interpreter is not a new machine. These
    # fields are not even parameters of compute_machine_fingerprint, which is the strongest form
    # the exclusion can take; this asserts it from the profile that carries them.
    changed = reference_profile(**{field_name: new_value})

    assert fingerprint_of(changed) == GOLDEN_FINGERPRINT


def test_gpu_enumeration_order_does_not_change_the_fingerprint() -> None:
    first = GpuProfile(index=0, name="RTX 5060 Ti", uuid="GPU-aaaa")
    second = GpuProfile(index=1, name="RTX 4090", uuid="GPU-bbbb")

    forwards = compute_machine_fingerprint(**{**REFERENCE_IDENTITY, "gpus": (first, second)})
    backwards = compute_machine_fingerprint(**{**REFERENCE_IDENTITY, "gpus": (second, first)})

    assert forwards == backwards


def test_an_identified_gpu_moving_to_another_slot_does_not_change_the_fingerprint() -> None:
    # The UUID is the device's real identity; the index is only where it was enumerated this boot.
    moved = GpuProfile(index=3, name=REFERENCE_GPU.name, uuid=REFERENCE_GPU.uuid)

    assert (
        compute_machine_fingerprint(**{**REFERENCE_IDENTITY, "gpus": (moved,)})
        == GOLDEN_FINGERPRINT
    )


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_a_blank_string_is_the_same_as_unreported(blank: str) -> None:
    # One collector reports a missing CPU model as None and another as ""; the machine is the same.
    unreported = compute_machine_fingerprint(**{**REFERENCE_IDENTITY, "cpu_model": None})
    blank_reported = compute_machine_fingerprint(**{**REFERENCE_IDENTITY, "cpu_model": blank})

    assert blank_reported == unreported


def test_surrounding_whitespace_does_not_change_the_fingerprint() -> None:
    # /proc/cpuinfo and nvidia-smi fields routinely carry it; two readers, one machine.
    padded = compute_machine_fingerprint(
        **{**REFERENCE_IDENTITY, "cpu_model": "  AMD Ryzen 9 9950X 16-Core Processor\n"}
    )

    assert padded == GOLDEN_FINGERPRINT


@pytest.mark.parametrize("field_name", ["physical_cores", "logical_cores", "ram_bytes"])
def test_a_whole_valued_float_quantity_matches_the_equal_integer(field_name: str) -> None:
    # How a collector did its arithmetic must not decide which machine it is on.
    as_float = float(REFERENCE_IDENTITY[field_name])

    assert (
        compute_machine_fingerprint(**{**REFERENCE_IDENTITY, field_name: as_float})
        == GOLDEN_FINGERPRINT
    )


# --- Sensitivity: these changes MUST re-identify the machine ----------------------------------


@pytest.mark.parametrize(
    ("field_name", "new_value"),
    [
        ("hostname", "laptop"),
        ("os_name", "Darwin"),
        ("architecture", "aarch64"),
        ("cpu_model", "Intel Core Ultra 9 285K"),
        ("physical_cores", 8),
        ("logical_cores", 16),
        ("ram_bytes", 32 * 1024**3),
        ("gpus", ()),
        ("gpus", (REFERENCE_GPU, GpuProfile(index=1, name="RTX 4090", uuid="GPU-bbbb"))),
        ("gpus", (GpuProfile(index=0, name="RTX 4090", uuid=REFERENCE_GPU.uuid),)),
        ("gpus", (GpuProfile(index=0, name=REFERENCE_GPU.name, uuid="GPU-replaced"),)),
    ],
)
def test_an_identity_field_changes_the_fingerprint(field_name: str, new_value: Any) -> None:
    assert compute_machine_fingerprint(**{**REFERENCE_IDENTITY, field_name: new_value}) != (
        GOLDEN_FINGERPRINT
    )


@pytest.mark.parametrize("field_name", ["hostname", "os_name", "architecture", "cpu_model"])
def test_an_unreported_string_field_changes_the_fingerprint(field_name: str) -> None:
    # Losing a field is a real identity change: the machine now carries less identity than the one
    # the golden describes, and merging their histories would be a guess.
    assert compute_machine_fingerprint(**{**REFERENCE_IDENTITY, field_name: None}) != (
        GOLDEN_FINGERPRINT
    )


# --- Machines that cannot describe themselves -------------------------------------------------


def test_a_machine_that_reports_nothing_still_has_one_stable_fingerprint() -> None:
    # Development plan Phase 3, acceptance criterion 2. It carries less identity; it still has one.
    def blank_fingerprint() -> str:
        return compute_machine_fingerprint(
            hostname=None,
            os_name=None,
            architecture=None,
            cpu_model=None,
            physical_cores=UNSUPPORTED,
            logical_cores=UNSUPPORTED,
            ram_bytes=UNSUPPORTED,
            gpus=(),
        )

    assert len(blank_fingerprint()) == 64
    assert blank_fingerprint() == blank_fingerprint()


def test_unsupported_and_none_hash_as_the_same_literal_string() -> None:
    # Machine Identity §3: unreadable fields hash as the literal "unsupported". Asserted from
    # outside by the documented, accepted consequence — a CPU that genuinely reports the word
    # "unsupported" is indistinguishable from one that could not be read at all.
    unreadable = compute_machine_fingerprint(
        **{**REFERENCE_IDENTITY, "cpu_model": None, "ram_bytes": UNSUPPORTED}
    )
    literal = compute_machine_fingerprint(
        **{**REFERENCE_IDENTITY, "cpu_model": "unsupported", "ram_bytes": "unsupported"}
    )

    assert unreadable == literal


def test_two_identical_unidentified_gpus_are_not_one_gpu() -> None:
    # The documented failure mode: with no UUID, two identical cards are indistinguishable unless
    # the index joins their entries. A set would collapse them and lose half the hardware.
    one_card = (GpuProfile(index=0, name="RTX 5060 Ti", uuid=None),)
    two_cards = (
        GpuProfile(index=0, name="RTX 5060 Ti", uuid=None),
        GpuProfile(index=1, name="RTX 5060 Ti", uuid=None),
    )

    assert compute_machine_fingerprint(
        **{**REFERENCE_IDENTITY, "gpus": one_card}
    ) != compute_machine_fingerprint(**{**REFERENCE_IDENTITY, "gpus": two_cards})


def test_an_unidentified_gpu_set_is_order_independent() -> None:
    first = GpuProfile(index=0, name="RTX 5060 Ti", uuid=None)
    second = GpuProfile(index=1, name="RTX 4090", uuid=None)

    forwards = compute_machine_fingerprint(**{**REFERENCE_IDENTITY, "gpus": (first, second)})
    backwards = compute_machine_fingerprint(**{**REFERENCE_IDENTITY, "gpus": (second, first)})

    assert forwards == backwards


def test_an_unidentified_gpu_changing_slot_does_change_the_fingerprint() -> None:
    # The explicit trade-off documented on compute_machine_fingerprint: without a UUID the index is
    # the only thing separating two identical cards, so it has to count.
    slot_zero = (GpuProfile(index=0, name="RTX 5060 Ti", uuid=None),)
    slot_one = (GpuProfile(index=1, name="RTX 5060 Ti", uuid=None),)

    assert compute_machine_fingerprint(
        **{**REFERENCE_IDENTITY, "gpus": slot_zero}
    ) != compute_machine_fingerprint(**{**REFERENCE_IDENTITY, "gpus": slot_one})


def test_a_gpu_with_a_uuid_is_not_the_same_as_one_without() -> None:
    identified = (GpuProfile(index=0, name="RTX 5060 Ti", uuid="GPU-aaaa"),)
    unidentified = (GpuProfile(index=0, name="RTX 5060 Ti", uuid=None),)

    assert compute_machine_fingerprint(
        **{**REFERENCE_IDENTITY, "gpus": identified}
    ) != compute_machine_fingerprint(**{**REFERENCE_IDENTITY, "gpus": unidentified})


def test_a_non_finite_quantity_is_refused_rather_than_fingerprinted() -> None:
    with pytest.raises(ValidationError, match="non-finite"):
        compute_machine_fingerprint(**{**REFERENCE_IDENTITY, "ram_bytes": float("nan")})


# --- GpuProfile -------------------------------------------------------------------------------


def test_a_gpu_profile_defaults_to_an_unknown_vendor_and_unsupported_vram() -> None:
    gpu = GpuProfile(index=0, name=None, uuid=None)

    assert gpu.vendor is GpuVendor.UNKNOWN
    assert gpu.vram_total_bytes is UNSUPPORTED
    assert gpu.driver_version is None


def test_a_gpu_profile_is_frozen_and_hashable() -> None:
    gpu = GpuProfile(index=0, name="RTX 5060 Ti", uuid="GPU-aaaa")

    assert {gpu, GpuProfile(index=0, name="RTX 5060 Ti", uuid="GPU-aaaa")} == {gpu}
    with pytest.raises(AttributeError):
        gpu.index = 1  # type: ignore[misc]  # the refused assignment is the point of the test


def test_a_negative_gpu_index_is_refused() -> None:
    with pytest.raises(ValidationError, match="0-based device index"):
        GpuProfile(index=-1, name="RTX 5060 Ti", uuid="GPU-aaaa")


def test_negative_vram_is_refused() -> None:
    with pytest.raises(ValidationError, match="must not be negative"):
        GpuProfile(index=0, name="RTX 5060 Ti", uuid="GPU-aaaa", vram_total_bytes=-1)


# --- StorageDevice ----------------------------------------------------------------------------


def test_a_storage_device_defaults_to_an_unknown_rotational_state() -> None:
    # None rather than False: guessing would attribute a slow cold load to the wrong cause.
    device = StorageDevice(name="nvme0n1")

    assert device.rotational is None
    assert device.size_bytes is UNSUPPORTED


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_storage_device_without_a_name_is_refused(blank: str) -> None:
    with pytest.raises(ValidationError, match="non-empty device name"):
        StorageDevice(name=blank)


def test_negative_storage_size_is_refused() -> None:
    with pytest.raises(ValidationError, match="must not be negative"):
        StorageDevice(name="nvme0n1", size_bytes=-1)


# --- MachineProfile ---------------------------------------------------------------------------


def test_a_machine_profile_keeps_the_fingerprint_it_was_written_with() -> None:
    # Not re-derived: a profile read back from a database years later must reconstruct exactly as
    # it was written, including when the inclusion policy has since changed.
    stored = reference_profile(machine_fingerprint="an-older-policys-fingerprint")

    assert stored.machine_fingerprint == "an-older-policys-fingerprint"


def test_a_machine_profile_holds_exactly_the_documented_static_fields() -> None:
    # Machine Identity §1: static identity and live utilization never share a type. A profile that
    # gained "vram_used_bytes" would make every historical row referencing it meaningless the
    # moment that number changed, so the field set is asserted rather than trusted.
    assert set(MachineProfile.__dataclass_fields__) == {
        "machine_fingerprint",
        "hostname",
        "os_name",
        "os_version",
        "kernel",
        "architecture",
        "cpu_model",
        "physical_cores",
        "logical_cores",
        "ram_bytes",
        "gpus",
        "storage",
        "python_version",
        "observed_at",
    }


def test_a_machine_profile_defaults_to_no_hardware_reported() -> None:
    profile = MachineProfile(
        machine_fingerprint=GOLDEN_FINGERPRINT,
        hostname=None,
        os_name=None,
        os_version=None,
        kernel=None,
        architecture=None,
        cpu_model=None,
    )

    assert profile.physical_cores is UNSUPPORTED
    assert profile.gpus == ()
    assert profile.storage == ()
    assert profile.observed_at is None


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_machine_profile_without_a_fingerprint_is_refused(blank: str) -> None:
    with pytest.raises(ValidationError, match="non-empty fingerprint"):
        reference_profile(machine_fingerprint=blank)


@pytest.mark.parametrize("field_name", ["physical_cores", "logical_cores", "ram_bytes"])
def test_a_negative_machine_quantity_is_refused(field_name: str) -> None:
    with pytest.raises(ValidationError, match="must not be negative"):
        reference_profile(**{field_name: -1})


def test_a_non_numeric_quantity_is_refused_rather_than_coerced() -> None:
    with pytest.raises(ValidationError, match="must be a number or UNSUPPORTED"):
        reference_profile(ram_bytes="64GB")


def test_a_boolean_quantity_is_refused() -> None:
    # bool is an int in Python; `ram_bytes=True` would record one byte of memory.
    with pytest.raises(ValidationError, match="must be a number or UNSUPPORTED"):
        reference_profile(ram_bytes=True)


def test_a_non_finite_machine_quantity_is_refused() -> None:
    with pytest.raises(ValidationError, match="must be finite"):
        reference_profile(ram_bytes=float("inf"))


def test_a_naive_observation_time_is_refused() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        reference_profile(observed_at=datetime(2026, 8, 22, 14, 3, 11))  # noqa: DTZ001 — the point


def test_an_aware_non_utc_observation_time_is_accepted() -> None:
    # Aware is the requirement, not UTC: a collector reporting a local offset is unambiguous.
    profile = reference_profile(observed_at=datetime.fromisoformat("2026-08-22T14:03:11+02:00"))

    assert profile.observed_at is not None
