"""Every hint lands (R48 §2) through the script tools on a version-2 script in a temp folder: each
refusal's hint, sent back as the call's value, is accepted. A pose may start at 14.08 s of its shot (`pose_add` and
`event_move`), one at 14.081 s is refused with `latest_start_ms`; a cue moved past the shot is refused with the pass
less its length; a move inside the cue before names its time rounded up; a too-long line's `max_words`; a line-end
pose's `after_ms`, past the speaker's next line when that starts 300 ms after, none when no instant is left in the shot.
Every time-valued hint names its shot."""
from __future__ import annotations

from pathlib import Path

import pytest

from hub.modules.director import layout
from tests.engine.test_script_tools import NINE, Ctx, call, framed, on_disk, refused


@pytest.fixture
def ctx(tmp_path: Path) -> Ctx:
    return Ctx(tmp_path)


async def no(ctx: Ctx, name: str, args: dict) -> dict:
    """The refusal, the file untouched; every time-valued hint names its shot."""
    got = await refused(ctx, name, args)
    timed = [k for k in got["hints"] if k.endswith("_ms") and k not in ("over_ms", "most_ms")]
    assert not timed or got["hints"]["shot"], got
    return got


def shot_events(ctx: Ctx, shot: str) -> list[dict]:
    s = next(s for sc in on_disk(ctx)["scenes"] for s in sc["shots"] if s["id"] == shot)
    return [{**e, "at": e["start_ms"] - s["start_ms"]} for e in s["events"]]


def end_keyframe(ctx: Ctx, shot: str, line: str) -> str:
    return next(e["id"] for e in shot_events(ctx, shot) if e.get("anchor") == {"line": line, "at": "end"})


async def test_a_pose_may_start_at_14_08_s_and_the_latest_start_lands(ctx: Ctx) -> None:
    await framed(ctx)
    long = " ".join(["Hello"] * 35) + "."                   # 13.64 s held, no silence before 14.08 s
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 6", "words": long})
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "point", "start_ms": 14_080})
    assert any(e["at"] == 14_080 and e.get("pose") == "point" for e in shot_events(ctx, "s1")), \
        "its 1 s ends at 15.08 s"
    await call(ctx, "line_add", {"shot": "s2", "speaker": "Character 7", "words": long})
    got = await no(ctx, "pose_add", {"shot": "s2", "character": "Character 7", "pose": "point", "start_ms": 14_081})
    assert got == {"problem": "Pose p7 would fall outside shot s2's 15.08 s",
                   "fix": "Place it inside the shot: start it at latest_start_ms or earlier",
                   "hints": {"shot": "s2", "shot_max_end_ms": 15_080, "latest_start_ms": 14_080}}
    await call(ctx, "pose_add", {"shot": "s2", "character": "Character 7", "pose": "point",
                                 "start_ms": got["hints"]["latest_start_ms"]})
    await call(ctx, "pose_add", {"shot": "s2", "character": "Character 6", "pose": "sit", "start_ms": 1000})
    sit = next(e["id"] for e in shot_events(ctx, "s2") if e.get("pose") == "sit")
    got = await no(ctx, "event_move", {"id": sit, "start_ms": 14_081})
    assert got["hints"] == {"shot": "s2", "shot_max_end_ms": 15_080, "latest_start_ms": 14_080}
    await call(ctx, "event_move", {"id": sit, "start_ms": got["hints"]["latest_start_ms"]})
    assert any(e["id"] == sit and e["at"] == 14_080 for e in shot_events(ctx, "s2"))


async def test_a_cue_moved_past_the_shot_is_told_the_latest_start_that_lands(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7",
                                 "words": " ".join(["Hello"] * 35) + "."})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause",
                                "anchor": {"line": "l1", "at": "start"}})
    got = await no(ctx, "event_move", {"id": "c1", "start_ms": 14_000})
    assert got["hints"]["latest_start_ms"] == 15_080 - 2000
    await call(ctx, "event_move", {"id": "c1", "start_ms": got["hints"]["latest_start_ms"]})


