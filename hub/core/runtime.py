"""Core assembly: every service, the module wiring and the ASGI app. One event loop, no locks."""
from __future__ import annotations

import asyncio
import copy
import os
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import BaseRoute

from hub import VERSION
from hub.core import clipthumb
from hub.core.admin import NetworkAdmin
from hub.core.api import Invalid, JobLane, Module
from hub.core.apply import apply
from hub.core.bus import Bus
from hub.core.context import Events, ModuleCtx, NoEngine
from hub.core.delivery import Delivery
from hub.core.devices import Devices
from hub.core.dispatch import Dispatcher
from hub.core.features import Tool, tools_of
from hub.core.fileroutes import file_routes
from hub.core.files import Files
from hub.core.guard import Gate, Guard, http_route, ws_route
from hub.core.jobs import JobBook
from hub.core.line import Line, Timing
from hub.core.mcp import DEFAULT as MCP_DEFAULT
from hub.core.mcp import McpAccess, McpEndpoint
from hub.core.messages import CLOSE_UNPAIRED
from hub.core.routes import core_routes, install_handlers
from hub.core.session import Session
from hub.core.store import Store
from hub.core.vram import Vram
from hub.core.web import web_routes
from hub.settings import (
    VIDEO_TIERS_MAX,
    SettingsError,
    characters_root,
    drive_root,
    host_entry,
    hosts,
    profile_choices,
    save,
    storyboards_folder,
    video_profile_choices,
)
from hub.settings_edit import ui_patch

DIST = Path(__file__).resolve().parents[2] / "web" / "dist"



