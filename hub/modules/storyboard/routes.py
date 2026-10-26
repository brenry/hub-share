"""The Storyboard's HTTP routes: none until a web option is chosen (a Storyboard tab, or a section in Media)."""
from __future__ import annotations

from hub.core.api import Route

ROUTES: tuple[Route, ...] = ()
