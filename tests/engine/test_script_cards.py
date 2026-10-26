"""Edits on the cards and shots: what a box holds is what render sends; a stretched shot moves the next; one
shot rendered alone. Neutral words only (CLAUDE.md)."""
from __future__ import annotations

import json
from typing import Any

from hub.modules.director import frame, owner, render, routes, tools
from tests.engine.helpers import FakeRequest
from tests.engine.test_script_render import cat, ctx, two_shots  # noqa: F401  (the fixtures)
from tests.engine.test_script_render import edit as render_edit


def held(c: Any) -> dict:
    return json.loads((routes.folder(c) / "Script 1.json").read_text(encoding="utf-8"))


async def press(c: Any, **more: Any) -> dict:
    render.running.clear()                               # the job before ended
    return await routes.post_render(c, FakeRequest(body=json.dumps({"name": "Script 1", **more}).encode()))


async def edit(c: Any, **op: Any) -> dict:
    return await owner.edit_op(c, {"name": "Script 1", **op})


async def test_each_card_field_the_user_types_is_what_renders(ctx: Any) -> None:  # noqa: F811
    await two_shots(ctx)
    who = held(ctx)["context"]["cast"][0]["name"]
    for field, value in (("look", "look 1"), ("costume", "costume 1"), ("ignore", "ignore 1"), ("home", "40")):
        assert "problem" not in await edit(ctx, op="member", member=who, field=field, value=value)
    for field, value in (("name", "set 1"), ("description", "description 1"), ("elements", "element 1, element 2"),
                         ("props", "prop 1: words 1\nprop 2"), ("style", "style 1")):
        assert "problem" not in await edit(ctx, op="set", field=field, value=value)
    got = await press(ctx)
    text = ctx.jobs.get(got["job"]).plan.tasks[0]["prompt"]
    for want in ("look 1. costume 1.", "set 1. description 1. element 1. element 2. prop 1. words 1. prop 2.",
                 "style 1"):
        assert want in text, (want, text)
    for gone in ("Ignore:", "ignore 1", "Home:", "40", "Props:"):
        assert gone not in text, (gone, text)                     # they stay on the card
    for field in ("costume", "ignore"):
        await edit(ctx, op="member", member=who, field=field, value="")
    await edit(ctx, op="set", field="props", value="")
    got = await press(ctx)
    text = ctx.jobs.get(got["job"]).plan.tasks[0]["prompt"]
    for gone in ("costume 1", "ignore 1", "prop 1"):
        assert gone.casefold() not in text.casefold(), (gone, text)
    assert await edit(ctx, op="member", member=who, field="home", value="x") == {
        "problem": "Home is a whole number from 0 to 100"}


async def test_a_shot_stretched_moves_the_next_and_renders_alone(ctx: Any) -> None:  # noqa: F811
    await two_shots(ctx)
    first, second = held(ctx)["scenes"][0]["shots"][:2]
    got = await edit(ctx, op="change", id=first["id"], fields={"camera": {"framing": "framing 1"}, "action": "action 1",
                                                                "seconds": 12})
    assert "problem" not in got, got
    a, b = held(ctx)["scenes"][0]["shots"][:2]
    assert a["end_ms"] - a["start_ms"] >= 12_000 and b["start_ms"] == a["end_ms"], (a, b)
    assert b["start_ms"] - second["start_ms"] == a["end_ms"] - first["end_ms"], "the next shot moved by the stretch"
    got = await press(ctx, shot=a["id"])
    assert got.get("shots") == 1, got
    tasks = ctx.jobs.get(got["job"]).plan.tasks
    assert len(tasks) == 1 and "action 1" in tasks[0]["prompt"].casefold(), tasks


