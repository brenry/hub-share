"""A scene's `done`, its silences and its gap lines. The seconds sent with a `done` are written; an old silence
never refuses a call that leaves it as long; every gap line's calls land in the order named; `done` on a scene with no
shot is recorded; nothing shown or asked past 60 s."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub.core.api import Invalid
from hub.modules.director import air, layout, length, timing
from tests.engine.test_script_air import FIXTURE, NAME, AirCtx, gap_line, on_disk, owner_file
from tests.engine.test_script_tools import NINE, Ctx, call, framed


def dump(ctx: AirCtx) -> dict[str, tuple[int, int]]:
    """Each line's, cue's and Director's pose's (start, end) on disk, by id."""
    s = on_disk(ctx, NAME)
    return {e["id"]: (e["start_ms"], e["end_ms"]) for sc in s["scenes"] for sh in sc["shots"] for e in sh["events"]
            if e["kind"] in ("line", "cue") or (e["kind"] == "pose" and not e.get("auto"))}


async def tryit(ctx: Ctx, name: str, args: dict) -> dict:
    """The call's answer, or its refusal's {problem, fix, hints} under `refused`."""
    try:
        return await call(ctx, name, args)
    except Invalid as e:
        return {"refused": json.loads(e.text)}


def one_shot(events: list[dict], end: int, seconds: int | None = None, more_shots: list[dict] | None = None) -> dict:
    script = json.loads(FIXTURE.read_text(encoding="utf-8"))
    sc = script["scenes"][0]
    if seconds is None:
        sc.pop("seconds", None)
    else:
        sc["seconds"] = seconds
    sc["shots"] = [{"id": "s1", "start_ms": 0, "end_ms": end, "camera": "Wide shot", "events": events},
                   *(more_shots or [])]
    return script


def ln(i: str, who: str, a: int, b: int, words: str = "word, word, word word word word?") -> dict:
    return {"id": i, "kind": "line", "start_ms": a, "end_ms": b, "speaker": who, "words": words}


def cue(i: str, a: int, b: int) -> dict:
    return {"id": i, "kind": "cue", "cue": "reaction", "start_ms": a, "end_ms": b, "words": "Laughter."}


def second_round() -> dict:
    ev1 = [ln("l1", "Character 7", 0, 3852, "word, word word word word. word word word word?"),
           ln("l2", "Character 8", 3852, 6888, "word, word. word word word word word."),
           ln("l4", "Character 7", 6888, 9516, "word word word. word word word?")]
    more = [{"id": "s2", "start_ms": 9516, "end_ms": 12960, "camera": "Two-shot", "events": [
                ln("l5", "Character 7", 9516, 12960, "word word? word word word. word word word word?")]},
            {"id": "s3", "start_ms": 12960, "end_ms": 13960, "camera": {"framing": "close-up", "on": ["Character 8"]},
             "events": []}]
    return one_shot(ev1, 9516, 15, more)


async def test_second_round_seconds_and_done(tmp_path: Path) -> None:
    """`seconds: 30` with `done` and a gap: both written, 30 s on disk and the scene done; the next
    line lands against 30 s. `done` alone is recorded; `seconds: 0` with `done` takes the length off."""
    ctx = AirCtx(tmp_path)
    await owner_file(ctx, second_round())
    sent = len(ctx.bus.sent)
    got = await tryit(ctx, "scene_change", {"scene": 1, "seconds": 30, "done": True})
    assert "refused" not in got
    assert on_disk(ctx, NAME)["scenes"][0]["seconds"] == 30 and on_disk(ctx, NAME)["scenes"][0]["done"] is True
    assert [s[1] for s in ctx.bus.sent[sent:]] == ["changed"], "director.changed published"
    added = await call(ctx, "line_add", {"shot": "s2", "speaker": "Character 8",
                                         "words": "word word word word word, word word word."})
    assert added["state"][1].startswith("line l6 · Character 8 · shot s2")
    assert "refused" not in await tryit(ctx, "scene_change", {"scene": 1, "done": True})
    assert on_disk(ctx, NAME)["scenes"][0]["done"] is True
    assert "refused" not in await tryit(ctx, "scene_change", {"scene": 1, "seconds": 0, "done": True})
    assert "seconds" not in on_disk(ctx, NAME)["scenes"][0] and on_disk(ctx, NAME)["scenes"][0]["done"] is True


@pytest.mark.parametrize("sent", [{"id": "l4"}, {"ref": {"speaker": "Character 8", "nth": 1}}, {"id": "l3"}])
async def test_remove_after_preexisting_hole(tmp_path: Path, sent: dict) -> None:
    """S2's 7.38 s silence, left as long with c1 after it, never refuses the removal."""
    ctx = AirCtx(tmp_path)
    await owner_file(ctx)
    assert "refused" not in await tryit(ctx, "event_remove", sent)


