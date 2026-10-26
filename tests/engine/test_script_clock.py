"""One meaning of start_ms (`hub/modules/director/clock.py`) through the script tools, on a script whose
shot s2 starts at 3 642 ms: `event_move` counts from the start of the event's shot or of the named shot of the same
scene, a line taking its anchored events along; a shot of another scene refused with its scene's shots; every refusal
that names a time names its shot and gives the time as an offset in it, and that offset sent back lands; the answer
and read lines give the shot-relative and the script time; the file stays absolute; a refusal leaves it byte for byte
unchanged and publishes nothing."""
from __future__ import annotations

from pathlib import Path

import pytest

from hub.modules.director import layout, tools
from tests.engine.test_script_tools import NINE, Ctx, call, framed, on_disk, refused

THANKS = "Thank you, friend."                         # 3 words: 1 154 + 180 = 1 334 ms at 2.6


@pytest.fixture
def ctx(tmp_path: Path) -> Ctx:
    return Ctx(tmp_path)


def where(ctx: Ctx, ident: str) -> tuple[str, dict]:
    """(the shot id holding `ident`, the event) on disk."""
    for sc in on_disk(ctx)["scenes"]:
        for shot in sc["shots"]:
            for ev in shot["events"]:
                if ev["id"] == ident:
                    return shot["id"], ev
    raise AssertionError(ident)


def shot_of(ctx: Ctx, ident: str) -> dict:
    return next(s for sc in on_disk(ctx)["scenes"] for s in sc["shots"] if s["id"] == ident)


async def two_shots(ctx: Ctx) -> None:
    """s1: l1 Character 7 0–3642; s2 from 3642: l2 Character 6 0–1334, c1 at l2's end; s3 after it; scene 2 with s4."""
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "line_add", {"shot": "s2", "speaker": "Character 6", "words": THANKS})
    await call(ctx, "cue_add", {"shot": "s2", "cue": "reaction", "words": "Applause",
                                "anchor": {"line": "l2", "at": "end"}})
    await call(ctx, "shot_add", {"scene": 1, "camera": "Close on Character 7"})
    await call(ctx, "scene_add", {"title": "Two", "cast": ["Character 7"]})
    await call(ctx, "shot_add", {"scene": 2, "camera": "Wide"})
    assert shot_of(ctx, "s2")["start_ms"] == 3642


async def test_event_move_counts_from_the_start_of_its_own_shot(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "cue_add", {"shot": "s2", "cue": "music", "words": "A sting"})
    got = await call(ctx, "event_move", {"id": "c1", "start_ms": 1000})
    assert where(ctx, "c1")[1]["start_ms"] == 4642, "the file stays absolute"
    assert got["state"][1] == ("the 1st music cue, c1: A sting · "
                                "moved cue c1 · music · shot s2 · 1.00–3.00 s (script 4.64–6.64 s)")
    assert got["state"][2] == "shot s2 · script 3.64–6.64 s · 12.08 s left"


async def test_a_line_moved_into_another_shot_takes_its_anchored_cue_along(ctx: Ctx) -> None:
    await two_shots(ctx)
    s3 = shot_of(ctx, "s3")["start_ms"]
    got = await call(ctx, "event_move", {"id": "l2", "shot": "s3", "start_ms": 0})
    assert [e["id"] for e in shot_of(ctx, "s2")["events"]] == ["p3", "p4"], "its shot-start keyframes stay"
    assert [e["id"] for e in shot_of(ctx, "s3")["events"]] == ["p6", "p7", "l2", "c1", "p5"]
    assert where(ctx, "p5")[1]["start_ms"] == 4642 + 1334, "the speaker's line-end keyframe along with it"
    assert where(ctx, "c1")[1]["anchor"] == {"line": "l2", "at": "end"}, "the cue keeps its anchor"
    s2 = shot_of(ctx, "s2")
    assert (s2["start_ms"], s2["end_ms"]) == (3642, 3642 + layout.SHOT_MIN_MS), "s2 timed again, now empty"
    new = shot_of(ctx, "s3")
    assert new["start_ms"] == 4642 and new["start_ms"] != s3, "the later shots moved"
    assert where(ctx, "l2")[1]["start_ms"] == 4642 and where(ctx, "c1")[1]["start_ms"] == 4642 + 1334
    assert shot_of(ctx, "s4")["start_ms"] == new["end_ms"]
    assert got["state"][1] == ("Character 6's 1st line (scene 1), l2: Thank you, friend. · "
                                "moved line l2 · Character 6 · shot s3 · 0.00–1.33 s (script 4.64–5.98 s) · from s2")
    assert len(got["state"]) <= 6