async def test_a_time_in_a_fix_is_rounded_up(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "cue_add", {"shot": "s1", "cue": "music", "words": "A sting"})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause"})
    await call(ctx, "event_change", {"id": "c1", "fields": {"seconds": 2.334}})
    await call(ctx, "event_move", {"id": "c2", "start_ms": 3000})
    got = await no(ctx, "event_move", {"id": "c2", "start_ms": 1000})
    assert got == {"problem": "c2 would start inside c1", "fix": "event_move c2 to 2.34 s or later",
                   "hints": {"shot": "s1", "suggested_start_ms": 2334}}, "2 334 ms: 2.34 s, not 2.33"
    assert layout.secs_up(2334) == "2.34" and layout.secs_up(2000) == "2.00" and layout.secs(2334) == "2.33"
    await call(ctx, "event_move", {"id": "c2", "start_ms": got["hints"]["suggested_start_ms"]})


async def test_a_too_long_lines_max_words_lands(ctx: Ctx) -> None:
    await framed(ctx)
    words = " ".join([NINE] * 5).split()
    got = await no(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": " ".join(words)})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7",
                                 "words": " ".join(words[:got["hints"]["max_words"]])})


async def test_a_line_end_pose_hint_lands(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause"})
    got = await no(ctx, "event_change", {"id": end_keyframe(ctx, "s1", "l1"), "fields": {"pose": "sit"}})
    assert got["hints"]["after_ms"] == 3642 + 500
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "sit",
                                 "start_ms": got["hints"]["after_ms"]})


async def test_a_line_end_hint_past_the_speakers_next_line_300_ms_after(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "event_move", {"id": "l2", "start_ms": 3642 + 300})         # 3 942–7 584
    got = await no(ctx, "event_change", {"id": end_keyframe(ctx, "s1", "l1"), "fields": {"pose": "sit"}})
    assert got["hints"]["after_ms"] == 3942 + 3642 + 500, "not 4 142, inside the speaker's next line"
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "sit",
                                 "start_ms": got["hints"]["after_ms"]})


async def test_no_after_ms_when_no_instant_is_left_in_the_shot(ctx: Ctx) -> None:
    await framed(ctx)
    words = " ".join(["Hello"] * 35) + "."
    end = layout.line_ms(words)
    assert end < layout.LAST_POSE_MS < end + layout.AFTER_LINE_MS
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": words})
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 6", "pose": "sit", "start_ms": end + 50})
    got = await no(ctx, "event_change", {"id": end_keyframe(ctx, "s1", "l1"), "fields": {"pose": "sit"}})
    assert got == {"problem": "Character 7 would change from stand to sit while speaking l1",
                   "fix": "Set it at the line's start, or in the next shot",
                   "hints": {"shot": "s1", "line": "l1", "start_pose": "stand"}}
    await call(ctx, "pose_add", {"shot": "s2", "character": "Character 7", "pose": "sit", "start_ms": 0})



# ---------------------------------------------------------------- six ways a hint failed to land, (a)-(f)
async def test_a_latest_start_blind_to_the_cue_behind_is_tried_and_lands(ctx: Ctx) -> None:
    """(a): `latest_start_ms` is tried against the cue it pushes, not only the pass less the cue's own length."""
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7",
                                 "words": " ".join(["Hello"] * 30) + "."})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "music", "words": "A sting",
                                "anchor": {"line": "l1", "at": "start"}})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause"})
    await call(ctx, "event_move", {"id": "c2", "start_ms": 13_080})
    got = await no(ctx, "event_move", {"id": "c1", "start_ms": 13_080})
    assert got["problem"] == "Cue c1 would fall outside shot s1's 15.08 s"
    assert got["hints"]["latest_start_ms"] == 11_080, "13 080 pushes c2 past the pass: tried, the next one found"
    await call(ctx, "event_move", {"id": "c1", "start_ms": got["hints"]["latest_start_ms"]})


