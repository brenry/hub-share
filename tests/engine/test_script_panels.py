"""The sketch panels' places and prompts (`hub/modules/director/panels.py`, `sketch.py`, the take
and put of `tools._write`): a panel at each shot's start and at each pose-category change inside a shot; a panel follows
its cause through a write, its id and picture kept, and goes with its cause; the fill pass adds the missing ones once;
`script_read` lists them; the prompt holds the context alone, in blueprint A.6's order, with no name in it."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hub.modules.director import drawing, panels, sketch, tools
from tests.engine.test_media_characters import png_bytes
from tests.engine.test_script_tools import CONTEXT, NINE, Ctx, call, framed, on_disk


@pytest.fixture
def ctx(tmp_path: Path) -> Ctx:
    drawing._state.update(ctx=None, event=None, task=None, busy=None)
    drawing.waiting.clear()
    drawing.failed.clear()
    return Ctx(tmp_path)


def placed(script: dict) -> list[tuple[str, int, str]]:
    """[(shot id, offset from the shot's start, panel id)] in script order."""
    return [(shot["id"], p["at_ms"] - shot["start_ms"], p["id"]) for _, shot, p in panels.panels(script)]


def shot_of(script: dict, ident: str) -> dict:
    return next(s for sc in script["scenes"] for s in sc["shots"] if s["id"] == ident)


async def posed(ctx: Ctx) -> None:
    """Script 1, s1: Character 6 stands at 0 (the start), sits at 1.0 s, Character 7 stands at 1.0 s (that pose in force
    already); at 2.0 s Character 7 raises both arms and Character 6 stands: two changes at one instant. s2: Character 6
    stands and Character 7 raises both arms at 0.5 s, each the pose in force carried from s1."""
    await framed(ctx)
    for who, pose, at in (("Character 6", "stand", 0), ("Character 6", "sit", 1000), ("Character 7", "stand", 1000),
                          ("Character 7", "arms_raised", 2000), ("Character 6", "stand", 2000)):
        await call(ctx, "pose_add", {"shot": "s1", "character": who, "pose": pose, "start_ms": at})
    for who, pose in (("Character 6", "stand"), ("Character 7", "arms_raised")):
        await call(ctx, "pose_add", {"shot": "s2", "character": who, "pose": pose, "start_ms": 500})


async def test_the_causes_of_a_script_of_two_shots(ctx: Ctx) -> None:
    await posed(ctx)
    script = on_disk(ctx)
    assert placed(script) == [], "a tool write adds no panel"
    found = panels.causes(script)
    s1 = shot_of(script, "s1")
    assert [(c["shot"]["id"], c["at_ms"] - c["shot"]["start_ms"], c["start"], sorted(c["poses"])) for c in found] == [
        ("s1", 0, True, []), ("s1", 1000, False, ["p5"]), ("s1", 2000, False, ["p7", "p8"]), ("s2", 0, True, [])]
    scene = script["scenes"][0]
    assert panels.in_force(scene, s1, "character 6", s1["start_ms"] + 1500) == "sit"
    assert panels.in_force(scene, s1, "Character 6", s1["start_ms"] + 1000, strict=True) == "stand"
    s2 = shot_of(script, "s2")
    assert panels.in_force(scene, s2, "Character 7", s2["start_ms"]) == "arms_raised"


async def test_the_fill_pass_adds_the_missing_panels_once(ctx: Ctx) -> None:
    await posed(ctx)
    sent = len(ctx.bus.sent)
    await tools.fill(ctx)
    script = on_disk(ctx)
    assert placed(script) == [("s1", 0, "f1"), ("s1", 1000, "f2"), ("s1", 2000, "f3"), ("s2", 0, "f4")]
    assert all(p["picture"] is None and p["stale"] is False for _, _, p in panels.panels(script))
    assert len(ctx.bus.sent) == sent + 1 and ctx.bus.sent[-1][2]["name"] == "Script 1"
    before = (ctx.files.roots["scripts"] / "Script 1.json").read_bytes()
    await tools.fill(ctx)
    assert (ctx.files.roots["scripts"] / "Script 1.json").read_bytes() == before, "no write"
    assert len(ctx.bus.sent) == sent + 1, "no publish"
    await call(ctx, "event_remove", {"id": "p5"})                  # f2 goes with its cause
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 6", "pose": "sit", "start_ms": 1200})
    await tools.fill(ctx)
    assert placed(on_disk(ctx)) == [("s1", 0, "f1"), ("s1", 1200, "f5"), ("s1", 2000, "f3"), ("s2", 0, "f4")], \
        "ids never reused"


async def test_a_panel_follows_its_cause_and_goes_with_it(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": "Line one."})
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 6", "pose": "sit", "anchor": {"line": "l1",
                                                                                              "at": "end"}})
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 6", "pose": "point", "start_ms": 300})
    await tools.fill(ctx)
    await tools.drawn(ctx, "Script 1", "f2", "out/2026-10-19/a.png")
    script = on_disk(ctx)
    end = next(e for e in shot_of(script, "s1")["events"] if e["id"] == "l1")["end_ms"]
    assert placed(script) == [("s1", 0, "f1"), ("s1", 300, "f2"), ("s1", end, "f3"), ("s2", 0, "f4")]
    sent = len(ctx.bus.sent)
    await call(ctx, "event_change", {"id": "l1", "fields": {"words": NINE}})        # a push: l1 ends later
    script = on_disk(ctx)
    later = next(e for e in shot_of(script, "s1")["events"] if e["id"] == "l1")["end_ms"]
    assert later > end and placed(script) == [("s1", 0, "f1"), ("s1", 300, "f2"), ("s1", later, "f3"),
                                              ("s2", 0, "f4")]
    assert panels.find(script, "f2")[2]["picture"] == "out/2026-10-19/a.png"
    s2 = shot_of(script, "s2")
    assert panels.find(script, "f4")[2]["at_ms"] == s2["start_ms"], "the pushed shot's panel moves with it"
    assert len(ctx.bus.sent) == sent + 1, "one publish for the write"
    await call(ctx, "event_remove", {"id": "p7"})                                   # f2 goes with its pose
    assert placed(on_disk(ctx)) == [("s1", 0, "f1"), ("s1", later, "f3"), ("s2", 0, "f4")]
    await call(ctx, "event_change", {"id": "p6", "fields": {"pose": "stand"}})      # back to the pose in force
    assert placed(on_disk(ctx)) == [("s1", 0, "f1"), ("s2", 0, "f4")]


