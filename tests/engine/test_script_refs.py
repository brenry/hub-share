"""References (`ref`): `event_change`, `event_move` and `event_remove` take a `ref` naming one thing as the
message named it (`{speaker, nth}`, `{cue, nth}`, `{shot: n}`), resolved by the Hub (`hub/modules/director/refs.py`) on
the file as read, the answer starting with what it named; `id` still lands and echoes; a reference's refusals each
`{problem, fix, hints}` with the file unchanged; a reference call's timing refusal is the same call's by id and its hint
sent back with the same ref lands; every write answer's cast line lists the scene's lines, the read gives each scene's;
the round-1 fixture (`fixtures/round-1.json`) resolves as written."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from hub.modules.director import landing, refs, routes, scripts, tools
from tests.engine.test_media_characters import png_bytes
from tests.engine.test_script_tools import CONTEXT, Ctx, Model, call, on_disk, refused

ROOT = Path(__file__).resolve().parents[2]
ROUND1 = ROOT / "tests" / "engine" / "fixtures" / "round-1.json"
DRUNK = "word word, word, word word word word"
MEMBER = {"name": "Character 8", "look": "A green alien", "costume": "A silver suit", "ignore": "The chair", "home": 70}
FIX = "Send ref as the message names it: {speaker, nth}, {cue, nth} or {shot: n}"
SHOT_FIX = ("Name a line {speaker, nth} or a cue {cue, nth}; event_change {ref: {shot: n}, fields: {camera}} changes "
            "a shot")
LISTED = ("1 · Character 7 · Line one runs to… | 1 · Character 8 · Thanks, friend, great line. | "
          "2 · Character 7 · word word, word, word… | 2 · Character 8 · word word word word.")


@pytest.fixture
def ctx(tmp_path: Path) -> Ctx:
    c = Ctx(tmp_path)
    (tmp_path / "Characters" / "Character 8.png").write_bytes(png_bytes())
    return c


async def show(ctx: Ctx) -> None:
    """Shot s1 (Character 7 l1, Character 8 l2), shot s2 (Character 7 l3, Character 8 l4), then s3 after s1: the 2nd
    shot."""
    ctx.model = Model(json.dumps({**CONTEXT, "cast": [CONTEXT["cast"][0], MEMBER]}))
    await call(ctx, "script_start", {"name": "Script 1", "story": "Character 7 meets Character 8"})
    await call(ctx, "scene_add", {"title": "The meeting", "cast": ["Character 7", "Character 8"]})
    await call(ctx, "shot_add", {"scene": 1, "camera": {"framing": "Wide shot of the stage"}})
    await call(ctx, "shot_add", {"scene": 1, "camera": {"framing": "Close on Character 8"}})
    for shot, who, words in (("s1", "Character 7", "Line one runs to the end."),
                             ("s1", "Character 8", "Thanks, friend, great line."), ("s2", "Character 7", DRUNK),
                             ("s2", "Character 8", "word word word word.")):
        await call(ctx, "line_add", {"shot": shot, "speaker": who, "words": words})
    await call(ctx, "shot_add", {"scene": 1, "camera": {"framing": "Two-shot of the table"}, "after": "s1"})


def lines(ctx: Ctx) -> dict[str, dict]:
    return {e["id"]: e for s in shots(ctx) for e in s["events"] if e["kind"] == "line"}


def shots(ctx: Ctx) -> list[dict]:
    return [s for sc in on_disk(ctx)["scenes"] for s in sc["shots"]]


async def test_the_speakers_second_line_is_removed_not_the_second_line_overall(ctx: Ctx) -> None:
    await show(ctx)
    got = await call(ctx, "event_remove", {"ref": {"speaker": "Character 7", "nth": 2}})
    assert got["state"][1].startswith("Character 7's 2nd line, l3: word word, word, word… · removed Character 7's "
                                      "line l3")
    assert sorted(lines(ctx)) == ["l1", "l2", "l4"]


async def test_the_speakers_first_line_changed_in_place(ctx: Ctx) -> None:
    await show(ctx)
    count = (len(lines(ctx)), len(shots(ctx)))
    got = await call(ctx, "event_change", {"ref": {"speaker": "character 7", "nth": 1},
                                           "fields": {"words": "Hello all."}})
    assert got["state"][1].startswith("Character 7's 1st line, l1: Line one runs to… · changed line l1")
    assert lines(ctx)["l1"]["words"] == "Hello all." and (len(lines(ctx)), len(shots(ctx))) == count


async def test_shot_2_is_the_second_shot_on_the_users_screen_not_s2(ctx: Ctx) -> None:
    await show(ctx)
    got = await call(ctx, "event_change", {"ref": {"shot": 2}, "fields": {"camera": {"framing": "close-up",
                                                                                     "on": ["Character 8"]}}})
    assert got["state"][1].startswith("shot 2, s3: Two-shot of the table · changed shot s3 · camera close-up")
    [s1, s3, s2] = shots(ctx)
    assert (s3["id"], s3["camera"]["framing"], s3["camera"]["on"]) == ("s3", "close-up", ["Character 8"])
    assert s2["camera"] == {"framing": "Close on Character 8"} and len(shots(ctx)) == 3


async def test_a_cue_by_kind_and_a_line_moved_by_the_users_number(ctx: Ctx) -> None:
    await show(ctx)
    l4 = lines(ctx)["l4"]
    s2 = next(s for s in shots(ctx) if s["id"] == "s2")
    got = await call(ctx, "event_move", {"ref": {"speaker": "Character 8", "nth": 2},
                                         "start_ms": l4["start_ms"] - s2["start_ms"] + 500})
    assert got["state"][1].startswith("Character 8's 2nd line, l4: word word word word. · moved line l4")
    assert lines(ctx)["l4"]["start_ms"] == l4["start_ms"] + 500
    await call(ctx, "cue_add", {"shot": "s2", "cue": "reaction", "words": "Laughter and applause from the crowd"})
    got = await call(ctx, "event_change", {"ref": {"cue": "reaction", "nth": 1}, "fields": {"words": "Applause"}})
    assert got["state"][1].startswith("the 1st reaction cue, c1: Laughter and applause from… · changed cue c1")


async def test_a_second_scene_counts_in_the_last_unless_named(ctx: Ctx) -> None:
    await show(ctx)
    await call(ctx, "scene_add", {"title": "Good night", "cast": ["Character 7", "Character 8"]})
    await call(ctx, "shot_add", {"scene": 2, "camera": {"framing": "Wide shot"}})
    await call(ctx, "line_add", {"shot": "s4", "speaker": "Character 7", "words": "Good night, everyone."})
    last = await call(ctx, "event_change", {"ref": {"speaker": "Character 7", "nth": 1}, "fields": {"words": "Bye."}})
    assert last["state"][1].startswith("Character 7's 1st line (scene 2), l5: Good night, everyone. · changed line l5")
    named = await call(ctx, "event_change", {"ref": {"speaker": "Character 7", "nth": 1, "scene": 1},
                                             "fields": {"words": "Hi."}})
    assert named["state"][1].startswith("Character 7's 1st line (scene 1), l1: Line one runs to… · changed line l1")
    assert (lines(ctx)["l1"]["words"], lines(ctx)["l5"]["words"]) == ("Hi.", "Bye.")


async def test_an_id_still_lands_and_says_what_it_hit(ctx: Ctx) -> None:
    await show(ctx)
    got = await call(ctx, "event_change", {"id": "l2", "fields": {"words": "Thank you."}})
    assert got["state"][1].startswith("Character 8's 1st line, l2: Thanks, friend, great line. · changed line l2")


async def test_every_refusal_with_its_fix_and_hints(ctx: Ctx) -> None:
    await show(ctx)
    await call(ctx, "cue_add", {"shot": "s2", "cue": "reaction", "words": "Laughter and applause from the crowd"})
    first_line = {"speaker": "Character 7", "nth": 1}
    cases = [
        ("event_remove", {}, "Name what to change", FIX, {}),
        ("event_remove", {"ref": first_line, "id": "l1"}, "ref and id, not both", FIX, {}),
        ("event_change", {"ref": {"speaker": "Character 7"}, "fields": {"words": "x"}}, "A ref names one thing", FIX,
         {}),
        ("event_remove", {"ref": {"shot": 1, "nth": 1}}, "A ref names one thing", FIX, {}),
        ("event_remove", {"ref": {"shot": 1}}, "Shot s1 is not empty: l1, l2",
         "Remove or move what is in it first (event_remove, or event_move with shot)",
         {"shot": "s1", "ids": ["l1", "l2"]}),
        ("event_move", {"ref": {"shot": 1}, "start_ms": 0}, "event_move takes a line, cue or pose, not a shot",
         SHOT_FIX, {}),
        ("event_remove", {"ref": {"speaker": "Character 7", "nth": 3}}, "Character 7 has 2 lines in scene 1, not 3",
         "Name one the hints list", {"lines": LISTED.split(" | ")}),
        ("event_remove", {"ref": {"cue": "reaction", "nth": 2}}, "Scene 1 has 1 reaction cue, not 2",
         "Name one the hints list", {"cues": ["1 · reaction · Laughter and applause from…"]}),
        ("event_remove", {"ref": {"cue": "music", "nth": 1}}, "Scene 1 has 0 music cues, not 1",
         "Name one the hints list", {"cues": ["1 · reaction · Laughter and applause from…"]}),
        ("event_change", {"ref": {"shot": 4}, "fields": {"camera": {"framing": "wide"}}}, "Scene 1 has 3 shots, not 4",
         "Name one the hints list", {"shots": ["1 · s1 · Wide shot of the stage", "2 · s3 · Two-shot of the table",
                                               "3 · s2 · Close on Character 8"]}),
        ("event_remove", {"ref": {"speaker": "Character 6", "nth": 1}}, "Character 6 is not in scene 1's cast",
         "Give the line to one of the scene's cast, or add a scene with this cast",
         {"valid_speakers": ["Character 7", "Character 8"]}),
        ("event_remove", {"ref": {**first_line, "scene": 5}}, "There is no scene 5",
         "Name a scene by its number, or call scene_add", {"scenes": [{"scene": 1, "title": "The meeting"}]}),
    ]
    for name, args, problem, fix, hints in cases:
        assert await refused(ctx, name, args) == {"problem": problem, "fix": fix, "hints": hints}, args


async def test_a_reference_refused_for_its_timing_is_the_id_calls_refusal_and_its_hint_lands(ctx: Ctx) -> None:
    await show(ctx)
    by_id = await refused(ctx, "event_move", {"id": "l4", "start_ms": 0})
    by_ref = await refused(ctx, "event_move", {"ref": {"speaker": "Character 8", "nth": 2}, "start_ms": 0})
    assert by_ref == by_id
    hints = by_ref["hints"]
    key = next(k for k in (*landing.STARTS, "end_ms") if k in hints)
    got = await call(ctx, "event_move", {"ref": {"speaker": "Character 8", "nth": 2}, "start_ms": hints[key],
                                         "shot": hints["shot"]})
    assert got["state"][1].startswith("Character 8's 2nd line, l4: word word word word. · moved line l4")


async def test_every_answer_lists_the_scenes_lines_and_the_read_each_scenes(ctx: Ctx) -> None:
    await show(ctx)
    got = await call(ctx, "event_change", {"ref": {"shot": 1}, "fields": {"camera": {"framing": "wide"}}})
    assert got["state"][-1] == f"scene 1 cast: Character 7, Character 8 · lines: {LISTED}" and len(got["state"]) <= 6
    added = await call(ctx, "line_add", {"shot": "s3", "speaker": "Character 8", "words": "Hello."})
    assert added["state"][-1].endswith(" | 2 · Character 8 · Hello. | 2 · Character 7 · word word, word, word… | "
                                       "3 · Character 8 · word word word word."), "timeline order: s3 before s2"
    read = (await call(ctx, "script_read", {}))["read"]
    k = read.index(f"scene 1 lines: {added['state'][-1].split(' · lines: ')[1]}")
    s2 = [e["id"] for e in shots(ctx)[-1]["events"] if e["kind"] != "panel"]
    assert read[k - 1].split()[0] in s2 and all(" panel " in x for x in read[k + 1:]), "after scene 1's last event"


def test_the_owners_round_1_file_resolves_as_the_owner_meant_it(ctx: Ctx) -> None:
    folder = ctx.files.roots["scripts"]
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROUND1, folder / "Round 1.json")
    script = tools._bare(scripts.opened(folder, "Round 1", routes.characters(ctx)))
    assert [s["id"] for s in script["scenes"][0]["shots"]] == ["s1", "s4", "s3", "s2"]
    cases = [({"speaker": "Character 7", "nth": 2}, "l3", "Character 7's 2nd line, l3: word word, word. word…"),
             ({"speaker": "Character 7", "nth": 3}, "l5", "Character 7's 3rd line, l5: word, word word word…"),
             ({"shot": 2}, "s4", "shot 2, s4: Camera 2."),
             ({"cue": "reaction", "nth": 1}, "c1", None)]
    for ref, ident, echo in cases:
        sent, said = refs.resolve(script, {"ref": ref, "fields": {}}, "event_change")
        assert sent == {"id": ident, "fields": {}} and (echo is None or said == echo), ref
    assert refs.listing(script, 1) == ("1 · Character 7 · word, word, word word… | "
                                       "2 · Character 7 · word word, word. word… | "
                                       "3 · Character 7 · word, word word word… | "
                                       "1 · Character 8 · word word word word…")
