"""Timing (`hub/modules/director/timing.py`) through the script tools on a version-2 script in a temp
folder: a line as long as its words at the Hub's pace (its own when it has one, 2.6 with no `pace` service) plus the
turn pause; a lengthened line pushes what sat behind it by exactly the overrun, the later shots by the same, and the
answer names what moved; a shortened one pulls them back; a pause made with `event_move` is kept until the line
before it grows past it; a cue put after the last line follows that line; a move onto the line before is refused, a
move into the line after pushes it; two anchored cues at once refused; the 15 080 ms shot and a pose pushed into its own
character's line refused, the file byte for byte unchanged and nothing published; a scene runs past 60 s; a
removed line or cue, or one moved into another shot, pulls back what sat right behind it;
`retime(x, x) == x` on the example."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from hub.modules.director import edit, timing
from tests.engine.test_script_shape import FIXTURE
from tests.engine.test_script_tools import NINE, Ctx, call, framed, on_disk, refused

TEN = NINE + " Truly."                               # 10 words: 3 846 + 180 = 4 026 ms at 2.6
EIGHTEEN = NINE + " " + NINE                         # 7 103 ms at 2.6


class Paced(Ctx):
    """The Hub with Generate running: `pace` offered (`generate_image/manifest.py` start)."""

    def __init__(self, tmp: Path, pace: float) -> None:
        super().__init__(tmp)
        self.pace = pace

    def service(self, name: str) -> Any:
        return (lambda: self.pace) if name == "pace" else super().service(name)


@pytest.fixture
def ctx(tmp_path: Path) -> Ctx:
    return Ctx(tmp_path)


def events(ctx: Ctx, shot: int = 0) -> dict[str, tuple[int, int]]:
    """The shot's lines and cues; the keyframes the Hub fills are `keyframes`."""
    s = on_disk(ctx)["scenes"][0]["shots"][shot]
    return {e["id"]: (e["start_ms"], e["end_ms"]) for e in s["events"] if e["kind"] != "pose"}


def keyframes(ctx: Ctx, shot: int = 0) -> dict[str, tuple[int, str]]:
    s = on_disk(ctx)["scenes"][0]["shots"][shot]
    return {e["id"]: (e["start_ms"], e["pose"]) for e in s["events"] if e["kind"] == "pose"}


def shot_span(ctx: Ctx, shot: int) -> tuple[int, int]:
    s = on_disk(ctx)["scenes"][0]["shots"][shot]
    return s["start_ms"], s["end_ms"]


async def three_lines(ctx: Ctx) -> None:
    """s1: l1 Character 7 0–3642, l2 Character 6 3642–4591, l3 Character 7 4591–8233, c1 after the last line 8233–10233;
    s2 empty; the keyframes p1–p4 at the shots' starts, p5 at l1's end, p6–p7 at l2's start and end, p8–p9 at l3's."""
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 6", "words": "Thank you."})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause"})