async def test_a_held_shot_in_a_named_full_scene_stretches_and_deletes(ctx: Any) -> None:  # noqa: F811
    await two_shots(ctx)
    for _ in range(3):                                   # wordless shots, each held 6 s
        got = await edit(ctx, op="add_shot", scene=1, camera={"framing": "framing 2"}, seconds=6)
        assert "problem" not in got, got
    script = held(ctx)
    scene = script["scenes"][0]
    scene["seconds"] = round((scene["shots"][-1]["end_ms"] - scene["shots"][0]["start_ms"]) / 1000)
    (routes.folder(ctx) / "Script 1.json").write_text(json.dumps(script), encoding="utf-8")
    last = scene["shots"][-1]
    got = await edit(ctx, op="change", id=scene["shots"][-2]["id"], fields={"seconds": 12})
    assert "problem" not in got, got
    after = held(ctx)["scenes"][0]
    assert "seconds" not in after, "the edit freed the named length"
    assert after["shots"][-1]["end_ms"] - last["end_ms"] == 6_000, "the shot after moved 6 s"
    got = await edit(ctx, op="remove", id=after["shots"][0]["id"])     # a shot with lines in it
    assert "problem" not in got, got
    assert len(held(ctx)["scenes"][0]["shots"]) == len(after["shots"]) - 1


async def test_an_emptied_action_or_move_is_taken_off(ctx: Any) -> None:  # noqa: F811
    await two_shots(ctx)
    sid = held(ctx)["scenes"][0]["shots"][0]["id"]
    assert "problem" not in await edit(ctx, op="change", id=sid, fields={"action": "action 1"})
    assert "problem" not in await edit(ctx, op="change", id=sid, fields={"action": ""})
    camera = {"framing": "framing 1", "move": ""}
    assert "problem" not in await edit(ctx, op="change", id=sid, fields={"camera": camera})
    shot = held(ctx)["scenes"][0]["shots"][0]
    assert "action" not in shot and shot["camera"] == {"framing": "framing 1"}, shot


async def test_render_this_shot_joins_the_video_again(ctx: Any, monkeypatch: Any) -> None:  # noqa: F811
    await two_shots(ctx)
    got = await press(ctx)
    made = []
    for stem in ("x1", "x2", "x3"):
        path = ctx.files.roots["clips"] / "2026-10-21" / f"{stem}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x00" * 64)
        made.append(f"clips/2026-10-21/{stem}.mp4")
    await ctx.jobs.get(got["job"]).plan.finish({1: made[0], 2: made[1], 3: made[2]})
    kept = ctx.doc("shotclips", {}).get()["Script 1"]
    assert set(kept) == {"s1", "s2"}, kept
    monkeypatch.setattr(ctx.files, "clip_facts", lambda item: {"w": 640, "h": 360, "fps": 24.0, "frames": 97,
                                                                "audio": True})
    got = await press(ctx, shot="s2")
    plan = ctx.jobs.get(got["job"]).plan
    assert len(plan.tasks) == 2, "the shot's clip, then the join"
    join = json.loads(plan.tasks[1]) if isinstance(plan.tasks[1], str) else plan.tasks[1]
    assert str(ctx.files.existing_media(kept["s1"])) in json.dumps(join), join
    assert plan.inputs[-1] == {"items.1.path": (1, "kept")}, plan.inputs[-1]
    assert plan.summary["step_names"][-1].startswith("Join")


async def test_the_typed_video_length_is_written_and_nothing_sent_back(ctx: Any) -> None:  # noqa: F811
    from hub.modules.director import length, say
    await two_shots(ctx)
    assert "problem" not in await edit(ctx, op="length", seconds=180)
    scene = held(ctx)["scenes"][0]
    assert scene["seconds"] == 180 and length.length(scene) < 162_000, "the shots stay as they are"
    assert not hasattr(say, "short"), "a short scene is reported, never sent back"


async def test_a_pasted_h3_prompt_goes_to_the_clip_as_pasted(ctx: Any) -> None:  # noqa: F811
    pasted = ("subject_definitions: <Subject 1> is the person in <Picture 1>.\nsummary: " + "word " * 300 +
              "\nretention_analysis: N/A\ndetailed_description: [Shot 1] 0:00-0:03 one\noverall_soundscape: N/A\n"
              "non_diegetic_music: N/A")
    await two_shots(ctx)
    sid = held(ctx)["scenes"][0]["shots"][0]["id"]
    assert "problem" not in await edit(ctx, op="change", id=sid, fields={"action": pasted})
    got = await press(ctx)
    assert ctx.jobs.get(got["job"]).plan.tasks[0]["prompt"] == pasted.strip()