async def test_removing_l1_still_refused(tmp_path: Path) -> None:
    """The hole that grows (7.52 s to 10.65 s) is unpaired: refused."""
    ctx = AirCtx(tmp_path)
    await owner_file(ctx)
    got = (await tryit(ctx, "event_remove", {"id": "l1"}))["refused"]
    assert got["problem"] == "Character 7's line would leave 10.7 s of silence after the scene's start"


async def test_move_out_after_preexisting_hole(tmp_path: Path) -> None:
    ctx = AirCtx(tmp_path)
    await owner_file(ctx)
    assert "refused" not in await tryit(ctx, "event_move", {"id": "l4", "start_ms": 0, "shot": "s4"})
    assert "l4" in [e["id"] for e in on_disk(ctx, NAME)["scenes"][0]["shots"][1]["events"]]


async def test_remove_between_two_short_pauses(tmp_path: Path) -> None:
    """A 3.3 s hole the removal makes is refused, rightly."""
    ctx = Ctx(tmp_path)
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 6", "words": "Thank you, friend."})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": "So tell us."})
    ev = {e["id"]: e for e in on_disk(ctx)["scenes"][0]["shots"][0]["events"]}
    await call(ctx, "event_move", {"id": "l2", "start_ms": ev["l2"]["start_ms"] + 1000})
    ev = {e["id"]: e for e in on_disk(ctx)["scenes"][0]["shots"][0]["events"]}
    await call(ctx, "event_move", {"id": "l3", "start_ms": ev["l3"]["start_ms"] + 1000})
    got = (await tryit(ctx, "event_remove", {"ref": {"speaker": "Character 6", "nth": 1}}))["refused"]
    assert got["problem"] == "Character 7's line would leave 3.3 s of silence after Character 7's"


def _calls(gap: str) -> list[tuple[str, dict]]:
    """The calls a gap line names, in order."""
    inside = gap[gap.index("(") + 1:gap.rindex(")")]
    out = []
    for part in inside.split(", then "):
        assert part.startswith("event_move {")
        body = part[len("event_move "):].replace("id:", '"id":').replace("start_ms:", '"start_ms":')
        out.append(("event_move", json.loads(body)))
    return out


async def _lands_in_order(ctx: AirCtx, expected: str) -> None:
    read = (await call(ctx, "script_read", {}))["read"]
    gap = gap_line(read)
    assert gap == f"scene 1 gaps: {expected}"
    for name, args in _calls(gap):
        assert "refused" not in (got := await tryit(ctx, name, args)), (args, got)
    assert gap_line((await call(ctx, "script_read", {}))["read"]) is None, "no gap left"


@pytest.mark.parametrize("kind", ["line", "cue"])
async def test_gap_call_refused_when_a_short_pause_follows(tmp_path: Path, kind: str) -> None:
    """L1 500-3128, a 2.87 s hole, l3 6000-8628, a 1.0 s pause, X: the paused one first, then l3."""
    ctx = AirCtx(tmp_path)
    x = ln("l6", "Character 8", 9628, 12256) if kind == "line" else cue("c9", 9628, 11628)
    await owner_file(ctx, one_shot([ln("l1", "Character 7", 500, 3128), ln("l3", "Character 7", 6000, 8628), x],
                                   x["end_ms"]))
    i = x["id"]
    await _lands_in_order(ctx, f's1 at 3.13–6.00 s: 2.87 s of silence before l3 (event_move {{id: "{i}", start_ms: '
                               '8628}, then event_move {id: "l3", start_ms: 3128})')
    at = dump(ctx)
    assert at["l3"][0] == 3128 and at[i][0] == at["l3"][1], "the paused one follows l3"


async def test_gap_calls_for_two_paused_lines(tmp_path: Path) -> None:
    """Two lines each after a 1.0 s pause: three calls, last first."""
    ctx = AirCtx(tmp_path)
    ev = [ln("l1", "Character 7", 500, 3128), ln("l3", "Character 7", 6000, 8628), ln("l6", "Character 8", 9628, 12256),
          ln("l7", "Character 7", 13256, 15000)]
    await owner_file(ctx, one_shot(ev, 15000))
    await _lands_in_order(ctx, 's1 at 3.13–6.00 s: 2.87 s of silence before l3 (event_move {id: "l7", start_ms: '
                               '12256}, then event_move {id: "l6", start_ms: 8628}, then event_move {id: "l3", '
                               'start_ms: 3128})')


