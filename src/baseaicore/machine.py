"""Domain module — the static identity of the machine a measurement was produced on.

Imports no framework and performs no I/O. The values here are *defined* in this module and
*collected* by SweatMeter (spec §3): nothing below reads ``/proc``, runs ``nvidia-smi``, or knows
that either exists.

Static identity and live utilization are deliberately separate types with separate lifetimes. A
machine profile that carried "VRAM currently used" would make every historical row that references
it meaningless the moment that number changed, which is why utilization lives in SweatMeter's
``TelemetrySample`` and never here
(Machine Identity §1).

The fingerprint's policy — what identifies a machine, and what merely happens to be true of it
today (Machine Identity §3):

**Included**, because changing it changes what a measurement means: ``hostname``, ``os_name``,
``architecture``, ``cpu_model``, ``physical_cores``, ``logical_cores``, ``ram_bytes``, and the GPU
set as ``(name, uuid)`` per device.

**Excluded**, each for a reason:

* *GPU driver version, CUDA/ROCm version* — a driver upgrade must not orphan a machine's entire
  measurement history. Version *changes* are drift signals recorded on the run, never identity
  components (Machine Identity §5).
* *Attached storage* — plugging in a disk is not a new machine.
* *OS version and kernel* — upgrades, not hardware; drift signals like the driver version.
* *Python version* — application environment, not machine identity; recorded on the run.
* *Per-GPU VRAM, vendor, compute capability* — determined by the GPU model, which the name already
  pins. Including them would add no identity and one more field a collector could fail to report.
* *Live utilization* — not identity.
* *Container/VM identifiers* — not stable, and not meaningful on the primary deployment shape.

The policy is inherited verbatim from the prior implementation, where it was the correct call
(inventory §2.2); the tests in
``tests/unit/test_machine.py`` assert each exclusion, so it stays a property of the code rather
than a claim in prose.

**Known limitation, deliberately not solved here.** ``hostname`` is an identity input, so a machine
whose hostname churns (DHCP, a recreated container) fragments its own history. The escape hatch —
an operator-supplied fingerprint override — is *specified* as a future extension rather than
shipped, because it would have to be honoured by every consumer that stores a fingerprint and no
consumer specifies one today (spec §21). Shipping it now would create a setting nothing reads.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from baseaicore.errors import ValidationError
from baseaicore.hashing import canonical_json, sha256_of
from baseaicore.measurement import UNSUPPORTED

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from baseaicore.measurement import Measurement, Unsupported

__all__ = [
    "GpuProfile",
    "GpuVendor",
    "MachineProfile",
    "StorageDevice",
    "compute_machine_fingerprint",
]


class GpuVendor(StrEnum):
    """Who makes the device, which decides which telemetry interface can read it.

    ``UNKNOWN`` is the honest default rather than a guess: a device the collector could not
    attribute is not an NVIDIA device by assumption. It is not part of the machine fingerprint —
    the GPU's name already pins the model, and a collector that improved its vendor detection must
    not thereby re-identify the machine.
    """

    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    APPLE = "apple"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class GpuProfile:
    """Static identity of one GPU, as a collector reported it.

    Immutable. Only ``name``, ``uuid`` and — when the UUID is missing — ``index`` contribute to the
    machine fingerprint; see :func:`compute_machine_fingerprint` and this module's policy table for
    why the driver and toolkit versions do not.

    Attributes:
        index: The device's enumeration position, ``0``-based. Also the value FreeWeight and
            LoadCoach attribute a per-device measurement to
            (ADR-0027).
        uuid: The device's stable hardware identifier, unchanged across reboots and across
            re-enumeration. This is the GPU's real identity; ``index`` is only where it happened to
            be enumerated this boot. ``None`` when the collector could not read one.
        name: The marketing name, e.g. ``"NVIDIA GeForce RTX 5060 Ti"``.
        vram_total_bytes: Total device memory. Total, never used — used memory is telemetry.
        driver_version: The installed driver version. A drift signal, not identity.
        cuda_version: The CUDA/ROCm toolkit version. A drift signal, not identity.
        compute_capability: The device's compute capability, e.g. ``"12.0"``.
        vendor: Who makes the device.
    """

    index: int
    name: str | None
    uuid: str | None
    vram_total_bytes: Measurement = UNSUPPORTED
    driver_version: str | None = None
    cuda_version: str | None = None
    compute_capability: str | None = None
    vendor: GpuVendor = GpuVendor.UNKNOWN

    def __post_init__(self) -> None:
        """Validate the index and the VRAM total.

        Raises:
            ValidationError: If ``index`` is negative, or ``vram_total_bytes`` is not a
                non-negative finite number or :data:`~baseaicore.measurement.UNSUPPORTED`.
        """
        if self.index < 0:
            raise ValidationError(
                f"GpuProfile.index must be a 0-based device index; got {self.index}.",
                details={"field": "index", "value": self.index},
            )
        _validate_quantity(self.vram_total_bytes, owner="GpuProfile", field_name="vram_total_bytes")


@dataclass(frozen=True, slots=True)
class StorageDevice:
    """A storage device attached to the machine.

    Recorded as provenance — a benchmark that loaded weights from a spinning disk explains its own
    cold-start timings — and deliberately excluded from the machine fingerprint, because plugging
    in a disk does not make a machine a different machine.

    Attributes:
        name: The device name as the OS exposes it, e.g. ``"nvme0n1"``.
        size_bytes: Total capacity.
        model: The device's model string, if the OS exposes one.
        rotational: ``True`` for a spinning disk, ``False`` for solid state, ``None`` when the
            collector could not tell. ``None`` rather than a default of ``False``: guessing here
            would attribute a cold-load time to the wrong cause.
    """

    name: str
    size_bytes: Measurement = UNSUPPORTED
    model: str | None = None
    rotational: bool | None = None

    def __post_init__(self) -> None:
        """Validate the device name and its size.

        Raises:
            ValidationError: If ``name`` is empty or only whitespace, or ``size_bytes`` is not a
                non-negative finite number or :data:`~baseaicore.measurement.UNSUPPORTED`.
        """
        if not self.name or not self.name.strip():
            raise ValidationError(
                f"StorageDevice.name must be the non-empty device name the OS exposes; got "
                f"{self.name!r}.",
                details={"field": "name", "value": self.name},
            )
        _validate_quantity(self.size_bytes, owner="StorageDevice", field_name="size_bytes")


@dataclass(frozen=True, slots=True)
class MachineProfile:
    """The static identity of one machine, persisted once per fingerprint.

    Immutable. Every field other than ``machine_fingerprint`` is optional in the sense that a
    collector may be unable to read it: strings that were not reported are ``None`` and quantities
    that were not reported are :data:`~baseaicore.measurement.UNSUPPORTED`, and both hash as
    ``"unsupported"`` so a machine that cannot describe itself fully still has one stable identity.

    ``machine_fingerprint`` is the *recorded* fingerprint, not a derived property. It is neither
    computed nor re-verified in ``__post_init__``, and that is deliberate: a profile read back from
    a database years later must reconstruct exactly as it was written, including the case where the
    inclusion policy has since changed. SweatMeter computes it once, with
    :func:`compute_machine_fingerprint`, at the moment it collects the fields.

    Attributes:
        machine_fingerprint: The identity this profile was stored under.
        hostname: The machine's hostname. Part of the fingerprint — see the module docstring's note
            on hostname churn.
        os_name: e.g. ``"Linux"``.
        os_version: e.g. ``"Ubuntu 26.04 LTS"``. A drift signal, not identity.
        kernel: The kernel release string. A drift signal, not identity.
        architecture: e.g. ``"x86_64"``.
        cpu_model: The CPU's model string.
        physical_cores: Physical core count.
        logical_cores: Logical core count, hyperthreads included.
        ram_bytes: Total system memory.
        gpus: Every visible GPU. A tuple, and never summed across
            (ADR-0027).
        storage: Attached storage devices. Provenance only; excluded from the fingerprint.
        python_version: The interpreter that produced the measurement. Application environment
            rather than machine identity, so it is recorded here and excluded from the fingerprint.
        observed_at: When this snapshot was taken. Timezone-aware, UTC.
    """

    machine_fingerprint: str
    hostname: str | None
    os_name: str | None
    os_version: str | None
    kernel: str | None
    architecture: str | None
    cpu_model: str | None
    physical_cores: Measurement = UNSUPPORTED
    logical_cores: Measurement = UNSUPPORTED
    ram_bytes: Measurement = UNSUPPORTED
    gpus: tuple[GpuProfile, ...] = ()
    storage: tuple[StorageDevice, ...] = ()
    python_version: str | None = None
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate the fingerprint, the quantities and the observation time.

        Raises:
            ValidationError: If ``machine_fingerprint`` is blank, if any quantity is not a
                non-negative finite number or :data:`~baseaicore.measurement.UNSUPPORTED`, or if
                ``observed_at`` is naive. A naive timestamp makes "which snapshot is newest?"
                unanswerable, the same rule every other timestamp in this package follows.
        """
        if not self.machine_fingerprint or not self.machine_fingerprint.strip():
            raise ValidationError(
                "MachineProfile.machine_fingerprint must be a non-empty fingerprint; got "
                f"{self.machine_fingerprint!r}. Compute it with compute_machine_fingerprint().",
                details={"field": "machine_fingerprint", "value": self.machine_fingerprint},
            )
        for field_name in ("physical_cores", "logical_cores", "ram_bytes"):
            _validate_quantity(
                getattr(self, field_name), owner="MachineProfile", field_name=field_name
            )
        if self.observed_at is not None:
            tzinfo = self.observed_at.tzinfo
            if tzinfo is None or tzinfo.utcoffset(self.observed_at) is None:
                raise ValidationError(
                    "MachineProfile.observed_at must be timezone-aware; a naive timestamp makes "
                    "it ambiguous when this machine was observed.",
                    details={"field": "observed_at"},
                )


