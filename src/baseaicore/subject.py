"""Domain module — whether two measurements may honestly be compared.

Imports no framework and performs no I/O.

A :class:`MeasurementSubject` is the triple every result is measured against: which weights, under
what runtime settings, on which machine. Comparability follows from that triple alone for most of
the matrix in
Canonical Model Identity §5; the two rows
that additionally turn on the benchmark version and the dataset hash take those as explicit
arguments to :meth:`MeasurementSubject.is_comparable_with`, because neither is part of a
measurement subject. Omitting them yields :attr:`Comparability.INDETERMINATE`, never
:attr:`Comparability.COMPARABLE` — a helper that answered "yes" because it was not told what it
needed would be worse than no helper.

The matrix is a set of judgement calls, not a derivation, so every branch below cites the table row
it implements: changing a rule means editing this module and the architecture document together,
never one without the other (development plan Phase 2, "Gold standards").
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from baseaicore.errors import ValidationError
from baseaicore.identity import IdentityConfidence

if TYPE_CHECKING:
    from collections.abc import Mapping

    from baseaicore.identity import ModelIdentity

__all__ = [
    "Comparability",
    "ComparabilityVerdict",
    "MeasurementSubject",
    "MetricKind",
]


class MetricKind(StrEnum):
    """The class of metric being compared, because comparability differs by class.

    A quality metric survives a machine change — the same weights answer the same question the
    same way. Performance, memory and energy metrics do not: they measure the hardware as much as
    the model (`Canonical Model Identity §5`, row 3).
    """

    QUALITY = "quality"
    PERFORMANCE = "performance"
    MEMORY = "memory"
    ENERGY = "energy"


class Comparability(StrEnum):
    """The four possible outcomes of a comparability check.

    ``COMPARABLE`` alone means safe to merge or average directly. ``SEPARATE`` and ``WARN`` are
    both "yes, but": ``SEPARATE`` means the two measurements may be shown side by side as an
    explicit, never-merged comparison (a runtime-profile or quantization study, or two results
    from different benchmark versions); ``WARN`` means direct comparison is allowed but the result
    carries a caveat the UI must show (a cross-machine quality comparison, or a ``name_only``
    identity across a gap in time). ``INDETERMINATE`` means this check was not given enough
    information to answer at all — never treated as ``COMPARABLE`` by default.
    """

    COMPARABLE = "comparable"
    SEPARATE = "separate"
    WARN = "warn"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class ComparabilityVerdict:
    """The result of a comparability check: a categorical outcome plus why.

    The reason is not decoration — it is what a UI shows next to the outcome, and what a
    regression-detection job logs when it refuses to compare two results.

    Attributes:
        comparability: The categorical outcome.
        reason: One human-readable sentence naming the matrix row that produced this outcome.
    """

    comparability: Comparability
    reason: str


@dataclass(frozen=True, slots=True)
class MeasurementSubject:
    """What one measurement was actually measured against: weights, runtime, machine.

    A measurement is never stored without its full subject (`Canonical Model Identity` §5, Rule
    3). The subject deliberately excludes the benchmark version and the dataset hash — those
    describe the *test*, not the *thing being tested* — which is why
    :meth:`is_comparable_with` takes them as separate arguments rather than storing them here.

    Attributes:
        identity: Which weights were measured.
        runtime_profile_hash: :attr:`~baseaicore.runtime.RuntimeProfile.profile_hash` of the
            profile the model was served under.
        machine_fingerprint: :func:`~baseaicore.machine.compute_machine_fingerprint` of the
            machine the measurement ran on.
    """

    identity: ModelIdentity
    runtime_profile_hash: str
    machine_fingerprint: str

    def __post_init__(self) -> None:
        """Validate that the hash fields are not blank.

        Raises:
            ValidationError: If ``runtime_profile_hash`` or ``machine_fingerprint`` is empty or
                only whitespace — a blank hash is always a construction bug, never a real subject.
        """
        for field_name in ("runtime_profile_hash", "machine_fingerprint"):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValidationError(
                    f"MeasurementSubject.{field_name} must be a non-empty hash; got {value!r}.",
                    details={"field": field_name, "value": value},
                )

    # Signature fixed by spec.md §7; splitting the two benchmark/dataset pairs into an object
    # would hide that they are deliberately optional and independently omittable.
    def is_comparable_with(  # noqa: PLR0913 — see comment above
        self,
        other: MeasurementSubject,
        *,
        metric_kind: MetricKind,
        benchmark_version: str | None = None,
        other_benchmark_version: str | None = None,
        dataset_hashes: Mapping[str, str] | None = None,
        other_dataset_hashes: Mapping[str, str] | None = None,
    ) -> ComparabilityVerdict:
        """Decide whether a measurement on this subject may be compared with one on ``other``.

        Implements the matrix in
        Canonical Model Identity §5,
        evaluated in this order — each condition is checked only once the ones before it have
        been ruled out, mirroring the table's own row order:

        1. Different identity: :attr:`Comparability.INDETERMINATE`. A subject alone cannot tell
           a quantization variant of the same family from an unrelated model — that needs the
           descriptor's ``family``, which is not part of a measurement subject.
        2. Same identity, different ``runtime_profile_hash``: :attr:`Comparability.SEPARATE` —
           the runtime-comparison case (a KV-precision or context-size study), shown side by side
           and never merged, regardless of ``metric_kind``.
        3. Same identity and profile, different ``machine_fingerprint``: depends on
           ``metric_kind``. Quality survives a machine change
           (:attr:`Comparability.WARN`, badge the machine); performance, memory and energy do not
           (:attr:`Comparability.SEPARATE`).
        4. Same subject: falls through to benchmark version and dataset hash, both required.
           Missing either yields :attr:`Comparability.INDETERMINATE`; a mismatch on either yields
           :attr:`Comparability.SEPARATE`, never averaged.
        5. Same subject, same benchmark version, same dataset hash:
           :attr:`Comparability.COMPARABLE` — unless this identity is
           :attr:`~baseaicore.identity.IdentityConfidence.NAME_ONLY`, in which case the weights
           behind the name cannot be proven unchanged between the two measurements and the
           verdict is :attr:`Comparability.WARN` instead.

        Args:
            other: The subject to compare against.
            metric_kind: What kind of metric is being compared. Only changes the outcome of the
                cross-machine row, but is required for every call because a caller must always
                know which kind of number it is asking about.
            benchmark_version: This measurement's benchmark version, if comparing benchmark
                results. Required, together with ``other_benchmark_version``, to reach anything
                more specific than :attr:`Comparability.INDETERMINATE` when the subjects match.
            other_benchmark_version: ``other``'s benchmark version.
            dataset_hashes: This measurement's dataset hashes, keyed by dataset name. Required,
                together with ``other_dataset_hashes``, for the same reason.
            other_dataset_hashes: ``other``'s dataset hashes.

        Returns:
            The outcome and a human-readable reason. Never :attr:`Comparability.COMPARABLE` when
            information required to reach it was not supplied.
        """
        if self.identity != other.identity:
            return ComparabilityVerdict(
                Comparability.INDETERMINATE,
                "Different identity: a measurement subject alone does not carry model family, so "
                "whether this is a quantization comparison or two unrelated models is unknown.",
            )

        if self.runtime_profile_hash != other.runtime_profile_hash:
            return ComparabilityVerdict(
                Comparability.SEPARATE,
                "Same identity but different runtime profile "
                f"({self.runtime_profile_hash} vs {other.runtime_profile_hash}): comparable only "
                "as an explicit runtime comparison, never merged.",
            )

        if self.machine_fingerprint != other.machine_fingerprint:
            return _cross_machine_verdict(self, other, metric_kind)

        return _same_subject_verdict(
            self,
            benchmark_version=benchmark_version,
            other_benchmark_version=other_benchmark_version,
            dataset_hashes=dataset_hashes,
            other_dataset_hashes=other_dataset_hashes,
        )


def _cross_machine_verdict(
    subject: MeasurementSubject, other: MeasurementSubject, metric_kind: MetricKind
) -> ComparabilityVerdict:
    """Implement row 3: same identity and runtime profile, different machine."""
    machines = f"{subject.machine_fingerprint} vs {other.machine_fingerprint}"
    if metric_kind is MetricKind.QUALITY:
        return ComparabilityVerdict(
            Comparability.WARN,
            f"Same identity and runtime profile but different machine ({machines}): quality "
            "metrics are comparable across machines — badge the machine in the presentation.",
        )
    return ComparabilityVerdict(
        Comparability.SEPARATE,
        f"Same identity and runtime profile but different machine ({machines}): "
        f"{metric_kind.value} metrics measure the hardware as much as the model and are not "
        "comparable across machines.",
    )


def _same_subject_verdict(
    subject: MeasurementSubject,
    *,
    benchmark_version: str | None,
    other_benchmark_version: str | None,
    dataset_hashes: Mapping[str, str] | None,
    other_dataset_hashes: Mapping[str, str] | None,
) -> ComparabilityVerdict:
    """Implement rows 1, 2 and 6: same identity, runtime profile and machine."""
    if benchmark_version is None or other_benchmark_version is None:
        return ComparabilityVerdict(
            Comparability.INDETERMINATE,
            "Same subject, but at least one benchmark_version was not supplied.",
        )
    if benchmark_version != other_benchmark_version:
        return ComparabilityVerdict(
            Comparability.SEPARATE,
            f"Same subject but different benchmark version ({benchmark_version!r} vs "
            f"{other_benchmark_version!r}): never averaged.",
        )
    if dataset_hashes is None or other_dataset_hashes is None:
        return ComparabilityVerdict(
            Comparability.INDETERMINATE,
            "Same subject and benchmark version, but at least one dataset_hashes was not supplied.",
        )
    if dict(dataset_hashes) != dict(other_dataset_hashes):
        return ComparabilityVerdict(
            Comparability.SEPARATE,
            "Same subject and benchmark version but different dataset hashes: never averaged.",
        )
    if subject.identity.identity_confidence is IdentityConfidence.NAME_ONLY:
        return ComparabilityVerdict(
            Comparability.WARN,
            "Same subject, benchmark version and dataset hash, but this identity is name_only: "
            "the weights behind the name cannot be proven unchanged between the two "
            "measurements.",
        )
    return ComparabilityVerdict(
        Comparability.COMPARABLE,
        "Same subject, same benchmark version, same dataset hash: directly comparable.",
    )
