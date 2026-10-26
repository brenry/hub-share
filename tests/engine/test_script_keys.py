"""Pose keyframes (`hub/modules/director/keys.py`) through the script tools on a
version-2 script in a temp folder: every cast member's keyframe at a shot's start, a speaker's at the line's start and
(when anything in the shot runs after the line) its end, each in the pose in force, filled without the Director asking,
never twice and never lengthening a shot; `pose_add` at a keyframe's instant replaces it and the line's end follows; a
pose that would move a speaker while the speaker speaks refused with the fix, the file byte for byte unchanged and
nothing published, and a pose sent at the hint's `after_ms` (the line's end + 500 ms) accepted; a pose asked at the
speaker's line end keyed 500 ms after it; the keyframes follow a pushed line; removing a line takes its
holding keyframes; a required keyframe refused for removal; the example drawn as written; a filled keyframe
marked `auto`, worked out again on every write with its id kept, filled again when removed; a speaker's back-to-back
lines one run, a pose asked at its end or inside it keyed after it and every hint naming that time."""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from hub.core.api import Invalid
from hub.modules.director import keys, panels, scriptshape
from tests.engine.test_script_shape import FIXTURE
from tests.engine.test_script_tools import NINE, Ctx, call, framed, on_disk, refused

THANKS = "Thank you, friend."                         # 1 334 ms at 2.6


@pytest.fixture
def ctx(tmp_path: Path) -> Ctx:
    return Ctx(tmp_path)


def poses(ctx: Ctx, shot: str, name: str = "Script 1") -> list[tuple[str, str, int, str, str | None]]:
    """(id, character, offset in the shot, pose, anchor) of the shot's keyframes, by time."""
    s = next(s for sc in on_disk(ctx, name)["scenes"] for s in sc["shots"] if s["id"] == shot)
    return [(e["id"], e["character"], e["start_ms"] - s["start_ms"], e["pose"],
             f"{e['anchor']['line']} {e['anchor']['at']}" if "anchor" in e else None)
            for e in sorted((e for e in s["events"] if e["kind"] == "pose"), key=lambda e: (e["start_ms"], e["id"]))]


def span(ctx: Ctx, shot: str) -> tuple[int, int]:
    s = next(s for sc in on_disk(ctx)["scenes"] for s in sc["shots"] if s["id"] == shot)
    return s["start_ms"], s["end_ms"]


async def two_speakers(ctx: Ctx) -> None:
    """s1: l1 Character 6 0–1334 (p6 at its end), Character 7 arms_raised from 500 (p5), l2 Character 7 1334–4976 with
    p7 at its start, c1 after it 4976–6976 and so p8 at l2's end."""
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 6", "words": THANKS})
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "arms_raised", "start_ms": 500})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause"})


async def test_shot_add_gives_every_cast_member_a_keyframe_at_its_start(ctx: Ctx) -> None:
    await framed(ctx)
    assert poses(ctx, "s1") == [("p1", "Character 7", 0, "stand", None), ("p2", "Character 6", 0, "stand", None)]
    await call(ctx, "event_change", {"id": "p4", "fields": {"pose": "sit"}})                # Character 6 at s2's start
    got = await call(ctx, "shot_add", {"scene": 1, "camera": "Close on Character 7"})
    assert poses(ctx, "s3") == [("p5", "Character 7", 0, "stand", None), ("p6", "Character 6", 0, "sit", None)], \
        "the pose in force at the end of the scene's shot before"
    assert got["state"][2] == "keys p5–p6 added"
    assert len(got["state"]) <= 6


async def test_line_add_gives_the_speaker_keyframes_at_its_start_and_end(ctx: Ctx) -> None:
    await two_speakers(ctx)
    assert poses(ctx, "s1") == [("p1", "Character 7", 0, "stand", None), ("p2", "Character 6", 0, "stand", None),
                                ("p5", "Character 7", 500, "arms_raised", None),
                                ("p6", "Character 6", 1334, "stand", "l1 end"),
                                ("p7", "Character 7", 1334, "arms_raised", "l2 start"),
                                ("p8", "Character 7", 4976, "arms_raised", "l2 end")]
    assert span(ctx, "s1") == (0, 4976 + 2000), "the cue holds the shot; no filled keyframe lengthens it"


