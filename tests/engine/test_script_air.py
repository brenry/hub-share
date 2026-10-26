"""No hole, no empty shot, the length fits, through the script tools on the round-1 file (`fixtures/round-1.json`), with
Character 7 and Character 8 in Characters and the Hub's pace 2.451 (the file's): the file read lists its two silences
and its empty shot, the lock too, a write that does not lengthen them is accepted and each gap's call lands; the audit's
sequence (the removal closes its time; the two moves that made the file's silences refused word for word, the file
untouched); 1.5 s accepted, 1.501 s refused; a Director's pose holds, an `auto` keyframe does not; row 2's hint lands;
an empty shot refused at `scene_change {done}` and removed by `event_remove`; the length answered both ways with its fix
line."""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from hub.modules.director import air, layout
from tests.engine.test_media_characters import png_bytes
from tests.engine.test_script_tools import NINE, Ctx, call, framed, on_disk, refused

FIXTURE = Path(__file__).parent / "fixtures" / "round-1.json"
NAME = "Script 1"
PACE = 2.451
FIX = "Write a line, a cue or a pose there, or move it closer"
L2 = "word word word, word word word! word word word word word word word word word word word word."
GAPS = ['s1 at 3.13–10.65 s: 7.52 s of silence before l3 (event_move {id: "l3", start_ms: 3128})',
        's4: nothing in it, shot 2 of scene 1 (event_remove {id: "s4"}, or line_add into it)',
        's2 at 0.00–7.38 s: 7.38 s of silence before l4 (event_move {id: "l4", start_ms: 0})']


class AirCtx(Ctx):
    """Character 7 and Character 8 in Characters; the Hub's pace 2.451 (a `pace` service), so the file's times stand."""

    def __init__(self, tmp: Path) -> None:
        super().__init__(tmp)
        (tmp / "Characters" / "Character 8.png").write_bytes(png_bytes())
        self.files.roots["scripts"].mkdir(parents=True, exist_ok=True)

    def service(self, name: str) -> Any:
        return (lambda: PACE) if name == "pace" else super().service(name)


@pytest.fixture
def ctx(tmp_path: Path) -> AirCtx:
    return AirCtx(tmp_path)


def path(ctx: Ctx) -> Path:
    return ctx.files.roots["scripts"] / f"{NAME}.json"


async def owner_file(ctx: Ctx, script: dict | None = None) -> list[str]:
    """The fixture (or `script`) in the Scripts folder, opened by `script_read`: -> its read lines."""
    if script is None:
        shutil.copyfile(FIXTURE, path(ctx))
    else:
        path(ctx).write_text(json.dumps(script), encoding="utf-8")
    return (await call(ctx, "script_read", {"name": NAME}))["read"]


def shots(ctx: Ctx) -> dict[str, dict]:
    return {s["id"]: s for s in on_disk(ctx, NAME)["scenes"][0]["shots"]}


def events(ctx: Ctx) -> dict[str, dict]:
    return {e["id"]: e for s in shots(ctx).values() for e in s["events"]}


def gap_line(read: list[str]) -> str | None:
    return next((line for line in read if line.startswith("scene 1 gaps: ")), None)


async def test_the_owners_file_lists_its_silences_and_its_empty_shot(ctx: AirCtx) -> None:
    read = await owner_file(ctx)
    assert gap_line(read) == "scene 1 gaps: " + " | ".join(GAPS)
    said = await call(ctx, "scene_change", {"scene": 1, "seconds": 30})        # lengthens no silence: accepted
    assert said["state"][1] == "scene 1 · 30 s asked · runs 32.58 s · 2.58 s over · dead air 14.90 s"
    assert said["state"][-1].startswith("scene 1 cast: "), "no fix line"
    assert len(said["state"]) <= 6
    for k, sent in ((0, ("event_move", {"id": "l3", "start_ms": 3128})),
                    (2, ("event_move", {"id": "l4", "start_ms": 0})), (1, ("event_remove", {"id": "s4"}))):
        await call(ctx, *sent)
        found = gap_line((await call(ctx, "script_read", {}))["read"])
        assert GAPS[k][:12] not in (found or ""), sent
    assert gap_line((await call(ctx, "script_read", {}))["read"]) is None, "no gap left"


def rebuilt() -> dict:
    """The file before messages 2-4 s4 out; Character 8's l2 (18 words, 3 128-10 652) back in
    s1; l4 at s2's start; s3 and s2 one second earlier; no keyframe and no panel (one write fills the keyframes)."""
    script = json.loads(FIXTURE.read_text(encoding="utf-8"))
    scene = script["scenes"][0]
    s1, s4, s3, s2 = scene["shots"]
    scene["shots"].remove(s4)
    for shot in scene["shots"]:
        shot["events"] = [e for e in shot["events"] if e["kind"] in ("line", "cue")]
    s1["events"].append({"id": "l2", "kind": "line", "start_ms": 3128, "end_ms": 10652, "speaker": "Character 8",
                         "words": L2})
    layout.move(s3, -1000)
    s2.update(start_ms=18356, end_ms=24208)
    for e, (a, b) in zip(s2["events"], ((18356, 22208), (22208, 24208)), strict=True):
        e["start_ms"], e["end_ms"] = a, b
    return script


