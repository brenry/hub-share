"""The script tools over the Hub's MCP server: the thirteen tools and then the
twelve (`scene_change` after `scene_add`; `script_say` first), each with an input schema the
server checks; a refusal is `isError` with the JSON `{problem, fix, hints}`; a write reaches an open window as
`director.changed`; the pointer through start, read, rename and delete."""
from __future__ import annotations

import json
from pathlib import Path

from hub.core.files import Files
from hub.modules.director import manifest as director
from hub.modules.generate_image import manifest as generate_image
from hub.modules.loras import manifest as loras
from hub.modules.media import manifest as media
from hub.modules.sequence import manifest as sequence
from tests.core.harness import own_modules, start_hub
from tests.core.test_mcp import call, rpc
from tests.engine.test_media_characters import png_bytes
from tests.engine.test_script_shape import FIXTURE
from tests.engine.test_script_tools import CONTEXT, Model

THIRTEEN = ["get_generate_image_settings", "set_generate_image_settings", "list_image_models", "list_characters",
            "generate_image", "direct_clip", "direct_scene", "redo_shot", "list_loras", "list_sequences",
            "list_sequence_clips", "add_last_clip", "join_sequence"]
TWELVE = ["script_say", "script_start", "context_set", "scene_add", "scene_change", "shot_add", "line_add", "cue_add",
          "pose_add", "event_move", "event_change", "event_remove", "script_read"]
TWO = ["script_lock", "script_unlock", "script_track", "script_stems", "script_render"]


async def test_the_tools_the_pointer_and_the_lane(tmp_path: Path) -> None:
    cast = tmp_path / "Characters"
    cast.mkdir()
    for name in ("Character 1", "Character 2", "Character 7", "Character 6"):   # the fixture's cast, then CONTEXT's
        (cast / f"{name}.png").write_bytes(png_bytes())
    (Files(tmp_path / "data").roots["scripts"] / "Example.json").write_bytes(FIXTURE.read_bytes())
    hub = await start_hub(tmp_path / "data", modules=[*own_modules(), generate_image.MODULE, loras.MODULE,
                                                      sequence.MODULE, media.MODULE, director.MODULE],
                          settings={"paths": {"characters": str(cast)}})
    try:
        hub.core.mcp.set_enabled(True)
        listed = (await rpc(hub, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})).json()["result"]["tools"]
        assert [t["name"] for t in listed] == THIRTEEN + TWELVE + TWO
        for t in listed[13:]:
            schema = t["inputSchema"]
            assert t["description"].endswith(".") and schema["type"] == "object"
            assert schema["additionalProperties"] is False and set(schema["required"]) <= set(schema["properties"])
        saying = next(t["inputSchema"] for t in listed if t["name"] == "script_say")
        assert saying["required"] == ["words"] and "maxLength" not in saying["properties"]["words"]
        moving = next(t["inputSchema"] for t in listed if t["name"] == "event_move")
        assert "shot" in moving["properties"] and moving["required"] == ["start_ms"], "start_ms required"
        assert "ref" in moving["properties"] and "id" in moving["properties"], "ref or id"

        async def tool(name: str, args: dict) -> dict:
            return (await rpc(hub, call(name, args))).json()["result"]

        def text(result: dict) -> dict:
            return json.loads(result["content"][0]["text"])

        none = await tool("script_read", {})
        assert none["isError"] is True and text(none) == {"problem": "No script is open", "fix": "Call script_start, "
                                                          "or script_read with a name", "hints": {}}
        assert (await tool("line_add", {"shot": "s1"}))["content"][0]["text"] == "speaker is required"
        cookie = hub.pair()
        w = await hub.screen(cookie, "workspace", "w")
        read = await tool("script_read", {"name": "Example"})
        assert read["isError"] is False and text(read)["read"][0] == "Example · 1 scenes · 3 shots · 24.00 s"
        renamed = await hub.http("POST", "/api/director/rename", cookie,
                                 json_body={"name": "Example", "to": "Script 1"})
        assert renamed.json() == {"name": "Script 1"}
        added = await tool("cue_add", {"shot": "s1", "cue": "effect", "words": "A door"})
        assert text(added)["script"] == "Script 1", "the pointer moved with the rename"
        got = await w.recv("director.changed", timeout=2)
        while got["d"]["name"] == "Example":           # the read's fill pass added Example's panels
            got = await w.recv("director.changed", timeout=2)
        assert got["d"]["name"] == "Script 1" and isinstance(got["d"]["revision"], int)
        hub.core.services["ask"] = Model(json.dumps(CONTEXT))
        begun = await tool("script_start", {"name": "Script 2", "story": "Character 1 meets Character 2"})
        changed = [(await w.recv("director.changed", timeout=2))["d"]["name"]]
        while changed[-1] == "Script 1":                   # the fill pass's panels for Script 1 come first
            changed.append((await w.recv("director.changed", timeout=2))["d"]["name"])
        assert text(begun)["script"] == "Script 2" and changed[-1] == "Script 2"
        assert text(await tool("script_read", {}))["script"] == "Script 2"
        gone = await hub.http("POST", "/api/director/delete", cookie, json_body={"name": "Script 2"})
        assert gone.status == 204
        assert text(await tool("scene_add", {"title": "One", "cast": ["Character 7"]}))["problem"] == \
            "No script is open"
        assert text(await tool("script_read", {"name": "Script 1"}))["script"] == "Script 1"
    finally:
        await hub.close()