async def test_no_end_keyframe_for_a_line_that_ends_its_shot_and_no_shot_lengthened(ctx: Ctx) -> None:
    await framed(ctx)
    got = await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    assert not any(x.startswith("keys ") for x in got["state"]), "l1 ends s1: its end is the shot's"
    assert poses(ctx, "s1") == [("p1", "Character 7", 0, "stand", None), ("p2", "Character 6", 0, "stand", None)]
    assert span(ctx, "s1") == (0, 3642) and span(ctx, "s2") == (3642, 4642), "the shot as long as its line"
    got = await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause"})
    assert got["state"][2] == "keys p5 added", "the cue runs after l1: the speaker's keyframe at its end"
    assert poses(ctx, "s1")[-1] == ("p5", "Character 7", 3642, "stand", "l1 end")
    assert span(ctx, "s1") == (0, 3642 + 2000), "the cue's length, not a keyframe's second"
    await call(ctx, "event_remove", {"id": "c1"})
    assert [p[0] for p in poses(ctx, "s1")] == ["p1", "p2"], "l1 ends s1 again: no keyframe at the shot's end"
    assert span(ctx, "s1") == (0, 3642)


async def test_fill_twice_adds_nothing(ctx: Ctx) -> None:
    await two_speakers(ctx)
    script = on_disk(ctx)
    again = copy.deepcopy(script)
    assert keys.fill(again, lambda: "x") == [] and again == script
    example = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert keys.fill(copy.deepcopy(example), lambda: "x") == [], "the example already holds every keyframe"


async def test_pose_add_at_a_keyframe_replaces_it_and_the_line_end_follows(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause"})        # p5 at l1's end
    got = await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "arms_raised",
                                       "anchor": {"line": "l1", "at": "start"}})
    assert got["state"][1] == \
        "pose p1 · Character 7 · shot s1 · 0.00–3.64 s (script 0.00–3.64 s) · arms_raised (replaced)"
    assert poses(ctx, "s1") == [("p1", "Character 7", 0, "arms_raised", None), ("p2", "Character 6", 0, "stand", None),
                                ("p5", "Character 7", 3642, "arms_raised", "l1 end")], "held through the line"
    await call(ctx, "event_change", {"id": "p1", "fields": {"pose": "point"}})
    assert [p[3] for p in poses(ctx, "s1") if p[1] == "Character 7"] == ["point", "point"], "event_change too"
    nxt = await call(ctx, "pose_add", {"shot": "s1", "character": "Character 6", "pose": "sit", "start_ms": 100})
    assert nxt["state"][1].startswith("pose p6 "), "no id taken by a replace"


async def test_a_pose_that_moves_a_speaker_while_the_speaker_speaks_is_refused_and_its_hint_lands(ctx: Ctx) -> None:
    await two_speakers(ctx)
    got = await refused(ctx, "event_change", {"id": "p8", "fields": {"pose": "sit"}})
    assert got == {"problem": "Character 7 would change from arms_raised to sit while speaking l2",
                   "fix": "Give the new pose start_ms = after_ms (5.48 s, after those lines), or set it at the line's "
                   "start",
                   "hints": {"shot": "s1", "line": "l2", "start_pose": "arms_raised", "after_ms": 4976 + 500}}
    after = await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "point",
                                         "start_ms": got["hints"]["after_ms"]})
    assert after["state"][1] == "pose p9 · Character 7 · shot s1 · 5.48–6.98 s (script 5.48–6.98 s)", \
        "the line's end + 500 ms, an ordinary pose"
    assert ("p8", "Character 7", 4976, "arms_raised", "l2 end") in poses(ctx, "s1"), "the line-end keyframe kept"
    later = await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "sit", "start_ms": 5600})
    assert later["state"][1].startswith("pose p10 · Character 7 · shot s1 · 5.60–"), "after the line: accepted"