async def test_script_read_lists_each_panel(ctx: Ctx) -> None:
    await posed(ctx)
    await tools.fill(ctx)
    (ctx.files.roots["out"] / "2026-10-19").mkdir(parents=True)
    (ctx.files.roots["out"] / "2026-10-19" / "a.png").write_bytes(png_bytes())   # in Temp
    await tools.drawn(ctx, "Script 1", "f1", "out/2026-10-19/a.png")
    read = (await call(ctx, "script_read", {}))["read"]
    s2 = shot_of(on_disk(ctx), "s2")["start_ms"] / 1000
    assert read[-4:] == ["f1 panel s1 0.00 (script 0.00) · drawn out/2026-10-19/a.png",
                         "f2 panel s1 1.00 (script 1.00) · waiting", "f3 panel s1 2.00 (script 2.00) · waiting",
                         f"f4 panel s2 0.00 (script {s2:.2f}) · waiting"]
    assert not any(" panel " in line for line in read[:-4]), "the events as before"


def test_the_prompt_holds_the_context_alone_in_its_order() -> None:
    context = copy.deepcopy(CONTEXT)
    shot = {"id": "s2", "start_ms": 1000, "end_ms": 5000, "camera": "Close on Character 7 as Character 6 sits",
            "events": [{"id": "l1", "kind": "line", "start_ms": 1000, "end_ms": 3000, "speaker": "Character 7",
                        "words": "Thank you, friend."},
                       {"id": "c1", "kind": "cue", "start_ms": 1000, "end_ms": 3000, "cue": "reaction",
                        "words": "Applause"},
                       {"id": "p1", "kind": "pose", "start_ms": 2000, "end_ms": 5000, "character": "Character 6",
                        "pose": "sit"}]}
    scene = {"title": "The opening", "cast": ["Character 6", "Character 7"], "shots": [shot]}
    script = {"version": 2, "context": context, "scenes": [scene]}
    text, why = sketch.prompt(script, scene, shot, 2000)
    assert why is None and \
        text == "Close on Character 7 as Character 6 sits. The stage, Table. Character 7 stand. Character 6 sit."
    for absent in ("Thank you", "Applause", "Mug", "background", "chair", "scripted", "bare stage",
                   "tall figure", "navy", "in grey", "red dress"):
        assert absent.casefold() not in text.casefold()
    assert sketch.prompt(script, scene, shot, 1000)[0].endswith(". Character 6 stand."), "the pose at the panel's time"
    del context["cast"][1]["costume"]
    del context["set"]["description"]
    assert sketch.prompt(script, scene, shot, 2000) == (text, None), "no wait for a costume"
    del context["set"]
    assert sketch.prompt(script, scene, shot, 2000) == (None, "the context has no set")


async def test_a_member_without_a_costume_waits_with_that_reason(ctx: Ctx) -> None:
    await posed(ctx)
    path = ctx.files.roots["scripts"] / "Script 1.json"
    script = json.loads(path.read_text())
    del script["context"]["cast"][1]["costume"]
    path.write_text(json.dumps(script))
    await tools.fill(ctx)
    read = (await call(ctx, "script_read", {}))["read"]
    assert read[-1].endswith(" · waiting"), "a costume is waited for no more"
    del script["context"]["set"]
    path.write_text(json.dumps(script))
    await tools.fill(ctx)
    read = (await call(ctx, "script_read", {}))["read"]
    assert read[-1].endswith(" · waiting: the context has no set")


def test_the_panel_is_the_scripts_words_alone() -> None:
    """The prompt less the fields' text and the joins is empty: the camera words, the set's name and
    elements, each one in frame with the pose in force, nothing of the Hub's."""
    context = {"cast": [{"name": "Character 1", "home": 20}, {"name": "Character 2", "home": 80}],
               "set": {"name": "Set 1", "description": "Description 1", "elements": ["Element 1", "Element 2"]}}
    shot = {"id": "s1", "start_ms": 0, "end_ms": 2000, "camera": {"framing": "Framing 1", "move": "Move 1"},
            "events": [{"id": "p1", "kind": "pose", "start_ms": 0, "end_ms": 2000, "character": "Character 2",
                        "pose": "arms_raised"}]}
    scene = {"title": "Scene 1", "cast": ["Character 2", "Character 1"], "shots": [shot]}
    text, why = sketch.prompt({"version": 2, "context": context, "scenes": [scene]}, scene, shot, 0)
    assert why is None
    fields = ["Framing 1, Move 1", "Set 1, Element 1, Element 2", "Character 1 stand", "Character 2 arms raised"]
    assert text == ". ".join(fields) + "."
    rest = text
    for words in ("Framing 1", "Move 1", "Set 1", "Element 1", "Element 2", "Character 1", "Character 2", "stand",
                  "arms raised"):
        rest = rest.replace(words, "", 1)
    assert rest.replace(".", "").replace(",", "").split() == [], "nothing but the fields and the joins"
