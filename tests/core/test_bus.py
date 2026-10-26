"""Screens over real WebSockets: welcome, presence, focus, sockets, delivery, close codes, beat, going_off."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from hub.core import bus as bus_mod
from hub.core.api import Module, SocketGroup, Tab
from tests.core.harness import FAST, Hub, own_modules, start_hub
from tests.fakes.mp4 import tiny_mp4
from tests.fakes.screen import Screen, ws_status
from tests.fakes.wav import tiny_wav

TOOL = Module(id="tool-a", title="Tool A", tab=Tab("Tool A", 10),
              sockets=(SocketGroup("edit_source", "Edit image", ("image",), 1),
                       SocketGroup("reference", "Reference", ("image",), 3),
                       SocketGroup("clip", "Clip", ("video",), 1),
                       SocketGroup("sound", "Sound", ("audio",), 1)))
REFS = {"tool": "tool-a", "mode": "refs", "primary": "reference", "sockets": [
    {"id": "reference_1", "group": "reference", "label": "Reference 1", "accepts": ["image"], "filled": True},
    {"id": "reference_2", "group": "reference", "label": "Reference 2", "accepts": ["image"], "filled": False}]}


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    h = await start_hub(tmp_path / "data", modules=[*own_modules(), TOOL])
    for name in ("a.png", "b.png"):
        (h.data / "outputs" / "day").mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 8)).save(h.data / "outputs" / "day" / name)
    yield h
    await h.close()


async def pair_two(hub: Hub) -> tuple[Screen, Screen]:
    cookie = hub.pair()
    w = await hub.screen(cookie, "workspace", "scr_W")
    m = await hub.screen(cookie, "media", "scr_M", label="Right")
    return w, m


async def test_welcome_snapshot_and_presence(hub: Hub) -> None:
    w, m = await pair_two(hub)
    wel = m.welcome
    assert wel["proto"] == 1 and wel["boot"] == hub.core.boot and len(wel["boot"]) == 16
    assert wel["you"]["lanes"] == ["focus", "jobs", "media", "presence", "settings"], "jobs: a clip's verdict"
    assert w.welcome["you"]["lanes"] == ["assistant.chat", "gpu", "jobs", "presence", "settings"]
    assert wel["tools"] == [{"id": "tool-a", "title": "Tool A", "tab": {"label": "Tool A", "order": 10}, "sockets": [
        {"id": "edit_source", "label": "Edit image", "kinds": ["image"], "max": 1},
        {"id": "reference", "label": "Reference", "kinds": ["image"], "max": 3},
        {"id": "clip", "label": "Clip", "kinds": ["video"], "max": 1},
        {"id": "sound", "label": "Sound", "kinds": ["audio"], "max": 1}]}]
    assert wel["presence"]["screens"] == {"workspace": 1, "media": 1, "aux": 0}
    assert wel["presence"]["labels"]["media"] == ["Right"]
    assert wel["focus"] is None and wel["jobs"] == [] and "gpus" in wel["gpu"]
    assert wel["settings"] == {"diagnostics": False,
                               "vram": {"idle_unload": True, "idle_minutes": 10, "clip_previews": False}}
    assert [c["module"] for c in wel["cards"]] == ["network", "assistant"]
    await m.close()
    p = await w.recv("presence", where=lambda x: x["d"]["screens"]["media"] == 0)
    assert p["d"]["screens"]["workspace"] == 1


async def test_presence_counts_unique_screens_and_a_duplicate_id_replaces_the_old_line(hub: Hub) -> None:
    cookie = hub.pair()
    old = await hub.screen(cookie, "media", "scr_same")
    new = await hub.screen(cookie, "media", "scr_same")
    assert await old.closed() == 4009
    assert new.welcome["presence"]["screens"]["media"] == 1
    w = await hub.screen(cookie, "workspace", "scr_W")
    assert w.welcome["presence"]["screens"] == {"workspace": 1, "media": 1, "aux": 0}
    assert w.welcome["presence"]["devices"] == {hub.core.devices.records()[0]["id"]: 2}


async def test_focus_and_sockets_reach_media(hub: Hub) -> None:
    w, m = await pair_two(hub)
    await w.send("focus", {"tool": "tool-a"})
    f = await m.recv("focus", where=lambda x: x["d"])
    assert f["d"] == {"screen": "scr_W", "tool": "tool-a", "label": "Tool A", "mode": None, "primary": None,
                      "sockets": []}
    await w.send("sockets", REFS)
    f = await m.recv("focus", where=lambda x: x["d"] and x["d"]["sockets"])
    assert f["d"]["primary"] == "reference" and len(f["d"]["sockets"]) == 2
    bad = [{**REFS, "sockets": [{**REFS["sockets"][0], "group": "nope"}]},
           {**REFS, "sockets": [{**REFS["sockets"][0], "id": f"r{i}"} for i in range(4)]},
           {**REFS, "sockets": [{**REFS["sockets"][0], "accepts": ["video"]}]},
           {**REFS, "tool": "network"}]
    for decl in bad:
        await w.send("sockets", decl, id="s1")
        assert (await w.recv("error"))["d"]["code"] == "invalid"
    assert hub.core.bus.focus_record()["sockets"] == REFS["sockets"]  # type: ignore[index]
    await m.send("focus", {"tool": "tool-a"}, id="x")
    assert (await m.recv("error"))["d"]["text"] == "Not allowed from this screen"
    await w.close()
    assert (await m.recv("focus", where=lambda x: x["d"] is None))["d"] is None


async def test_delivery_round_trip_with_partial_result_and_idempotent_retry(hub: Hub) -> None:
    w, m = await pair_two(hub)
    await w.send("focus", {"tool": "tool-a"})
    await w.send("sockets", REFS)
    await m.recv("focus", where=lambda x: x["d"] and x["d"]["sockets"])
    items = ["out/day/a.png", "out/day/b.png"]
    await m.send("send", {"socket": "reference", "items": items}, id="snd_1")
    d = await w.recv("deliver")
    assert d["id"] == "snd_1" and d["d"]["from"] == {"role": "media", "label": "Right"}
    assert [i["url"].split("?")[0] for i in d["d"]["items"]] == ["/files/out/day/a.png", "/files/out/day/b.png"]
    m2 = await hub.screen(hub.pair(name="Other", addr="127.0.0.1"), "media", "scr_M2")
    await m2.send("send", {"socket": "reference", "items": items}, id="snd_1")  # a retry from a new line joins
    await w.send("received", {"placed": [{"item": items[0], "socket": "reference_2", "input": "in/x.png"}],
                              "refused": [{"item": items[1], "reason": "full", "text": "references are full"}]},
                 re="snd_1")
    first = await m.recv("delivery")
    second = await m2.recv("delivery")
    for r in (first, second):
        assert r["re"] == "snd_1" and r["d"] == {
            "status": "done", "tool": "tool-a", "toolLabel": "Tool A",
            "placed": [{"item": items[0], "socket": "reference_2"}],
            "refused": [{"item": items[1], "reason": "full", "text": "references are full"}]}
    await m.send("send", {"socket": "reference", "items": items}, id="snd_1")
    assert (await m.recv("delivery"))["d"]["status"] == "done"
    assert not [x for x in w.seen if x["t"] == "deliver" and x is not d]


async def test_a_send_of_51_items_is_delivered_and_answered_whole(hub: Hub) -> None:
    for k in range(51):                                             # no count of the Hub's on a send
        Image.new("RGB", (8, 8)).save(hub.data / "outputs" / "day" / f"p{k}.png")
    items = [f"out/day/p{k}.png" for k in range(51)]
    w, m = await pair_two(hub)
    await w.send("focus", {"tool": "tool-a"})
    await w.send("sockets", REFS)
    await m.recv("focus", where=lambda x: x["d"] and x["d"]["sockets"])
    await m.send("send", {"socket": "reference", "items": items}, id="snd_51")
    assert [i["id"] for i in (await w.recv("deliver"))["d"]["items"]] == items
    await w.send("received", {"placed": [{"item": i, "socket": "reference"} for i in items[:26]],
                              "refused": [{"item": i, "reason": "full", "text": "full"} for i in items[26:]]},
                 re="snd_51")
    d = (await m.recv("delivery"))["d"]
    assert [x["item"] for x in d["placed"]] == items[:26] and [x["item"] for x in d["refused"]] == items[26:]


@pytest.mark.parametrize("payload, reason", [
    ({"tool": "other", "socket": "reference", "items": ["out/day/a.png"]}, "offline"),
    ({"socket": "edit_source", "items": ["out/day/a.png"]}, "no_socket"),
    ({"socket": "reference", "items": ["out/day/missing.png"]}, "bad_item"),
    ({"socket": "reference", "items": ["../etc/passwd"]}, "bad_item"),
])
async def test_pre_checks(hub: Hub, payload: dict, reason: str) -> None:
    w, m = await pair_two(hub)
    await m.send("send", {"socket": "reference", "items": ["out/day/a.png"]}, id="snd_nofocus")
    assert (await m.recv("delivery"))["d"]["reason"] == "no_tool"
    await w.send("focus", {"tool": "tool-a"})
    await w.send("sockets", REFS)
    await m.recv("focus", where=lambda x: x["d"] and x["d"]["sockets"])
    await m.send("send", payload, id="snd_2")
    r = await m.recv("delivery", where=lambda x: x["re"] == "snd_2")
    assert r["d"]["status"] == "failed" and r["d"]["reason"] == reason and r["d"]["text"]


async def test_kind_mismatch_timeout_late_receipt_and_gone(hub: Hub) -> None:
    w, m = await pair_two(hub)
    await w.send("focus", {"tool": "tool-a"})
    clip = {"tool": "tool-a", "mode": None, "primary": None, "sockets": [
        {"id": "clip", "group": "clip", "label": "Clip", "accepts": ["video"], "filled": False}, *REFS["sockets"]]}
    await w.send("sockets", clip)
    await m.recv("focus", where=lambda x: x["d"] and x["d"]["sockets"])
    await m.send("send", {"socket": "clip", "items": ["out/day/a.png"]}, id="snd_k")
    assert (await m.recv("delivery"))["d"]["reason"] == "kind"
    await m.send("send", {"socket": "reference_2", "items": ["out/day/a.png"]}, id="snd_t")
    await w.recv("deliver")
    r = await m.recv("delivery", timeout=FAST.deliver_s + 2)
    assert r["d"] == {"status": "failed", "reason": "timeout", "text": "No answer from Tool A"}
    await w.send("received", {"placed": [], "refused": []}, re="snd_t")
    await m.send("send", {"socket": "reference", "items": ["out/day/b.png"]}, id="snd_g")
    await w.recv("deliver", where=lambda x: x["id"] == "snd_g")
    await w.close()
    r = await m.recv("delivery", where=lambda x: x["re"] == "snd_g")
    assert r["d"]["reason"] == "gone"
    assert not [x for x in m.seen if x["t"] == "delivery" and x["re"] == "snd_t" and x["d"]["status"] == "done"]


async def test_a_sound_goes_to_a_sound_socket_with_its_seconds(hub: Hub) -> None:
    """Media's Put in Sound. A sound passes the pre-check for an audio socket and is delivered with its seconds;
    a sound to a picture socket, or a picture to the sound socket, is the wrong kind."""
    (hub.data / "sounds" / "day").mkdir(parents=True, exist_ok=True)
    (hub.data / "sounds" / "day" / "line.wav").write_bytes(tiny_wav(seconds=2.0))
    w, m = await pair_two(hub)
    await w.send("focus", {"tool": "tool-a"})
    box = {"id": "sound", "group": "sound", "label": "Sound", "accepts": ["audio"], "filled": False}
    await w.send("sockets", {**REFS, "sockets": [*REFS["sockets"], box]})
    await m.recv("focus", where=lambda x: x["d"] and len(x["d"]["sockets"]) == 3)
    await m.send("send", {"socket": "sound", "items": ["sounds/day/line.wav"]}, id="snd_s")
    d = await w.recv("deliver", where=lambda x: x["id"] == "snd_s")
    assert d["d"]["socket"] == "sound" and d["d"]["items"] == [
        {"id": "sounds/day/line.wav", "kind": "sound", "url": d["d"]["items"][0]["url"], "seconds": 2.0}]
    for socket, item, sid in (("reference", "sounds/day/line.wav", "snd_r"), ("sound", "out/day/a.png", "snd_i")):
        await m.send("send", {"socket": socket, "items": [item]}, id=sid)
        assert (await m.recv("delivery", where=lambda x, s=sid: x["re"] == s))["d"]["reason"] == "kind"


async def test_a_clip_goes_to_a_video_socket_with_its_seconds(hub: Hub) -> None:
    """Media's Put in Video. A clip passes the pre-check for a video socket and is delivered with its
    seconds (the Video box shows them and refuses one under 2 s)."""
    (hub.data / "clips" / "day").mkdir(parents=True, exist_ok=True)
    (hub.data / "clips" / "day" / "clip1.mp4").write_bytes(tiny_mp4(w=64, h=48, frames=72))
    w, m = await pair_two(hub)
    await w.send("focus", {"tool": "tool-a"})
    box = {"id": "clip", "group": "clip", "label": "Video", "accepts": ["video"], "filled": False}
    await w.send("sockets", {**REFS, "sockets": [*REFS["sockets"], box]})
    await m.recv("focus", where=lambda x: x["d"] and len(x["d"]["sockets"]) == 3)
    await m.send("send", {"socket": "clip", "items": ["clips/day/clip1.mp4"]}, id="snd_v")
    d = await w.recv("deliver", where=lambda x: x["id"] == "snd_v")
    [item] = d["d"]["items"]
    assert (item["id"], item["kind"], item["seconds"]) == ("clips/day/clip1.mp4", "clip", 3.0)


async def test_unpaired_bad_origin_and_too_many_lines(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    cookie = hub.pair()
    s = await Screen.open(hub.port, None)
    assert await s.closed() == 4003
    assert await ws_status(hub.port, "/bus", {"Origin": "http://evil.example", "Cookie": f"hub_screen={cookie}"}) == 403
    assert await ws_status(hub.port, "/bus", {"Cookie": f"hub_screen={cookie}"}) == 403
    monkeypatch.setattr(bus_mod.M, "MAX_LINES", 2)
    await hub.screen(cookie, "workspace", "s1")
    await hub.screen(cookie, "media", "s2")
    third = await Screen.open(hub.port, cookie)
    assert await third.closed() == 4013


async def test_protocol_errors_rate_and_size(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    cookie = hub.pair()
    silent = await Screen.open(hub.port, cookie)
    assert await silent.closed(timeout=FAST.hello_s + 3) == 4008
    s = await Screen.open(hub.port, cookie)
    await s.send("focus", {"tool": "x"})
    assert (await s.recv("error"))["d"] == {"code": "protocol", "text": "hello expected first"}
    s = await hub.screen(cookie, "workspace", "p1")
    for _ in range(2):
        await s.send("nope.unknown_thing")
        assert (await s.recv("error"))["d"]["code"] == "protocol"
    await s.ws.send("not json")
    assert await s.closed() == 4008
    s = await hub.screen(cookie, "workspace", "p2")
    await s.ws.send('{"t":"sub","d":{"lanes":["' + "x" * 70_000 + '"]}}')
    assert await s.closed() == 1009
    s = await hub.screen(cookie, "workspace", "p3")
    for _ in range(80):
        await s.send("gpu.refresh")
    assert await s.closed() == 4029


async def test_sub_unsub_and_beat_only_after_silence(tmp_path: Path) -> None:
    hub = await start_hub(tmp_path / "data", timing=replace(FAST, beat_s=0.3))
    try:
        cookie = hub.pair()
        s = await hub.screen(cookie, "aux", "a1")
        await s.send("sub", {"lanes": ["gpu"]})
        await s.send("gpu.refresh")
        assert (await s.recv("gpu"))["d"]["gpus"][0]["uuid"] == "GPU-fake-0"
        await s.send("unsub", {"lanes": ["gpu", "presence"]})
        await s.send("sub", {"lanes": ["nope"]}, id="b")
        assert (await s.recv("error"))["d"]["field"] == "lanes"
        assert (await s.recv("beat", timeout=2))["t"] == "beat"
    finally:
        await hub.close()


@pytest.mark.parametrize("restart, reason, code", [(False, "shutdown", 4000), (True, "restart", 4001)])
async def test_going_off_before_close(tmp_path: Path, restart: bool, reason: str, code: int) -> None:
    hub = await start_hub(tmp_path / "data")
    cookie = hub.pair()
    s = await hub.screen(cookie, "media", "m1")
    if restart:
        (hub.data / "run").mkdir(exist_ok=True)
        (hub.data / "run" / "restart").touch()
    closing = asyncio.create_task(hub.close())
    assert await s.closed() == code
    await closing
    last = [x for x in s.seen if x["t"] == "going_off"]
    assert last and last[-1]["d"]["reason"] == reason
    assert not (hub.data / "run" / "restart").exists()