async def test_a_pose_asked_at_the_speakers_line_end_is_keyed_500_ms_after_it(ctx: Ctx) -> None:
    await two_speakers(ctx)
    got = await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "point",
                                       "anchor": {"line": "l2", "at": "end"}})
    assert got["state"][1] == "pose p9 · Character 7 · shot s1 · 5.48–6.98 s (script 5.48–6.98 s)", "500 ms on"
    first_poses = [p for p in poses(ctx, "s1") if p[1] == "Character 7"]
    assert first_poses[-3:] == [("p7", "Character 7", 1334, "arms_raised", "l2 start"),
                                ("p8", "Character 7", 4976, "arms_raised", "l2 end"),
                                ("p9", "Character 7", 5476, "point", None)], \
        "arms_raised through l2; point eases from its end"
    other = await call(ctx, "pose_add", {"shot": "s1", "character": "Character 6", "pose": "sit", "start_ms": 4976})
    assert other["state"][1].startswith("pose p10 · Character 6 · shot s1 · 4.98–"), "another's line end: as before"
    await call(ctx, "event_move", {"id": "p9", "start_ms": 4976})
    assert ("p9", "Character 7", 5476, "point", None) in poses(ctx, "s1"), \
        "no path stores another pose at the speaker's line end: keyed after it"


async def test_a_pose_at_a_line_that_ends_its_shot_is_added_at_after_ms(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    got = await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "point", "start_ms": 3642})
    assert got["state"][1] == "pose p5 · Character 7 · shot s1 · 4.14–5.14 s (script 4.14–5.14 s)"
    assert span(ctx, "s1") == (0, 4142 + 1000), "a pose the Director set is seen a second"
    assert [p for p in poses(ctx, "s1") if p[1] == "Character 7"] == [
        ("p1", "Character 7", 0, "stand", None), ("p6", "Character 7", 3642, "stand", "l1 end"),
        ("p5", "Character 7", 4142, "point", None)], "stand through l1"


async def test_the_keyframes_follow_a_pushed_line(ctx: Ctx) -> None:
    await two_speakers(ctx)
    got = await call(ctx, "event_change", {"id": "l1", "fields": {"words": "Thank you so much, friend."}})
    assert got["state"][2] == "moved l2, c1, p6–p8 +0.77 s; shots s2 +0.77 s"
    assert [(p[0], p[2]) for p in poses(ctx, "s1") if p[4]] == [("p6", 2103), ("p7", 2103), ("p8", 5745)]


async def test_removing_a_line_takes_its_holding_keyframes(ctx: Ctx) -> None:
    await two_speakers(ctx)
    got = await call(ctx, "event_remove", {"id": "l2"})
    assert got["state"][1] == ("Character 7's 1st line, l2: Line one opens here,… · "
                                "removed Character 7's line l2 · shot s1 · with p7, p8")
    assert [p[0] for p in poses(ctx, "s1")] == ["p1", "p2", "p5", "p6"]


async def test_a_line_whose_start_keyframe_changes_the_pose_is_refused_for_removal(ctx: Ctx) -> None:
    await two_speakers(ctx)
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "point",
                                 "anchor": {"line": "l2", "at": "start"}})
    got = await refused(ctx, "event_remove", {"id": "l2"})
    assert got == {"problem": "Line l2 has events anchored to it", "fix": "Remove or move those first",
                   "hints": {"anchored": ["p7"]}}


async def test_a_required_keyframe_is_refused_for_removal(ctx: Ctx) -> None:
    await two_speakers(ctx)
    await call(ctx, "event_change", {"id": "p2", "fields": {"pose": "sit"}})        # the Director's now
    got = await refused(ctx, "event_remove", {"id": "p2"})
    assert got == {"problem": "p2 is Character 6's pose at the start of shot s1",
                   "fix": "Change it: event_change {id: p2, fields: {pose}}", "hints": {"required": "shot start"}}
    gone = await call(ctx, "event_remove", {"id": "p5"})
    assert gone["state"][1] == "Character 7's pose p5: arms_raised · removed Character 7's pose p5 · shot s1", \
        "a keyframe the Director set and nothing needs"


async def test_a_filled_keyframe_removed_is_filled_again(ctx: Ctx) -> None:
    await two_speakers(ctx)
    before = poses(ctx, "s1")
    for ident, said in (("p2", "Character 6's pose p2: stand"), ("p8", "Character 7's pose p8: arms_raised")):
        got = await call(ctx, "event_remove", {"id": ident})
        assert got["state"][1] == f"{said} · {ident} is the Hub's; filled again", "not refused"
    assert poses(ctx, "s1") == before, "the same keyframes, the same ids"


def autos(ctx: Ctx) -> list[str]:
    return [e["id"] for sc in on_disk(ctx)["scenes"] for s in sc["shots"] for e in s["events"] if e.get("auto")]


