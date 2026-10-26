"""A screen's line: its bounded outbox (with in-place coalescing), rate bucket and state."""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from hub.core import messages as M
from hub.core.api import Device


@dataclass
class Timing:
    hello_s: float = 5.0
    beat_s: float = 25.0
    deliver_s: float = 5.0
    session_grace_s: float = 15.0      # the last window gone this long: the session ends (a reload is far quicker)


class Outbox:
    """Bounded FIFO where a keyed message may replace its queued predecessor in place."""

    def __init__(self, limit: int = M.QUEUE_LIMIT) -> None:
        self.items: deque[list] = deque()
        self.index: dict[str, list] = {}
        self.ready = asyncio.Event()
        self.limit = limit

    def push(self, m: dict, key: str | None = None, replace: bool = True) -> bool:
        if key is not None and replace:
            entry = self.index.get(key)
            if entry is not None and entry[2]:
                entry[0] = m
                return True
        if len(self.items) >= self.limit:
            return False
        entry = [m, key, replace]
        self.items.append(entry)
        if key is not None:
            self.index[key] = entry
        self.ready.set()
        return True

    async def next(self, timeout: float) -> dict | None:
        if not self.items:
            self.ready.clear()
            try:
                await asyncio.wait_for(self.ready.wait(), timeout)
            except TimeoutError:
                return None
        entry = self.items.popleft()
        if entry[1] is not None and self.index.get(entry[1]) is entry:
            del self.index[entry[1]]
        return entry[0]


class Bucket:
    def __init__(self, rate: float = M.RATE_PER_S, burst: float = M.RATE_BURST) -> None:
        self.rate, self.burst, self.tokens, self.at = rate, burst, burst, time.monotonic()

    def take(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.burst, self.tokens + (now - self.at) * self.rate)
        self.at = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True


@dataclass(eq=False)
class Line:
    ws: Any
    device: Device
    screen: str
    role: str
    label: str
    lanes: set[str]
    since: float = field(default_factory=time.monotonic)
    out: Outbox = field(default_factory=Outbox)
    bucket: Bucket = field(default_factory=Bucket)
    tool: str | None = None
    sockets: dict[str, dict] = field(default_factory=dict)
    writer: asyncio.Task | None = None
    strikes: int = 0
    closed: bool = False
