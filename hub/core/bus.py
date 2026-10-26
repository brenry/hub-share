"""The bus: one WebSocket line per screen, lanes, presence, focus and socket declarations.

Every lane carries current state, never deltas, so a dropped screen just reconnects and
gets fresh snapshots. Each line has its own bounded outbox and writer task; a broadcast
never waits on a slow screen. `beat` is sent only after a line has been silent for 25 s.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

from hub.core import messages as M
from hub.core.api import Device, Invalid, Module
from hub.core.devices import Devices
from hub.core.line import Line, Timing

Handler = Callable[["Line", dict], Awaitable[None]]


class Bus:
    def __init__(self, devices: Devices, boot: str, version: str, timing: Timing | None = None) -> None:
        self.devices, self.boot, self.version = devices, boot, version
        self.timing = timing or Timing()
        self.lines: dict[str, Line] = {}
        self.focus_line: Line | None = None
        self.tools: dict[str, Module] = {}
        self.lane_roles: dict[str, tuple[str, ...]] = {}
        self.handlers: dict[str, Handler] = {"focus": self._focus, "sockets": self._declare,
                                             "sub": self._sub, "unsub": self._unsub}
        self.fallback: Handler | None = None
        self.engines: Callable[[], dict] = dict
        self.welcome_extra: Callable[[Line], dict] = lambda line: {}
        self.on_close: list[Callable[[Line], None]] = []
        self.on_presence: list[Callable[[], None]] = []
        self._waiting = 0

    # ---------------------------------------------------------------- outbound
    def send(self, line: Line, m: dict, key: str | None = None, replace: bool = True) -> None:
        if not line.closed and not line.out.push(m, key, replace):
            asyncio.get_running_loop().create_task(self.shut(line, M.CLOSE_SLOW))

    def publish(self, lane: str, t: str, d: Any, key: str | None = None, replace: bool = True) -> None:
        m = M.msg(t, d)
        for line in list(self.lines.values()):
            if lane in line.lanes:
                self.send(line, m, key, replace)

    async def _write(self, line: Line) -> None:
        try:
            while True:
                m = await line.out.next(self.timing.beat_s)
                await line.ws.send_text(M.encode(m if m is not None else {"t": "beat"}))
        except asyncio.CancelledError:
            raise
        except Exception:
            return

    async def shut(self, line: Line, code: int, last: dict | None = None) -> None:
        if line.writer is not None:
            line.writer.cancel()
        try:
            if last is not None:
                await line.ws.send_text(M.encode(last))
            await line.ws.close(code)
        except Exception:
            pass

    async def going_off(self, restart: bool) -> None:
        reason = "restart" if restart else "shutdown"
        last = M.msg("going_off", {"reason": reason, "back_in_s": 10 if restart else None})
        code = M.CLOSE_RESTART if restart else M.CLOSE_OFF
        await asyncio.gather(*(self.shut(line, code, last) for line in list(self.lines.values())))

    # ---------------------------------------------------------------- state
    def presence(self) -> dict:
        screens = {r: 0 for r in M.ROLES}
        labels: dict[str, set[str]] = {r: set() for r in M.ROLES}
        for line in self.lines.values():
            screens[line.role] += 1
            if line.label:
                labels[line.role].add(line.label)
        return {"screens": screens, "labels": {r: sorted(v) for r, v in labels.items()},
                "engines": self.engines(), "devices": self.devices.counts()}

    def presence_changed(self) -> None:
        self.publish("presence", "presence", self.presence(), key="presence")
        for cb in self.on_presence:
            cb()

    def focus_record(self) -> dict | None:
        line = self.focus_line
        if line is None or line.tool is None:
            return None
        mod = self.tools.get(line.tool)
        decl = line.sockets.get(line.tool, {})
        return {"screen": line.screen, "tool": line.tool, "label": mod.title if mod else line.tool,
                "mode": decl.get("mode"), "primary": decl.get("primary"), "sockets": decl.get("sockets", [])}

    def _focus_changed(self) -> None:
        self.publish("focus", "focus", self.focus_record(), key="focus")

    def default_lanes(self, role: str) -> set[str]:
        return set(M.DEFAULT_LANES[role]) | {lane for lane, roles in self.lane_roles.items() if role in roles}

    # ---------------------------------------------------------------- a line's life
    async def serve(self, ws: Any, device: Device) -> None:
        """Run one screen line. The guard has already checked Host, Origin and the cookie."""
        await ws.accept()
        if len(self.lines) + self._waiting >= M.MAX_LINES:
            await ws.close(M.CLOSE_TOO_MANY)
            return
        self.devices.attach(device.id, ws)
        line: Line | None = None
        try:
            self._waiting += 1
            try:
                line = await self._hello(ws, device)
            finally:
                self._waiting -= 1
            if line is not None:
                await self._read(line)
        finally:
            self.devices.detach(device.id, ws)
            if line is not None:
                self._drop(line)
            else:
                self.presence_changed()

    async def _hello(self, ws: Any, device: Device) -> Line | None:
        try:
            raw = await asyncio.wait_for(ws.receive(), self.timing.hello_s)
            if raw.get("type") != "websocket.receive" or raw.get("text") is None:
                raise M.ProtocolError("hello expected first")
            m = M.parse(raw["text"])
            d = m["d"]
            if m["t"] != "hello" or d.get("proto") != M.PROTO or d.get("role") not in M.ROLES:
                raise M.ProtocolError("hello expected first")
            screen, label, subs = d.get("screen"), d.get("label") or "", d.get("subs")
            if not isinstance(screen, str) or not M.ID.match(screen):
                raise M.ProtocolError("hello needs a screen id")
            if not isinstance(label, str) or len(label) > 40:
                raise M.ProtocolError("label must be short text")
            lanes = self.default_lanes(d["role"]) if subs is None else self._lanes(subs)
        except (TimeoutError, M.ProtocolError, Invalid) as e:
            text = "hello expected first" if isinstance(e, TimeoutError) else str(e)
            try:
                await ws.send_text(M.encode(M.error("protocol", text)))
                await ws.close(M.CLOSE_PROTOCOL)
            except Exception:
                pass
            return None
        old = self.lines.pop(screen, None)
        if old is not None:
            asyncio.get_running_loop().create_task(self.shut(old, M.CLOSE_REPLACED))
        line = Line(ws=ws, device=device, screen=screen, role=d["role"], label=label, lanes=lanes)
        self.lines[screen] = line
        line.writer = asyncio.get_running_loop().create_task(self._write(line))
        welcome = {"proto": M.PROTO, "boot": self.boot, "version": self.version,
                   "you": {"screen": screen, "role": line.role, "lanes": sorted(lanes),
                           "device": {"id": device.id, "name": device.name}},
                   "limits": {"max_bytes": M.MAX_BYTES, "deliver_timeout_s": self.timing.deliver_s,
                              "beat_after_s": self.timing.beat_s, "silence_s": 60},
                   "tools": self.tool_list(), "presence": self.presence(), "focus": self.focus_record()}
        welcome.update(self.welcome_extra(line))
        self.send(line, M.msg("welcome", welcome, re=m["id"]))
        self.presence_changed()
        return line

    def tool_list(self) -> list[dict]:
        mods = sorted((m for m in self.tools.values() if m.tab), key=lambda m: (m.tab.order if m.tab else 0, m.id))
        return [{"id": m.id, "title": m.title, "tab": {"label": m.tab.label, "order": m.tab.order} if m.tab else None,
                 "sockets": [{"id": g.id, "label": g.label, "kinds": list(g.kinds), "max": g.max} for g in m.sockets]}
                for m in mods]

    async def _read(self, line: Line) -> None:
        while True:
            raw = await line.ws.receive()
            if raw.get("type") != "websocket.receive":
                return
            text = raw.get("text")
            if text is None:
                await self._strike(line, None, "Text frames only")
                continue
            if len(text.encode()) > M.MAX_BYTES:
                await self.shut(line, M.CLOSE_TOO_BIG)
                return
            if not line.bucket.take():
                await self.shut(line, M.CLOSE_RATE)
                return
            try:
                m = M.parse(text)
            except M.ProtocolError as e:
                await self._strike(line, None, str(e))
                continue
            await self.dispatch(line, m)

    async def dispatch(self, line: Line, m: dict) -> None:
        t = m["t"]
        try:
            handler = self.handlers.get(t)
            if handler is None and "." in t and self.fallback is not None:
                handler = self.fallback
            if handler is None:
                raise M.ProtocolError(f"Unknown message {t}")
            await handler(line, m)
        except M.ProtocolError as e:
            await self._strike(line, m["id"], str(e))
        except M.Refused as e:
            self.send(line, M.error(e.code, e.text, re=m["id"]))
        except Invalid as e:
            self.send(line, M.error("invalid", e.text, re=m["id"], field=e.field))
        except Exception:
            self.send(line, M.error("internal", "Something went wrong", re=m["id"]))

    async def _strike(self, line: Line, re: str | None, text: str) -> None:
        line.strikes += 1
        self.send(line, M.error("protocol", text, re=re))
        if line.strikes >= M.STRIKES:
            await self.shut(line, M.CLOSE_PROTOCOL)

    def _drop(self, line: Line) -> None:
        line.closed = True
        if line.writer is not None:
            line.writer.cancel()
        if self.lines.get(line.screen) is line:
            del self.lines[line.screen]
        for cb in self.on_close:
            cb(line)
        if self.focus_line is line:
            others = [x for x in self.lines.values() if x.role == "workspace" and x.tool is not None]
            self.focus_line = max(others, key=lambda x: x.since, default=None)
            self._focus_changed()
        self.presence_changed()

    # ---------------------------------------------------------------- built-in messages
    @staticmethod
    def require(line: Line, *roles: str) -> None:
        if line.role not in roles:
            raise M.ProtocolError("Not allowed from this screen")

    def _lanes(self, lanes: Any) -> set[str]:
        known = set(M.CORE_LANES) | set(self.lane_roles)
        if not isinstance(lanes, list) or not all(isinstance(x, str) and x in known for x in lanes):
            raise Invalid("lanes", "Unknown lane")
        return set(lanes)

    async def _sub(self, line: Line, m: dict) -> None:
        line.lanes |= self._lanes(m["d"].get("lanes"))

    async def _unsub(self, line: Line, m: dict) -> None:
        line.lanes -= self._lanes(m["d"].get("lanes"))

    async def _focus(self, line: Line, m: dict) -> None:
        self.require(line, "workspace")
        tool = m["d"].get("tool")
        if tool is not None and (tool not in self.tools or self.tools[tool].tab is None):
            raise Invalid("tool", "Unknown tool")
        line.tool, self.focus_line = tool, line
        self._focus_changed()

    async def _declare(self, line: Line, m: dict) -> None:
        self.require(line, "workspace")
        d = m["d"]
        mod = self.tools.get(d.get("tool", ""))
        if mod is None or not mod.sockets:
            raise Invalid("tool", "That tool takes no media")
        groups = {g.id: g for g in mod.sockets}
        socks, mode, primary = d.get("sockets"), d.get("mode"), d.get("primary")
        if not isinstance(socks, list) or len(socks) > 64:
            raise Invalid("sockets", "sockets must be a list")
        clean, counts = [], Counter[str]()
        for s in socks:
            ok = (isinstance(s, dict) and isinstance(s.get("id"), str) and M.ID.match(s["id"])
                  and s.get("group") in groups and isinstance(s.get("label"), str) and len(s["label"]) <= 60
                  and isinstance(s.get("filled"), bool) and isinstance(s.get("accepts"), list) and s["accepts"]
                  and set(s["accepts"]) <= set(groups[s["group"]].kinds))
            if not ok or any(c["id"] == s["id"] for c in clean):
                raise Invalid("sockets", "A socket does not match the tool's declaration")
            counts[s["group"]] += 1
            if counts[s["group"]] > groups[s["group"]].max:
                raise Invalid("sockets", f"Too many {groups[s['group']].label} sockets")
            clean.append({k: s[k] for k in ("id", "group", "label", "accepts", "filled")})
        if mode is not None and (not isinstance(mode, str) or len(mode) > 20):
            raise Invalid("mode", "mode must be short text")
        if primary is not None and primary not in groups and all(c["id"] != primary for c in clean):
            raise Invalid("primary", "primary must name a socket or group")
        line.sockets[mod.id] = {"mode": mode, "primary": primary, "sockets": clean}
        if self.focus_line is line and line.tool == mod.id:
            self._focus_changed()
