"""Core HTTP routes (`/api/settings`, `/api/cards`) and the bus messages for jobs, GPUs and modules."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.requests import Request
from starlette.routing import BaseRoute

from hub.core import messages as M
from hub.core.guard import http_route
from hub.core.line import Line

if TYPE_CHECKING:
    from hub.core.runtime import Core


def core_routes(core: Core) -> list[BaseRoute]:
    async def get_settings(request: Request) -> dict:
        return core.settings_view()

    async def patch_settings(request: Request) -> dict:
        await core.update_settings(await request.json())
        return core.settings_view()

    async def get_cards(request: Request) -> list:
        return core.cards()

    async def restart(request: Request) -> dict:
        core.restart()
        return {"restarting": True}

    return [http_route(core.gate, "/api/settings", "GET", get_settings, "screen"),
            http_route(core.gate, "/api/settings", "PATCH", patch_settings, "screen"),
            http_route(core.gate, "/api/settings/restart", "POST", restart, "screen"),
            http_route(core.gate, "/api/cards", "GET", get_cards, "screen")]


def _job_id(m: dict) -> Any:
    return m["d"].get("job")


def install_handlers(core: Core) -> None:
    bus, book = core.bus, core.book

    def reply(line: Line, m: dict, d: dict) -> None:
        if m["id"] is not None:
            bus.send(line, M.msg("reply", d, re=m["id"]))

    async def submit(line: Line, m: dict) -> None:
        bus.require(line, "workspace", "media")   # Media's Generate button queues the saved draft too
        d = m["d"]
        tool, kind = d.get("tool"), d.get("kind")
        if not isinstance(tool, str) or not isinstance(kind, str):
            raise M.Refused("invalid", "Say which tool and job kind")
        job = book.submit(f"{tool}.{kind}", d.get("params"))
        reply(line, m, {"job": job.id, "state": job.state, "position": book.record(book.entries[job.id])["position"]})

    async def cancel(line: Line, m: dict) -> None:
        bus.require(line, "workspace")
        job = book.cancel(_job_id(m)) if isinstance(_job_id(m), str) else None
        if job is None:
            raise M.Refused("not_found", "That job is gone")
        reply(line, m, {"job": job.id, "state": job.state})

    async def clear(line: Line, m: dict) -> None:
        bus.require(line, "workspace")
        lane = m["d"].get("lane")
        reply(line, m, {"cleared": book.clear(lane if isinstance(lane, str) else None)})

    def simple(action: Any) -> Any:
        async def handler(line: Line, m: dict) -> None:
            bus.require(line, "workspace")
            action(_job_id(m))
            reply(line, m, {"job": _job_id(m)})
        return handler

    async def gpu_refresh(line: Line, m: dict) -> None:
        core.vram.read(max_age=1.0)
        core.vram.publish()

    async def gpu_plan(line: Line, m: dict) -> None:
        bus.require(line, "workspace")
        model = m["d"].get("model")
        lane = next((x for x in book.lanes.values() if x.kind == "image"), None)
        if not isinstance(model, str) or lane is None:
            raise M.Refused("unavailable", "Engine is offline")
        plan = core.vram.plan(lane, model, model)
        reply(line, m, {"light": plan.light, "text": plan.text})

    async def gpu_release(line: Line, m: dict) -> None:
        """Unload one GPU's model (`lane`), or, without a lane (Media's clear-cache), every GPU that is idle."""
        bus.require(line, "workspace", "media")
        lane_id = m["d"].get("lane")
        if lane_id:
            lane = core.vram.lanes.get(lane_id)
            if lane is None or lane.busy():
                raise M.Refused("forbidden", "That GPU is busy")
            ids = [lane.id]
        else:
            ids = [lane.id for lane in core.vram.lanes.values() if not lane.busy()]
            if not ids:
                raise M.Refused("forbidden", "Every GPU is busy")
        reply(line, m, {"ok": await core.vram.release(ids, "owner")})

    async def engine_start(line: Line, m: dict) -> None:
        bus.require(line, "workspace")
        for lane in book.lanes.values():
            lane.reset()
        core.vram.changed()
        reply(line, m, {"ok": True})

    async def module_call(line: Line, m: dict) -> None:
        entry = core.handlers.get(m["t"])
        if entry is None:
            raise M.ProtocolError(f"Unknown message {m['t']}")
        fn, ctx = entry
        result = await fn(ctx, {"screen": line.screen, "role": line.role, "device": line.device.id}, m["d"])
        reply(line, m, result if isinstance(result, dict) else {})

    bus.handlers.update({
        "job.submit": submit, "job.cancel": cancel, "job.clear": clear,
        "job.dismiss": simple(book.dismiss),
        "gpu.refresh": gpu_refresh, "gpu.plan": gpu_plan, "gpu.release": gpu_release, "engine.start": engine_start,
    })
    bus.fallback = module_call
