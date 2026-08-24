"""Domain module — the base error hierarchy every suite component reuses.

Imports no framework and raises nothing itself: this module only *defines* the exception types
that the rest of the suite raises, so that an error crossing a package boundary is recognisable
and has a stable machine-readable ``code``.

Every ``code`` in this module is part of the public contract (spec §11). Adding a subclass is a
minor change; changing what an existing code means is a major one, because codes appear in API
error envelopes, in stored event rows and in CLI exit-code mapping.
"""

from __future__ import annotations

from typing import Any, ClassVar

__all__ = [
    "ConfigurationError",
    "ConflictError",
    "DependencyUnavailableError",
    "NotFoundError",
    "SuiteError",
    "UnsupportedOperationError",
    "UnsupportedPlatformError",
    "ValidationError",
]


class SuiteError(Exception):
    """Base for every error raised anywhere in the suite.

    Carries a stable ``code`` and an optional ``details`` mapping. ``details`` is structured
    context for the caller to log or render — it is never formatted into the message, because a
    message is for humans and ``details`` is for machines, and mixing the two produces log lines
    that cannot be aggregated.

    ``details`` must never contain a secret, a prompt or generated content
    (security standards); it travels into API error envelopes.

    Attributes:
        code: Stable machine-readable identifier, shared by every instance of the class.
        message: The human-readable description passed at construction.
        details: A shallow copy of the mapping passed at construction, or an empty mapping. The
            copy exists so a caller mutating its own dict afterwards cannot change a raised error.
    """

    code: ClassVar[str] = "INTERNAL_ERROR"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        """Build the error.

        Args:
            message: What failed, what was expected, and what the caller can do about it. A bare
                "invalid" is a defect (coding standards §6).
            details: Structured context. Copied, so later mutation of the caller's dict cannot
                change the raised error.
        """
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = dict(details) if details is not None else {}

    def __str__(self) -> str:
        """Return the message alone, so a printed traceback stays readable."""
        return self.message

    def __repr__(self) -> str:
        """Return a stable representation naming the class, code, message and details."""
        return (
            f"{type(self).__name__}(code={self.code!r}, message={self.message!r}, "
            f"details={self.details!r})"
        )

    def __reduce__(self) -> tuple[Any, ...]:
        """Pickle with ``details`` intact.

        The default reduction for an exception replays ``args``, which holds only the message —
        an error crossing a process boundary would arrive with its structured context silently
        emptied, and structured context is the half a machine reads.
        """
        return (_rebuild_error, (type(self), self.message, self.details))


class ConfigurationError(SuiteError):
    """Configuration is absent, malformed, or internally contradictory."""

    code: ClassVar[str] = "CONFIGURATION_ERROR"


class ValidationError(SuiteError):
    """A value failed a domain rule: wrong shape, wrong range, or a broken invariant.

    This is the error every constructor in this package raises. It names the field and the
    expectation, never just "invalid".
    """

    code: ClassVar[str] = "VALIDATION_ERROR"


class NotFoundError(SuiteError):
    """A named entity does not exist."""

    code: ClassVar[str] = "NOT_FOUND"


class ConflictError(SuiteError):
    """The operation contradicts existing state — a uniqueness violation or a lost update."""

    code: ClassVar[str] = "CONFLICT"


class UnsupportedOperationError(SuiteError):
    """The operation is understood but this implementation refuses to perform it.

    Distinct from :class:`UnsupportedPlatformError`: the refusal is about the operation, not the
    machine it would run on.
    """

    code: ClassVar[str] = "UNSUPPORTED_OPERATION"


class UnsupportedPlatformError(SuiteError):
    """This platform cannot provide what was asked for.

    Defined here and raised elsewhere: nothing in ``baseaicore`` branches on platform (spec §16).
    SweatMeter and the applications raise it when an OS lacks a sensor or an interface.
    """

    code: ClassVar[str] = "UNSUPPORTED_PLATFORM"


class DependencyUnavailableError(SuiteError):
    """A required external dependency — a provider, a database, a device — is unreachable."""

    code: ClassVar[str] = "DEPENDENCY_UNAVAILABLE"


def _rebuild_error(
    error_type: type[SuiteError], message: str, details: dict[str, Any]
) -> SuiteError:
    """Reconstruct a pickled error; ``details`` is keyword-only, so unpickling needs this shim."""
    return error_type(message, details=details)
