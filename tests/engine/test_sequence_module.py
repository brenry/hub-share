"""The Edit Video module (`hub/modules/sequence/`): its declarations, its four tools with their exact names, labels and
schemas, every route with its shape and its `sequence.changed` message, the body limit of PUT /one, the newest clip
Generate made (`add_last_clip`), and the join job: one `sequence.join` job whose one task is a join request
(`kind` "join").
The worker's join is not run here (a fake lane takes the job)."""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

import pytest

from hub.core.api import NO_MODEL, Invalid
from hub.core.features import tools_of
from hub.core.files import Files
from hub.core.registry import discover, validate
from hub.modules.media import manifest as media
from hub.modules.sequence import join, last, manifest, routes
from tests.core.fake_lane import FakeLane
from tests.core.harness import Hub, own_modules, start_hub
from tests.core.test_mcp import call, result, rpc
from tests.engine.helpers import FakeCtx, FakeEngine
from tests.engine.sequence_kit import DAY, clip, seq_path, two, whole
from tests.fakes.fake_probes import FakeProbes

ARG = {"type": "object", "additionalProperties": False, "required": ["sequence"],
       "properties": {"sequence": {"type": "string", "minLength": 1}}}
TOOLS = [
    ("list_sequences", "Sequences by name, with the number of items and the seconds of each.",
     {"type": "object", "additionalProperties": False, "properties": {}}),
    ("list_sequence_clips", "Items of one sequence by track in play order: place, clip or sound id, in and out in "
                            "seconds, seconds kept, and where a track 2 item starts.", ARG),
    ("add_last_clip", "Adds the newest clip Generate Image made to the end of a sequence's track 1, whole; a new name "
                      "starts a new sequence.", ARG),
    ("join_sequence", "Queues one file of a sequence, cut at in and out points: an MP4 into Clips when track 1 holds "
                      "clips, else a WAV into Sounds.", ARG),
]
ONLY = ("A sequence holds item ids, order, in and out points, where track 2's items start and their level, fades "
        "and duck only")


async def open_hub(tmp_path: Path, settings: dict | None = None) -> Hub:
    probes = FakeProbes()
    hub = await start_hub(tmp_path / "data", lanes=[FakeLane(tmp_path / "data" / "outputs", probes)],
                          modules=[*own_modules(), media.MODULE, manifest.MODULE], probes=probes, settings=settings)
    hub.core.mcp.set_enabled(True)
    return hub


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    h = await open_hub(tmp_path)
    last._last.clear()
    yield h
    last._last.clear()
    await h.close()


def test_the_declarations() -> None:
    validate([manifest.MODULE])
    mods, errors = discover()
    assert "sequence" in {m.id for m in mods} and errors == [], "on by default"
    m = manifest.MODULE
    assert (m.id, m.title, m.tab.label, m.tab.order, m.lanes) == ("sequence", "Edit Video", "Edit Video", 20,
                                                                  ("changed",))
    assert (m.screen, m.sockets, m.card, dict(m.jobs)) == (None, (), None, {"join": join.plan})
    assert dict(m.listens) == {"job.finished": last.on_finished, "session.ended": last.on_ended,
                               "media.deleted": routes.on_deleted, "sequence.written": routes.on_written}
    assert [(r.method, r.path, r.auth, r.body_limit) for r in m.routes] == [
        ("GET", "/all", "screen", 65_536), ("GET", "/one", "screen", 65_536), ("POST", "/new", "screen", 65_536),
        ("PUT", "/one", "screen", 131_072), ("POST", "/rename", "screen", 65_536),
        ("POST", "/delete", "screen", 65_536), ("POST", "/join", "screen", 65_536)]


def test_four_tools_with_their_labels_and_schemas() -> None:
    assert [(t.name, t.description, t.input_schema) for t in tools_of(manifest.MODULE)] == TOOLS
    for _name, text, _schema in TOOLS:
        assert len(text) <= 200 and text.endswith(".") and not re.search(r"\b(always|never|must)\b", text, re.I)


