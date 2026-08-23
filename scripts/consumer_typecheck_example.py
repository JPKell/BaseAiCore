"""A minimal downstream consumer, used only by CI's ``install-check`` job.

Not part of the package, not covered by pytest, and not on the default ``mypy src tests`` path.
Its only job is to prove — against the *built wheel*, with nothing editable on the path — that
``py.typed`` actually makes ``mypy --strict`` see ``baseaicore``'s types from a project that only
depends on the published distribution (development plan Phase 4, "mypy sees the types from a
consumer project").
"""

from __future__ import annotations

from baseaicore import UNSUPPORTED, CapabilityId, ModelIdentity, ProviderKind, is_supported


def check() -> tuple[str, bool, bool]:
    """Exercise enough of the public surface that a missing stub would fail ``mypy --strict``."""
    identity = ModelIdentity(ProviderKind.OLLAMA, "qwen3.5:9b-q8_0")
    capability = CapabilityId("coding.python")
    return identity.canonical_id, capability.is_specialization, is_supported(UNSUPPORTED)
