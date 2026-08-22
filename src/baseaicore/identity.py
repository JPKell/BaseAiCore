"""Domain module — canonical model identity: which weights, on which provider kind.

Imports no framework and performs no I/O.

Identity answers "which weights?" and nothing else. It never contains a score, a configuration, an
endpoint or a label — those are the descriptor, the runtime profile and the application's own
data, and conflating them is the documented way a system like this rots
(``docs/architecture/canonical-model-identity.md`` §1).

The canonical-ID format is fixed by
[ADR-0024](../../docs/adr/0024-canonical-id-and-model-references.md). It is a persisted, indexed
lookup key in three databases and a field in every cross-application payload, so its golden test
is the one test in this repository that must never be "updated to match" a change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from baseaicore.errors import ValidationError

__all__ = [
    "IdentityConfidence",
    "ModelIdentity",
    "ProviderKind",
    "normalize_digest",
]

_DIGEST_ALGORITHM_PREFIX = "sha256:"
_DIGEST_HEX_LENGTH = 64
# 12 hex characters is ~48 bits of the digest: short enough to read in a table, a log line or a UI
# badge, and far beyond the collision risk of one machine's model library (ADR-0024 §1).
_DIGEST_SHORT_LENGTH = 12
_DIGEST_UNKNOWN = "unknown"
_HEX_DIGITS = frozenset("0123456789abcdef")


class ProviderKind(StrEnum):
    """The kind of provider serving a model — not the endpoint it is served from.

    Kind rather than address, because the same weights served by Ollama and by vLLM behave
    differently enough (templating, sampling defaults, KV handling) that their measurements are
    not interchangeable, while a port or hostname change is a deployment detail that must not
    fragment a model's history.

    Adding a member is a backwards-compatible change; renaming one is not, because the value is
    persisted and appears in every canonical ID.
    """

    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"
    LLAMACPP = "llamacpp"
    VLLM = "vllm"
    FAKE = "fake"


class IdentityConfidence(StrEnum):
    """How firmly an identity pins down a specific set of weights.

    Stored alongside every measurement. A ``NAME_ONLY`` result carries a permanent caveat: the
    provider exposed no digest, so it can never be proven later to describe the same weights —
    a tag such as ``qwen3.5:latest`` can be repointed at any time. LoadCoach reduces evidence
    confidence for it and FreeWeight shows it in the UI
    ([ADR-0017](../../docs/adr/0017-benchmark-confidence-and-freshness.md)).
    """

    DIGEST = "digest"
    NAME_ONLY = "name_only"


def normalize_digest(value: str | None) -> str | None:
    """Normalize a provider-reported artifact digest, or report that it cannot be normalized.

    Providers report digests inconsistently: bare hex, ``sha256:``-prefixed, upper or lower case,
    sometimes padded with whitespace. ModelRack calls this on every provider response so that
    exactly one shape ever reaches storage (ADR-0024 §2).

    Args:
        value: Whatever the provider reported, or ``None``.

    Returns:
        ``"sha256:"`` followed by 64 lowercase hex characters, or ``None`` if the input was
        ``None``, empty, the wrong length, not hexadecimal, or carried an algorithm prefix other
        than ``sha256:``. Returning ``None`` rather than raising is deliberate: a digest that will
        not normalize must produce a ``name_only`` identity with a recorded reason, not a failed
        model listing and not a malformed identity.
    """
    if value is None:
        return None
    candidate = value.strip().lower()
    if candidate.startswith(_DIGEST_ALGORITHM_PREFIX):
        candidate = candidate[len(_DIGEST_ALGORITHM_PREFIX) :]
    if len(candidate) != _DIGEST_HEX_LENGTH:
        return None
    if not _HEX_DIGITS.issuperset(candidate):
        return None
    return f"{_DIGEST_ALGORITHM_PREFIX}{candidate}"


@dataclass(frozen=True, slots=True)
class ModelIdentity:
    """Immutable name of one set of weights as exposed by one kind of provider.

    Two identities are equal — and hash equal — if and only if all three fields are equal. That
    equality is stable across processes, machines and Python versions, because it is built from
    plain strings and nothing else.

    Explicitly excluded, and each for a reason: the endpoint URL and hostname (deployment detail),
    the file path (machine-local), quantization and parameter count (descriptive metadata that the
    name usually encodes but the descriptor owns), any measurement, and any user-assigned label.

    Attributes:
        provider_kind: Which kind of provider serves these weights.
        provider_model_name: Exactly as the provider names it, case and punctuation preserved, so
            it round-trips back to the provider unchanged. It may legitimately contain ``/``,
            ``:`` and ``@`` (``hf.co/user/repo:q4``), which is why the canonical ID is never
            parsed to recover it and never used as a URL path segment.
        artifact_digest: ``"sha256:"`` + 64 lowercase hex characters when the provider exposes
            one, else ``None``. The only field that survives a retag, and therefore the only thing
            that makes a comparison across two weeks honest. Pass it through
            :func:`normalize_digest` first.
    """

    provider_kind: ProviderKind
    provider_model_name: str
    artifact_digest: str | None = None

    # Cached on first use, per spec §15. Excluded from equality, hashing and repr so it can never
    # affect what this value object *means*; it is derived from the fields, not one of them.
    _canonical_id_cache: str | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate the fields, raising rather than storing an identity that cannot be trusted.

        Raises:
            ValidationError: If ``provider_model_name`` is empty or only whitespace, or if
                ``artifact_digest`` is not already in normalized form.
        """
        if not self.provider_model_name or not self.provider_model_name.strip():
            raise ValidationError(
                "provider_model_name must be a non-empty name as the provider reports it; got "
                f"{self.provider_model_name!r}.",
                details={"field": "provider_model_name", "value": self.provider_model_name},
            )
        if self.artifact_digest is not None and (
            normalize_digest(self.artifact_digest) != self.artifact_digest
        ):
            raise ValidationError(
                f"artifact_digest must be 'sha256:' followed by 64 lowercase hex characters; got "
                f"{self.artifact_digest!r}. Call normalize_digest() on the provider's value first "
                "and record a reason when it returns None — a digest that will not normalize "
                "produces a name_only identity, never a malformed one (ADR-0024 §2).",
                details={"field": "artifact_digest", "value": self.artifact_digest},
            )

    @property
    def identity_confidence(self) -> IdentityConfidence:
        """Whether this identity pins the exact weights or only the name they were served under."""
        return (
            IdentityConfidence.DIGEST
            if self.artifact_digest is not None
            else IdentityConfidence.NAME_ONLY
        )

    @property
    def canonical_id(self) -> str:
        """Return the stable, human-readable identity string.

        The format is ``{provider_kind}/{provider_model_name}@{digest_short}``, where
        ``digest_short`` is ``"sha256:"`` followed by the first 12 hex characters of the digest,
        or the literal ``unknown``::

            ollama/qwen3.5:9b-q8_0@sha256:1f3a9c4e2b70
            ollama/qwen3.5:9b-q8_0@unknown

        The algorithm prefix is retained so the string stays meaningful the day a provider exposes
        a digest that is not SHA-256.

        This is a **display and lookup** key. It is lossy — a model name may itself contain ``/``,
        ``:`` and ``@`` — so it is never parsed back into its parts (they are always available
        separately) and never used as a URL path segment (ADR-0024, sections 3 and 4).

        Returns:
            The canonical ID. Computed once and cached; the cache is invisible to equality,
            hashing and ``repr``.
        """
        cached = self._canonical_id_cache
        if cached is None:
            digest_short = (
                f"{_DIGEST_ALGORITHM_PREFIX}"
                f"{self.artifact_digest[len(_DIGEST_ALGORITHM_PREFIX) :][:_DIGEST_SHORT_LENGTH]}"
                if self.artifact_digest is not None
                else _DIGEST_UNKNOWN
            )
            cached = f"{self.provider_kind.value}/{self.provider_model_name}@{digest_short}"
            # The instance is frozen against callers, not against its own memoization; the value
            # written is a pure function of fields that can never change.
            object.__setattr__(self, "_canonical_id_cache", cached)
        return cached

    def with_digest(self, digest: str) -> ModelIdentity:
        """Return the same identity with its artifact digest set.

        The upgrade path: a model first seen through a listing that reported no digest is later
        confirmed by a call that does. The result differs only in the digest, and its confidence
        becomes :attr:`IdentityConfidence.DIGEST`.

        Args:
            digest: A digest in any shape the provider reports it; it is normalized here.

        Returns:
            A new :class:`ModelIdentity`. The original is unchanged — these are value objects.

        Raises:
            ValidationError: If ``digest`` will not normalize. This raises rather than silently
                dropping the value, because a caller who cannot tell the difference between "the
                digest was applied" and "the digest was discarded" will record the wrong identity
                confidence. Call :func:`normalize_digest` first and record the reason on ``None``.
        """
        normalized = normalize_digest(digest)
        if normalized is None:
            raise ValidationError(
                f"Cannot upgrade identity with the unusable digest {digest!r}; expected 64 hex "
                "characters, optionally prefixed with 'sha256:'. Call normalize_digest() first "
                "and record why the provider's value was discarded (ADR-0024 §2).",
                details={"field": "digest", "value": digest},
            )
        return ModelIdentity(
            provider_kind=self.provider_kind,
            provider_model_name=self.provider_model_name,
            artifact_digest=normalized,
        )

    def __str__(self) -> str:
        """Return the canonical ID, so an identity interpolated into a log line is greppable."""
        return self.canonical_id