async def test_a_line_lasts_its_words_at_the_hubs_pace_or_its_own_or_2_6(tmp_path: Path) -> None:
    paced = Paced(tmp_path, 3.0)
    await framed(paced)
    await call(paced, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(paced, "line_add", {"shot": "s1", "speaker": "Character 6", "words": NINE, "pace": 2.6})
    assert events(paced) == {"l1": (0, 3180), "l2": (3180, 3180 + 3642)}
    assert shot_span(paced, 1)[0] == 6822, "l2 ends s1: no keyframe filled at its end"


async def test_no_pace_service_is_the_engines_2_6(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    assert events(ctx) == {"l1": (0, 3642)}
    assert keyframes(ctx) == {"p1": (0, "stand"), "p2": (0, "stand")}, "l1 ends its shot: no end keyframe"


async def test_a_lengthened_line_pushes_its_followers_and_the_later_shots_by_the_overrun(ctx: Ctx) -> None:
    await three_lines(ctx)
    assert events(ctx) == {"l1": (0, 3642), "l2": (3642, 4591), "l3": (4591, 8233), "c1": (8233, 10233)}
    assert shot_span(ctx, 1) == (10233, 11233)
    got = await call(ctx, "event_change", {"id": "l1", "fields": {"words": TEN}})
    over = 4026 - 3642
    assert events(ctx) == {"l1": (0, 4026), "l2": (3642 + over, 4591 + over), "l3": (4591 + over, 8233 + over),
                           "c1": (8233 + over, 10233 + over)}
    assert shot_span(ctx, 1) == (10233 + over, 11233 + over)
    assert got["state"][1] == ("Character 7's 1st line, l1: Line one opens here,… · "
                                "changed line l1 · Character 7 · shot s1 · 0.00–4.03 s (script 0.00–4.03 s)")
    assert got["state"][2] == "moved l2–l3, c1, p5–p9 +0.38 s; shots s2 +0.38 s"
    assert len(got["state"]) <= 6
    shortened = await call(ctx, "event_change", {"id": "l1", "fields": {"words": NINE}})
    assert events(ctx) == {"l1": (0, 3642), "l2": (3642, 4591), "l3": (4591, 8233), "c1": (8233, 10233)}
    assert shortened["state"][2] == "moved l2–l3, c1, p5–p9 -0.38 s; shots s2 -0.38 s", "pulled back with it"


async def test_a_pause_made_by_event_move_stays_until_the_line_before_grows_past_it(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 6", "words": "Thank you."})
    await call(ctx, "event_move", {"id": "l2", "start_ms": 5000})
    grew = await call(ctx, "event_change", {"id": "l1", "fields": {"words": TEN}})
    assert events(ctx)["l2"] == (5000, 5949), "grew 0.38 s into a 1.36 s pause: l2 stays"
    assert grew["state"][2] == "moved p5 +0.38 s", "nothing else moved but the line's own end keyframe"
    shorter = await call(ctx, "event_change", {"id": "l1", "fields": {"words": NINE}})
    assert events(ctx)["l2"] == (5000, 5949) and shorter["state"][2] == "moved p5 -0.38 s", "the pause is kept"
    await call(ctx, "event_change", {"id": "l1", "fields": {"words": EIGHTEEN}})
    assert events(ctx)["l2"] == (7103, 8052), "the pause eaten first, then pushed"


async def test_a_cue_put_after_the_last_line_follows_that_line(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause"})
    assert events(ctx)["c1"] == (3642, 5642)
    await call(ctx, "event_change", {"id": "l1", "fields": {"words": TEN}})
    assert events(ctx)["c1"] == (4026, 6026)
    await call(ctx, "event_change", {"id": "l1", "fields": {"words": "Hello."}})
    assert events(ctx)["c1"] == (565, 2565)


async def test_a_move_onto_the_line_before_is_refused_into_the_line_after_pushes(ctx: Ctx) -> None:
    await framed(ctx)
    for words in (NINE, "Thank you.", NINE):
        await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": words})
    got = await refused(ctx, "event_move", {"id": "l2", "start_ms": 3000})
    assert got == {"problem": "Line l2 would overlap line l1", "fix": "Move it where no other line of the shot is: "
                   "one speaker at a time", "hints": {"shot": "s1", "suggested_start_ms": 3642}}
    await call(ctx, "event_move", {"id": "l3", "start_ms": 6000})            # a pause before l3
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 6", "pose": "sit", "start_ms": 4000})
    moved = await call(ctx, "event_move", {"id": "l2", "start_ms": 5500})   # l2 now runs into l3
    assert events(ctx)["l2"] == (5500, 6449) and events(ctx)["l3"] == (6449, 10091)
    assert moved["state"][2] == "moved l3 +0.45 s; p6 +1.86 s; shots s2 +0.45 s", "p7 at l3's start dropped"
    assert [ms for ms, _ in keyframes(ctx).values()].count(6449) == 1, "l2's end and l3's start: one keyframe"


async def test_two_anchored_cues_at_once_are_refused(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 6", "words": "Thank you."})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause",
                                "anchor": {"line": "l1", "at": "end"}})
    got = await refused(ctx, "cue_add", {"shot": "s1", "cue": "music", "words": "A sting",
                                         "anchor": {"line": "l2", "at": "start"}})
    assert got == {"problem": "c2 would start inside c1", "fix": "Remove its anchor, or move the cue before it",
                   "hints": {"shot": "s1", "anchor": {"line": "l1", "at": "start"}}}, \
        "cue_add takes no start: its correction an anchor, tried"


async def test_a_moved_cue_inside_the_cue_before_is_refused_with_its_time(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "cue_add", {"shot": "s1", "cue": "music", "words": "A sting"})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause"})
    await call(ctx, "event_move", {"id": "c2", "start_ms": 3000})
    got = await refused(ctx, "event_move", {"id": "c2", "start_ms": 1000})
    assert got == {"problem": "c2 would start inside c1", "fix": "event_move c2 to 2.00 s or later",
                   "hints": {"shot": "s1", "suggested_start_ms": 2000}}


async def test_a_push_past_one_pass_is_refused(ctx: Ctx) -> None:
    await framed(ctx)
    for _ in range(3):
        await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 6", "words": "Yes."})       # s1 ends 11 491
    got = await refused(ctx, "event_change", {"id": "l1", "fields": {"words": " ".join([NINE] * 3)}})
    assert got["problem"] == "Line l1 would carry shot s1 past 15.08 s"
    assert got["hints"] == {"shot": "s1", "max_words": 18, "suggested_end_ms": 15_080}, \
        "room for l1 with the lines behind it"


async def test_a_pose_pushed_into_its_characters_own_line_is_refused(ctx: Ctx) -> None:
    await three_lines(ctx)
    await call(ctx, "event_remove", {"id": "c1"})
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "point", "start_ms": 9000})
    got = await refused(ctx, "event_change", {"id": "l1", "fields": {"words": EIGHTEEN}})
    assert got == {"problem": "Pose p10 of Character 7 starts inside Character 7's own line l3",
                   "fix": "Set it at the line's start, or in the next shot",
                   "hints": {"shot": "s1", "line": "l3", "start_ms": 8052, "end_ms": 11694, "id": "p10"}}
    await call(ctx, "event_move", {"id": "p10", "shot": "s2", "start_ms": 0})
    await call(ctx, "event_change", {"id": "l1", "fields": {"words": EIGHTEEN}})     # the hint sent back


async def test_a_scene_has_no_most_seconds(ctx: Ctx) -> None:
    await framed(ctx)
    for n in range(1, 6):
        if n > 2:
            await call(ctx, "shot_add", {"scene": 1, "camera": "Wide"})
        for _ in range(3):
            await call(ctx, "line_add", {"shot": f"s{n}", "speaker": "Character 7", "words": NINE})
    await call(ctx, "shot_add", {"scene": 1, "camera": "Close"})
    await call(ctx, "line_add", {"shot": "s6", "speaker": "Character 7", "words": NINE})          # 58.27 s
    await call(ctx, "line_add", {"shot": "s6", "speaker": "Character 7", "words": NINE})          # 61.91 s: it lands
    assert sum(ev["kind"] == "line" for ev in on_disk(ctx)["scenes"][0]["shots"][-1]["events"]) == 2
    assert not hasattr(timing, "most"), "no most seconds per scene"


async def test_a_removed_line_pulls_its_followers_and_the_later_shots_back(ctx: Ctx) -> None:
    await three_lines(ctx)
    got = await call(ctx, "event_remove", {"id": "l2"})
    gap = 4591 - 3642
    assert events(ctx) == {"l1": (0, 3642), "l3": (3642, 8233 - gap), "c1": (8233 - gap, 10233 - gap)}
    assert shot_span(ctx, 1) == (10233 - gap, 11233 - gap), "as if l2 were shortened to nothing"
    assert got["state"][2] == "moved l3, c1, p9 -0.95 s; shots s2 -0.95 s", "p8 at l3's start merged with p5"


async def test_removing_the_first_line_pulls_the_next_to_the_shots_start(ctx: Ctx) -> None:
    await three_lines(ctx)
    got = await call(ctx, "event_remove", {"id": "l1"})
    assert events(ctx) == {"l2": (0, 949), "l3": (949, 4591), "c1": (4591, 6591)}
    assert got["state"][2] == "moved l2–l3, c1, p7–p9 -3.64 s; shots s2 -3.64 s"


async def test_a_removed_cue_pulls_the_cue_behind_it_back(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "cue_add", {"shot": "s1", "cue": "music", "words": "A sting"})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause"})
    assert events(ctx) == {"c1": (0, 2000), "c2": (2000, 4000)}
    got = await call(ctx, "event_remove", {"id": "c1"})
    assert events(ctx) == {"c2": (0, 2000)} and shot_span(ctx, 1) == (2000, 3000)
    assert got["state"][2] == "moved c2 -2.00 s; shots s2 -2.00 s"


async def test_a_line_moved_into_another_shot_pulls_back_the_line_behind_it(ctx: Ctx) -> None:
    await three_lines(ctx)
    got = await call(ctx, "event_move", {"id": "l2", "shot": "s2", "start_ms": 0})
    gap = 4591 - 3642
    assert events(ctx) == {"l1": (0, 3642), "l3": (3642, 8233 - gap), "c1": (8233 - gap, 10233 - gap)}
    assert events(ctx, 1) == {"l2": (10233 - gap, 10233)}
    assert got["state"][2] == "moved l3, c1, p9 -0.95 s; shots s2 -0.95 s"


async def test_a_pause_before_the_removed_line_stays(ctx: Ctx) -> None:
    await framed(ctx)
    for words in (NINE, "Thank you."):
        await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": words})
    await call(ctx, "event_move", {"id": "l2", "start_ms": 5000})          # a pause before l2
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})     # l3 right behind it
    assert events(ctx) == {"l1": (0, 3642), "l2": (5000, 5949), "l3": (5949, 9591)}
    await call(ctx, "event_remove", {"id": "l2"})
    assert events(ctx) == {"l1": (0, 3642), "l3": (5000, 8642)}, "pulled back to where l2 began: the pause kept"


def test_retiming_a_timed_script_changes_nothing() -> None:
    example = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for pace in (None, 3.0):
        x = copy.deepcopy(example)
        assert timing.retime(copy.deepcopy(x), x, pace=pace) == (example, {"events": {}, "shots": {}})
    edit.ensure_shot_ids(x, {})
    assert timing.retime(copy.deepcopy(x), x)[0] == x
