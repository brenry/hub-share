"""Smart delivery: send -> deliver -> received -> delivery.

Pre-checks answer at once with a reason. Otherwise the focused tool's line gets `deliver`
and must answer `received` within the timeout. Each `sendId` and its result are kept
10 minutes (at most 256), so a retry after a reconnect never delivers twice.
"""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from hub.core import messages as M
from hub.core.api import Invalid
from hub.core.bus import Bus
from hub.core.files import Files
from hub.core.line import Line

KEEP_S = 600
KEEP_MAX = 256
REASONS = {"full", "one_only", "kind", "missing", "busy", "error"}
SOCKET_KIND = {"clip": "video", "sound": "audio"}     # a Hub item's kind as a socket names it (`api.Kind`)


@dataclass(eq=False)
class Pending:
    target: Line | None
    tool: str
    label: str
    waiters: set[Line] = field(default_factory=set)
    result: dict | None = None
    at: float = field(default_factory=time.monotonic)
    timer: asyncio.TimerHandle | None = None


class Delivery:
    def __init__(self, bus: Bus, files: Files) -> None:
        self.bus, self.files = bus, files
        self.sends: OrderedDict[str, Pending] = OrderedDict()
        bus.handlers.update({"send": self.send, "received": self.received})
        bus.on_close.append(self.closed)

    def _trim(self) -> None:
        now = time.monotonic()
        for sid, p in list(self.sends.items()):
            if p.result is not None and (now - p.at > KEEP_S or len(self.sends) > KEEP_MAX):
                del self.sends[sid]

    def _finish(self, sid: str, result: dict) -> None:
        p = self.sends[sid]
        p.result = result
        if p.timer is not None:
            p.timer.cancel()
        for line in p.waiters:
            self.bus.send(line, M.msg("delivery", result, re=sid))
        p.waiters.clear()

    async def send(self, line: Line, m: dict) -> None:
        sid = m["id"]
        if sid is None:
            raise M.ProtocolError("send needs an id")
        self._trim()
        known = self.sends.get(sid)
        if known is not None:
            if known.result is not None:
                self.bus.send(line, M.msg("delivery", known.result, re=sid))
            else:
                known.waiters.add(line)
            return
        d = m["d"]
        items, socket, tool = d.get("items"), d.get("socket"), d.get("tool")
        if not isinstance(items, list) or not items or not all(isinstance(i, str) for i in items):
            raise Invalid("items", "Send at least 1 item")
        if not isinstance(socket, str) or (tool is not None and not isinstance(tool, str)):
            raise Invalid("socket", "Say where the items go")
        focus, target = self.bus.focus_record(), self.bus.focus_line
        p = Pending(target=target, tool=focus["tool"] if focus else "", label=focus["label"] if focus else "",
                    waiters={line})
        self.sends[sid] = p
        failed = self._precheck(focus, tool, socket, items)
        if failed is not None:
            self._finish(sid, {"status": "failed", "reason": failed[0], "text": failed[1]})
            return
        assert target is not None and focus is not None
        payload = {"tool": p.tool, "socket": socket, "from": {"role": line.role, "label": line.label},
                   "items": [self._item(i) for i in items]}
        self.bus.send(target, M.msg("deliver", payload, id=sid))
        p.timer = asyncio.get_running_loop().call_later(self.bus.timing.deliver_s, self._timeout, sid)

    def _item(self, item: str) -> dict[str, Any]:
        """A delivered item: its id, kind and address; a sound also its seconds (the Sound box shows them), and
        so does a clip (the Video box)."""
        out: dict[str, Any] = {"id": item, "kind": self.files.kind(item), "url": self.files.url(item)}
        facts = (self.files.sound_facts(item) if out["kind"] == "sound"
                 else self.files.clip_facts(item) if out["kind"] == "clip" else None)
        return {**out, "seconds": facts["seconds"]} if facts else out

    def _precheck(self, focus: dict | None, tool: str | None, socket: str, items: list[str]) -> tuple[str, str] | None:
        if focus is None:
            return "no_tool", "No tool is open"
        if tool is not None and tool != focus["tool"]:
            label = self.bus.tools[tool].title if tool in self.bus.tools else "That tool"
            return "offline", f"{label} is offline"
        slots = [s for s in focus["sockets"] if socket in (s["group"], s["id"])]
        if not slots:
            return "no_socket", f"{focus['label']} has no place for that right now"
        accepts = {k for s in slots for k in s["accepts"]}
        for item in items:
            try:
                self.files.existing_media(item)
            except Invalid:
                return "bad_item", "That image is no longer available"
            kind = self.files.kind(item) or ""
            if SOCKET_KIND.get(kind, kind) not in accepts:
                return "kind", f"{focus['label']} cannot take that kind of item there"
        return None

    def _timeout(self, sid: str) -> None:
        p = self.sends.get(sid)
        if p is not None and p.result is None:
            self._finish(sid, {"status": "failed", "reason": "timeout", "text": f"No answer from {p.label}"})

    async def received(self, line: Line, m: dict) -> None:
        sid = m["re"]
        p = self.sends.get(sid) if sid else None
        if p is None or p.result is not None or p.target is not line:
            return
        d = m["d"]
        placed = [{"item": x["item"], "socket": x["socket"]} for x in _list(d.get("placed"))
                  if isinstance(x.get("item"), str) and isinstance(x.get("socket"), str)]
        refused = [{"item": x["item"], "reason": x["reason"] if x.get("reason") in REASONS else "error",
                    "text": str(x.get("text") or "Not added")[:120]}
                   for x in _list(d.get("refused")) if isinstance(x.get("item"), str)]
        result = {"status": "done", "tool": p.tool, "toolLabel": p.label, "placed": placed, "refused": refused}
        self._finish(sid, result)

    def closed(self, line: Line) -> None:
        for sid, p in list(self.sends.items()):
            p.waiters.discard(line)
            if p.target is line and p.result is None:
                self._finish(sid, {"status": "failed", "reason": "gone", "text": f"{p.label} went offline"})


def _list(value: Any) -> list[dict]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []
