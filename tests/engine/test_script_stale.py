"""Sketch panels kept current (`hub/modules/director/stale.py`, `frame.change`, `landing.write`, `drawing.py`): on
`test_script_tools`'s context with its shots drawn, `event_change` of a shot's camera changes it and marks that shot's
panels stale and no other; a field a shot does not have or a blank camera refused, the file untouched, a camera of any
length written; a line's `event_change` and its correction as before; an element marks every scene's panels, a costume,
the style and a scene's length none, a rename the panels it stands in; a pose its own moment and the later ones it
holds; a moved panel and an undrawn one never; the loop redraws a stale panel after the job running, in script order; a
change while a job runs makes its finish stale; a stale panel gone from Media is not drawn and not stale;
`script_read`'s stale lines."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hub.modules.director import drawing, panels, sketch
from tests.engine.test_script_drawing import DrawCtx, finished
from tests.engine.test_script_tools import NINE, call, framed, on_disk, refused

NO_SET = "the context has no set"


@pytest.fixture
async def ctx(tmp_path: Path) -> Any:
    """As `test_script_drawing.py`'s: the loop stopped, nothing waiting or failed."""
    await drawing.stop()
    drawing.waiting.clear()
    drawing.failed.clear()
    yield DrawCtx(tmp_path)
    await drawing.stop()


def panel(ctx: DrawCtx, ident: str) -> dict:
    return panels.find(on_disk(ctx), ident)[2]


def stale(ctx: DrawCtx) -> list[str]:
    return [p["id"] for _, _, p in panels.panels(on_disk(ctx)) if p["stale"]]


async def draw_all(ctx: DrawCtx) -> None:
    """Every panel the loop takes drawn, each its own picture `out/d/<panel>-<job>.png`."""
    for _ in range(20):
        await drawing.step(ctx)
        held = drawing.busy()
        if held is None:
            return
        await drawing.on_finished(ctx, finished(ctx, "done", f"out/d/{held['panel']}-{held['job']}.png"))
    raise AssertionError("the loop never stopped")


async def drawn_script(ctx: DrawCtx, second_scene: bool = False) -> None:
    """Script 1: scene 1 (Character 7, Character 6) with s1 and s2, Character 7's line in s1; scene 2 (Character 7)
    with s3; all drawn."""
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    if second_scene:
        await call(ctx, "scene_add", {"title": "The table", "cast": ["Character 7"]})
        await call(ctx, "shot_add", {"scene": 2, "camera": "Character 7 at the table"})
    await draw_all(ctx)
    assert all(p["picture"] for _, _, p in panels.panels(on_disk(ctx))) and not stale(ctx)


async def test_a_shots_camera_changed_marks_its_panels_alone(ctx: DrawCtx) -> None:
    await drawn_script(ctx)
    got = await call(ctx, "event_change", {"id": "s2", "fields": {"camera": "Close shot on Character 6"}})
    assert got["state"][1] == "shot 2, s2: Close on Character 6 · changed shot s2 · camera Close shot on Character 6"
    held = next(s for s in on_disk(ctx)["scenes"][0]["shots"] if s["id"] == "s2")
    assert held["camera"]["framing"] == "Close shot on Character 6"
    assert stale(ctx) == ["f2"] and panel(ctx, "f2")["picture"].startswith("out/d/f2-")


async def test_a_shot_field_other_than_camera_or_a_blank_camera_is_refused(ctx: DrawCtx) -> None:
    await drawn_script(ctx)
    got = await refused(ctx, "event_change", {"id": "s2", "fields": {"start_ms": 5}})
    assert got == {"problem": "A shot has no field start_ms",
                   "fix": "Change a shot's camera, its seconds or its action",
                   "hints": {"fields": ["camera", "seconds", "action"]}}  # the held length, the action
    got = await refused(ctx, "event_change", {"id": "s2", "fields": {"camera": " "}})
    assert got["problem"] == "A shot's camera is text, not blank" and got["hints"] == {"fields": ["camera"]}
    await call(ctx, "event_change", {"id": "s2", "fields": {"camera": "x" * 301}})     # any length
    assert on_disk(ctx)["scenes"][0]["shots"][1]["camera"] == {"framing": "x" * 301}


