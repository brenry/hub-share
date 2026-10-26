"""Recasting (`frame.py`, `context.py`, `scriptshape.py`, `tools.py`): `context_set {remove: true}` takes a member out
of the context, every scene's cast and every pose (the Hub's and the Director's) in one call, the member's props kept
with no owner, refused only while the member has lines; the script timed again when a pose went; a version-2 scene
left with no cast reads; the did-line names what went; a `to` rename renames the member in each shot's camera
words, as written, by the name's first word too, with no length cap."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hub.core.api import Invalid
from hub.modules.director import layout, scriptshape
from tests.engine.test_media_characters import png_bytes
from tests.engine.test_script_shape import FIXTURE
from tests.engine.test_script_tools import Ctx, Model, call, on_disk, refused

LONG = "Character 8 the Words of Words and Words Words"


def _member(name: str, home: int) -> dict:
    return {"name": name, "look": f"{name}'s look", "costume": "A suit", "ignore": "The background", "home": home}


@pytest.fixture
def ctx(tmp_path: Path) -> Ctx:
    made = Ctx(tmp_path)
    for name in ("Character 8", "Character 5", "Character 10", "One Two", "Three Two", "One", LONG):
        (tmp_path / "Characters" / f"{name}.png").write_bytes(png_bytes())
    return made


async def _show(ctx: Ctx, cast: list[str], cameras: list[str], scenes: list[list[str]] | None = None) -> None:
    """Script 1: the context `cast` (the first owns the Mug); scene 1 cast `cast` with a shot per camera; then a scene
    per further cast in `scenes`, one shot each."""
    context = {"cast": [_member(n, 10 + 10 * i) for i, n in enumerate(cast)],
             "set": {"name": "The stage", "description": "A bare stage", "elements": ["Table"],
                     "props": [{"name": "Mug", "owner": cast[0], "description": "A white mug"}]},
             "style": "Bright light"}
    ctx.model = Model(json.dumps(context))
    await call(ctx, "script_start", {"name": "Script 1", "story": " and ".join(cast)})
    for n, members in enumerate([cast, *(scenes or [])], 1):
        await call(ctx, "scene_add", {"title": f"Scene {n}", "cast": members})
        for camera in cameras if n == 1 else ["Wide"]:
            await call(ctx, "shot_add", {"scene": n, "camera": camera})


def _poses(script: dict, who: str) -> list[str]:
    return [ev["id"] for sc in script["scenes"] for shot in sc["shots"] for ev in shot["events"]
            if ev["kind"] == "pose" and ev["character"] == who]


def _named(script: dict, who: str) -> bool:
    """Whether any context member, scene cast place or pose still names `who`."""
    return (any(m["name"] == who for m in script["context"]["cast"])
            or any(who in sc["cast"] for sc in script["scenes"]) or bool(_poses(script, who)))


async def test_a_member_with_no_line_is_removed_in_one_call(ctx: Ctx) -> None:
    await _show(ctx, ["Character 5", "Character 7", "Character 8"], ["Wide shot of the stage"])
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 5", "pose": "point", "start_ms": 500})
    poses = _poses(on_disk(ctx), "Character 5")
    assert len(poses) == 2, "the Hub's keyframe at the shot's start and the Director's pose"
    done = await call(ctx, "context_set", {"cast": [{"name": "Character 5", "remove": True}]})
    assert done["state"][1] == (f"context · removed Character 5 · poses {', '.join(poses)} · scenes 1 · props Mug · "
                                "cast Character 7, Character 8 · set The stage · style")
    script = on_disk(ctx)
    assert not _named(script, "Character 5") and script["context"]["set"]["props"][0] == {
        "name": "Mug", "owner": None, "description": "A white mug"}


async def test_a_member_with_a_line_is_refused_until_it_is_removed(ctx: Ctx) -> None:
    await _show(ctx, ["Character 7", "Character 8"], ["Wide shot of the stage"])
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 8", "words": "Thank you, friend."})
    got = await refused(ctx, "context_set", {"cast": [{"name": "Character 8", "remove": True}]})
    assert got == {"problem": "Character 8 still has lines",
                   "fix": "Remove those lines with event_remove, then send this again", "hints": {"lines": ["l1"]}}
    await call(ctx, "event_remove", {"id": "l1"})
    done = await call(ctx, "context_set", {"cast": [{"name": "Character 8", "remove": True}]})
    assert done["state"][1].startswith("context · removed Character 8 · poses ")
    assert not _named(on_disk(ctx), "Character 8")


async def test_a_shot_the_members_pose_held_open_closes(ctx: Ctx) -> None:
    await _show(ctx, ["Character 7", "Character 5"], ["Wide shot of the stage", "Close on Character 7"])
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 5", "pose": "point", "start_ms": 1500})
    s1, s2 = on_disk(ctx)["scenes"][0]["shots"]
    assert s1["end_ms"] == s1["start_ms"] + 2500 == s2["start_ms"], "held open one second past the member's pose"
    await call(ctx, "context_set", {"cast": [{"name": "Character 5", "remove": True}]})
    s1, s2 = on_disk(ctx)["scenes"][0]["shots"]
    assert s1["end_ms"] == s1["start_ms"] + layout.SHOT_MIN_MS == s2["start_ms"]


async def test_a_scene_whose_only_cast_the_member_was_has_none(ctx: Ctx) -> None:
    await _show(ctx, ["Character 7", "Character 5"], ["Wide shot of the stage"], scenes=[["Character 5"]])
    await call(ctx, "context_set", {"cast": [{"name": "Character 5", "remove": True}]})
    script = on_disk(ctx)
    assert script["scenes"][1]["cast"] == [] and scriptshape.read(copy.deepcopy(script), {"character 7"})
    got = await refused(ctx, "line_add", {"shot": "s2", "speaker": "Character 7", "words": "Hello there."})
    assert got["problem"] == "Character 7 is not in scene 2's cast" and got["hints"]["valid_speakers"] == []


def test_a_version_1_scene_with_no_cast_is_refused() -> None:
    script = json.loads(FIXTURE.read_text(encoding="utf-8"))
    del script["context"]
    script["version"], script["scenes"][0]["cast"] = 1, []
    with pytest.raises(Invalid) as e:
        scriptshape.read(script, {"character 7", "character 6"})
    assert e.value.text == "Scene 1: the cast is a list of 1 or more names"


async def _cameras(ctx: Ctx, cast: list[str], cameras: list[str], old: str, to: str) -> list[str]:
    await _show(ctx, cast, cameras)
    done = await call(ctx, "context_set", {"cast": [{"name": old, "to": to}]})
    assert done["state"][1].startswith(f"context · {old} → {to} · ")
    return [shot["camera"]["framing"] for shot in on_disk(ctx)["scenes"][0]["shots"]]


async def test_a_rename_renames_the_camera_words(ctx: Ctx) -> None:
    got = await _cameras(ctx, ["Character 7", "Character 8"],
                         ["Close on Character 8, Character 7 behind", "The Character 8ian ship"],
                         "Character 8", "Character 6")
    assert got == ["Close on Character 6, Character 7 behind", "The Character 8ian ship"]


async def test_a_rename_matches_the_name_as_written(ctx: Ctx) -> None:
    got = await _cameras(ctx, ["Character 7", "Character 5"], ["a character 5's kitchen, Character 5 at the stove"],
                         "Character 5", "Character 10")
    assert got == ["a character 5's kitchen, Character 10 at the stove"]


async def test_a_rename_follows_the_first_word(ctx: Ctx) -> None:
    got = await _cameras(ctx, ["One Two", "Character 6"], ["One Two waves; close on One"], "One Two", "Three Two")
    assert got == ["Three Two waves; close on Three"]


async def test_a_first_word_another_member_holds_is_left(ctx: Ctx) -> None:
    got = await _cameras(ctx, ["One Two", "One"], ["One Two waves; close on One"], "One Two", "Three Two")
    assert got == ["Three Two waves; close on One"]


async def test_a_camera_past_300_characters_is_written(ctx: Ctx) -> None:
    camera = "Close on Character 8 " + "x" * 270                     # no length cap of the Hub's
    await _show(ctx, ["Character 7", "Character 8"], ["Wide", camera])
    await call(ctx, "context_set", {"cast": [{"name": "Character 8", "to": LONG}]})
    written = on_disk(ctx)["scenes"][0]["shots"][1]["camera"]
    framing = written["framing"] if isinstance(written, dict) else written
    assert framing == f"Close on {LONG} " + "x" * 270 and len(framing) > 300
