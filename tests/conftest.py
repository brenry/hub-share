"""Shared test setup: keep every test hermetic (no inherited hub data folder, no scope asked of a real user manager)."""
from __future__ import annotations

import pytest

from hub.core import enginescope
from hub.modules.director import mix, render


@pytest.fixture(autouse=True)
def _no_hub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUB_DATA", raising=False)


@pytest.fixture(autouse=True)
def _no_engine_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """Workers start inside the test's own process tree; test_engine_scope.py turns scopes on with a stand-in."""
    monkeypatch.setattr(enginescope, "_answer", False)


@pytest.fixture(autouse=True)
def _no_mix_held() -> None:
    """The mix's in-memory jobs and refusals (`mix.running`, `mix.failed`) never carry from one test into
    the next (a stand-in book's job never ends, so `mix.prune` would keep it); nor does a Render job of `render.running`
    (a script name another test renders under would read it on a ctx with no jobs)."""
    mix.running.clear()
    mix.failed.clear()
    render.running.clear()
