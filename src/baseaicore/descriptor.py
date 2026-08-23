"""Domain module — descriptive metadata about a model, as a provider reports it.

Imports no framework and performs no I/O.

Kept separate from ``ModelIdentity``: identity answers "which weights?" and never changes shape
across a refresh, while a descriptor answers "what does the provider currently say about these
weights?" and is expected to be re-read
([Canonical Model Identity §3](../../docs/architecture/canonical-model-identity.md)). A benchmark
result keeps the descriptor snapshot it was produced with; a later refresh never rewrites history
(same document, §7 rule 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from baseaicore.errors import ValidationError
from baseaicore.measurement import UNSUPPORTED

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from baseaicore.identity import ModelIdentity
    from baseaicore.measurement import Measurement

__all__ = ["ModelCapabilityFlag", "ModelDescriptor"]


class ModelCapabilityFlag(StrEnum):
    """A capability a provider *claims* a model has, distinct from a measured capability.

    FreeWeight's benchmark results record what a model can *demonstrably* do; this flag records
    only what the provider *says* it can do. The two are never conflated
    (``docs/architecture/canonical-model-identity.md`` §3).
    """

    TOOLS = "tools"
    VISION = "vision"
    THINKING = "thinking"
    STRUCTURED_OUTPUT = "structured_output"
    EMBEDDING = "embedding"


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    """Descriptive facts about a model, as reported by a provider at a point in time.

    Refreshable, unlike :class:`~baseaicore.identity.ModelIdentity`: a provider's own account of a
    model's architecture can be re-read at any time, and each reading is its own descriptor rather
    than a mutation of the last one.

    The architecture fields (``layers``, ``kv_heads``, ``head_dim``, …) are load-bearing:
    FreeWeight's KV-cache benchmark computes a theoretical bytes-per-token from them and compares
    it against the observed VRAM slope. A field the provider did not report makes that benchmark
    return :data:`~baseaicore.measurement.UNSUPPORTED`, never a wrong number built from a guess.

    Attributes:
        identity: The weights this descriptor describes.
        observed_at: When this snapshot was read from the provider. Timezone-aware, UTC.
        family: The model family name, e.g. ``"qwen3.5"``.
        architecture: The architecture name, e.g. ``"transformer"``, ``"mamba"``.
        parameter_count: Total parameter count.
        active_parameter_count: MoE active parameters per token; equal to ``parameter_count`` for
            a dense model.
        expert_count: Number of experts, for a mixture-of-experts model.
        quantization: Weight quantization, e.g. ``"Q8_0"``.
        weight_format: File format, e.g. ``"gguf"``, ``"safetensors"``.
        size_bytes: On-disk size of the weights.
        max_context: The context length the model *advertises*. Not the context a provider is
            actually configured to serve — that is a runtime concern, ``served_context``
            ([ADR-0023](../../docs/adr/0023-runtime-profile-resolution.md) §4).
        embedding_dim: Hidden/embedding dimension.
        layers: Transformer layer count.
        attention_heads: Attention head count.
        kv_heads: Key/value head count (equal to ``attention_heads`` without grouped-query
            attention).
        head_dim: Dimension of each attention head.
        vocab_size: Tokenizer vocabulary size.
        rope_config: RoPE scaling configuration, in the provider's own shape.
        sliding_window: Sliding-attention window size, if the architecture uses one.
        declared_capabilities: What the provider claims this model can do.
        license_text: The model's license, if the provider exposes one.
        raw: The untouched provider response. Preserved for diagnostics and for extracting fields
            the normalizer does not yet know about. Nothing above ModelRack may read this for
            business logic (``docs/architecture/canonical-model-identity.md`` §3).
    """

    identity: ModelIdentity
    observed_at: datetime
    family: str | None = None
    architecture: str | None = None
    parameter_count: Measurement = UNSUPPORTED
    active_parameter_count: Measurement = UNSUPPORTED
    expert_count: Measurement = UNSUPPORTED
    quantization: str | None = None
    weight_format: str | None = None
    size_bytes: Measurement = UNSUPPORTED
    max_context: Measurement = UNSUPPORTED
    embedding_dim: Measurement = UNSUPPORTED
    layers: Measurement = UNSUPPORTED
    attention_heads: Measurement = UNSUPPORTED
    kv_heads: Measurement = UNSUPPORTED
    head_dim: Measurement = UNSUPPORTED
    vocab_size: Measurement = UNSUPPORTED
    rope_config: Mapping[str, Any] | None = None
    sliding_window: Measurement = UNSUPPORTED
    declared_capabilities: frozenset[ModelCapabilityFlag] = frozenset()
    license_text: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate ``observed_at``.

        Raises:
            ValidationError: If ``observed_at`` is naive. Which snapshot is newest, and what a
                stored result's descriptor meant "at the time", depends on the instant — an
                ambiguous instant has no defensible answer, the same rule this package applies to
                every other timestamp.
        """
        tzinfo = self.observed_at.tzinfo
        if tzinfo is None or tzinfo.utcoffset(self.observed_at) is None:
            raise ValidationError(
                "ModelDescriptor.observed_at must be timezone-aware; a naive timestamp makes it "
                "ambiguous when this snapshot was read.",
                details={"field": "observed_at"},
            )
