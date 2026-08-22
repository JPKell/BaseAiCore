"""Domain module — the ``Unsupported`` sentinel and the ``Measurement`` type.

Imports no framework and performs no I/O. This is the module that makes
[ADR-0016](../../docs/adr/0016-unavailable-is-not-zero.md) enforceable rather than aspirational:
a measurement this environment cannot provide is a value that *refuses* to behave like a number,
so the idioms that would fabricate one fail loudly at development time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, NoReturn, TypeGuard

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "UNSUPPORTED",
    "Measurement",
    "Unsupported",
    "is_supported",
    "supported_values",
]


class Unsupported:
    """Sentinel for a measurement this environment genuinely cannot provide.

    Boolean, numeric and ordering coercion all raise :class:`TypeError` on purpose. The failure
    this guards against is ``value or 0`` / ``value + x`` quietly turning "not measurable" into a
    real-looking number — the most damaging bug class in a measurement system, because the result
    is indistinguishable from a real reading once it reaches an average, a chart or a routing
    decision ([ADR-0016](../../docs/adr/0016-unavailable-is-not-zero.md)).

    Equality and hashing are *not* refused. They are identity-based and total: ``UNSUPPORTED ==
    UNSUPPORTED`` is ``True``, ``UNSUPPORTED == 0`` is ``False``, and the sentinel can sit inside
    a frozen dataclass that needs ``__eq__`` and ``__hash__``. Refusing them would make every
    value object containing a measurement unhashable, which buys no safety: an equality test
    cannot fabricate a number.

    Invariants:
        * There is exactly one instance, process-wide. ``Unsupported()`` returns it, and it
          survives ``copy``, ``deepcopy`` and ``pickle`` as the same object, so ``is`` comparison
          is safe after a round trip through a queue or a cache.
        * It is immutable and therefore thread-safe.

    Serialization is the caller's job and is fixed by ADR-0016: the JSON form is the string
    ``"unsupported"`` (:func:`baseaicore.hashing.canonical_json` emits it), storage is ``NULL``
    plus a reason, and the UI renders an em dash with that reason. Never ``null``, never ``0``.
    """

    __slots__ = ()

    _instance: Unsupported | None = None

    def __new__(cls) -> Unsupported:
        """Return the one process-wide instance, creating it on first call."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _refuse(self, *_args: object, **_kwargs: object) -> NoReturn:
        """Raise :class:`TypeError`, naming the sentinel and what the caller should do instead."""
        raise TypeError(
            "UNSUPPORTED is not a number: this measurement does not exist in this environment. "
            "Test it with `is_supported(value)` or `value is UNSUPPORTED` before using it, and "
            "exclude it from aggregates rather than coercing it (ADR-0016)."
        )

    # Truthiness first: `value or 0` and `if value:` are the idioms this type exists to stop.
    __bool__ = _refuse
    __int__ = _refuse
    __float__ = _refuse
    __index__ = _refuse
    __complex__ = _refuse
    __round__ = _refuse
    __trunc__ = _refuse
    __floor__ = _refuse
    __ceil__ = _refuse

    # Arithmetic, in both operand positions: `total + value` must fail as loudly as `value + total`.
    __add__ = _refuse
    __radd__ = _refuse
    __sub__ = _refuse
    __rsub__ = _refuse
    __mul__ = _refuse
    __rmul__ = _refuse
    __truediv__ = _refuse
    __rtruediv__ = _refuse
    __floordiv__ = _refuse
    __rfloordiv__ = _refuse
    __mod__ = _refuse
    __rmod__ = _refuse
    __pow__ = _refuse
    __rpow__ = _refuse
    __neg__ = _refuse
    __pos__ = _refuse
    __abs__ = _refuse

    # Ordering: `max(values)` and `sorted(values)` must not silently rank an absent measurement.
    __lt__ = _refuse
    __le__ = _refuse
    __gt__ = _refuse
    __ge__ = _refuse

    def __hash__(self) -> int:
        """Return a constant hash — there is one instance, so one hash."""
        return hash(Unsupported)

    def __repr__(self) -> str:
        """Return ``"UNSUPPORTED"``, the name the singleton is imported under."""
        return "UNSUPPORTED"

    def __str__(self) -> str:
        """Return ``"unsupported"``, the suite-wide serialized form (ADR-0016 §4)."""
        return "unsupported"

    def __reduce__(self) -> tuple[type[Unsupported], tuple[()]]:
        """Pickle as a call to ``Unsupported()``, which returns the singleton."""
        return (Unsupported, ())

    def __copy__(self) -> Unsupported:
        """Return the singleton: a copy of a singleton is the singleton."""
        return self

    def __deepcopy__(self, _memo: dict[int, Any]) -> Unsupported:
        """Return the singleton: a deep copy of a singleton is still the singleton."""
        return self


UNSUPPORTED: Final[Unsupported] = Unsupported()
"""The one process-wide :class:`Unsupported` instance. Compare with ``is``."""

type Measurement = int | float | Unsupported
"""A number that may not exist here.

This is the real annotation for any quantity a provider, sensor or benchmark might fail to
report. Never ``Any``, and never ``float | None`` — ``None`` keeps its ordinary Python meaning of
"no value in this context" (an optional digest), which is a different statement from "this
environment cannot measure it" (ADR-0016 §9).
"""


def is_supported[T](value: T | Unsupported) -> TypeGuard[T]:
    """Report whether a value that might be unavailable carries a real one.

    Generic in what it guards, so it narrows to whatever the caller's own union holds: a
    :data:`Measurement` narrows to ``int | float``, a token count to ``int``, and a
    :class:`~baseaicore.money.Money` price to ``Money``. The alternative — hard-coding
    ``int | float`` — would force a cast at every non-numeric measurement site, and a cast is
    exactly the thing that lets an unsupported value slip through untested.

    Args:
        value: The value to test.

    Returns:
        ``True`` unless ``value`` is :data:`UNSUPPORTED`. The ``True`` branch is narrowed for the
        type checker, so it can be used without a cast.
    """
    return value is not UNSUPPORTED


def supported_values(values: Iterable[Measurement]) -> list[int | float]:
    """Filter an iterable of measurements down to the ones that exist.

    The intended use is aggregation. ADR-0016 §6 requires that unsupported values be *excluded*
    from a statistic and that the sample count behind that statistic be reported alongside it —
    so callers compare ``len(supported_values(xs))`` against ``len(xs)`` and say what they
    dropped. A statistic over an empty result is itself unsupported, not zero.

    Args:
        values: Measurements in any order; the order is preserved.

    Returns:
        A new list containing only the real numbers, in input order. Possibly empty, which is the
        caller's signal that the metric is unsupported rather than zero.
    """
    return [value for value in values if is_supported(value)]