# The signature is fixed by spec §7, and each argument is an independent identity input that a
# collector may or may not have been able to read; bundling them into an object would just be
# MachineProfile, which cannot be built until its fingerprint exists.
def compute_machine_fingerprint(  # noqa: PLR0913 — see comment above
    *,
    hostname: str | None,
    os_name: str | None,
    architecture: str | None,
    cpu_model: str | None,
    physical_cores: Measurement,
    logical_cores: Measurement,
    ram_bytes: Measurement,
    gpus: Sequence[GpuProfile],
) -> str:
    """Compute the stable identity of a machine from the hardware that changes measurements.

    The digest is taken over the canonical JSON of a document with one key per identity input, so
    it is byte-stable across processes, machines and Python versions
    (:func:`~baseaicore.hashing.sha256_of`). Only the arguments below participate: everything the
    module docstring lists as excluded is absent from the signature entirely, which is the strongest
    form the exclusion policy can take — a driver upgrade cannot change this result because the
    driver version is not reachable from here.

    Two normalizations exist purely to stop one machine from having two identities:

    * **Unreported is one value.** A string argument that is ``None``, empty or only whitespace
      hashes as the literal ``"unsupported"``, exactly as
      :data:`~baseaicore.measurement.UNSUPPORTED` does for the numeric arguments (Machine Identity
      §3). One collector reporting a missing CPU model as ``None`` and another reporting it as
      ``""`` must not produce two fingerprints for one machine. The accepted consequence is that a
      machine whose CPU model genuinely reads ``"unsupported"`` is indistinguishable from one that
      could not report it.
    * **Surrounding whitespace is stripped**, because ``/proc/cpuinfo`` and ``nvidia-smi`` fields
      routinely carry it and the machine must not get a second identity depending on which reader
      ran. This is the opposite of the rule for a *model* name, which round-trips back to a
      provider byte-exactly and is therefore never touched
      (:func:`~baseaicore.hashing.canonical_json`); a hostname in a fingerprint is never sent
      anywhere, so only its identity matters.

    GPUs contribute their ``(name, uuid)`` pair, and the entries are sorted before hashing, so the
    order a collector happened to enumerate the devices in does not change the machine. When a GPU
    reports no UUID, its ``index`` joins its entry: without that, two identical cards in one machine
    would produce two identical entries, and the machine would be indistinguishable from a machine
    with a differently-sized identical set. The trade-off is explicit — for a GPU with no UUID, and
    only for such a GPU, re-enumeration changes the fingerprint.

    Args:
        hostname: The machine's hostname, or ``None`` if unreported.
        os_name: The OS name, e.g. ``"Linux"``. Not the OS *version*, which is drift, not identity.
        architecture: The CPU architecture, e.g. ``"x86_64"``.
        cpu_model: The CPU's model string.
        physical_cores: Physical core count, or :data:`~baseaicore.measurement.UNSUPPORTED`.
        logical_cores: Logical core count, or :data:`~baseaicore.measurement.UNSUPPORTED`.
        ram_bytes: Total system memory, or :data:`~baseaicore.measurement.UNSUPPORTED`.
        gpus: Every visible GPU, in any order.

    Returns:
        64 lowercase hex characters. Equal inputs always give equal fingerprints; a whole-valued
        ``float`` and the equal ``int`` count as equal inputs, so a collector that computed
        ``ram_bytes`` in floating point does not re-identify the machine.

    Raises:
        ValidationError: If a quantity is a non-finite float, via
            :func:`~baseaicore.hashing.canonical_json` — a ``nan`` reaching a fingerprint is a
            measurement that was never taken.
    """
    return sha256_of(
        {
            "hostname": _identity_text(hostname),
            "os_name": _identity_text(os_name),
            "architecture": _identity_text(architecture),
            "cpu_model": _identity_text(cpu_model),
            "physical_cores": _identity_number(physical_cores),
            "logical_cores": _identity_number(logical_cores),
            "ram_bytes": _identity_number(ram_bytes),
            "gpus": _gpu_identity_entries(gpus),
        }
    )


