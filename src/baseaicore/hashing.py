"""Domain module — canonical JSON and the hash every fingerprint in the suite is built from.

Imports no framework and performs no I/O.

"Canonical" here means: two structures that are equal produce byte-identical output, on every
platform, in every process, in every supported Python version. That property is what makes a
machine fingerprint, a runtime profile hash and a pricing hash comparable across machines and
across time (gold standard G8), so this module refuses anything it cannot serialize
deterministically rather than falling back on ``repr``.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, NoReturn

from baseaicore.errors import ValidationError
from baseaicore.measurement import UNSUPPORTED
from baseaicore.timeutil import to_rfc3339

__all__ = ["canonical_json", "sha256_of"]

_UNSUPPORTED_JSON = "unsupported"


def canonical_json(value: Any) -> str:  # noqa: ANN401 — accepts any JSON-shaped structure by design
    """Serialize a structure to canonical JSON: sorted keys, no whitespace, stable numbers.

    The guarantee is byte-identity, not readability. Keys are sorted, separators are minimal,
    non-ASCII characters are emitted as themselves (the result is UTF-8 text, and
    :func:`sha256_of` encodes it as UTF-8), and every value type that could serialize two ways is
    either normalized to one form or refused.

    Accepted values and their canonical forms:

    * ``dict``/``Mapping`` — keys must be strings, and are sorted by code point.
    * ``list``/``tuple`` and other non-string sequences — order is preserved, because order is
      meaning. A caller that wants order-independence sorts before calling.
    * ``str``, ``int``, ``bool``, ``None`` — as JSON.
    * ``float`` — Python's shortest round-tripping repr, which is platform-stable. ``-0.0`` is
      normalized to ``0.0``; ``nan`` and ``±inf`` are refused, since they are not JSON and a
      ``nan`` reaching a hash is a fabricated measurement in disguise.
    * :data:`~baseaicore.measurement.UNSUPPORTED` — the string ``"unsupported"``, fixed by
      ADR-0016 §4. Never ``null``, never ``0``.
    * :class:`~enum.Enum` — its value, serialized by these same rules.
    * :class:`~datetime.datetime` — RFC 3339 with millisecond precision (:func:`to_rfc3339`), so
      it must be timezone-aware.

    Everything else is refused, including :class:`~decimal.Decimal` (``Decimal("3.0")`` and
    ``Decimal("3.00")`` are equal but serialize differently, so hashing one would depend on how it
    was typed — see ADR-0030; convert to
    :class:`~baseaicore.money.Money` or to a string first), ``bytes``, ``set`` and arbitrary
    objects.

    Strings are **not** Unicode-normalized. Two visually identical names in NFC and NFD hash
    differently, which is deliberate: a provider's model name must round-trip byte-exactly
    (canonical model identity §2), and silently normalizing it here would
    make the hash disagree with the equality of the object it came from.

    Args:
        value: The structure to serialize.

    Returns:
        Canonical JSON text. Byte-identical for equal inputs.

    Raises:
        ValidationError: If the structure contains an unserializable type, a non-string mapping
            key, a non-finite float, a naive datetime, or a reference cycle.

    Security:
        Never call this on a structure containing a secret. Its output is what gets hashed,
        logged, stored and exported, and it makes no attempt to redact
        (security standards).
    """
    return json.dumps(
        _normalize(value, ()),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_of(value: Any) -> str:  # noqa: ANN401 — same structure as canonical_json
    """Return the SHA-256 hex digest of a structure's canonical JSON.

    This is the hash behind every fingerprint in the suite. Because it goes through
    :func:`canonical_json`, two equal structures always produce the same digest and two different
    ones effectively never do.

    Args:
        value: The structure to hash, subject to :func:`canonical_json`'s accepted types.

    Returns:
        64 lowercase hex characters.

    Raises:
        ValidationError: Whatever :func:`canonical_json` would raise for the same input.
    """
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _normalize(value: Any, path: tuple[int, ...]) -> Any:  # noqa: ANN401 — recursive normalizer
    """Convert one value to a JSON-safe form, dispatching containers before scalars.

    ``path`` holds the ``id()`` of every container currently being visited, which is how cycles
    are detected.
    """
    if isinstance(value, Enum):
        return _normalize(value.value, path)
    if isinstance(value, Mapping):
        return _normalize_mapping(value, path)
    if _is_normalizable_sequence(value):
        return _normalize_sequence(value, path)
    return _normalize_scalar(value)


def _is_normalizable_sequence(value: object) -> bool:
    """Report whether a value is a sequence to be serialized as a JSON array.

    ``str`` and the bytes-like types are sequences in Python but are not arrays here: ``str`` has
    its own JSON form, and bytes would silently become a list of integers.
    """
    return isinstance(value, Sequence) and not isinstance(
        value, str | bytes | bytearray | memoryview
    )


def _normalize_scalar(value: Any) -> Any:  # noqa: ANN401 — one arm of the recursive normalizer
    """Convert one non-container value to a JSON-safe form, refusing anything ambiguous."""
    if value is UNSUPPORTED:
        return _UNSUPPORTED_JSON
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return str(value)  # collapses str subclasses to plain str, so the output cannot vary
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return _normalize_float(value)
    if isinstance(value, datetime):
        return to_rfc3339(value)
    _refuse(value)


def _normalize_float(value: float) -> float:
    """Return a float safe to serialize, refusing the non-finite ones."""
    if not math.isfinite(value):
        raise ValidationError(
            f"Cannot canonicalize the non-finite float {value!r}: it is not valid JSON, and a "
            "nan or infinity in a hashed structure is a measurement that was never taken. Use "
            "UNSUPPORTED for a value this environment cannot provide.",
            details={"value": repr(value)},
        )
    return value + 0.0  # normalizes -0.0 to 0.0; every other float is unchanged


def _refuse(value: object) -> NoReturn:
    """Raise the most specific refusal available for a value canonical JSON cannot represent."""
    if isinstance(value, Decimal):
        raise ValidationError(
            "Decimal is not canonicalizable: Decimal('3.0') and Decimal('3.00') are equal but "
            "serialize differently, so the hash would depend on how the value was typed. Use "
            "baseaicore.money.Money for an amount, or convert to str deliberately (ADR-0030).",
            details={"value": str(value)},
        )
    if isinstance(value, bytes | bytearray | memoryview):
        raise ValidationError(
            "Cannot canonicalize raw bytes: there is no single obvious text form, and the wrong "
            "guess changes every hash built from it. Encode deliberately — .hex() for a digest, "
            "base64 for opaque payloads — and pass the string.",
            details={"type": type(value).__name__},
        )
    raise ValidationError(
        f"Cannot canonicalize a value of type {type(value).__name__!r}. Canonical JSON accepts "
        "mappings, sequences, str, int, bool, float, None, Enum, datetime and UNSUPPORTED; "
        "convert anything else to one of those first.",
        details={"type": type(value).__name__},
    )


def _normalize_mapping(value: Mapping[Any, Any], path: tuple[int, ...]) -> dict[str, Any]:
    """Normalize a mapping, rejecting non-string keys and cycles."""
    inner = _descend(value, path)
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValidationError(
                f"Mapping keys must be strings for canonical JSON; got a "
                f"{type(key).__name__!r} key ({key!r}). Non-string keys would be coerced to "
                "strings and could then collide silently.",
                details={"key": repr(key), "key_type": type(key).__name__},
            )
        result[str(key)] = _normalize(item, inner)
    return result


def _normalize_sequence(value: Sequence[Any], path: tuple[int, ...]) -> list[Any]:
    """Normalize a non-string sequence, preserving order and rejecting cycles."""
    inner = _descend(value, path)
    return [_normalize(item, inner) for item in value]


def _descend(container: object, path: tuple[int, ...]) -> tuple[int, ...]:
    """Return the visit path extended by ``container``, raising if it is already on it."""
    marker = id(container)
    if marker in path:
        raise ValidationError(
            "Cannot canonicalize a structure that contains a reference cycle; a cycle has no "
            "finite serialization.",
            details={"type": type(container).__name__},
        )
    return (*path, marker)