def expected_task(hub: Hub, items: list[dict]) -> dict:
    files = hub.core.files
    out = []
    for it in items:
        f = files.clip_facts(it["clip"])
        out.append({"path": os.path.realpath(files.resolve(it["clip"])), "in": it["in"], "out": it["out"],
                    "fps": float(f["fps"]), "w": f["w"], "h": f["h"], "frames": f["frames"], "audio": f["audio"],
                    "sound": False})
    return {"kind": "join", "items": out, "canvas": {"w": out[0]["w"], "h": out[0]["h"], "fps": out[0]["fps"]},
            "audio": [], "crf": 18, "preset": "medium", "out_kind": "mp4",
            "duck": {"threshold": 0.05, "ratio": 6.0, "attack": 50.0, "release": 400.0},
            "lanes": [], "target": None, "solo": None, "length_ms": 0}


def no_times(listing: dict) -> dict:
    return {"sequences": [{k: v for k, v in x.items() if k != "changed"} for x in listing["sequences"]]}


async def test_every_route_its_shape_and_its_message(hub: Hub) -> None:
    files, cookie = hub.core.files, hub.pair()
    w = await hub.screen(cookie, "workspace", "w")
    a, b = clip(files, "101500-123"), clip(files, "101600-456", frames=48, fps=16, w=544, h=960, audio=True)

    async def changed() -> dict:
        return (await w.recv("sequence.changed", timeout=2))["d"]

    made = (await hub.http("POST", "/api/sequence/new", cookie, json_body={"name": " Film "})).json()
    assert made == {"name": "Film", "revision": 0, "tracks": [[], []]}
    assert await changed() == {"name": "Film", "revision": 0}
    again = await hub.http("POST", "/api/sequence/new", cookie, json_body={"name": "Film"})
    assert (again.status, again.json()["text"]) == (400, "A sequence named Film already exists")
    empty = await hub.http("POST", "/api/sequence/join", cookie, json_body={"name": "Film"})
    assert (empty.status, empty.json()["text"]) == (400, "The sequence is empty")
    video = [whole(a), {"clip": b, "in": 8, "out": 40}]
    put = await hub.http("PUT", "/api/sequence/one", cookie,
                         json_body={"name": "Film", "revision": 0, "tracks": two(video)})
    assert put.status == 200, put.json()
    drawn = put.json()
    assert drawn == {"name": "Film", "revision": 1, "tracks": [[
        {**whole(a), "kind": "clip", "id": a, "w": 960, "h": 544, "fps": 24.0, "frames": 124, "seconds": 5.17,
         "kept": 5.17, "audio": False, "url": files.url(a)},
        {"clip": b, "in": 8, "out": 40, "kind": "clip", "id": b, "w": 544, "h": 960, "fps": 16.0, "frames": 48,
         "seconds": 3.0, "kept": 2.0, "audio": True, "url": files.url(b)}], []]}
    assert await changed() == {"name": "Film", "revision": 1}
    stale = await hub.http("PUT", "/api/sequence/one", cookie,
                           json_body={"name": "Film", "revision": 0, "tracks": two([])})
    assert (stale.status, stale.json()["text"]) == (400, "The sequence changed in another window")
    for extra in ({"prompt": "a fox"}, {"model": "any"}, {"video": []}, {"audio": []}):
        bad = await hub.http("PUT", "/api/sequence/one", cookie,
                             json_body={"name": "Film", "revision": 1, "tracks": two([]), **extra})
        assert (bad.status, bad.json()["text"]) == (400, ONLY)
    assert no_times((await hub.http("GET", "/api/sequence/all", cookie)).json()) == {
        "sequences": [{"name": "Film", "clips": 2, "seconds": 7.17}]}
    assert (await hub.http("GET", "/api/sequence/one?name=Film", cookie)).json() == drawn
    nameless = await hub.http("GET", "/api/sequence/one", cookie)
    assert (nameless.status, nameless.json()["text"]) == (400, "Name the sequence")

    assert (await hub.http("GET", f"/files/{seq_path(files, 'Film').relative_to(files.roots['clips'].parent)}",
                           cookie)).status == 404, "no media route serves a sequence's file"
    listed = (await hub.http("GET", "/api/media?root=clips", cookie)).json()
    assert sorted(i["id"] for i in listed["items"]) == [a, b] and listed["groups"] == [], "not in Clips"

    joined = await hub.http("POST", "/api/sequence/join", cookie, json_body={"name": "Film"})
    job = hub.core.book.get(joined.json()["job"])
    assert (job.kind, job.tool, job.plan.model, job.plan.lane_kind) == ("sequence.join", "sequence", NO_MODEL, "image")
    assert job.plan.tasks == (expected_task(hub, video),)
    assert job.plan.summary == {"kind": "clip", "mode": "join", "title": "Save · Film · 2 items", "clips": 2,
                                "seconds": 7.17}

    files.resolve(a).unlink()
    dropped = (await hub.http("GET", "/api/sequence/one?name=Film", cookie)).json()
    assert (dropped["revision"], [it["clip"] for it in dropped["tracks"][0]]) == (2, [b])
    assert await changed() == {"name": "Film", "revision": 2}, "a read that dropped a gone clip tells the windows"
    renamed = await hub.http("POST", "/api/sequence/rename", cookie, json_body={"name": "Film", "to": "Trailer"})
    assert renamed.json() == {"name": "Trailer"} and await changed() == {"name": "Trailer", "revision": 2}
    gone = await hub.http("POST", "/api/sequence/delete", cookie, json_body={"name": "Trailer"})
    assert gone.status == 204 and await changed() == {"name": "Trailer", "revision": -1}
    assert files.clip_facts(b) is not None
    assert no_times((await hub.http("GET", "/api/sequence/all", cookie)).json()) == {"sequences": []}
    missing = await hub.http("POST", "/api/sequence/delete", cookie, json_body={"name": "Trailer"})
    assert missing.json()["text"] == "There is no sequence named Trailer"


