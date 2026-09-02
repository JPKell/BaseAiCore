"""Domain module — how sensitive a piece of data is, on one ordered scale.

Imports no framework and performs no I/O.

The suite needs exactly one answer to "may data of this classification go to that target?", and
that question is an **ordering** — `classification <= target ceiling` — not a set membership and
not a string equality. Because the comparison is the contract, the ordering lives here rather than
in each component that performs it: two components disagreeing about whether `internal` outranks
`confidential` would be a silent egress bug that no test in either one could catch
(ADR-0046).
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["DataClassification"]


class DataClassification(StrEnum):
    """How sensitive a body of data is: an ordered rank, fixed for the life of the suite.

    Three levels, deliberately: fewer cannot express the shipped tier ladder (a local tier serves
    anything, a cheap remote tier serves up to internal, a frontier tier serves public only), and
    more would be levels no operator can distinguish in practice. **The ordering is the contract**
    — adding a level is a new ADR, not a minor release, because a new member has to be given a
    position and every value stored under the old vocabulary acquires a new meaning relative to it.

    The lattice join every consumer needs is the built-in :func:`max`::

        >>> from baseaicore import DataClassification as DC
        >>> max(DC.PUBLIC, DC.CONFIDENTIAL)
        <DataClassification.CONFIDENTIAL: 'confidential'>

    Ordering is by **rank**, never by the member's string value — alphabetically
    ``"confidential" < "internal" < "public"``, which is exactly backwards. That trap is why the
    four ordering operators are defined here rather than inherited from :class:`str`, and why
    comparing a member against a bare string **raises** instead of quietly answering
    alphabetically.

    The default, wherever one is needed, is :attr:`CONFIDENTIAL`: an undeclared classification is
    the most restrictive one, so an omission costs a user a remote tier rather than costing them
    their data. Callers own that default — this type does not impose it, because the type has no
    "absent" member and deliberately never will.

    This is a rank, not a taxonomy. It answers "how far may this travel", and it says nothing about
    which regulation covers the data or what kind of data it is; a deployment that needs kinds
    carries them as metadata beside the rank, never as a second vocabulary that also claims to
    govern egress.
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"

    @property
    def rank(self) -> int:
        """Return this level's position in the ordering, lowest first.

        Public API because it is what a caller stores or indexes when it needs the ordering in a
        database rather than in Python. It is **not** the serialized form: rows, payloads and
        configuration all carry the member's string value, so inserting a level later renumbers
        ranks without rewriting data.

        Returns:
            ``0`` for :attr:`PUBLIC`, ``1`` for :attr:`INTERNAL`, ``2`` for :attr:`CONFIDENTIAL`.
        """
        return _RANKS[self]

    def _rank_of(self, other: object) -> int:
        """Return ``other``'s rank, or refuse if it is not a member of this enum.

        Raises:
            TypeError: If ``other`` is not a :class:`DataClassification`. A bare string is refused
                rather than compared, because this class subclasses :class:`str` and returning
                ``NotImplemented`` would let Python fall back to alphabetical string ordering —
                which is silently wrong in the direction that permits egress.
        """
        if not isinstance(other, DataClassification):
            message = (
                "DataClassification is ordered by rank, and comparing it against "
                f"{other!r} would fall back to alphabetical string ordering, which is backwards "
                "('confidential' < 'internal' < 'public'). Convert the operand with "
                "DataClassification(value) first."
            )
            raise TypeError(message)
        return _RANKS[other]

    def __lt__(self, other: object) -> bool:
        """Return whether this level is strictly less restrictive than ``other``."""
        return self.rank < self._rank_of(other)

    def __le__(self, other: object) -> bool:
        """Return whether this level is no more restrictive than ``other``."""
        return self.rank <= self._rank_of(other)

    def __gt__(self, other: object) -> bool:
        """Return whether this level is strictly more restrictive than ``other``."""
        return self.rank > self._rank_of(other)

    def __ge__(self, other: object) -> bool:
        """Return whether this level is at least as restrictive as ``other``."""
        return self.rank >= self._rank_of(other)


_RANKS: dict[DataClassification, int] = {
    DataClassification.PUBLIC: 0,
    DataClassification.INTERNAL: 1,
    DataClassification.CONFIDENTIAL: 2,
}
