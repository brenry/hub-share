"""The in-house MCP endpoint over raw HTTP: negotiation, status codes, JSON-RPC errors, tools."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from hub.core.api import Action, Ctx, Invalid, JobPlan, Module
from hub.core.schema import check
from hub.modules.generate_image import manifest as generate_image
from hub.modules.loras import manifest as loras
from hub.modules.sequence import manifest as sequence
from tests.core.fake_lane import FakeLane
from tests.core.harness import Hub, own_modules, start_hub
from tests.engine.helpers import FakeEngine, load_catalog, write_lora
from tests.fakes.fake_probes import FakeProbes


async def make(ctx: Ctx, args: dict) -> dict:
    job = ctx.jobs.submit("image", {"prompt": args["prompt"]})
    return {"job_id": job.id, "state": job.state}


GEN = Module(id="gen", title="Gen", jobs={"image": lambda p, ctx: JobPlan("image", "flux", ({},), {"model": "Flux"})},
             actions=(Action("make_image", "Make an image.", {
                 "type": "object", "required": ["prompt"], "additionalProperties": False,
                 "properties": {"prompt": {"type": "string", "minLength": 1},
                                "count": {"type": "integer", "minimum": 1, "maximum": 4, "default": 1}}}, make),))


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    probes = FakeProbes()
    h = await start_hub(tmp_path / "data", lanes=[FakeLane(tmp_path / "data" / "outputs", probes)],
                        modules=[*own_modules(), GEN], probes=probes)
    h.core.mcp.set_enabled(True)
    yield h
    await h.close()


async def rpc(hub: Hub, body: Any, headers: dict[str, str] | None = None) -> Any:
    hdrs = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {hub.core.mcp.key()}", **(headers or {})}
    return await hub.http("POST", "/mcp", body=body if isinstance(body, str) else json.dumps(body), headers=hdrs,
                          origin=False)


async def result(hub: Hub, name: str, arguments: Any) -> Any:
    """Call a tool; -> the parsed JSON text of its result."""
    return json.loads((await rpc(hub, call(name, arguments))).json()["result"]["content"][0]["text"])


def call(name: str, arguments: Any, rid: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


async def test_initialize_negotiates_and_is_stateless(hub: Hub) -> None:
    for asked, got in (("2025-06-18", "2025-06-18"), ("2025-03-26", "2025-03-26"), ("2099-01-01", "2025-11-25")):
        r = await rpc(hub, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": asked, "capabilities": {}, "clientInfo": {"name": "Open WebUI", "version": "0.11"}}})
        assert r.status == 200 and r.headers["content-type"] == "application/json"
        assert "mcp-session-id" not in r.headers
        assert r.json() == {"jsonrpc": "2.0", "id": 1, "result": {
            "protocolVersion": got, "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "hub", "version": "0.1.0"}}}
    assert hub.core.mcp.clients()[0]["name"] == "Open WebUI"
    r = await rpc(hub, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert r.status == 202 and r.body == b""
    assert (await rpc(hub, {"jsonrpc": "2.0", "id": 9, "result": {}})).status == 202
    assert (await rpc(hub, {"jsonrpc": "2.0", "id": "p", "method": "ping"})).json()["result"] == {}


async def test_transport_rules(hub: Hub) -> None:
    for method in ("GET", "DELETE"):
        r = await hub.http(method, "/mcp")
        assert r.status == 405 and r.headers["allow"] == "POST"
    ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    r = await rpc(hub, ping, {"MCP-Protocol-Version": "2026-07-28"})
    assert r.status == 400 and r.headers["content-type"].startswith("text/plain")
    assert hub.core.mcp.clients()[0]["status"] == "Refused: unsupported protocol version"
    assert (await rpc(hub, ping, {"MCP-Protocol-Version": "2025-11-25"})).status == 200
    assert (await rpc(hub, ping, {"Origin": "http://evil.example"})).status == 403
    assert (await rpc(hub, ping, {"Origin": hub.origin})).status == 200
    assert (await rpc(hub, ping, {"Authorization": "Bearer anything"})).status == 401
    assert (await rpc(hub, ping, {"Content-Type": "text/plain"})).status == 415
    hub.core.mcp.set_enabled(False)
    assert (await rpc(hub, ping)).status == 503


@pytest.mark.parametrize("body, status, code", [
    ("{nope", 400, -32700), ("[]", 400, -32600), ('{"id":1,"method":"ping"}', 400, -32600),
    ('{"jsonrpc":"2.0","id":true,"method":"ping"}', 400, -32600),
    ('{"jsonrpc":"2.0","id":1,"method":"resources/list"}', 200, -32601),
    ('{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"nope"}}', 200, -32602),
])
async def test_json_rpc_errors(hub: Hub, body: str, status: int, code: int) -> None:
    r = await rpc(hub, body)
    assert r.status == status and r.json()["error"]["code"] == code


async def test_tools_list_and_calls(hub: Hub) -> None:
    listed = (await rpc(hub, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})).json()["result"]["tools"]
    assert [t["name"] for t in listed] == ["make_image"], "no core tools: only what modules register"
    assert all(set(t) == {"name", "description", "inputSchema"} for t in listed)
    bad = (await rpc(hub, call("make_image", {"prompt": "x", "x": 1}))).json()["result"]
    assert bad == {"content": [{"type": "text", "text": "unknown argument x"}], "isError": True}
    missing = (await rpc(hub, call("make_image", {}))).json()["result"]
    assert missing["isError"] is True and missing["content"][0]["text"] == "prompt is required"
    made = await result(hub, "make_image", {"prompt": "a fox"})
    assert made["state"] == "queued", "an assistant's job queues at once, like a screen's"


async def test_the_shipped_modules_publish_six_generated_tools_and_a_set_changes_the_screen(tmp_path: Path) -> None:
    """Over the wire: tools/list is what the screen, the listings and the action declare; a set_… call changes what
    get_… returns, is saved for the Generate screen and reaches an open window as `generate-image.draft`."""
    hub = await start_hub(tmp_path / "data", modules=[*own_modules(), generate_image.MODULE, loras.MODULE,
                                                      sequence.MODULE])
    try:
        hub.core.mcp.set_enabled(True)
        write_lora(tmp_path / "loras" / "flux2_klein_9b" / "grain.safetensors", {"modelspec.title": "Film Grain"})
        hub.core.engine = FakeEngine(load_catalog("catalog_upstream.json", tmp_path / "loras"))
        listed = (await rpc(hub, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})).json()["result"]["tools"]
        assert [t["name"] for t in listed] == ["get_generate_image_settings", "set_generate_image_settings",
                                               "list_image_models", "list_characters", "generate_image",
                                               "direct_clip", "direct_scene", "redo_shot", "list_loras",
                                               "list_sequences", "list_sequence_clips", "add_last_clip",
                                               "join_sequence"], \
            "push_draft is gone: the draft never reaches the prompt box; Edit Video's four come after"
        assert len(listed) == 13, "eleven tools, then direct_scene and redo_shot: 13"
        assert listed[5] == {"name": "direct_clip",
                             "description": "Plan and render one clip from request, its words as written."
                                            " Not for a chat started with Script:, which the script tools write.",
                             "inputSchema": {"type": "object", "additionalProperties": False, "required": ["request"],
                                             "properties": {"request": {"type": "string", "minLength": 1}}}}
        assert listed[6] == {**listed[5], "name": "direct_scene", "description": "Plan, render and cut a scene of "
                             "several shots from request, its words as written. Not for a chat started "
                             "with Script:, which the script tools write."}
        assert listed[7] == {"name": "redo_shot", "description": "Render one shot of a scene again on a new seed and "
                             "cut the scene again with it.",
                             "inputSchema": {"type": "object", "additionalProperties": False, "required": ["shot"],
                                             "properties": {"shot": {"type": "integer", "minimum": 1},
                                                            "scene": {"type": "string", "minLength": 1}}}}
        arg = {"type": "object", "additionalProperties": False, "required": ["sequence"],
               "properties": {"sequence": {"type": "string", "minLength": 1}}}
        assert listed[9:] == [
            {"name": "list_sequences", "description": "Sequences by name, with the number of items and the seconds "
                                                      "of each.",
             "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}}},
            {"name": "list_sequence_clips", "description": "Items of one sequence by track in play order: place, clip "
                                                           "or sound id, in and out in seconds, seconds kept, and "
                                                           "where a track 2 item starts.", "inputSchema": arg},
            {"name": "add_last_clip", "description": "Adds the newest clip Generate Image made to the end of a "
                                                     "sequence's track 1, whole; a new name starts a new sequence.",
             "inputSchema": arg},
            {"name": "join_sequence", "description": "Queues one file of a sequence, cut at in and out points: an MP4 "
                                                     "into Clips when track 1 holds clips, else a WAV into Sounds.",
             "inputSchema": arg}]
        assert all(set(t) == {"name", "description", "inputSchema"} and t["description"].endswith(".") for t in listed)
        assert listed[3] == {"name": "list_characters",
                             "description": "Characters by name, with the notes on each, the words for its "
                                            "voice and whether it has a voice sample, from the Characters folder.",
                             "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}}}
        assert listed[4] == {"name": "generate_image",
                             "description": "Render the draft with the screen's settings, as the Generate button does."
                                            " Not for a chat started with Script:, which the script tools write.",
                             "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}}}
        assert not {"model", "references"} & set(listed[1]["inputSchema"]["properties"]), \
            "the screen's pick alone"
        cookie = hub.pair()
        w = await hub.screen(cookie, "workspace", "w")
        unpicked = (await rpc(hub, call("get_generate_image_settings", {}))).json()["result"]
        assert unpicked == {"content": [{"type": "text", "text": "The model picked on the Generate screen cannot run; "
                                                                 "pick one there"}], "isError": True}, "none chosen"
        await hub.http("PUT", "/api/generate-image/draft", cookie, {"model": "flux2_klein_9b"})   # the pulldown's pick
        await w.recv("generate-image.draft", timeout=2)
        before = await result(hub, "get_generate_image_settings", {})
        assert (before["draft"], before["model"], before["seed"], before["loras"]) == (
            "", "flux2_klein_9b", "random", []), "no draft yet; the pulldown's model"
        found = await result(hub, "list_loras", {"model": "flux2_klein_9b"})
        assert [x["name"] for x in found["loras"]] == ["Film Grain"]
        lora = {"id": found["loras"][0]["id"], "strength": 0.8}
        switch = (await rpc(hub, call("set_generate_image_settings", {"model": "z_image"}))).json()["result"]
        assert switch == {"content": [{"type": "text", "text": "unknown argument model"}], "isError": True}
        after = await result(hub, "set_generate_image_settings", {"steps": 6, "seed": "42", "aspect": "16:9",
                                                                  "loras": [lora]})
        assert (after["model"], after["steps"], after["seed"], after["aspect"]) == ("flux2_klein_9b", 6, "42", "16:9")
        assert after["loras"] == [{**lora, "file": "grain.safetensors"}]
        assert await result(hub, "get_generate_image_settings", {}) == after
        assert (await w.recv("generate-image.draft", timeout=2))["d"] == {}, (
            "the Generate windows redraw their bar; nothing switched, nothing to say")
        draft = (await hub.http("GET", "/api/generate-image/draft", cookie)).json()
        assert (draft["model"], draft["aspect"], draft["lorasByModel"]) == ("flux2_klein_9b", "16:9",
                                                                             {"flux2_klein_9b": [lora]})
        assert draft["advancedByModel"]["flux2_klein_9b"] == {"steps": 6, "guidance": None,
                                                              "seed": {"mode": "fixed", "value": 42}}
        bad = (await rpc(hub, call("set_generate_image_settings", {"count": 9}))).json()["result"]
        assert bad == {"content": [{"type": "text", "text": "count must be at most 6"}], "isError": True}
    finally:
        await hub.close()


async def test_the_draft_over_mcp_lands_beside_the_chat_and_generate_image_renders_it(tmp_path: Path) -> None:
    """The draft set through the generated set tool lands in the session (GET /draft shows it beside the
    untouched prompt; draft.json is not even touched) and the window hears `generate-image.draft`. Nothing moves it
    into the prompt box: push_draft is gone. generate_image renders the draft, never the box; an empty draft is one
    line. With no Generate window connected the set is refused, so nothing seeds a later session."""
    probes = FakeProbes()
    lane = FakeLane(tmp_path / "data" / "outputs", probes)
    hub = await start_hub(tmp_path / "data", lanes=[lane], probes=probes,
                          modules=[*own_modules(), generate_image.MODULE, loras.MODULE])
    on_disk = tmp_path / "data" / "generate-image" / "draft.json"
    try:
        hub.core.mcp.set_enabled(True)
        hub.core.engine = FakeEngine(load_catalog("catalog_upstream.json", tmp_path / "loras"))
        nobody = (await rpc(hub, call("set_generate_image_settings", {"draft": "a red fox in snow"}))).json()["result"]
        assert nobody == {"content": [{"type": "text", "text": "No Generate window is open"}], "isError": True}
        cookie = hub.pair()
        w = await hub.screen(cookie, "workspace", "w")
        assert (await hub.http("GET", "/api/generate-image/draft", cookie)).json() == {}, "nothing was held"
        empty = (await rpc(hub, call("generate_image", {}))).json()["result"]
        assert empty == {"content": [{"type": "text", "text": "The draft is empty"}], "isError": True}
        assert hub.core.book.entries == {}, "an empty draft renders nothing"
        gone = (await rpc(hub, call("push_draft", {}))).json()
        assert gone["error"]["code"] == -32602, "push_draft is no tool any more"
        first = (await rpc(hub, call("set_generate_image_settings", {"draft": "a red fox"}))).json()["result"]
        hub.core.store.flush()
        assert first["content"][0]["text"] == "The model picked on the Generate screen cannot run; pick one there"
        assert not on_disk.exists(), "no model picked: none chosen, nothing written"
        (tmp_path / "data" / "outputs" / "2026-10-09").mkdir(parents=True)
        Image.new("RGB", (64, 48)).save(tmp_path / "data" / "outputs" / "2026-10-09" / "ref.png")
        ref = {"id": "out/2026-10-09/ref.png", "w": 64, "h": 48}
        await hub.http("PUT", "/api/generate-image/draft", cookie,
                       {"model": "flux2_klein_9b", "aspect": "auto", "references": [ref], "prompt": "my own words"})
        hub.core.store.flush()
        saved = (on_disk.read_bytes(), on_disk.stat().st_mtime_ns)
        set_ = await result(hub, "set_generate_image_settings", {"draft": "a red fox in snow"})
        assert (set_["draft"], set_["width"], set_["height"]) == ("a red fox in snow", 1184, 880), "ref 1's shape"
        assert "prompt" not in set_
        await w.recv("generate-image.draft", timeout=2)
        draft = (await hub.http("GET", "/api/generate-image/draft", cookie)).json()
        assert (draft["draft"], draft["prompt"], draft["references"]) == ("a red fox in snow", "my own words", [ref]), \
            "the window's panel follows; the prompt box is as it was"
        hub.core.store.flush()
        assert (on_disk.read_bytes(), on_disk.stat().st_mtime_ns) == saved, "draft.json untouched by a draft"
        assert json.loads(saved[0]) == {"model": "flux2_klein_9b", "aspect": "auto",
                                        "lastModel": {"image": "flux2_klein_9b", "video": ""}}
        assert hub.core.book.entries == {}, "nothing rendered by a set: that is generate_image or the Generate press"
        made = await result(hub, "generate_image", {})
        assert set(made) == {"state"} and made["state"] in ("queued", "running")
        [entry] = hub.core.book.entries.values()
        assert entry.params["prompt"] == "a red fox in snow", "the draft is rendered, never the prompt box"
        assert entry.params["references"] == [ref["id"]] and entry.params["mode"] == "refs"
        draft = (await hub.http("GET", "/api/generate-image/draft", cookie)).json()
        assert (draft["draft"], draft["prompt"]) == ("a red fox in snow", "my own words"), "the render moves nothing"
        bad = (await rpc(hub, call("generate_image", {"prompt": "x"}))).json()["result"]
        assert bad == {"content": [{"type": "text", "text": "unknown argument prompt"}], "isError": True}
    finally:
        await hub.close()


async def test_an_mcp_job_runs_without_any_screen(hub: Hub) -> None:
    w = await hub.screen(hub.pair(), "workspace", "w")
    job = await result(hub, "make_image", {"prompt": "x"})
    await w.recv("job", where=lambda x: x["d"]["id"] == job["job_id"] and x["d"]["state"] == "done", timeout=5)
    done = hub.core.book.get(job["job_id"])
    assert done is not None and done.outputs == [f"out/2026-10-09/{job['job_id']}_1.png"]


async def test_the_key_gates_every_call_after_the_switch(hub: Hub) -> None:
    ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}}
    assert [(await rpc(hub, ping)).status for _ in range(30)] == [200] * 30
    for body in (ping, init, call("make_image", {"prompt": "x"})):
        for auth in ("", "Bearer", "Bearer wrong", hub.core.mcp.key()):
            r = await rpc(hub, body, {"Authorization": auth})
            assert (r.status, r.body) == (401, b"MCP key missing or wrong")
    assert hub.core.book.entries == {}, "a refused call never reaches a tool"
    hub.core.mcp.set_enabled(False)
    assert (await rpc(hub, ping, {"Authorization": "Bearer wrong"})).status == 503, "Off never says if a key is right"


@pytest.mark.parametrize("schema, args, error", [
    ({"properties": {"n": {"type": "integer", "minimum": 1}}}, {"n": 0}, "n must be at least 1"),
    ({"properties": {"n": {"type": "integer", "maximum": 4}}}, {"n": 5}, "n must be at most 4"),
    ({"properties": {"n": {"type": "integer"}}}, {"n": True}, "n must be a whole number"),
    ({"properties": {"n": {"type": "integer", "multipleOf": 16}}}, {"n": 20}, "n must be a multiple of 16"),
    ({"properties": {"s": {"type": "string", "minLength": 1}}}, {"s": ""}, "s must not be empty"),
    ({"properties": {"s": {"type": "string", "enum": ["a"]}}}, {"s": "b"}, "s must be one of: a"),
    ({"properties": {"m": {"type": "object", "maxProperties": 1, "additionalProperties": {"type": "number"}}}},
     {"m": {"a": 1, "b": 2}}, "m takes at most 1 entries"),
    ({"properties": {"m": {"type": "object", "additionalProperties": {"type": "number"}}}}, {"m": {"a": "x"}},
     "m.a must be a number"),
    ({"properties": {"l": {"type": "array", "maxItems": 1}}}, {"l": [1, 2]}, "l has the wrong number of items"),
    ({"properties": {"b": {"type": "boolean"}}}, {"b": 1}, "b must be true or false"),
    ({}, [1], "arguments must be an object"),
])
def test_schema_check(schema: dict, args: Any, error: str) -> None:
    with pytest.raises(Invalid, match=error.replace("(", r"\(")):
        check({"type": "object", **schema}, args)


def test_schema_fills_defaults() -> None:
    schema = {"type": "object", "properties": {"w": {"type": "integer", "default": 1024}, "m": {"type": "string"}}}
    assert check(schema, None) == {"w": 1024}
    assert check(schema, {"w": 512, "m": "x"}) == {"w": 512, "m": "x"}


def test_schema_takes_null_as_left_out_and_a_whole_float_as_an_integer() -> None:
    """What a get tool reports can come back to its set tool as it is: null for a setting that is not there is the
    same as leaving it out (a required one is still refused), and 15.0 is the whole number 15."""
    schema = {"type": "object", "additionalProperties": False, "required": ["id"],
              "properties": {"id": {"type": "string"}, "g": {"type": "number"}, "n": {"type": "integer"}}}
    assert check(schema, {"id": "a", "g": None, "n": 15.0}) == {"id": "a", "n": 15}
    with pytest.raises(Invalid, match="id must be text"):
        check(schema, {"id": None})
    with pytest.raises(Invalid, match="n must be a whole number"):
        check(schema, {"id": "a", "n": 15.5})
    with pytest.raises(Invalid, match="unknown argument x"):
        check(schema, {"id": "a", "x": None})