def items_body(n: int, item: str) -> str:
    return json.dumps({"name": "Long", "revision": 0, "tracks": [[{"clip": item, "in": 0, "out": 1000}] * n, []]})


async def test_a_sequence_takes_any_count_of_clips(tmp_path: Path) -> None:
    hub = await open_hub(tmp_path, {"modules": {"sequence": {"max_items": 999}}})    # a retired key
    try:
        cookie, item = hub.pair(), clip(hub.core.files, "101500-123", frames=1000)
        await hub.http("POST", "/api/sequence/new", cookie, json_body={"name": "Long"})
        hdrs = {"Content-Type": "application/json"}
        body = items_body(1000, item)
        assert 65_536 < len(body) < 131_072, "past the default body limit, under PUT /one's"
        ok = await hub.http("PUT", "/api/sequence/one", cookie, body=body, headers=hdrs)
        assert ok.status == 200 and len(ok.json()["tracks"][0]) == 1000
    finally:
        await hub.close()
    hub = await open_hub(tmp_path / "default")
    try:
        cookie, item = hub.pair(), clip(hub.core.files, "101500-123", frames=1000)
        await hub.http("POST", "/api/sequence/new", cookie, json_body={"name": "Long"})
        ok = await hub.http("PUT", "/api/sequence/one", cookie, body=items_body(201, item),
                            headers={"Content-Type": "application/json"})
        assert ok.status == 200 and len(ok.json()["tracks"][0]) == 201
    finally:
        await hub.close()


async def finished(hub: Hub, **data: object) -> None:
    hub.core.events.emit("job.finished", {"job": "j_x", "kind": "generate-image.image", "tool": "generate-image",
                                          "state": "done", "outputs": [], **data})
    await asyncio.sleep(0.05)


