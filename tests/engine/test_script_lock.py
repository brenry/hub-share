"""The lock (`hub/modules/director/lock.py`, `lockpress.script_lock`, `lockpress.script_unlock`): on
`test_script_tools`'s context with a stand-in Characters and voice samples, `script_lock` is the press: the script is
locked whatever its scenes say, no scene marked done, and Track is pressed (refused here: no Generate); a line missing a
voice field mended at the press; locked, the drawing writes nothing, a write lands and unlocks it; no head says ` ·
locked`; `script_unlock` clears the record and keeps `done`."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.director import drawing, panels, tools
from tests.engine.test_script_drawing import DrawCtx
from tests.engine.test_script_stale import draw_all
from tests.engine.test_script_tools import NINE, call, on_disk, started
from tests.fakes.wav import tiny_wav

THANKS = "Thank you, friend. It is lovely to be here."
REFUSED = "Generate Image is not running"                              # the stand-in has no Generate


@pytest.fixture
async def ctx(tmp_path: Path) -> Any:
    await drawing.stop()
    drawing.waiting.clear()
    drawing.failed.clear()
    held = DrawCtx(tmp_path)
    for name in ("Character 7", "Character 6"):
        (tmp_path / "Characters" / f"{name}.wav").write_bytes(tiny_wav(2.5, rate=8000))   # 2 s or more
    yield held
    await drawing.stop()
    drawing.waiting.clear()


def path(ctx: DrawCtx) -> Path:
    return ctx.files.roots["scripts"] / "Script 1.json"


def put(ctx: DrawCtx, script: dict) -> None:
    path(ctx).write_text(json.dumps(script), encoding="utf-8")


async def whole(ctx: DrawCtx) -> None:
    """Script 1: scene 1 (Character 7, Character 6), shot s1 on both, Character 7's l1 and Character 6's l2 with every
    field; all drawn."""
    await started(ctx)
    await call(ctx, "scene_add", {"title": "The opening", "cast": ["Character 7", "Character 6"]})
    await call(ctx, "shot_add", {"scene": 1, "camera": {"framing": "Wide shot of the stage",
                                                        "on": ["Character 7", "Character 6"]}})
    for who, words in (("Character 7", NINE), ("Character 6", THANKS)):
        await call(ctx, "line_add", {"shot": "s1", "speaker": who, "words": words, "language": "English",
                                     "emotion": "warm", "pace": 2.6})
    await draw_all(ctx)


async def pressed(ctx: DrawCtx) -> dict:
    """`script_lock` refused by Track (no Generate here): its {problem, fix, hints}."""
    with pytest.raises(Invalid) as e:
        await call(ctx, "script_lock", {})
    return json.loads(e.value.text)


def edited(ctx: DrawCtx) -> dict:
    return on_disk(ctx)


def line(script: dict, ident: str) -> dict:
    return next(ev for shot in script["scenes"][0]["shots"] for ev in shot["events"] if ev["id"] == ident)


def keyframe(script: dict, who: str, ms: int) -> dict:
    shot = script["scenes"][0]["shots"][0]
    return next(ev for ev in shot["events"] if ev["kind"] == "pose" and ev["character"] == who and ev["start_ms"] == ms)


async def test_a_whole_script_locks_and_a_write_on_it_lands(ctx: DrawCtx) -> None:
    await whole(ctx)
    script = edited(ctx)
    l2 = line(script, "l2")
    shot = script["scenes"][0]["shots"][0]
    assert not any(ev["kind"] == "pose" and ev["start_ms"] == l2["end_ms"] for ev in shot["events"]), \
        "l2 closes its shot: no end keyframe"
    sent = len(ctx.bus.sent)
    assert (await pressed(ctx))["problem"] == REFUSED
    held = edited(ctx)["lock"]
    assert held["locked"] is True and isinstance(held["at"], str) and "T" in held["at"]
    assert not any("done" in sc for sc in edited(ctx)["scenes"]), "no scene marked done"
    assert len(ctx.bus.sent) == sent + 1, "the lock, one write"
    read = await call(ctx, "script_read", {})
    assert not read["read"][0].endswith(" · locked"), "no head says locked"
    before = path(ctx).read_bytes()
    assert (await pressed(ctx))["problem"] == REFUSED and path(ctx).read_bytes() == before
    gone = ctx.files.roots["out"] / "d"
    for item in gone.iterdir():
        item.unlink()                                 # every picture gone from Media: fill would forget them
    f1 = panels.panels(edited(ctx))[0][2]["id"]
    await tools.fill(ctx)
    await tools.drawn(ctx, "Script 1", f1, "out/d/new.png")
    assert path(ctx).read_bytes() == before, "the drawing writes nothing to a locked script"
    await draw_all(ctx)
    done = await call(ctx, "event_change", {"id": "l1", "fields": {"emotion": "calm"}})   # no "locked" in the answer
    assert line(edited(ctx), "l1")["emotion"] == "calm" and edited(ctx)["lock"]["locked"] is False
    assert not done["state"][0].endswith(" · locked")
    scene = await call(ctx, "scene_change", {"scene": 1, "done": True})
    assert edited(ctx)["scenes"][0]["done"] is True and not any("gap" in x for x in scene["state"])
    assert (await pressed(ctx))["problem"] == REFUSED and edited(ctx)["lock"]["locked"] is True
    done = await call(ctx, "script_unlock", {})
    assert done["state"][1] == "unlocked" and not any("paused" in x for x in done["state"])
    assert edited(ctx)["lock"] == {"locked": False, "at": None}
    assert edited(ctx)["scenes"][0]["done"] is True, "done untouched"
    assert (await call(ctx, "script_unlock", {}))["state"][1] == "no record to clear"
    done = await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": "Hello."})
    assert done["state"][1].startswith("line l3 · Character 7") and not edited(ctx)["lock"]["locked"]


async def test_a_line_without_language_and_pace_gets_the_pace_alone(ctx: DrawCtx) -> None:
    await whole(ctx)
    script = edited(ctx)
    line(script, "l1")["language"] = "German"
    del line(script, "l2")["language"], line(script, "l2")["pace"]
    put(ctx, script)                                              # l2 with no language and no pace
    got = await pressed(ctx)                                     # mended by the press
    assert got["problem"] == REFUSED and "gaps" not in got["hints"]
    held = line(edited(ctx), "l2")
    assert (held["emotion"], held["pace"]) == ("warm", 2.6) and "language" not in held, "the pace alone"