async def before_the_owners_messages(ctx: AirCtx) -> None:
    assert layout.line_ms(L2, PACE) == 10652 - 3128
    await owner_file(ctx, rebuilt())
    await call(ctx, "scene_change", {"scene": 1, "seconds": 30})              # the one write that fills the keys


async def test_the_audits_sequence_refused_where_the_silence_is_made(ctx: AirCtx) -> None:
    await before_the_owners_messages(ctx)
    gone = await call(ctx, "event_remove", {"ref": {"speaker": "Character 8", "nth": 1}})
    assert gone["state"][1].startswith("Character 8's 1st line, l2: word word word, word… · removed Character 8's "
                                       "line l2 · shot s1")
    assert gone["state"][0].endswith(" · 16.68 s")
    got = shots(ctx)
    assert events(ctx)["l3"]["start_ms"] == 3128, "no hole: the time it held closes"
    assert (got["s3"]["start_ms"], got["s3"]["end_ms"], got["s2"]["start_ms"], got["s2"]["end_ms"]) == \
        (6164, 10832, 10832, 16684)
    assert gap_line((await call(ctx, "script_read", {}))["read"]) is None
    l3 = await refused(ctx, "event_move", {"id": "l3", "start_ms": 10652}, NAME)
    assert l3 == {"problem": "Character 7's line would leave 7.5 s of silence after Character 7's", "fix": FIX,
                  "hints": {"shot": "s1", "gap_ms": 7524, "after_ms": 3128}}
    held = [e for e in shots(ctx)["s1"]["events"] if e["kind"] == "pose" and 3128 <= e["start_ms"] < 10652]
    assert held and all(e.get("auto") for e in held), "an auto keyframe in the stretch holds nothing"
    l4 = await refused(ctx, "event_move", {"id": "l4", "start_ms": 7376}, NAME)
    assert l4 == {"problem": "Character 8's line would leave 7.4 s of silence after Character 7's", "fix": FIX,
                  "hints": {"shot": "s2", "gap_ms": 7376, "after_ms": 0}}
    moved = await call(ctx, "event_move", {"id": "l3", "start_ms": l3["hints"]["after_ms"]})
    assert events(ctx)["l3"]["start_ms"] == 3128 and len(moved["state"]) <= 6, "the hint lands: no move"


async def test_a_pause_of_1_5_s_is_kept_1_501_refused_a_pose_holds(ctx: AirCtx) -> None:
    await before_the_owners_messages(ctx)
    await call(ctx, "event_remove", {"id": "l2"})
    await call(ctx, "event_move", {"id": "l3", "start_ms": 3128 + air.DEAD_AIR_MS})
    assert events(ctx)["l3"]["start_ms"] == 3128 + 1500, "1.5 s exactly: accepted"
    got = await refused(ctx, "event_move", {"id": "l3", "start_ms": 3128 + 1501}, NAME)
    assert got["problem"] == "Character 7's line would leave 1.5 s of silence after Character 7's"
    assert got["hints"] == {"shot": "s1", "gap_ms": 1501, "after_ms": 3128}
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 8", "pose": "sit", "start_ms": 4000})
    await call(ctx, "event_move", {"id": "l3", "start_ms": 5500})            # 0.87 s, the pose, 0.50 s
    assert events(ctx)["l3"]["start_ms"] == 5500, "a Director's pose holds its second"


def test_dead_air_is_only_a_pause_longer_than_1_5_s() -> None:
    """A pause of exactly 1 500 ms adds nothing to dead air, one of 1 501 ms adds 1 501."""
    for pause, want in ((1_500, 0), (1_501, 1_501)):
        line = {"kind": "line", "id": "l1", "speaker": "Character 7", "start_ms": pause, "end_ms": pause + 1_000}
        shot = {"id": "s1", "start_ms": 0, "end_ms": pause + 1_000, "events": [line]}
        assert air.dead({"shots": [shot]}) == want, pause


async def test_a_line_shortened_before_a_pause_is_refused_with_the_line_after_its_hint_lands(tmp_path: Path) -> None:
    ctx = Ctx(tmp_path)
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 6", "words": "Thank you."})
    await call(ctx, "event_move", {"id": "l2", "start_ms": 3642 + 1400})       # the Director's 1.4 s pause
    seven = "Line one opens here, and the rest."
    short = layout.line_ms(seven)
    got = await refused(ctx, "event_change", {"id": "l1", "fields": {"words": seven}})
    assert got["problem"] == \
        f"Character 6's line would leave {(5042 - short) / 1000:.1f} s of silence after Character 7's"
    assert got["fix"] == FIX and got["hints"]["id"] == "l2" and got["hints"]["shot"] == "s1"
    assert got["hints"]["gap_ms"] == 5042 - short
    fixed = got["hints"]["after_ms"]
    await call(ctx, "event_move", {"id": "l2", "start_ms": fixed, "shot": "s1"})   # row 2's hint, applied
    await call(ctx, "event_change", {"id": "l1", "fields": {"words": seven}})
    line = next(e for s in on_disk(ctx)["scenes"][0]["shots"] for e in s["events"] if e["id"] == "l2")
    assert line["start_ms"] - short <= air.DEAD_AIR_MS