async def test_refusals_name_their_shot_and_their_offsets_land(ctx: Ctx) -> None:
    await two_shots(ctx)
    await call(ctx, "line_add", {"shot": "s2", "speaker": "Character 7", "words": "Hello."})     # l3 at 1 334 in s2
    await call(ctx, "cue_add", {"shot": "s3", "cue": "music", "words": "A sting"})          # c2 at 0 in s3
    await call(ctx, "cue_add", {"shot": "s2", "cue": "effect", "words": "A door"})          # c3 in s2
    seen: list[dict] = []

    async def no(name: str, args: dict) -> dict:
        got = await refused(ctx, name, args)
        seen.append(got)
        return got

    got = await no("event_move", {"id": "l2", "shot": "s4", "start_ms": 0})
    assert got == {"problem": "Shot s4 is in scene 2, l2 in scene 1",
                   "fix": "Move it to a shot of scene 1, or remove it and add it again in scene 2",
                   "hints": {"shots": ["s1", "s2", "s3"]}}
    got = await no("event_move", {"id": "l2", "shot": "s9", "start_ms": 0})
    assert got["hints"] == {"shots": ["s1", "s2", "s3", "s4"]}
    got = await no("event_move", {"id": "l3", "start_ms": 500})
    assert got["hints"] == {"shot": "s2", "suggested_start_ms": 1334}
    await call(ctx, "event_move", {"id": "l3", "start_ms": got["hints"]["suggested_start_ms"]})
    assert where(ctx, "l3")[1]["start_ms"] == 3642 + 1334, "the hint sent back lands"
    got = await no("event_move", {"id": "c3", "shot": "s3", "start_ms": 500})
    assert got == {"problem": "c3 would start inside c2", "fix": "event_move c3 to 2.00 s or later in shot s3",
                   "hints": {"shot": "s3", "suggested_start_ms": 2000}}
    await call(ctx, "event_move", {"id": "c3", "shot": "s3", "start_ms": 2000})
    home, c3 = where(ctx, "c3")
    assert home == "s3" and c3["start_ms"] == shot_of(ctx, "s3")["start_ms"] + 2000
    got = await no("pose_add", {"shot": "s2", "character": "Character 6", "pose": "point", "start_ms": 500})
    assert got["hints"] == {"shot": "s2", "line": "l2", "start_ms": 0, "end_ms": 1334}
    did = await call(ctx, "pose_add", {"shot": "s2", "character": "Character 6", "pose": "point", "start_ms": 1334})
    assert did["state"][1] == "pose p11 · Character 6 · shot s2 · 1.83–3.33 s (script 5.48–6.98 s)", \
        "at the speaker's own line's end: keyed 500 ms after it"
    assert where(ctx, "p11")[1]["start_ms"] == 3642 + 1334 + 500 and "anchor" not in where(ctx, "p11")[1]
    assert where(ctx, "p5")[1]["start_ms"] == 3642 + 1334 and where(ctx, "p5")[1]["pose"] == "stand", \
        "the speaker's line-end keyframe holds the line-start pose"
    got = await no("line_add", {"shot": "s2", "speaker": "Character 7", "words": " ".join([NINE] * 5)})
    assert got["hints"]["shot"] == "s2" and got["hints"]["suggested_end_ms"] == 15_080 and "max_words" in got["hints"]
    got = await no("event_move", {"id": "c1", "start_ms": 14_000})
    assert got == {"problem": "Cue c1 would fall outside shot s2's 15.08 s",
                   "fix": "Place it inside the shot: start it at latest_start_ms or earlier",
                   "hints": {"shot": "s2", "shot_max_end_ms": 15_080, "latest_start_ms": 3_834}}
    props = next(a for a in tools.ACTIONS if a.name == "event_move").schema["properties"]
    assert "maximum" not in props["start_ms"], "the schema lets it through (no most ms)"
    got = await no("event_move", {"id": "c1", "start_ms": 20_000})
    assert got["hints"] == {"shot": "s2", "shot_max_end_ms": 15_080, "latest_start_ms": 3_834}, \
        "the Hub refuses it, with hints"
    for one in seen:
        timed = [k for k in one["hints"] if k.endswith("_ms") and k not in ("over_ms", "most_ms")]
        assert not timed or one["hints"]["shot"], one
        assert all(one["hints"][k] <= layout.SHOT_MAX_MS for k in timed), one
        assert "shot_start_ms" not in one["hints"]


async def test_script_read_gives_both_times(ctx: Ctx) -> None:
    await two_shots(ctx)
    read = (await call(ctx, "script_read", {}))["read"]
    at = read.index("s2 · scene 1 · script 3.64–6.98 s · Close on Character 6")
    assert read[at + 1:at + 6] == [f'l2 line Character 6 0.00–1.33 (script 3.64–4.98) "{THANKS}" · 2.6',
                                   "p3 pose Character 7 stand 0.00–3.33 (script 3.64–6.98)",
                                   "p4 pose Character 6 stand 0.00–1.33 (script 3.64–4.98)",
                                   'c1 cue reaction 1.33–3.33 (script 4.98–6.98) "Applause" at l2 end',
                                   "p5 pose Character 6 stand 1.33–3.33 (script 4.98–6.98) at l2 end"]
