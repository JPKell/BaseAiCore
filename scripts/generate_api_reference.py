#!/usr/bin/env python3
"""Regenerate ``docs/api.md`` from the public docstrings in ``baseaicore.__all__``.

Stdlib-only, matching the package's own zero-dependency policy (spec §3) rather than pulling in a
documentation generator for thirteen types. Run after any change to a public symbol's docstring or
to ``baseaicore.__all__`` itself::

    python scripts/generate_api_reference.py

The output is committed. This script does not run in CI, so a stale ``docs/api.md`` is caught by
review, not by a build failure -- there is no doc-drift job for this package yet.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import baseaicore

_OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "api.md"
_SUBMODULES = (
    "measurement",
    "identity",
    "ids",
    "timeutil",
    "hashing",
    "errors",
    "money",
    "cost",
    "descriptor",
    "runtime",
    "subject",
    "machine",
    "capability",
)


def _defining_module(name: str) -> str:
    """Return the dotted module path that actually defines ``name`` in its own ``__all__``."""
    if name == "__version__":
        return "baseaicore.__about__"
    for submodule_name in _SUBMODULES:
        submodule = importlib.import_module(f"baseaicore.{submodule_name}")
        if name in getattr(submodule, "__all__", ()):
            return f"baseaicore.{submodule_name}"
    return "baseaicore"  # pragma: no cover -- every current name resolves above


def _render_class(name: str, obj: type) -> list[str]:
    lines = [f"### `{name}`", "", f"Defined in `{_defining_module(name)}`.", ""]
    lines.append(inspect.getdoc(obj) or "*(undocumented)*")
    lines.append("")
    members: list[tuple[str, str, str]] = []
    for member_name, member in sorted(vars(obj).items()):
        if member_name.startswith("_"):
            continue
        if isinstance(member, property):
            summary = (inspect.getdoc(member.fget) or "").splitlines()
            members.append((member_name, "property", summary[0] if summary else ""))
        elif inspect.isfunction(member):
            signature = inspect.signature(member)
            summary = (inspect.getdoc(member) or "").splitlines()
            members.append((member_name, f"method{signature}", summary[0] if summary else ""))
    if members:
        lines.append("| Member | Kind | Summary |")
        lines.append("|---|---|---|")
        lines.extend(f"| `{n}` | {k} | {s} |" for n, k, s in members)
        lines.append("")
    return lines


def _render_function(name: str, obj: object) -> list[str]:
    signature = inspect.signature(obj)  # type: ignore[arg-type]
    lines = [f"### `{name}{signature}`", "", f"Defined in `{_defining_module(name)}`.", ""]
    lines.append(inspect.getdoc(obj) or "*(undocumented)*")
    lines.append("")
    return lines


def _render_constant(name: str, obj: object) -> list[str]:
    return [
        f"### `{name}`",
        "",
        f"Defined in `{_defining_module(name)}`.",
        "",
        f"Value: `{obj!r}` (`{type(obj).__name__}`)",
        "",
    ]


def main() -> None:
    """Write ``docs/api.md`` from the live ``baseaicore`` public surface."""
    lines = [
        "# API Reference",
        "",
        "Generated from the public docstrings in `baseaicore.__all__` by "
        "[`scripts/generate_api_reference.py`](../scripts/generate_api_reference.py). "
        "Do not hand-edit — regenerate instead.",
        "",
        f"`baseaicore {baseaicore.__version__}` — {len(baseaicore.__all__)} public symbols.",
        "",
    ]
    for name in sorted(baseaicore.__all__):
        obj = getattr(baseaicore, name)
        if inspect.isclass(obj):
            lines.extend(_render_class(name, obj))
        elif inspect.isfunction(obj):
            lines.extend(_render_function(name, obj))
        else:
            lines.extend(_render_constant(name, obj))
    _OUTPUT.write_text("\n".join(lines).rstrip() + "\n")
    print(f"Wrote {_OUTPUT} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