async def test_a_lines_change_answers_and_corrects_as_before(ctx: DrawCtx) -> None:
    await drawn_script(ctx)
    got = await call(ctx, "event_change", {"id": "l1", "fields": {"words": "Good evening."}})
    assert got["state"][1].startswith("Character 7's 1st line, l1: Line one opens here,… · changed line l1")
    words = " ".join([NINE] * 5).split()
    no = await refused(ctx, "event_change", {"id": "l1", "fields": {"words": " ".join(words)}})
    await call(ctx, "event_change", {"id": "l1", "fields": {"words": " ".join(words[:no["hints"]["max_words"]])}})
    assert not stale(ctx), "a line's words are not in a sketch; its moved panels are not stale"


async def test_a_costume_the_style_and_a_length_mark_none_a_rename_its_panels_an_element_all(ctx: DrawCtx) -> None:
    await drawn_script(ctx, second_scene=True)
    await call(ctx, "scene_change", {"scene": 1, "seconds": 12})
    await call(ctx, "context_set", {"cast": [{"name": "Character 6", "costume": "A green coat"}]})
    await call(ctx, "context_set", {"style": "A grainy colour look"})
    assert not stale(ctx), "a scene's length, a costume and the style are not in a sketch"
    cast = ctx.data_dir.parent.parent / "Characters"
    (cast / "Character 9.png").write_bytes((cast / "Character 6.png").read_bytes())
    await call(ctx, "context_set", {"cast": [{"name": "Character 6", "to": "Character 9"}]})
    named = [p["id"] for _, shot, p in panels.panels(on_disk(ctx)) if "Character 9" in sketch_text(ctx, shot, p)]
    assert named and stale(ctx) == named, "the name as written is in the sketch of each one in frame"
    await call(ctx, "context_set", {"set": {"elements": ["Table", "Two chairs"]}})
    assert stale(ctx) == ["f1", "f2", "f3"], "an element is in every scene's sketch"


def sketch_text(ctx: DrawCtx, shot: dict, panel: dict) -> str:
    script = on_disk(ctx)
    scene = next(sc for sc in script["scenes"] if any(s["id"] == shot["id"] for s in sc["shots"]))
    return sketch.prompt(script, scene, shot, panel["at_ms"])[0] or ""


async def test_a_pose_changed_marks_the_moments_it_holds(ctx: DrawCtx) -> None:
    await drawn_script(ctx)
    await call(ctx, "pose_add", {"shot": "s2", "character": "Character 6", "pose": "sit", "start_ms": 500})
    await call(ctx, "pose_add", {"shot": "s2", "character": "Character 7", "pose": "point", "start_ms": 1500})
    await call(ctx, "pose_add", {"shot": "s2", "character": "Character 6", "pose": "point", "start_ms": 2500})
    await draw_all(ctx)
    ids = [(p["id"], p["at_ms"]) for _, shot, p in panels.panels(on_disk(ctx)) if shot["id"] == "s2"]
    assert len(ids) == 4 and not stale(ctx), ids
    sit = next(e["id"] for s in on_disk(ctx)["scenes"][0]["shots"] for e in s["events"] if e.get("pose") == "sit")
    await call(ctx, "event_change", {"id": sit, "fields": {"pose": "turn"}})
    assert stale(ctx) == [ids[1][0], ids[2][0]], \
        "its own and Character 7's later one, not before it, not after the next one"


async def test_a_moved_panel_and_an_undrawn_one_are_never_marked(ctx: DrawCtx) -> None:
    await drawn_script(ctx)
    at = panel(ctx, "f2")["at_ms"]
    await call(ctx, "event_change", {"id": "l1", "fields": {"words": NINE + " " + NINE}})
    assert panel(ctx, "f2")["at_ms"] > at and not stale(ctx)
    await call(ctx, "shot_add", {"scene": 1, "camera": "Wide on the table"})
    await drawing.step(ctx)                                          # f3 added, its job submitted
    await call(ctx, "context_set", {"set": {"elements": ["Table", "Two chairs"]}})
    assert panel(ctx, "f3")["picture"] is None and not panel(ctx, "f3")["stale"]
    assert stale(ctx) == ["f1", "f2"]


