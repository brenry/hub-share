"""The session: someone is working while a window is connected. When the last window has been gone for a short
grace (a page reload reconnects well inside it), the session ends: everything the hub was holding for it is
forgotten — the chat, the prompt and reference boxes, the finished jobs. The next window starts from nothing but
what is in Temp. Nothing of a session is ever on disk.
"""
from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable


class Session:
    def __init__(self, bus_lines: Callable[[], int], on_end: Callable[[], None], grace_s: float) -> None:
        self._lines, self._on_end, self._grace = bus_lines, on_end, grace_s
        self._timer: asyncio.TimerHandle | None = None
        self.open = False
        self.id = ""                  # a new token for each session; a window that sees it change starts over

    def presence_changed(self) -> None:
        """Called by the bus whenever a window connects or leaves."""
        if self._lines() > 0:
            if not self.open:
                self.open, self.id = True, secrets.token_hex(8)
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        elif self.open and self._timer is None:
            self._timer = asyncio.get_running_loop().call_later(self._grace, self._end)

    def _end(self) -> None:
        self._timer = None
        if self._lines() > 0:
            return
        self.open = False
        self._on_end()

    def close(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
