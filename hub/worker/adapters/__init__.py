"""The engine adapters, in probe order: the only place an engine key family (and, in a facts file, a model name)
may be named. `select(root, session)` picks the first whose probe accepts the root."""
from __future__ import annotations

from typing import Any

try:
    from ..engineapi import Adapter, NoAdapter
    from ..engineapi import select as _select
    from .fork import Fork
    from .upstream import Upstream
except ImportError:  # run as a script by the engine's Python
    from adapters.fork import Fork
    from adapters.upstream import Upstream
    from engineapi import Adapter, NoAdapter
    from engineapi import select as _select

ADAPTERS: tuple[Adapter, ...] = (Upstream(), Fork())

__all__ = ["ADAPTERS", "NoAdapter", "by_flavour", "forced_config", "prepare", "select"]


def select(root: str, session: Any = None) -> Adapter:
    return _select(root, ADAPTERS, session)


def prepare(root: str) -> None:
    """Before the engine opens, the adapter that drives the root readies what the engine would fetch at start
    (`Unready`, one line, when it cannot). A root none drives is left for the opening to refuse."""
    try:
        adapter = select(root)
    except NoAdapter:
        return
    adapter.prepare(root)


def forced_config(root: str) -> dict[str, Any]:
    """What the engine's config must hold for the tasks of the adapter that drives the root, as seeded before the
    engine opens ({} for a root none drives)."""
    try:
        return dict(select(root).forced_config)
    except NoAdapter:
        return {}


def by_flavour(flavour: str) -> Adapter:
    """The adapter for the worker's flavour word (`legacy` or `upstream`)."""
    for adapter in ADAPTERS:
        if adapter.flavour == flavour:
            return adapter
    raise NoAdapter(f"No engine adapter for the {flavour!r} flavour")