async def test_a_filled_keyframe_is_marked_and_takes_the_pose_in_effect_on_every_write(ctx: Ctx) -> None:
    await framed(ctx)
    assert autos(ctx) == ["p1", "p2", "p3", "p4"], "the Hub's, marked"
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "arms_raised", "start_ms": 500})
    assert poses(ctx, "s2")[0] == ("p3", "Character 7", 0, "arms_raised", None), "s2 opens in the pose in effect"
    assert "p5" not in autos(ctx), "the Director's pose is never marked"
    await call(ctx, "pose_add", {"shot": "s2", "character": "Character 7", "pose": "arms_raised", "start_ms": 500})
    script = on_disk(ctx)
    s2 = next(s for s in script["scenes"][0]["shots"] if s["id"] == "s2")
    assert [c["at_ms"] - c["shot"]["start_ms"] for c in panels.causes(script) if c["shot"] is s2] == [0], \
        "no extra panel at s2 + 500"
    await call(ctx, "event_change", {"id": "p5", "fields": {"pose": "point"}})
    assert poses(ctx, "s2")[0] == ("p3", "Character 7", 0, "point", None), "worked out again, its id kept"
    await call(ctx, "event_change", {"id": "p3", "fields": {"pose": "sit"}})
    assert "p3" not in autos(ctx), "changed by the Director: the Director's now"
    await call(ctx, "event_change", {"id": "p5", "fields": {"pose": "stand"}})
    assert poses(ctx, "s2")[0] == ("p3", "Character 7", 0, "sit", None), "the fill never touches a Director-set pose"


async def test_auto_is_a_version_2_pose_key_and_true(ctx: Ctx) -> None:
    await framed(ctx)
    script, names = on_disk(ctx), {"character 7", "character 6"}
    assert scriptshape.read(copy.deepcopy(script), names)
    for where, value in (("pose", False), ("line", True)):
        bad = copy.deepcopy(script)
        shot = bad["scenes"][0]["shots"][0]
        shot["events"].append({"id": "l9", "kind": "line", "start_ms": 0, "end_ms": 900, "speaker": "Character 7",
                               "words": "Hi."})
        next(e for e in shot["events"] if e["kind"] == where)["auto"] = value
        with pytest.raises(Invalid):
            scriptshape.read(bad, names)
    one = {"version": 1, "scenes": [{"title": "T", "cast": ["Character 7"], "shots": [{"start_ms": 0, "end_ms": 900,
           "events": [{"id": "p1", "kind": "pose", "start_ms": 0, "end_ms": 900, "character": "Character 7",
                       "pose": "stand", "auto": True}]}]}]}
    with pytest.raises(Invalid):
        scriptshape.read(one, set())


async def back_to_back(ctx: Ctx) -> None:
    """s1: Character 7 l1 0–1334 and l2 1334–2668, one run; c1 after it, so p6 at the run's end."""
    await framed(ctx)
    for _ in range(2):
        await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": THANKS})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause"})


async def test_a_pose_asked_at_the_end_of_or_inside_a_run_is_keyed_after_the_run(ctx: Ctx) -> None:
    await back_to_back(ctx)
    assert [p for p in poses(ctx, "s1") if p[1] == "Character 7"] == [
        ("p1", "Character 7", 0, "stand", None), ("p5", "Character 7", 1334, "stand", "l1 end"),
        ("p6", "Character 7", 2668, "stand", "l2 end")]
    got = await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "point",
                                       "anchor": {"line": "l1", "at": "end"}})
    assert got["state"][1].startswith("pose p7 · Character 7 · shot s1 · 3.17–"), "the run's end + 500"
    got = await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "sit", "start_ms": 700})
    assert got["state"][1].startswith("pose p7 · Character 7 · shot s1 · 3.17–") and got["state"][1].endswith(
        "sit (replaced)"), "inside the run: the same instant"
    assert [p[3] for p in poses(ctx, "s1") if p[1] == "Character 7"][:3] == ["stand"] * 3, "still through the run"


