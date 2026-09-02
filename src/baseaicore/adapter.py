"""Domain module — the adapter axis of an execution subject.

Imports no framework and performs no I/O.

A LoRA adapter is a small weights delta applied to a base model at serving time, so the same
:class:`~baseaicore.identity.ModelIdentity` can produce measurably different behaviour from one
request to the next. The base artifact is byte-identical whether or not an adapter is applied — its
digest does not move — so the digest cannot do the separating, and the subject grows one optional
axis instead (ADR-0058).

Two rules from that record are enforced here rather than left to callers:

* **Identity is the served artifact's digest.** Renaming the file changes nothing; changing its
  content makes a new subject. ``source_digest`` records lineage and never participates in
  identity, because re-converting one training checkpoint can yield a different served artifact.
* **Base compatibility is verified by digest and fails closed.** A PEFT ``adapter_config.json``
  names its base by *name*, which is not a proof; :func:`verify_adapter_base_compatibility` accepts
  a name-only match only by returning visibly reduced identity confidence, and refuses a mismatch
  outright rather than applying an adapter to the wrong weights.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from baseaicore.errors import ValidationError
from baseaicore.identity import IdentityConfidence, ModelIdentity, normalize_digest

__all__ = ["AdapterIdentity", "verify_adapter_base_compatibility"]

_DIGEST_ALGORITHM_PREFIX = "sha256:"
_DIGEST_SHORT_LENGTH = 12
_NAME_MIN_LENGTH = 2
_NAME_MAX_LENGTH = 64
_NAME_FIRST_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz")
_NAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_-")


def _is_valid_name(value: str) -> bool:
    """Return whether ``value`` matches the manifest's adapter-name shape.

    The shape is ``^[a-z][a-z0-9_-]{1,63}$`` — the same one
    ``model.adapter_manifest`` validates, restated here as characters rather than as a regular
    expression so the two cannot drift on an escaping detail.
    """
    if not (_NAME_MIN_LENGTH <= len(value) <= _NAME_MAX_LENGTH):
        return False
    if value[0] not in _NAME_FIRST_CHARS:
        return False
    return _NAME_CHARS.issuperset(value)


@dataclass(frozen=True, slots=True)
class AdapterIdentity:
    """Immutable name of one LoRA adapter, addressed by the content of the artifact served.

    Two adapter identities are equal — and hash equal — if and only if their ``name`` and
    ``artifact_digest`` are equal, stably across processes and Python versions, because they are
    built from plain strings. ``source_digest`` is lineage and is deliberately **not** part of that
    equality (see its field comment); the name is, because it appears in the canonical subject
    string, and two equal values that render differently would be incoherent.

    Evidence measured on ``(base, adapterA)`` applies to ``(base, adapterA)`` and to nothing else:
    not to the bare base, and not to ``(base, adapterB)``. A LoRA routinely degrades capabilities
    it was not trained for, so an inherited score would be a number about different weights
    published under this subject's name (ADR-0059). A differing adapter axis is a **different
    subject**, in the same way a differing ``runtime_profile_hash`` already is.

    Explicitly excluded, each for a reason: a scale (there is nowhere for it to live, so applying
    one adapter at two scales would vary behaviour without varying identity — ADR-0063); the file
    path (a locator, not an identity, which is what makes a rename safe); the base it was trained
    on (declared in the manifest and *verified* by
    :func:`verify_adapter_base_compatibility`, not asserted here); and any measurement.

    Attributes:
        name: The manifest's human label, matching ``^[a-z][a-z0-9_-]{1,63}$``. It is the pin
            name, the display name and the token that appears in a canonical subject string.
        artifact_digest: ``"sha256:"`` + 64 lowercase hex characters, over the **served** GGUF
            artifact. Required, unlike a model identity's digest: the digest *is* this identity,
            so an adapter whose bytes cannot be named cannot be a subject at all.
        source_digest: Optional ``"sha256:"`` + 64 lowercase hex over the training checkpoint, for
            lineage only. Never part of identity, and never used for comparability.
    """

    name: str
    artifact_digest: str
    # Lineage, not identity: excluded from equality, hashing and comparability, because the served
    # artifact is what produced the behaviour and re-converting one checkpoint can yield a
    # different artifact. Two records of one served adapter that disagree about its provenance are
    # still records of the same subject.
    source_digest: str | None = field(default=None, compare=False)

    # Cached on first use, like ModelIdentity's canonical ID. Excluded from equality, hashing and
    # repr so it can never affect what this value object means; it is derived, not a field.
    _suffix_cache: str | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate the fields, refusing an adapter identity that cannot be trusted.

        Raises:
            ValidationError: If ``name`` does not match the manifest's name shape; if
                ``artifact_digest`` is not already in normalized form; or if ``source_digest`` is
                supplied and is not. A digest is not silently dropped or degraded here — unlike a
                model identity, which may legitimately be ``name_only``, an adapter with no usable
                artifact digest has no identity to be.
        """
        if not _is_valid_name(self.name):
            raise ValidationError(
                f"Adapter name must match ^[a-z][a-z0-9_-]{{1,63}}$; got {self.name!r}. This is "
                "the manifest's name shape, and it is what appears in a canonical subject string.",
                details={"field": "name", "value": self.name},
            )
        if normalize_digest(self.artifact_digest) != self.artifact_digest:
            raise ValidationError(
                "artifact_digest must be 'sha256:' followed by 64 lowercase hex characters over "
                f"the served artifact; got {self.artifact_digest!r}. Call normalize_digest() "
                "first. An adapter is content-addressed, so a digest that will not normalize is a "
                "refusal, never a name_only adapter (ADR-0058).",
                details={"field": "artifact_digest", "value": self.artifact_digest},
            )
        if self.source_digest is not None and (
            normalize_digest(self.source_digest) != self.source_digest
        ):
            raise ValidationError(
                "source_digest must be 'sha256:' followed by 64 lowercase hex characters, or "
                f"None; got {self.source_digest!r}. Lineage that cannot be named is recorded as "
                "absent, never as a malformed value.",
                details={"field": "source_digest", "value": self.source_digest},
            )

    @property
    def digest_short(self) -> str:
        """Return ``"sha256:"`` plus the first 12 hex characters of the artifact digest.

        The same truncation rule ADR-0024 §1 fixed for a model identity, reused rather than
        re-derived so one string cannot be shortened two ways.
        """
        hex_part = self.artifact_digest[len(_DIGEST_ALGORITHM_PREFIX) :]
        return f"{_DIGEST_ALGORITHM_PREFIX}{hex_part[:_DIGEST_SHORT_LENGTH]}"

    @property
    def canonical_suffix(self) -> str:
        """Return the suffix this adapter contributes to a canonical subject string.

        The form is ``+{name}@{digest_short}``, appended to a model identity's canonical ID by
        :attr:`~baseaicore.subject.MeasurementSubject.canonical_subject_id`::

            +factcheck@sha256:9e2b41d07c55

        Like the canonical ID itself, this is a **display and lookup** key: lossy, never parsed
        back into its parts, and never a URL path segment (ADR-0024 §3 and §4). Where a canonical
        subject string appears as a URL query-parameter value, the ``+`` is percent-encoded as
        ``%2B``, because a bare ``+`` decodes to a space under form encoding and would silently
        resolve to a different subject, or to none.

        Returns:
            The suffix, including its leading ``+``. Computed once and cached; the cache is
            invisible to equality, hashing and ``repr``.
        """
        cached = self._suffix_cache
        if cached is None:
            cached = f"+{self.name}@{self.digest_short}"
            # Frozen against callers, not against its own memoization; the value written is a pure
            # function of fields that can never change.
            object.__setattr__(self, "_suffix_cache", cached)
        return cached

    def __str__(self) -> str:
        """Return ``name@digest_short``, so an adapter in a log line is greppable."""
        return self.canonical_suffix[1:]


