"""Shared fixtures and the guards every test in this repository runs under.

The guards enforce the determinism rules in testing standards §4: no test
reaches the network, and no test writes to the developer's real configuration or data directories.
``baseaicore`` performs no I/O at all, so both guards are here to *prove* that rather than to
contain it — a future change that reached for a socket or an XDG path would fail loudly instead of
passing quietly on the machine that made it.

Naive-datetime calls are caught by ruff's ``DTZ`` rules rather than by a runtime guard: this
package calls ``datetime.now`` in exactly one place, ``timeutil.utc_now``, and
``tests/unit/test_timeutil.py`` asserts that its result is timezone-aware.
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, NoReturn

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

FROZEN_NOW = datetime(2026, 8, 22, 14, 3, 11, 250_000, tzinfo=UTC)
"""The instant every clock-dependent test runs at. Fixed so goldens never depend on the calendar."""


@pytest.fixture
def frozen_clock() -> Iterator[datetime]:
    """Yield a fixed timezone-aware instant for injecting as a ``Clock``.

    Use as ``UlidGenerator(clock=lambda: frozen_clock)``. An injected clock is preferred over
    patching the interpreter's, per coding standards §5.
    """
    yield FROZEN_NOW


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that opens a network socket."""

    def refuse(*_args: Any, **_kwargs: Any) -> NoReturn:
        raise AssertionError(
            "A test attempted a network connection. baseaicore performs no I/O; if this is a new "
            "dependency it violates spec §3, and if it is a test double it should be injected."
        )

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point every XDG root and ``HOME`` at a temporary directory for the duration of a test."""
    for variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(variable, str(tmp_path / variable.lower()))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
