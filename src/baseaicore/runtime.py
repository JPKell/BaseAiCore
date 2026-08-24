"""Domain module — how a model is asked to run, kept separate from which model it is.

Imports no framework and performs no I/O.

The same weights under different runtime settings are a different measurement subject: KV-cache
precision, context size and GPU-layer placement move memory and speed metrics by factors, not by
percentages
(Canonical Model Identity §4). Sampling
parameters (temperature, top_p, seed, stop sequences, …) are **not** part of a runtime profile —
they change per request and are recorded on the sample/job, not on how the model is loaded and
served.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from baseaicore.hashing import sha256_of

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["RuntimeProfile"]

_PROFILE_HASH_LENGTH = 16


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    """How a provider is asked to load and serve a model. Hashes to a stable key.

    Every field is optional: ``RuntimeProfile()`` with everything at its default means "provider
    defaults" and is itself a legal, hashable profile — there is no "no profile" state
    (ADR-0023 §1).

    Immutable and hashable. ``profile_hash`` is computed lazily and cached on the instance.

    Attributes:
        context_size: Requested context window, in tokens.
        kv_cache_precision: KV-cache quantization, e.g. ``"f16"``, ``"q8_0"``, ``"q4_0"``.
        gpu_layers: Number of layers offloaded to GPU.
        flash_attention: Whether flash attention is requested.
        threads: CPU thread count requested.
        batch_size: Requested batch size.
        keep_alive: How long the provider is asked to keep the model loaded, e.g. ``"5m"``.
        provider_options: Anything provider-specific that does not have its own field. Hashed
            deterministically like every other field, nested mappings included, so two profiles
            differing only in one nested option hash differently.
    """

    context_size: int | None = None
    kv_cache_precision: str | None = None
    gpu_layers: int | None = None
    flash_attention: bool | None = None
    threads: int | None = None
    batch_size: int | None = None
    keep_alive: str | None = None
    provider_options: Mapping[str, Any] = field(default_factory=dict)

    _profile_hash_cache: str | None = field(default=None, init=False, repr=False, compare=False)

    @property
    def profile_hash(self) -> str:
        """Return a stable 16-character identifier for this runtime profile.

        SHA-256 over the canonical JSON of every field other than ``None``, truncated to 16 hex
        characters. Fields left at ``None`` are excluded rather than hashed as ``null``, so a
        profile that does not mention ``threads`` hashes identically to one built before the
        field existed — adding a new optional field is additive, not a silent hash break for
        every profile that does not set it.

        Returns:
            16 lowercase hex characters. Computed once and cached; the cache is invisible to
            equality, hashing and ``repr``.
        """
        cached = self._profile_hash_cache
        if cached is None:
            fields: dict[str, Any] = {
                "context_size": self.context_size,
                "kv_cache_precision": self.kv_cache_precision,
                "gpu_layers": self.gpu_layers,
                "flash_attention": self.flash_attention,
                "threads": self.threads,
                "batch_size": self.batch_size,
                "keep_alive": self.keep_alive,
                "provider_options": dict(self.provider_options),
            }
            non_none = {name: value for name, value in fields.items() if value is not None}
            cached = sha256_of(non_none)[:_PROFILE_HASH_LENGTH]
            # The instance is frozen against callers, not against its own memoization; the value
            # written is a pure function of fields that can never change.
            object.__setattr__(self, "_profile_hash_cache", cached)
        return cached