def verify_adapter_base_compatibility(
    served_base: ModelIdentity,
    *,
    declared_base_name: str,
    declared_base_digest: str | None = None,
) -> IdentityConfidence:
    """Check an adapter's declared base against the base actually being served, failing closed.

    Applying an adapter to the wrong base produces plausible, confident, wrong output, which is the
    worst failure available here — so a mismatch is a refusal rather than an attempt, and an
    unverifiable claim is reported as reduced confidence rather than accepted as a match
    (ADR-0058 rule 5).

    The confidence returned is the **existing** :class:`~baseaicore.identity.IdentityConfidence`,
    not a parallel flag: the suite already knows how to display, store and discount a ``name_only``
    identity, and an adapter's uncertainty rides the same rail.

    Args:
        served_base: The identity of the base the provider actually launched — the digest it
            hashed, not the one a manifest hoped for.
        declared_base_name: The provider model name the adapter's manifest declares as its base.
        declared_base_digest: The artifact digest the manifest declares, in normalized form, when
            it declares one. ``None`` means the manifest names its base without proving it, which
            is what a PEFT ``adapter_config.json`` alone can support.

    Returns:
        :attr:`~baseaicore.identity.IdentityConfidence.DIGEST` when the declared digest matches the
        served base's, and :attr:`~baseaicore.identity.IdentityConfidence.NAME_ONLY` when the
        manifest declared no digest and the names match. A ``NAME_ONLY`` result is a permanent
        caveat that must be flagged everywhere the resulting subject surfaces.

    Raises:
        ValidationError: If the declared digest does not match the served base's digest; if the
            manifest declares a digest and the served base exposes none, so the claim cannot be
            checked at all; or if no digest was declared and the base names differ. Each is a
            refusal to apply the adapter, never a downgrade to a weaker check.
    """
    if declared_base_digest is not None:
        if served_base.artifact_digest is None:
            raise ValidationError(
                f"Adapter declares base digest {declared_base_digest!r}, but the served base "
                f"{served_base.canonical_id} exposes no digest, so the claim cannot be verified. "
                "Refusing rather than applying an adapter to weights that cannot be identified.",
                details={
                    "declared_base_digest": declared_base_digest,
                    "served_base": served_base.canonical_id,
                },
            )
        if declared_base_digest != served_base.artifact_digest:
            raise ValidationError(
                f"Adapter declares base digest {declared_base_digest!r}, but the served base is "
                f"{served_base.artifact_digest!r}. An adapter applied to a base it was not "
                "trained on produces plausible, wrong output; base compatibility fails closed.",
                details={
                    "declared_base_digest": declared_base_digest,
                    "served_base_digest": served_base.artifact_digest,
                },
            )
        return IdentityConfidence.DIGEST

    if declared_base_name != served_base.provider_model_name:
        raise ValidationError(
            f"Adapter declares base name {declared_base_name!r}, but the served base is "
            f"{served_base.provider_model_name!r}. With no declared digest the name is the only "
            "check there is, so a mismatch is a refusal.",
            details={
                "declared_base_name": declared_base_name,
                "served_base_name": served_base.provider_model_name,
            },
        )
    return IdentityConfidence.NAME_ONLY
