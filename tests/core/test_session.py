"""The session: while a window is connected, the hub holds the prompt, the assistant's draft, the reference boxes,
the finished jobs and the chat for it, in memory. When the last window has been gone for the grace, all of it is
forgotten; a reload inside the grace keeps everything. Nothing of a session is ever on disk."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from hub.core.api import Ctx, Invalid, JobPlan, Module, Tab
from hub.core.session import Session
from hub.modules.generate_image.manifest import MODULE as GENERATE
from tests.core.fake_lane import FakeLane
from tests.core.harness import Hub, own_modules, start_hub
from tests.fakes.fake_probes import FakeProbes

ENDED: list[dict] = []


async def test_the_grace_runs_only_while_no_window_is_connected() -> None:
    lines, ended = [0], []
    s = Session(lambda: lines[0], lambda: ended.append(1), grace_s=0.05)
    s.presence_changed()                       # nothing connected yet: no session, nothing to end
    await asyncio.sleep(0.1)
    assert ended == [] and s.open is False
    lines[0] = 1
    s.presence_changed()                       # a window: the session is open
    lines[0] = 0
    s.presence_changed()                       # gone: the grace starts
    lines[0] = 1
    s.presence_changed()                       # back inside it (a reload): nothing ends
    await asyncio.sleep(0.1)
    assert ended == [] and s.open is True
    lines[0] = 0
    s.presence_changed()
    s.presence_changed()                       # told twice: one timer
    await asyncio.sleep(0.1)
    assert ended == [1] and s.open is False
    s.presence_changed()                       # still nobody: nothing more happens
    await asyncio.sleep(0.1)
    assert ended == [1]
    s.close()


def build(params: dict, ctx: Ctx) -> JobPlan:
    if not params.get("prompt"):
        raise Invalid("prompt", "Write a prompt")
    return JobPlan(lane_kind="image", model="flux", tasks=({"seed": 1},), summary={"model": "Flux"})


async def on_ended(ctx: Ctx, data: dict) -> None:
    ENDED.append(data)


GEN = Module(id="gen", title="Gen", tab=Tab("Gen", 10), jobs={"image": build}, listens={"session.ended": on_ended})


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    ENDED.clear()
    probes = FakeProbes()
    lane = FakeLane(tmp_path / "data" / "outputs", probes)
    h = await start_hub(tmp_path / "data", lanes=[lane], modules=[*own_modules(), GEN, GENERATE], probes=probes)
    yield h
    await h.close()


async def draft(hub: Hub, cookie: str) -> dict:
    return (await hub.http("GET", "/api/generate-image/draft", cookie)).json()


async def test_the_session_is_forgotten_when_the_last_window_has_been_gone_for_the_grace(hub: Hub) -> None:
    cookie = hub.pair()
    w = await hub.screen(cookie, "workspace", "w")
    body = {"model": "flux", "prompt": "a grey cat asleep under an apple tree", "aspect": "auto", "size": 1,
            "images": 1, "lorasByModel": {"flux": [{"id": "flux/a.safetensors", "strength": 0.8}]},
            "advancedByModel": {}, "references": [{"id": "out/2026-10-09/r.png", "w": 8, "h": 8}], "selected": "x",
            "draft": "a grey cat, the assistant's take"}
    assert (await hub.http("PUT", "/api/generate-image/draft", cookie, json_body=body)).status == 200
    assert (await draft(hub, cookie))["prompt"] == body["prompt"]
    assert (await draft(hub, cookie))["draft"] == body["draft"]
    hub.core.store.flush()
    on_disk = json.loads((hub.data / "generate-image" / "draft.json").read_text())
    assert not {"prompt", "draft", "references", "selected"} & set(on_disk)
    assert on_disk["model"] == "flux" and on_disk["lorasByModel"] == body["lorasByModel"], "settings stay"
    assert "grey cat" not in (hub.data / "generate-image" / "draft.json").read_text()
    await w.send("job.submit", {"tool": "gen", "kind": "image", "params": {"prompt": "a cat"}}, id="r1")
    job_id = (await w.recv(where=lambda m: m.get("re") == "r1"))["d"]["job"]
    await w.recv("job", where=lambda x: x["d"]["state"] == "done", timeout=5)
    assert hub.core.book.get(job_id) is not None

    session_id = w.welcome["session"]
    assert len(session_id) == 16
    await w.close()                                            # the window goes; a reload comes back in time
    await asyncio.sleep(0.15)
    w2 = await hub.screen(cookie, "workspace", "w2")
    await asyncio.sleep(0.5)
    assert ENDED == [] and (await draft(hub, cookie))["prompt"] == body["prompt"], "a reload keeps the session"
    assert w2.welcome["session"] == session_id, "the same session: the window keeps what it has"
    assert hub.core.book.get(job_id) is not None

    await w2.close()                                           # gone for longer than the grace
    for _ in range(40):
        if ENDED:
            break
        await asyncio.sleep(0.05)
    assert ENDED == [{}]
    fresh = await draft(hub, cookie)
    assert not {"prompt", "draft", "references", "selected"} & set(fresh)
    assert fresh["model"] == "flux" and fresh["lorasByModel"] == body["lorasByModel"], "the saved settings stay"
    assert hub.core.book.get(job_id) is None, "finished jobs are gone with the session"
    w3 = await hub.screen(cookie, "workspace", "w3")
    hello = w3.welcome
    assert hello["jobs"] == [], "a new window starts from nothing"
    assert hello["session"] != session_id, "a new session: a window that kept an old prompt drops it"
    assert not list(hub.data.rglob("*.log")) and not (hub.data / "generate-image" / "session.json").exists()
    await w3.close()


async def test_a_job_that_finishes_with_nobody_there_is_not_kept(hub: Hub) -> None:
    """A job still running when the session ends, or one sent by Open WebUI with no window open at all, is
    forgotten the moment it finishes: there is nobody it is kept for."""
    cookie = hub.pair()
    w = await hub.screen(cookie, "workspace", "w")
    await w.send("job.submit", {"tool": "gen", "kind": "image", "params": {"prompt": "slow cat"}}, id="r1")
    job_id = (await w.recv(where=lambda m: m.get("re") == "r1"))["d"]["job"]
    await w.close()
    for _ in range(40):
        if ENDED:
            break
        await asyncio.sleep(0.05)
    assert ENDED == [{}]
    for _ in range(100):
        job = hub.core.book.get(job_id)
        if job is None or job.state in ("done", "failed"):
            break
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.1)
    assert hub.core.book.get(job_id) is None, "finished after the session ended: gone at once"
    direct = hub.core.book.submit("gen.image", {"prompt": "from the tool server"})
    for _ in range(100):
        if direct.state in ("done", "failed"):
            break
        await asyncio.sleep(0.05)
    assert direct.state == "done" and direct.outputs, "the caller still holds the job and sees its result"
    await asyncio.sleep(0.1)
    assert hub.core.book.get(direct.id) is None and hub.core.session.open is False
    w2 = await hub.screen(cookie, "workspace", "w2")
    assert w2.welcome["jobs"] == []
    await w2.close()