async def test_the_stale_panel_is_redrawn_after_the_running_job_in_script_order(ctx: DrawCtx) -> None:
    await framed(ctx)
    await drawing.step(ctx)
    await drawing.on_finished(ctx, finished(ctx, "done", "out/d/f1-old.png"))
    await drawing.step(ctx)
    assert drawing.busy()["panel"] == "f2"
    await call(ctx, "event_change", {"id": "s1", "fields": {"camera": "Close on Character 7"}})
    assert stale(ctx) == ["f1"]
    await drawing.step(ctx)
    assert [j.params["panel"] for j in ctx.jobs.made] == ["f1", "f2"], "the job running is never cancelled"
    read = (await call(ctx, "script_read", {}))["read"]
    assert read[-2].endswith("· stale out/d/f1-old.png") and read[-1].endswith("· drawing")
    await drawing.on_finished(ctx, finished(ctx, "done", "out/d/f2.png"))
    assert panel(ctx, "f2") == {**panel(ctx, "f2"), "picture": "out/d/f2.png", "stale": False}
    await drawing.step(ctx)
    assert ctx.jobs.made[-1].params["panel"] == "f1" and "Close on Character 7. " in ctx.jobs.made[-1].params["prompt"]
    read = (await call(ctx, "script_read", {}))["read"]
    assert read[-2].endswith("· drawing (stale out/d/f1-old.png)")
    await drawing.on_finished(ctx, finished(ctx, "done", "out/d/f1-new.png"))
    assert panel(ctx, "f1")["picture"] == "out/d/f1-new.png" and not stale(ctx)
    assert (ctx.files.roots["out"] / "d" / "f1-old.png").exists(), "the old sketch stays in Temp"


async def test_a_change_while_its_job_runs_makes_the_finish_stale(ctx: DrawCtx) -> None:
    await framed(ctx)
    await drawing.step(ctx)
    await call(ctx, "event_change", {"id": "s1", "fields": {"camera": "Close on Character 7"}})
    assert not stale(ctx), "no picture yet: nothing marked"
    await drawing.on_finished(ctx, finished(ctx, "done", "out/d/f1-old.png"))
    assert panel(ctx, "f1")["picture"] == "out/d/f1-old.png" and stale(ctx) == ["f1"]
    await drawing.step(ctx)
    assert [j.params["panel"] for j in ctx.jobs.made] == ["f1", "f1"]


async def test_a_stale_panel_gone_from_media_is_not_drawn_and_not_stale(ctx: DrawCtx) -> None:
    await drawn_script(ctx)
    await call(ctx, "event_change", {"id": "s2", "fields": {"camera": "Close shot on Character 6"}})
    gone = panel(ctx, "f2")["picture"]
    (ctx.files.roots["out"] / gone.split("/", 1)[1]).unlink()
    await drawing.step(ctx)
    assert panel(ctx, "f2")["picture"] is None and not panel(ctx, "f2")["stale"]


async def test_a_stale_panel_whose_prompt_is_not_whole_waits_with_the_reason(ctx: DrawCtx) -> None:
    await drawn_script(ctx)
    path = ctx.files.roots["scripts"] / "Script 1.json"
    held: Any = json.loads(path.read_text())
    del held["context"]["set"]
    for shot in held["scenes"][0]["shots"]:
        for ev in shot["events"]:
            if ev["kind"] == "panel" and ev["id"] == "f2":
                ev["stale"] = True
    path.write_text(json.dumps(held))
    read = (await call(ctx, "script_read", {}))["read"]
    assert read[-1].endswith(f"· stale {panel(ctx, 'f2')['picture']} · waiting: {NO_SET}")
    await drawing.step(ctx)
    assert drawing.busy() is None
