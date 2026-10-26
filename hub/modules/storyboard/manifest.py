"""Clip Cells: its settings, two listings and four actions, published as tools; no tab and no jobs of its own."""
from __future__ import annotations

from hub.core.api import Module

from . import cells, render, routes, screen

MODULE = Module(
    id="storyboard",
    title="Clip Cells",
    screen=screen.SCREEN,
    listings=cells.LISTINGS,
    actions=cells.ACTIONS + render.ACTIONS,
    listens={"job.finished": render.on_finished},
    routes=routes.ROUTES,
)