async def test_a_cue_made_too_long_is_named_with_its_most_seconds(ctx: Ctx) -> None:
    """(b): the changed cue carries the shot past its pass; its correction `max_seconds`."""
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "music", "words": "A sting"})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause"})
    got = await no(ctx, "event_change", {"id": "c1", "fields": {"seconds": 10}})
    assert got == {"problem": "Cue c1 at 10.00 s would carry shot s1 past 15.08 s",
                   "fix": "Give it at most max_seconds",
                   "hints": {"shot": "s1", "max_seconds": 9.4, "suggested_end_ms": 15_080}}
    await call(ctx, "event_change", {"id": "c1", "fields": {"seconds": got["hints"]["max_seconds"]}})


async def test_a_pose_at_a_line_end_with_no_instant_left_is_refused_once(ctx: Ctx) -> None:
    """(c): no `latest_start_ms` that leads into the speaker's own line; one refusal, no correction."""
    await framed(ctx)
    words = " ".join(["Hello"] * 35) + "."
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": words})
    end = layout.line_ms(words)
    for args in ({"anchor": {"line": "l1", "at": "end"}}, {"start_ms": end}):
        got = await no(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "point", **args})
        assert got == {"problem": "No instant is left after Character 7's line l1 in shot s1",
                       "fix": "Set it at the line's start, or in the next shot",
                       "hints": {"shot": "s1", "line": "l1", "end_ms": end}}


async def three_lines(ctx: Ctx, middle: str) -> None:
    await framed(ctx)
    for speaker, words in (("Character 7", NINE), ("Character 6", middle), ("Character 7", NINE)):
        await call(ctx, "line_add", {"shot": "s1", "speaker": speaker, "words": words})
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "point", "start_ms": 4000})


async def test_a_removal_is_never_refused_for_the_hubs_keyframes(ctx: Ctx) -> None:
    """(d): a removal's refusal names the speaker's own pose, never two of the Hub's keyframes."""
    await three_lines(ctx, NINE)
    got = await no(ctx, "event_remove", {"id": "l2"})
    autos = {e["id"] for e in shot_events(ctx, "s1") if e.get("auto")}
    assert got["problem"] == "Pose p9 of Character 7 starts inside Character 7's own line l3" and "p9" not in autos
    assert got["hints"]["id"] == "p9"
    # p9 sent past l3 as it is is left over 4 s past l3 once the removal pulls l3 back: no candidate
    # lands, so `after_ms` is left out and the fix names the other way, which lands.
    assert "after_ms" not in got["hints"] and got["fix"] == "Set it at the line's start, or in the next shot"
    await call(ctx, "event_move", {"id": "p9", "shot": "s2", "start_ms": 0})
    await call(ctx, "event_remove", {"id": "l2"})


async def test_an_after_ms_of_the_file_after_the_call_is_tried_on_the_file_before(ctx: Ctx) -> None:
    """(e): after the removal l3 ends at 7.28 s, but 7.78 s lies inside l3 as it still is; the hint that lands."""
    await three_lines(ctx, "Thank you.")
    l3 = next(e for e in shot_events(ctx, "s1") if e["id"] == "l3")
    got = await no(ctx, "event_remove", {"id": "l2"})
    assert got["hints"]["after_ms"] >= l3["end_ms"], "not 7 784, inside l3 before the call"
    await call(ctx, "event_move", {"id": "p9", "start_ms": got["hints"]["after_ms"], "shot": "s1"})
    await call(ctx, "event_remove", {"id": "l2"})


async def test_the_moving_fix_names_the_run_end_its_after_ms_names(ctx: Ctx) -> None:
    """(f): the fix's time is `after_ms`, after the speaker's lines, not the line's end."""
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": "Line one."})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": "Line one."})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause"})
    got = await no(ctx, "event_change", {"id": end_keyframe(ctx, "s1", "l1"), "fields": {"pose": "sit"}})
    after = got["hints"]["after_ms"]
    assert after == 2 * layout.line_ms("Line one.") + 500
    assert got["fix"] == f"Give the new pose start_ms = after_ms ({layout.secs_up(after)} s, after those lines), or " \
        "set it at the line's start"
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "sit", "start_ms": after})