async def refused(hub: Hub, name: str, args: dict) -> str:
    got = (await rpc(hub, call(name, args))).json()["result"]
    assert got["isError"] is True
    return got["content"][0]["text"]


async def test_the_tools(hub: Hub) -> None:
    files = hub.core.files
    a, b = clip(files, "101500-123"), clip(files, "101600-456", frames=48, fps=16)
    assert await result(hub, "list_sequences", {}) == {"sequences": []}
    assert await refused(hub, "add_last_clip", {"sequence": "Film"}) == "No clip made in this session yet"
    picture = f"out/{DAY}/101700-000.png"
    await finished(hub, outputs=[a], state="failed")
    await finished(hub, outputs=[a], kind="sequence.join")
    assert await refused(hub, "add_last_clip", {"sequence": "Film"}) == "No clip made in this session yet"
    await finished(hub, outputs=[a, picture])
    assert await result(hub, "add_last_clip", {"sequence": "Film"}) == {
        "sequence": "Film", "place": 1, "clip": a, "clips": 1, "seconds": 5.17}, "a new name starts a sequence"
    await finished(hub, outputs=[b])
    assert await result(hub, "add_last_clip", {"sequence": "Film"}) == {
        "sequence": "Film", "place": 2, "clip": b, "clips": 2, "seconds": 8.17}
    assert files.sequence("Film")["tracks"] == [[whole(a), whole(b, 48)], []]
    seq = files.sequence("Film")
    files.sequence_save("Film", two([{"clip": a, "in": 12, "out": 60}, whole(b, 48)], [{**whole(b, 48), "at": 1500}]),
                        seq["revision"], 200)
    assert no_times(await result(hub, "list_sequences", {})) == {
        "sequences": [{"name": "Film", "clips": 3, "seconds": 5.0}]}
    assert await result(hub, "list_sequence_clips", {"sequence": "Film"}) == {"sequence": "Film", "seconds": 5.0,
                                                                             "clips": [
        {"track": 1, "place": 1, "kind": "clip", "clip": a, "in_s": 0.5, "out_s": 2.5, "seconds": 2.0},
        {"track": 1, "place": 2, "kind": "clip", "clip": b, "in_s": 0.0, "out_s": 3.0, "seconds": 3.0},
        {"track": 2, "place": 1, "kind": "clip", "clip": b, "in_s": 0.0, "out_s": 3.0, "seconds": 3.0, "at_s": 1.5}]}
    seq = files.sequence("Film")
    files.sequence_save("Film", two(seq["tracks"][0]), seq["revision"], 200)
    assert await refused(hub, "list_sequence_clips", {"sequence": "Nope"}) == "There is no sequence named Nope"
    queued = await result(hub, "join_sequence", {"sequence": "Film"})
    assert (queued["kind"], queued["clips"], queued["seconds"]) == ("clip", 2, 5.0)
    job = hub.core.book.get(queued["job"])
    assert job.kind == "sequence.join" and job.plan.tasks == (
        expected_task(hub, [{"clip": a, "in": 12, "out": 60}, whole(b, 48)]),)
    hub.core.events.emit("session.ended", {})
    await asyncio.sleep(0.05)
    assert await refused(hub, "add_last_clip", {"sequence": "Film"}) == "No clip made in this session yet"
    files.sequence_new("Empty")
    assert await refused(hub, "join_sequence", {"sequence": "Empty"}) == "The sequence is empty"


def test_join_plans_refuse_a_gone_sequence(tmp_path: Path) -> None:
    ctx = FakeCtx("sequence", tmp_path / "data", FakeEngine(None))
    ctx.files = Files(tmp_path / "data")  # type: ignore[assignment]
    with pytest.raises(Invalid) as e:
        join.plan({"name": "Nope"}, ctx)  # type: ignore[arg-type]
    assert e.value.text == "There is no sequence named Nope"