def restart_service() -> None:
    """Ask systemd to restart the hub (it comes back on the saved port). Never run in tests."""
    try:
        subprocess.Popen(["systemctl", "--user", "restart", "hub.service"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        print("hub: the restart did not work; run: systemctl --user restart hub", file=sys.stderr)

class Core:
    def __init__(self, data_dir: Path, settings: dict, probes: Any, *, port: int, bound: list[str],
                 missing: list[str] | None = None, timing: Timing | None = None, dist: Path = DIST) -> None:
        self.data_dir, self.settings, self.port, self.dist = data_dir, settings, port, dist
        self.boot, self.started = secrets.token_hex(8), time.time()
        self.timing = timing or Timing()
        self.store, self.events = Store(), Events()
        self._cards: list[dict] | None = None
        self.modules: list[Module] = []
        self.ctxs: dict[str, ModuleCtx] = {}
        self.handlers: dict[str, tuple[Any, ModuleCtx]] = {}
        self.devices = Devices(data_dir, on_change=self._devices_changed)
        self.bus = Bus(self.devices, self.boot, VERSION, self.timing)
        self.files = Files(data_dir, drive_root(settings), characters_root(settings))
        clipthumb.engine_root[0] = str(settings["engine"].get("root") or "")   # where the engine's ffmpeg is
        self.files.set_storyboards(storyboards_folder(settings))
        self.delivery = Delivery(self.bus, self.files)
        self.vram = Vram(probes, lambda: self.settings, self.bus)
        self.book = JobBook(self.bus, lambda: self.settings, self.events.emit)
        self.dispatch = Dispatcher(self.book, self.vram, self.bus, self.files)
        self.mcp = McpAccess(self.store.doc(data_dir / "core" / "mcp.json", MCP_DEFAULT), on_change=self.cards_changed)
        # The tool server answers on every address the hub listens on (Open WebUI may run in a container, whose
        # calls arrive from the Docker bridge, not from 127.0.0.1); the key is what admits a caller.
        self.mcp.endpoints = [f"http://{host_entry(a, port)}/mcp" for a in bound]
        self.gate = Gate(self.devices, hosts(settings, port))
        self.network = NetworkAdmin(self.devices, lambda: self.settings, port, bound, missing or [], self.change_port)
        self.restart_service: Callable[[], None] = restart_service
        self.engine: Any = NoEngine()
        self.tools: dict[str, tuple[Tool, Any]] = {}
        self.services: dict[str, Callable[..., Any]] = {}   # what a module offers others by name (ctx.offer, 027)
        self.bus.engines = self.vram.engines
        self.bus.welcome_extra = self._welcome
        self.bus.on_presence.append(self.cards_changed)
        self.session = Session(lambda: len(self.bus.lines), self._session_ended, self.timing.session_grace_s)
        self.bus.on_presence.append(self.session.presence_changed)
        self.book.session_open = lambda: self.session.open
        self.vram.on_change.append(self.cards_changed)
        install_handlers(self)

    def _session_ended(self) -> None:
        """The last window has been gone for the grace: forget everything held for the session."""
        self.book.forget_finished()
        self.events.emit("session.ended", {})

    # ---------------------------------------------------------------- wiring
    def add_engine(self, lane: JobLane, engine: Any) -> None:
        self.dispatch.add_lane(lane)
        if isinstance(self.engine, NoEngine):
            self.engine = engine

    def load_modules(self, mods: list[Module]) -> None:
        for mod in mods:
            ctx = ModuleCtx(self, mod.id, self.data_dir / mod.id, self.settings["modules"].get(mod.id, {}), self.store)
            self.modules.append(mod)
            self.ctxs[mod.id] = ctx
            self.bus.tools[mod.id] = mod
            for lane in mod.lanes:
                self.bus.lane_roles[f"{mod.id}.{lane}"] = ("workspace", *mod.screens)
            for name, fn in mod.handlers.items():
                self.handlers[name] = (fn, ctx)
            for kind, build in mod.jobs.items():
                self.book.kinds[f"{mod.id}.{kind}"] = lambda params, build=build, ctx=ctx: build(params, ctx)
            for event, fn in mod.listens.items():
                self.events.listen(event, fn, ctx)
            for tool in tools_of(mod):
                self.tools[tool.name] = (tool, ctx)

    def app(self) -> Guard:
        self.mcp_endpoint = McpEndpoint(self.gate, self.mcp, self.tools)
        def changed(what: str) -> None:              # what the media module's own `_changed` sends
            self.bus.publish("media.changed", "media.changed", {"what": what})

        routes: list[BaseRoute] = [*web_routes(self.gate, self.devices, self.dist),
                                   *file_routes(self.gate, self.files, changed),
                                   *core_routes(self), self.mcp_endpoint.route(),
                                   ws_route(self.gate, "/bus", self.bus.serve, "screen", unpaired_close=CLOSE_UNPAIRED)]
        for mod in self.modules:
            ctx = self.ctxs[mod.id]
            for r in mod.routes:
                async def call(request: Request, r: Any = r, ctx: ModuleCtx = ctx) -> Any:
                    return await r.fn(ctx, request)
                routes.append(http_route(self.gate, f"/api/{mod.id}{r.path}", r.method, call, r.auth,
                                         r.body_limit, body="any"))
        return Guard(Starlette(routes=routes), self.gate)

    # ---------------------------------------------------------------- views
    def settings_msg(self) -> dict:
        v = self.settings["vram"]
        return {"diagnostics": self.settings["diagnostics"],
                "vram": {"idle_unload": v["idle_unload"], "idle_minutes": v["idle_minutes"],
                         "clip_previews": v["clip_previews"]}}

    def settings_view(self) -> dict:
        eng = self.settings["engine"]
        ok = os.path.isdir(eng["root"]) and os.path.isfile(eng["python"]) and os.access(eng["python"], os.X_OK)
        gpus = [g for g in self.vram.snapshot()["gpus"] if not g["unknown"]]
        return {**self.settings_msg(), "version": VERSION, "started": self.started, "data": str(self.data_dir),
                "drive": str(self.files.roots.get("drive") or ""),
                "characters": str(self.files.roots.get("chars") or ""),
                "engine": {"root": eng["root"], "python": eng["python"], "ok": ok, "profile": eng["profile"],
                           "profiles": profile_choices(), "profile_video": eng["profile_video"],
                           "video_profiles": video_profile_choices()},
                "image_model_folders": list(eng["model_folders"]), "helper_folders": list(eng["helper_folders"]),
                "lora_folders": list(self.settings["modules"].get("loras", {}).get("folders", [])),
                "video_lora_folders": list(self.settings["modules"].get("director", {}).get("video_lora_folders", [])),
                "video_tiers": self._video_tiers(), "video_tiers_max": VIDEO_TIERS_MAX,
                "gpus": [{"name": g["name"], "total_mb": g["total_mb"]} for g in gpus]}

    def _video_tiers(self) -> dict:
        """The engine's video tier names (its catalog, as last read) and the ones the size menu offers: the catalog's
        first ones, or the `video_tiers` names it reports (none of them: its first ones, as the screen does)."""
        cached = getattr(self.engine, "cached_catalog", None)
        cat = cached() if cached is not None else None
        names = list(dict.fromkeys(t["name"] for m in (cat or {}).get("models", []) if m.get("kind") == "video"
                                   for t in (m.get("video") or {}).get("tiers") or []))
        want = self.settings["modules"]["generate-image"]["video_tiers"]
        offered = names[:want] if isinstance(want, int) else [n for n in names if n in want]
        return {"names": names, "offered": offered or names[:VIDEO_TIERS_MAX]}

    def change_port(self, port: Any) -> None:
        """The port changed in Settings: check it is free on every address, save, restart on it."""
        if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
            raise Invalid("port", "Use a port from 1024 to 65535")
        if port == self.network.port:
            raise Invalid("port", f"The hub already uses port {port}")
        for addr in self.network.bound:
            with socket.socket(socket.AF_INET6 if ":" in addr else socket.AF_INET, socket.SOCK_STREAM) as probe:
                try:
                    probe.bind((addr, port))
                except OSError:
                    raise Invalid("port", f"Port {port} is already in use on {addr}") from None
        new = copy.deepcopy(self.settings)
        new["server"]["port"] = port
        save(self.data_dir, new)
        self.settings = new
        (self.data_dir / "run").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "run" / "restart").touch()
        asyncio.get_running_loop().call_later(1.0, self.restart_service)

    def restart(self) -> None:
        """Restart pressed in Settings: the hub comes back on the same addresses in a few seconds."""
        (self.data_dir / "run").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "run" / "restart").touch()
        asyncio.get_running_loop().call_later(0.5, self.restart_service)

    async def update_settings(self, changes: Any) -> None:
        """Check, save, apply live (media roots, engine, LoRA folders), then tell every window."""
        roots = {"temp": str(self.data_dir), "drive": str(self.files.roots.get("drive") or ""),
                 "characters": str(self.files.roots.get("chars") or "")}
        try:
            new = ui_patch(self.settings, changes, roots)
        except SettingsError as e:
            raise Invalid(e.field, e.text) from None
        save(self.data_dir, new)
        old, self.settings = self.settings, new
        await apply(self, old)
        self.bus.publish("settings", "settings", self.settings_msg(), key="settings")
        self.vram.rearm()
        self.cards_changed()

    def cards(self) -> list[dict]:
        out = []
        for mod in self.modules:
            if mod.card is None:
                continue
            try:
                state = mod.card.state(self.ctxs[mod.id])
                summary, status = state.summary, state.status
            except Exception:
                summary, status = "Unavailable", "error"
            out.append({"module": mod.id, "title": mod.card.title, "order": mod.card.order,
                        "summary": summary, "status": status})
        return sorted(out, key=lambda c: (c["order"], c["module"]))

    def cards_changed(self) -> None:
        cards = self.cards()
        if cards != self._cards:
            self._cards = cards
            self.bus.publish("settings", "cards", cards, key="cards")

    def _devices_changed(self) -> None:
        self.bus.presence_changed()

    def _welcome(self, line: Line) -> dict:
        self.vram.read(max_age=5.0)
        self.session.presence_changed()                   # this window opens the session if none is open
        return {"session": self.session.id, "jobs": self.book.snapshot(), "gpu": self.vram.snapshot(),
                "settings": self.settings_msg(), "cards": self.cards()}

    # ---------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        self.vram.read()  # the boot reading (shared with an engine lane's registration)
        self.vram.publish()
        for mod in self.modules:
            if mod.start is not None:
                try:
                    await mod.start(self.ctxs[mod.id])
                except Exception as e:
                    print(f"hub: module {mod.id} did not start: {e}", file=sys.stderr)
        self.cards_changed()

    async def stop(self, restart: bool) -> None:
        """Screens hear `going_off`, then 4001 (restart) or 4000 (off)."""
        await self.bus.going_off(restart)
        self.session.close()
        for mod in reversed(self.modules):
            if mod.stop is not None:
                try:
                    await asyncio.wait_for(mod.stop(self.ctxs[mod.id]), 5)
                except Exception as e:
                    why = "did not stop within 5 s" if isinstance(e, TimeoutError) else f"did not stop cleanly: {e}"
                    print(f"hub: module {mod.id} {why}", file=sys.stderr)
        for lane in list(self.book.lanes.values()):
            try:
                await asyncio.wait_for(lane.stop() if lane.busy() else lane.release("shutdown"), 10)
            except Exception:
                pass
        self.dispatch.close()
        self.store.flush()

