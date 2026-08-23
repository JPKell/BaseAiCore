"""Domain module — the capability identifier: the name of a claimed or demonstrated ability.

Imports no framework and performs no I/O.

A capability ID is pure vocabulary syntax: one or more lowercase, underscore-word segments joined
by ``.``, each further segment narrowing the one before it (``coding``, ``coding.python``,
``content.article_draft``). This package owns only the *type* and its syntax validation; the
vocabulary's *contents* and their version live in SetSpec, so that adding a term never requires a
BaseAiCore release (`docs/architecture/master-architecture.md`, `docs/architecture/
traceability-matrix.md` §"who owns the capability vocabulary").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from baseaicore.errors import ValidationError

__all__ = ["CapabilityId"]

_SEPARATOR = "."
_SEGMENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
# No spec fixes a number; this package owns the syntax, so it fixes one here. 64 is generous
# headroom over every term in the current specs (the longest today, `content.article_draft`, is
# 21 characters) while remaining a sane width for a future database column or UI badge — a bound
# exists only so "over-long" has one documented, tested meaning instead of none.
_MAX_LENGTH = 64


@dataclass(frozen=True, slots=True)
class CapabilityId:
    """A syntactically validated vocabulary term identifying a capability, generic or specialized.

    Immutable and hashable, so it can be a dictionary key or a set member. Two identifiers are
    equal, and hash equal, if and only if their ``value`` strings are equal.

    This type has no opinion on which terms exist or what they mean — it only proves that a
    string is a legal capability ID and computes the two syntactic relationships (root,
    specialization) that hold regardless of vocabulary contents. Whether ``coding.python`` is a
    real, current vocabulary term is SetSpec's question, not this one's.

    Attributes:
        value: The full dotted identifier, exactly as constructed, e.g. ``"coding"`` or
            ``"content.article_draft"``. This is the string form; there is no separate
            serialization because a capability ID has no representation that is not the string it
            was built from.
    """

    value: str

    def __post_init__(self) -> None:
        """Validate the identifier, raising rather than storing one that cannot be trusted.

        Raises:
            ValidationError: If ``value`` is empty, longer than the maximum length, has a
                leading, trailing or doubled ``.``, or contains a segment that is not lowercase
                ``[a-z][a-z0-9_]*`` (uppercase, digits or underscores leading a segment, spaces,
                or any other punctuation).
        """
        if not self.value:
            raise ValidationError(
                "CapabilityId requires a non-empty value shaped like 'root' or "
                "'root.specialization', e.g. 'coding' or 'coding.python'; got ''.",
                details={"field": "value", "value": self.value},
            )
        if len(self.value) > _MAX_LENGTH:
            raise ValidationError(
                f"CapabilityId must be at most {_MAX_LENGTH} characters; got "
                f"{len(self.value)} in {self.value!r}.",
                details={"field": "value", "value": self.value, "max_length": _MAX_LENGTH},
            )
        segments = self.value.split(_SEPARATOR)
        if any(not _SEGMENT_PATTERN.match(segment) for segment in segments):
            raise ValidationError(
                "CapabilityId must be one or more segments matching '[a-z][a-z0-9_]*', joined by "
                f"single '.' characters, with no leading, trailing or doubled separator; got "
                f"{self.value!r}.",
                details={"field": "value", "value": self.value},
            )

    @property
    def root(self) -> str:
        """The first, most general segment — itself a legal ``CapabilityId`` value.

        ``CapabilityId("coding").root == "coding"``; ``CapabilityId("coding.python").root ==
        "coding"``.
        """
        return self.value.partition(_SEPARATOR)[0]

    @property
    def is_specialization(self) -> bool:
        """Whether this identifier narrows a root with at least one further segment.

        ``CapabilityId("coding").is_specialization`` is ``False``;
        ``CapabilityId("coding.python").is_specialization`` is ``True``.
        """
        return _SEPARATOR in self.value

    def inherits_from(self, other: CapabilityId) -> bool:
        """Return whether ``other`` names this identifier or one of its ancestors.

        ``coding.python`` inherits from ``coding`` — and from itself. ``coding`` does not inherit
        from ``coding.python``: a general capability does not satisfy a request for a specific
        one, but a specific one satisfies a request for the general one it specializes. The
        relation is reflexive so that a task profile requiring exactly ``coding.python`` is
        satisfied by evidence recorded against ``coding.python`` itself, with no special case at
        the call site.

        Args:
            other: The candidate ancestor, or this identifier itself.

        Returns:
            ``True`` if ``self.value`` equals ``other.value``, or extends it by one or more
            further ``.``-separated segments; ``False`` otherwise.
        """
        return self.value == other.value or self.value.startswith(f"{other.value}{_SEPARATOR}")

    def __str__(self) -> str:
        """Return ``value``, so an identifier interpolated into a log line is greppable."""
        return self.value
