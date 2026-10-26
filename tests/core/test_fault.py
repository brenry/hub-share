"""Faults: a frozen screen, a slow reader, cross-site simple POSTs on every mutating route, a lane crash."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from pathlib import Path

import pytest
from starlette.routing import Route

from hub.core import messages as M
from hub.core.api import Ctx, JobPlan, Module, Tab
from hub.core.bus import Bus
from hub.core.devices import Devices
from hub.core.line import Line, Outbox
from tests.core.fake_lane import FakeLane
from tests.core.harness import own_modules, start_hub
from tests.fakes.fake_probes import FakeProbes


def frame(text: str) -> bytes:
    """One masked client text frame."""
    data, mask = text.encode(), os.urandom(4)
    head = bytes([0x81, 0x80 | len(data)]) if len(data) < 126 else bytes([0x81, 0xFE]) + len(data).to_bytes(2, "big")
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data))


async def test_a_frozen_screen_goes_off_after_the_ping_timeout_and_nothing_is_logged(
        tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    hub = await start_hub(tmp_path / "data", ping_s=0.3)
    try:
        cookie = hub.pair()
        w = await hub.screen(cookie, "workspace", "w")
        reader, writer = await asyncio.open_connection("127.0.0.1", hub.port)
        key = base64.b64encode(os.urandom(16)).decode()
        writer.write((f"GET /bus HTTP/1.1\r\nHost: 127.0.0.1:{hub.port}\r\nUpgrade: websocket\r\n"
                      f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                      f"Origin: {hub.origin}\r\nCookie: hub_screen={cookie}\r\n\r\n").encode())
        assert b" 101 " in await reader.readuntil(b"\r\n\r\n")
        writer.write(frame(json.dumps({"t": "hello", "d": {"proto": 1, "role": "media", "screen": "frozen"}})))
        await writer.drain()
        await w.recv("presence", where=lambda m: m["d"]["screens"]["media"] == 1)
        # never read again and never answer a ping: like a SIGSTOPped window
        await w.recv("presence", where=lambda m: m["d"]["screens"]["media"] == 0, timeout=5)
        writer.close()
    finally:
        await hub.close()
    out, err = capfd.readouterr()
    assert err == "" and out.strip() == "hub stopped"


class FakeWs:
    def __init__(self) -> None:
        self.closed_with: int | None = None

    async def close(self, code: int) -> None:
        self.closed_with = code

    async def send_text(self, text: str) -> None:
        await asyncio.sleep(10)


async def test_a_slow_reader_is_closed_with_4030(tmp_path: Path) -> None:
    bus = Bus(Devices(tmp_path), "boot", "0")
    ws = FakeWs()
    line = Line(ws=ws, device=None, screen="s", role="media", label="", lanes={"presence"},  # type: ignore[arg-type]
                out=Outbox(limit=3))
    for i in range(3):
        bus.send(line, M.msg("x", {"i": i}))
    bus.send(line, M.msg("presence", {"n": 1}), key="presence")
    bus.send(line, M.msg("presence", {"n": 2}), key="presence")
    assert ws.closed_with is None
    bus.send(line, M.msg("x", {"i": 99}))
    await asyncio.sleep(0.01)
    assert ws.closed_with == M.CLOSE_SLOW


def build(params: dict, ctx: Ctx) -> JobPlan:
    return JobPlan("image", "flux", ({},), {"model": "Flux"})


GEN = Module(id="gen", title="Gen", tab=Tab("Gen", 10), jobs={"image": build})


async def test_every_mutating_route_refuses_a_simple_cross_site_post(tmp_path: Path) -> None:
    hub = await start_hub(tmp_path / "data", modules="discover")
    try:
        cookie = hub.pair()
        routes = [r for r in hub.server.config.app.app.routes if isinstance(r, Route)]  # type: ignore[attr-defined]
        checked = 0
        for r in routes:
            for method in sorted((r.methods or set()) & {"POST", "PUT", "PATCH", "DELETE"}):
                path = re.sub(r"\{[^}]+\}", "x", r.path)
                res = await hub.http(method, path, cookie=cookie, body="a=b",
                                     headers={"Content-Type": "text/plain", "Origin": "http://evil.example"})
                assert res.status >= 400 and res.status != 500, (method, path, res.status)
                res = await hub.http(method, path, cookie=cookie, body="a=b", headers={"Content-Type": "text/plain"})
                assert res.status >= 400 and res.status != 500, (method, path, res.status)
                checked += 1
        assert checked >= 8
    finally:
        await hub.close()


class CrashOnce(FakeLane):
    crashed = False

    async def run(self, job, emit) -> None:  # type: ignore[no-untyped-def]
        if not self.crashed:
            self.crashed = True
            emit("task", {"task": 1, "of": 1})
            raise RuntimeError("Engine stopped unexpectedly (signal SIGSEGV)\nTraceback (most recent call last): ...")
        await super().run(job, emit)


async def test_a_lane_crash_fails_the_job_and_the_queue_continues(tmp_path: Path) -> None:
    probes = FakeProbes()
    lane = CrashOnce(tmp_path / "data" / "outputs", probes)
    hub = await start_hub(tmp_path / "data", lanes=[lane], modules=[*own_modules(), GEN], probes=probes)
    try:
        w = await hub.screen(hub.pair(), "workspace", "w")
        for rid in ("a", "b"):
            await w.send("job.submit", {"tool": "gen", "kind": "image", "params": {}}, id=rid)
        first = (await w.recv("reply", where=lambda m: m["re"] == "a"))["d"]["job"]
        second = (await w.recv("reply", where=lambda m: m["re"] == "b"))["d"]["job"]
        failed = await w.recv("job", where=lambda m: m["d"]["id"] == first and m["d"]["state"] == "failed")
        assert failed["d"]["error"] == {"text": "Engine stopped unexpectedly (signal SIGSEGV)"}
        await w.recv("job", where=lambda m: m["d"]["id"] == second and m["d"]["state"] == "done", timeout=5)
    finally:
        await hub.close()
