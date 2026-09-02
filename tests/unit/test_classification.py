"""Unit tests for the data-classification vocabulary.

The ordering below is fixed by ADR-0046. It is what three components compute egress against, so a
change that makes one of these fail is the change that is wrong, not the test. The pairwise table
is exhaustive by construction: every ordered pair of the three levels appears.
"""

from __future__ import annotations

import itertools
import json
import operator
from typing import TYPE_CHECKING

import pytest

from baseaicore.classification import DataClassification

if TYPE_CHECKING:
    from collections.abc import Callable

# ---- Golden ordering (ADR-0046) --------------------------------------------------------------
# Every ordered pair of levels, with the expected sign of the comparison. Exhaustive: 3 x 3 = 9.
GOLDEN_ORDERED_PAIRS = [
    (DataClassification.PUBLIC, DataClassification.PUBLIC, 0),
    (DataClassification.PUBLIC, DataClassification.INTERNAL, -1),
    (DataClassification.PUBLIC, DataClassification.CONFIDENTIAL, -1),
    (DataClassification.INTERNAL, DataClassification.PUBLIC, 1),
    (DataClassification.INTERNAL, DataClassification.INTERNAL, 0),
    (DataClassification.INTERNAL, DataClassification.CONFIDENTIAL, -1),
    (DataClassification.CONFIDENTIAL, DataClassification.PUBLIC, 1),
    (DataClassification.CONFIDENTIAL, DataClassification.INTERNAL, 1),
    (DataClassification.CONFIDENTIAL, DataClassification.CONFIDENTIAL, 0),
]

GOLDEN_SERIALIZED_VALUES = [
    (DataClassification.PUBLIC, "public", 0),
    (DataClassification.INTERNAL, "internal", 1),
    (DataClassification.CONFIDENTIAL, "confidential", 2),
]


@pytest.mark.parametrize(("left", "right", "sign"), GOLDEN_ORDERED_PAIRS)
def test_every_ordered_pair_compares_as_its_golden_says(
    left: DataClassification, right: DataClassification, sign: int
) -> None:
    assert (left < right) is (sign < 0)
    assert (left > right) is (sign > 0)
    assert (left <= right) is (sign <= 0)
    assert (left >= right) is (sign >= 0)


@pytest.mark.parametrize(("level", "value", "rank"), GOLDEN_SERIALIZED_VALUES)
def test_the_serialized_value_and_rank_match_their_goldens(
    level: DataClassification, value: str, rank: int
) -> None:
    assert level.value == value
    assert level.rank == rank
    assert DataClassification(value) is level


def test_the_levels_sort_least_restrictive_first() -> None:
    shuffled = [
        DataClassification.CONFIDENTIAL,
        DataClassification.PUBLIC,
        DataClassification.INTERNAL,
    ]

    assert sorted(shuffled) == [
        DataClassification.PUBLIC,
        DataClassification.INTERNAL,
        DataClassification.CONFIDENTIAL,
    ]


@pytest.mark.parametrize(
    ("left", "right"), list(itertools.product(DataClassification, DataClassification))
)
def test_max_is_the_lattice_join_for_every_pair(
    left: DataClassification, right: DataClassification
) -> None:
    # The operation every consumer needs — max(caller, adapter) — with no helper and no import.
    joined = max(left, right)

    assert joined >= left
    assert joined >= right
    assert joined in (left, right)


def test_ordering_is_by_rank_and_not_by_the_string_value() -> None:
    # The trap this class exists to close: alphabetically "confidential" < "internal" < "public",
    # which is exactly backwards, and a StrEnum would inherit that ordering silently.
    assert "confidential" < "internal" < "public"  # noqa: PLR0133 — the contrast is the test
    assert DataClassification.CONFIDENTIAL > DataClassification.INTERNAL
    assert DataClassification.INTERNAL > DataClassification.PUBLIC


@pytest.mark.parametrize("operand", ["internal", 1, None, object()])
@pytest.mark.parametrize(
    "compare", [operator.lt, operator.le, operator.gt, operator.ge], ids=["lt", "le", "gt", "ge"]
)
def test_comparing_against_a_non_member_refuses_rather_than_guessing(
    compare: Callable[[object, object], bool], operand: object
) -> None:
    # Returning NotImplemented would let Python fall back to str ordering for the string case,
    # which is silently wrong in the permissive direction.
    with pytest.raises(TypeError, match="ordered by rank"):
        compare(DataClassification.PUBLIC, operand)


@pytest.mark.parametrize(
    "compare", [operator.lt, operator.le, operator.gt, operator.ge], ids=["lt", "le", "gt", "ge"]
)
def test_the_reflected_comparison_also_refuses(
    compare: Callable[[object, object], bool],
) -> None:
    # A bare string on the left must not win by falling back to str.__lt__ against a str subclass:
    # DataClassification subclasses str, so Python would otherwise try the reflected operation.
    with pytest.raises(TypeError, match="ordered by rank"):
        compare("internal", DataClassification.PUBLIC)


def test_public_is_truthy_so_it_can_never_be_read_as_unset() -> None:
    # An IntEnum would make PUBLIC == 0 and therefore falsy, so `if classification:` would read
    # "public" as "not classified" — ADR-0016's bug class inside a governance type (ADR-0046 §2).
    assert bool(DataClassification.PUBLIC) is True
    assert DataClassification.PUBLIC != 0  # type: ignore[comparison-overlap]  # proving the point


def test_equality_with_the_serialized_string_still_works() -> None:
    # It is a StrEnum on purpose: configuration, payloads and rows carry the string.
    assert DataClassification.INTERNAL == "internal"  # type: ignore[comparison-overlap]  # a StrEnum
    assert json.dumps({"c": DataClassification.INTERNAL}) == '{"c": "internal"}'


def test_the_vocabulary_is_exactly_three_levels() -> None:
    # Adding one is a new ADR, not a minor release: the ordering is the contract.
    assert [level.value for level in DataClassification] == ["public", "internal", "confidential"]