async def test_gap_calls_for_a_pose_after_the_paused_cue(tmp_path: Path) -> None:
    """A Director's pose right behind the paused cue: the pose first (to its closed-up start), the cue, l3."""
    ctx = AirCtx(tmp_path)
    pose = {"id": "p9", "kind": "pose", "start_ms": 11628, "end_ms": 12628, "character": "Character 8",
            "pose": "point"}
    ev = [ln("l1", "Character 7", 500, 3128), ln("l3", "Character 7", 6000, 8628), cue("c9", 9628, 11628), pose]
    await owner_file(ctx, one_shot(ev, 12628))
    await _lands_in_order(ctx, 's1 at 3.13–6.00 s: 2.87 s of silence before l3 (event_move {id: "p9", start_ms: '
                               '7756}, then event_move {id: "c9", start_ms: 8628}, then event_move {id: "l3", '
                               'start_ms: 3128})')


async def test_gap_calls_for_the_speakers_own_pose_after_the_paused_cue(tmp_path: Path) -> None:
    """P9 Character 7's (l3's speaker): the cue, then that speaker's pose at no
    earlier than l3's end, then l3; each lands in order, no gap left after."""
    ctx = AirCtx(tmp_path)
    pose = {"id": "p9", "kind": "pose", "start_ms": 11628, "end_ms": 12628, "character": "Character 7",
            "pose": "point"}
    ev = [ln("l1", "Character 7", 500, 3128), ln("l3", "Character 7", 6000, 8628), cue("c9", 9628, 11628), pose]
    await owner_file(ctx, one_shot(ev, 12628))
    await _lands_in_order(ctx, 's1 at 3.13–6.00 s: 2.87 s of silence before l3 (event_move {id: "c9", start_ms: '
                               '8628}, then event_move {id: "p9", start_ms: 8628}, then event_move {id: "l3", '
                               'start_ms: 3128})')


async def test_gap_line_names_no_chain_that_cannot_land(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A chain with a refused call (here a pose past its latest start) is tried and not named: the
    gap line names the hole and its fix, no call."""
    ctx = AirCtx(tmp_path)
    pose = {"id": "p9", "kind": "pose", "start_ms": 11628, "end_ms": 12628, "character": "Character 8",
            "pose": "point"}
    ev = [ln("l1", "Character 7", 500, 3128), ln("l3", "Character 7", 6000, 8628), cue("c9", 9628, 11628), pose]
    await owner_file(ctx, one_shot(ev, 12628))
    monkeypatch.setattr(air, "_closing", lambda shot, h: [("p9", layout.LAST_POSE_MS + 1), ("l3", 3128)])
    gap = gap_line((await call(ctx, "script_read", {}))["read"])
    assert gap == ("scene 1 gaps: s1 at 3.13–6.00 s: 2.87 s of silence before l3 (write a line, a cue or a pose there, "
                   "or move it closer)")
    assert "event_move" not in gap


async def test_remove_every_shot(tmp_path: Path) -> None:
    """`done` on a scene with no shot is recorded, never refused."""
    ctx = Ctx(tmp_path)
    await framed(ctx)
    for _ in range(2):
        assert "refused" not in await tryit(ctx, "event_remove", {"ref": {"shot": 1}})
    assert on_disk(ctx)["scenes"][0]["shots"] == []
    assert "refused" not in await tryit(ctx, "scene_change", {"scene": 1, "done": True})
    assert on_disk(ctx)["scenes"][0]["done"] is True
    assert "refused" not in await tryit(ctx, "scene_add", {"title": "Two", "cast": ["Character 7"]})


def _scene(seconds: int, ms: int) -> dict:
    return {"title": "One", "cast": [], "seconds": seconds,
            "shots": [{"id": "s1", "start_ms": 0, "end_ms": ms, "events": []}]}


def test_a_length_is_shown_as_asked() -> None:
    """The length asked and the length run, never a range, never a fix line."""
    assert not hasattr(length, "window") and not hasattr(timing, "MOST_MS")
    assert length.asked(_scene(60, 50_500)) == " · 60 s asked"
    assert length.shown(_scene(60, 50_500), 1) == " · scene 1 50.50 s of 60 s"
    assert air.told(_scene(60, 50_500), 1, False) == ("scene 1 · 60 s asked · runs 50.50 s · 9.50 s under · "
                                                      "dead air 50.50 s", None)
    assert air.told(_scene(3700, 3_700_500), 1, False)[0].startswith("scene 1 · 3700 s asked · runs 3700.50 s · "
                                                                     "0.50 s over · ")
    assert length.asked(_scene(15, 10_000)) == " · 15 s asked"