def _identity_text(value: str | None) -> str | Unsupported:
    """Return a stripped identity string, or the sentinel when nothing was reported."""
    if value is None:
        return UNSUPPORTED
    stripped = value.strip()
    return stripped if stripped else UNSUPPORTED


def _identity_number(value: Measurement) -> Measurement:
    """Return a quantity with a whole-valued float collapsed to the equal ``int``.

    ``8_589_934_592`` and ``8_589_934_592.0`` are the same amount of memory but not the same JSON,
    and which one a collector produces is an implementation detail of how it did its arithmetic.
    Same spirit as :func:`~baseaicore.hashing.canonical_json` normalizing ``-0.0`` to ``0.0``.
    """
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _gpu_identity_entries(gpus: Sequence[GpuProfile]) -> list[dict[str, Any]]:
    """Return the GPU set's identity entries, sorted so enumeration order cannot matter."""
    entries: list[dict[str, Any]] = []
    for gpu in gpus:
        uuid = _identity_text(gpu.uuid)
        entries.append(
            {
                "name": _identity_text(gpu.name),
                "uuid": uuid,
                # Only a tie-breaker, and only when there is no UUID to identify the device by.
                # `None` here is Python's ordinary "not applicable", not an unreadable measurement.
                "index": gpu.index if uuid is UNSUPPORTED else None,
            }
        )
    # Sorted by their own canonical JSON: a total order over the entries that needs no assumption
    # about which fields are present, and that cannot raise the way comparing str against None
    # would.
    return sorted(entries, key=canonical_json)


def _validate_quantity(value: Measurement, *, owner: str, field_name: str) -> None:
    """Raise unless a quantity is a non-negative finite number or ``UNSUPPORTED``."""
    if value is UNSUPPORTED:
        return
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValidationError(
            f"{owner}.{field_name} must be a number or UNSUPPORTED; got {value!r}. Use "
            "UNSUPPORTED when the collector could not read it — never 0, which is a real reading "
            "of an empty machine (ADR-0016).",
            details={"field": field_name, "value": repr(value)},
        )
    if not math.isfinite(value):
        raise ValidationError(
            f"{owner}.{field_name} must be finite; got {value!r}. A nan or infinity in a machine "
            "profile is a failed calculation, not a hardware property.",
            details={"field": field_name, "value": repr(value)},
        )
    if value < 0:
        raise ValidationError(
            f"{owner}.{field_name} must not be negative; got {value!r}.",
            details={"field": field_name, "value": value},
        )