async def test_an_empty_shot_refused_at_done_and_taken_out(ctx: AirCtx) -> None:
    await owner_file(ctx)
    got = await call(ctx, "scene_change", {"scene": 1, "done": True})            # never refused
    assert on_disk(ctx, NAME)["scenes"][0]["done"] is True and not any("gap" in x for x in got["state"])
    was = shots(ctx)
    gone = await call(ctx, "event_remove", {"ref": {"shot": 2}})
    assert gone["state"][1] == ("shot 2, s4: Camera 2. · removed shot s4 · "
                                "scene 1")
    now = shots(ctx)
    assert list(now) == ["s1", "s3", "s2"] and not {"f4", "p15", "p16"} & set(events(ctx))
    assert (now["s3"]["start_ms"], now["s2"]["start_ms"]) == (was["s3"]["start_ms"] - 1000,
                                                              was["s2"]["start_ms"] - 1000)
    full = await refused(ctx, "event_remove", {"ref": {"shot": 1}}, NAME)
    assert full == {"problem": "Shot s1 is not empty: l1, l3",
                    "fix": "Remove or move what is in it first (event_remove, or event_move with shot)",
                    "hints": {"shot": "s1", "ids": ["l1", "l3"]}}
    move = await refused(ctx, "event_move", {"ref": {"shot": 1}, "start_ms": 0}, NAME)
    assert move == {"problem": "event_move takes a line, cue or pose, not a shot",
                    "fix": "Name a line {speaker, nth} or a cue {cue, nth}; event_change {ref: {shot: n}, fields: "
                           "{camera}} changes a shot", "hints": {}}


async def test_the_length_answered_both_ways_and_done_with_both_lengths(ctx: AirCtx) -> None:
    await before_the_owners_messages(ctx)
    await call(ctx, "event_remove", {"id": "l2"})
    under = await call(ctx, "scene_change", {"scene": 1, "seconds": 30})
    lead = "no dead air"                        # l1's 0.50 s lead-in is under 1.5 s: not dead air
    assert air.dead(on_disk(ctx, NAME)["scenes"][0]) == 0
    assert under["state"][1] == f"scene 1 · 30 s asked · runs 16.68 s · 13.32 s under · {lead}"
    assert under["state"][-1].startswith("scene 1 cast: ") and len(under["state"]) <= 6, "no fix line"
    over = await call(ctx, "scene_change", {"scene": 1, "seconds": 10})
    assert over["state"][1] == f"scene 1 · 10 s asked · runs 16.68 s · 6.68 s over · {lead}"
    assert over["state"][-1].startswith("scene 1 cast: ") and len(over["state"]) <= 6, "no fix line"
    await call(ctx, "scene_change", {"scene": 1, "done": True})                  # never refused
    assert on_disk(ctx, NAME)["scenes"][0]["done"] is True and on_disk(ctx, NAME)["scenes"][0]["seconds"] == 10
    before = copy.deepcopy(on_disk(ctx, NAME))
    done = await call(ctx, "scene_change", {"scene": 1, "seconds": 17, "done": True})
    assert done["state"][1] == f"scene 1 · done · 17 s asked · runs 16.68 s · 0.32 s under · {lead}"
    on_it = {"seconds": 2, "shots": [{"start_ms": 0, "end_ms": 2000, "events": []}]}
    assert air.told(on_it, 1, False) == ("scene 1 · 2 s asked · runs 2.00 s · on it · dead air 2.00 s", None)
    after = on_disk(ctx, NAME)
    assert after["scenes"][0]["done"] is True and after["scenes"][0]["seconds"] == 17     # recorded
    before["scenes"][0].update(seconds=17, done=True)
    for ev in (ev for sc in (before, after) for shot in sc["scenes"][0]["shots"] for ev in shot["events"]):
        for k in ("language", "emotion", "pace"):
            ev.pop(k, None)                       # every scene done, the lock mended the lines' voice fields
    assert after["scenes"] == before["scenes"], "nothing else written by done"
    got = await refused(ctx, "scene_change", {"scene": 1}, NAME)
    assert got == {"problem": "Send seconds, done or both",
                   "fix": "scene_change {scene, seconds} sets the length named for the scene; scene_change "
                          "{scene, done: true} when the scene is written", "hints": {}}
