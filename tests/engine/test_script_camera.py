"""A shot's camera as blueprint §2's object (`hub/modules/director/camera.py`): a text camera
reads as its framing, the object with framing, move and on; what the format refuses; `shot_add` with the object and
with text; a tool write turns the example's text cameras into objects with the same framing and marks no panel stale;
`event_change` merges into the camera; a rename and a removal reach `on`; the answer and `script_read` lines; the
sketch prompt draws only who is in frame; a changed `on` marks that shot's panels stale."""
from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.director import drawing, panels, scriptshape, sketch
from tests.engine.test_script_drawing import DrawCtx
from tests.engine.test_script_shape import FIXTURE
from tests.engine.test_script_stale import draw_all
from tests.engine.test_script_tools import CONTEXT, NINE, call, on_disk, refused, started

CHARS = {"character 7", "character 6"}
CLOSE_ON = {"framing": "close shot", "move": "slow push in", "on": ["Character 6"]}


@pytest.fixture
async def ctx(tmp_path: Path) -> Any:
    await drawing.stop()
    drawing.waiting.clear()
    drawing.failed.clear()
    yield DrawCtx(tmp_path)
    await drawing.stop()


def one(camera: Any, version: int = 2) -> dict:
    shot = {"start_ms": 0, "end_ms": 1000, "events": [], "camera": camera}
    script = {"version": version, "scenes": [{"title": "One", "cast": ["Character 7", "Character 6"], "shots": [shot]}]}
    if version == 2:
        script["context"] = copy.deepcopy(CONTEXT)
    return script


def problem(camera: Any, version: int = 2) -> str:
    with pytest.raises(Invalid) as e:
        scriptshape.read(one(camera, version), CHARS)
    return e.value.text


def test_the_two_forms_read_and_what_is_refused() -> None:
    assert scriptshape.read(one("Wide"), CHARS)
    assert scriptshape.read(one({"framing": "Wide", "move": "pan left", "on": ["character 7", "Character 6"]}), CHARS)
    assert scriptshape.read(one({"framing": "Wide", "on": []}), CHARS)
    at = "Scene 1, shot 1: "
    assert scriptshape.read(one("x" * 301), CHARS)                       # any length
    assert scriptshape.read(one({"framing": "x" * 301, "move": "x" * 121}), CHARS)
    assert problem(" ") == at + "camera is text, not blank"
    assert problem({"framing": ""}) == at + "the camera's framing is text, not blank"
    assert problem({"framing": "Wide", "move": " "}) == at + "the camera's move is text, not blank"
    assert problem({"framing": "Wide", "on": ["Character 4"]}) == \
        at + "the camera's on names Character 4, who is not in the scene's cast"
    assert problem({"framing": "Wide", "on": ["Character 6", "character 6"]}) == \
        at + "character 6 is in the camera's on twice"
    assert problem({"framing": "Wide", "tilt": "up"}) == at + "the camera has a key the format does not know: tilt"
    assert scriptshape.read(one({"move": "pan"}), CHARS)                 # a shot may come without a framing
    assert problem({"framing": "Wide"}, 1) == at + "a camera object is version 2"


async def test_shot_add_takes_the_object_and_text(ctx: DrawCtx) -> None:
    await started(ctx)
    await call(ctx, "scene_add", {"title": "The opening", "cast": ["Character 7", "Character 6"]})
    done = await call(ctx, "shot_add", {"scene": 1, "camera": CLOSE_ON})
    assert done["state"][1] == "shot s1 · scene 1 · close shot · slow push in · on Character 6"
    done = await call(ctx, "shot_add", {"scene": 1, "camera": "Wide shot of the stage"})
    assert done["state"][1] == "shot s2 · scene 1 · Wide shot of the stage"
    assert [s["camera"] for s in on_disk(ctx)["scenes"][0]["shots"]] == [CLOSE_ON,
                                                                         {"framing": "Wide shot of the stage"}]
    await call(ctx, "shot_add", {"scene": 1, "camera": {"framing": "Two shot", "on": []}})
    got = await refused(ctx, "shot_add", {"scene": 1, "camera": {"framing": "Wide", "on": ["Character 4"]}})
    assert got == {"problem": "Character 4 is not in scene 1's cast", "fix": "Name only the scene's cast in on",
                   "hints": {"valid_speakers": ["Character 7", "Character 6"]}}
    got = await refused(ctx, "shot_add", {"scene": 1, "camera": {"framing": "Wide",
                                                                 "on": ["Character 6", "Character 6"]}})
    assert got["problem"] == "Character 6 is in the camera's on twice" and \
        got["fix"] == "Name only the scene's cast in on"
    got = await refused(ctx, "shot_add", {"scene": 1, "camera": {"framing": "Wide", "move": " "}})
    assert got["problem"] == "The camera's move is text, not blank"
    assert got["hints"] == {"fields": ["camera"]}
    await call(ctx, "shot_add", {"scene": 1, "camera": {"framing": "Wide", "move": "x" * 121}})   # any length
    assert on_disk(ctx)["scenes"][0]["shots"][-1]["camera"] == {"framing": "Wide", "move": "x" * 121}
    read = await call(ctx, "script_read", {})
    assert "s1 · scene 1 · script 0.00–1.00 s · close shot · slow push in · on Character 6" in read["read"]
    assert "s2 · scene 1 · script 1.00–2.00 s · Wide shot of the stage" in read["read"]
    assert "s3 · scene 1 · script 2.00–3.00 s · Two shot · on nobody" in read["read"]