async def test_a_shot_s_own_pictures_are_its_pictures_in_order(ctx: Any) -> None:  # noqa: F811
    from PIL import Image

    from hub.modules.director import shotpics
    await two_shots(ctx)
    day = ctx.files.roots["out"] / "2026-10-21"
    day.mkdir(parents=True, exist_ok=True)
    ids = []
    for k in (1, 2):
        Image.new("RGB", (64, 64), (k * 40, 0, 0)).save(day / f"10101{k}-000.png")
        ids.append(f"out/2026-10-21/10101{k}-000.png")
    sid = held(ctx)["scenes"][0]["shots"][1]["id"]
    assert "problem" not in shotpics.put(ctx, "Script 1", sid, ids)
    got = await press(ctx)
    refs = [[str(r.get("path")).split("/")[-1] for r in t.get("references") or []]
            for t in ctx.jobs.get(got["job"]).plan.tasks if isinstance(t, dict)]
    assert ["101011-000.png", "101012-000.png"] in refs, refs


PASTED = """subject_definitions: <Subject 1> is the person in <Picture 1>. <Subject 2> is the place in <Picture 2>.
summary: summary 1
retention_analysis: <Subject 1> (appears in [Shot 1]): fully_preserved - look 1
detailed_description: [Shot 1] 0:00-0:03 <Subject 1> does action 1. 0:03–0:05 <Subject 1> does action 2.
overall_soundscape: sound 1
non_diegetic_music: N/A"""


async def test_an_imported_prompt_becomes_one_shot_per_time_range(ctx: Any) -> None:  # noqa: F811
    await two_shots(ctx)
    before = len(held(ctx)["scenes"][0]["shots"])
    got = await edit(ctx, op="import", text=PASTED)
    assert "problem" not in got, got
    shots = held(ctx)["scenes"][0]["shots"][before:]
    assert [s["seconds"] for s in shots] == [3, 2]
    one, two = (s["action"] for s in shots)
    assert one.startswith("subject_definitions: <Subject 1> is the person in <Picture 1>.")
    assert "summary: summary 1" in one
    assert "detailed_description: [Shot 1] 0:00-0:03 <Subject 1> does action 1." in one and "action 2" not in one
    assert "detailed_description: [Shot 1] 0:00-0:02 <Subject 1> does action 2." in two and "action 1" not in two
    assert "overall_soundscape: sound 1" in two and "non_diegetic_music: N/A" in two
    bad = await edit(ctx, op="import", text="detailed_description: no fields")
    assert bad == {"problem": "A MiniMax H3 prompt starts with subject_definitions:"}, bad


async def test_a_video_length_shorter_than_the_scenes_before_writes_nothing(ctx: Any) -> None:  # noqa: F811
    """The op `length` at or below what the scenes before the last run: nothing written, one line."""
    await two_shots(ctx)
    await tools._write(ctx, lambda s, c, ch: frame.scene_add(s, {"title": "Scene two", "cast": ["A"]}), None,
                       "Script 1")
    assert "problem" not in await render_edit(ctx, "add_shot", scene=2, camera={"framing": "Wide"})
    path = routes.folder(ctx) / "Script 1.json"
    second = json.loads(path.read_text(encoding="utf-8"))["scenes"][1]["shots"][0]["start_ms"] // 1000
    before = path.read_bytes()
    got = await owner.edit_op(ctx, {"name": "Script 1", "op": "length", "seconds": second})
    assert got == {"problem": owner.SHORT.format(second)}
    assert path.read_bytes() == before, "the file byte for byte unchanged"
    assert "problem" not in await owner.edit_op(ctx, {"name": "Script 1", "op": "length", "seconds": second + 4})
    assert json.loads(path.read_text(encoding="utf-8"))["scenes"][1]["seconds"] == 4, "as typed, less the scenes before"