async def test_every_hint_of_a_run_names_its_end_and_lands(ctx: Ctx) -> None:
    await back_to_back(ctx)
    got = await refused(ctx, "event_change", {"id": "p5", "fields": {"pose": "sit"}})
    assert got["hints"]["after_ms"] == 2668 + 500, "not inside l2"
    landed = await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "sit",
                                          "start_ms": got["hints"]["after_ms"]})
    assert landed["state"][1].startswith("pose p7 · Character 7 · shot s1 · 3.17–"), "accepted where the hint says"
    got = await refused(ctx, "event_change", {"id": "l2", "fields": {"words": NINE}})
    assert got["hints"]["after_ms"] == 1334 + 3642 + 500, "l2 grown past p7: the run's new end + 500"


async def test_the_example_is_drawn_as_written(ctx: Ctx) -> None:
    shutil.copy(FIXTURE, ctx.files.roots["scripts"] / "Example.json")
    await call(ctx, "script_read", {"name": "Example"})
    got = await call(ctx, "cue_add", {"shot": "s3", "cue": "reaction", "words": "Laughter"})
    s1 = poses(ctx, "s1", "Example")
    assert ("p4", "Character 1", 8142, "point", None) in s1 \
        and ("p12", "Character 1", 7642, "arms_raised", "l1 end") in s1, \
        "its arms_raised to point across l1 mended on the first write, not refused: point after l1"
    assert "p4, p6, p10 +0.50 s" in got["state"][2], "the moved line names the keyframes keyed after their lines"


# ---------------------------------------------------------------- the line end holds
async def test_an_echo_at_the_speakers_line_end_follows_a_start_changed_another_way(ctx: Ctx) -> None:
    """The speaker's line-end keyframe, the speaker's own, holds the line-start pose; the start changes through the
    shot-start pose (the line-start keyframe is the Hub's, in force), and the end follows."""
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 6", "words": "Thank you."})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause"})
    end = next(p for p in poses(ctx, "s1") if p[4] == "l2 end")
    await call(ctx, "event_change", {"id": end[0], "fields": {"pose": "stand"}})  # the Director's own now, same pose
    first = next(p for p in poses(ctx, "s1") if p[1] == "Character 7" and p[2] == 0)
    await call(ctx, "event_change", {"id": first[0], "fields": {"pose": "sit"}})
    first_poses = [p for p in poses(ctx, "s1") if p[1] == "Character 7"]
    assert [p[3] for p in first_poses] == ["sit", "sit", "sit"], first_poses
    assert next(p for p in first_poses if p[0] == end[0])[2] == end[2], "kept at the speaker's line end"


async def test_another_pose_brought_to_the_speakers_line_end_is_keyed_after_it_and_named(ctx: Ctx) -> None:
    """A line moved so it ends where the speaker's pose stands; the pose keyed after the line, the moved line naming
    it."""
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "point", "start_ms": 5000})
    got = await call(ctx, "event_move", {"id": "l1", "start_ms": 5000 - 3642})
    assert ("p5", "Character 7", 5500, "point", None) in poses(ctx, "s1"), poses(ctx, "s1")
    assert [p for p in poses(ctx, "s1") if p[1] == "Character 7" and p[2] == 5000][0][3] == "stand", \
        "the speaker's start pose"
    assert "p5 +0.50 s" in got["state"][2]


async def test_another_pose_at_the_speakers_line_end_with_no_instant_left_refuses_the_write(ctx: Ctx) -> None:
    """No instant after the line in the shot: the write is refused, no correction."""
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 6",
                                 "words": " ".join(["Hello"] * 25) + "."})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "point", "start_ms": 13_900})
    got = await refused(ctx, "event_move", {"id": "l2", "start_ms": 13_900 - 3642})
    assert got == {"problem": "Character 7's pose p7 at the end of l2 is not the pose at its start (stand), and no "
                   "instant is left after it in shot s1",
                   "fix": "event_move p7 into the next shot, or event_change it to stand",
                   "hints": {"shot": "s1", "line": "l2", "id": "p7", "start_pose": "stand"}}


async def test_a_pose_moved_to_the_speakers_line_end_is_keyed_after_it(ctx: Ctx) -> None:
    """`event_move` asks the after-the-line instant as `pose_add` does."""
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "point", "start_ms": 5000})
    got = await call(ctx, "event_move", {"id": "p5", "start_ms": 3642})
    assert got["state"][1].startswith("Character 7's pose p5: point · moved pose p5 · Character 7 · shot s1 · 4.14–")