async def test_a_write_turns_the_examples_text_cameras_into_objects(ctx: DrawCtx) -> None:
    folder = ctx.files.roots["scripts"]
    shutil.copy(FIXTURE, folder / "Example.json")
    texts = [s["camera"] for s in on_disk(ctx, "Example")["scenes"][0]["shots"]]
    await call(ctx, "script_read", {"name": "Example"})
    await draw_all(ctx)
    await call(ctx, "cue_add", {"shot": "s3", "cue": "reaction", "words": "Laughter"})
    held = on_disk(ctx, "Example")
    assert [s["camera"] for s in held["scenes"][0]["shots"]] == [{"framing": t} for t in texts]
    assert not [p["id"] for _, _, p in panels.panels(held) if p["stale"]], "the same prompt: nothing stale"


async def test_event_change_merges_into_the_camera(ctx: DrawCtx) -> None:
    await started(ctx)
    await call(ctx, "scene_add", {"title": "The opening", "cast": ["Character 7", "Character 6"]})
    await call(ctx, "shot_add", {"scene": 1, "camera": {"framing": "close shot", "move": "slow push in"}})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 6", "words": NINE})
    await draw_all(ctx)
    done = await call(ctx, "event_change", {"id": "s1", "fields": {"camera": {"on": ["Character 6"]}}})
    assert done["state"][1] == ("shot 1, s1: close shot · slow push in · "
                                 "changed shot s1 · camera close shot · slow push in · on Character 6")
    assert on_disk(ctx)["scenes"][0]["shots"][0]["camera"] == CLOSE_ON
    assert [p["id"] for _, _, p in panels.panels(on_disk(ctx)) if p["stale"]], "on changed: its panels stale"
    await call(ctx, "event_change", {"id": "s1", "fields": {"camera": "medium shot"}})
    assert on_disk(ctx)["scenes"][0]["shots"][0]["camera"] == {**CLOSE_ON, "framing": "medium shot"}
    got = await refused(ctx, "event_change", {"id": "s1", "fields": {"camera": {"tilt": "up"}}})
    assert got["problem"] == "The camera has a key the format does not know: tilt"
    assert got["hints"] == {"fields": ["camera"]}


async def test_a_rename_and_a_removal_reach_the_camera(ctx: DrawCtx, tmp_path: Path) -> None:
    await started(ctx)
    await call(ctx, "scene_add", {"title": "The opening", "cast": ["Character 7", "Character 6"]})
    await call(ctx, "shot_add", {"scene": 1, "camera": {"framing": "close on Character 6", "move": "past Character 6",
                                                        "on": ["character 6", "Character 7"]}})
    shutil.copy(tmp_path / "Characters" / "Character 6.png", tmp_path / "Characters" / "Character 8.png")
    await call(ctx, "context_set", {"cast": [{"name": "Character 6", "to": "Character 8"}]})
    assert on_disk(ctx)["scenes"][0]["shots"][0]["camera"] == {"framing": "close on Character 8",
                                                               "move": "past Character 8",
                                                               "on": ["Character 8", "Character 7"]}
    await call(ctx, "context_set", {"cast": [{"name": "Character 8", "remove": True}]})
    assert on_disk(ctx)["scenes"][0]["shots"][0]["camera"]["on"] == ["Character 7"]


def test_the_sketch_draws_only_who_is_in_frame() -> None:
    context = copy.deepcopy(CONTEXT)
    del context["cast"][0]["costume"]                       # Character 7, off frame, has no costume
    shot = {"id": "s1", "start_ms": 0, "end_ms": 1000, "events": [], "camera": CLOSE_ON}
    scene = {"title": "One", "cast": ["Character 7", "Character 6"], "shots": [shot]}
    text, why = sketch.prompt({"version": 2, "context": context, "scenes": [scene]}, scene, shot, 0)
    assert why is None
    assert text.endswith(". Character 6 stand.")
    assert "Character 7" not in text and "in grey" not in text and "red dress" not in text
    assert text.startswith("close shot, slow push in. ")
    shot["camera"] = {"framing": "close shot"}
    text, why = sketch.prompt({"version": 2, "context": context, "scenes": [scene]}, scene, shot, 0)
    assert why is None and "Character 7 stand. Character 6 stand" in text, \
        "no on: the scene's cast is in frame, as before"
