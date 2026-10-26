"""The mix on the Director's side (`place.py`, `mix.py`, the route, `scriptshape`, `lock`, `track`). Pure, on the real
script shape: R54's placement cases (`test_place.py`), the lanes, fades and hash. On `test_script_track`'s context with
a stand-in Characters and stand-in measures (its stand-in lane and `test_cue_takes`' measures): the job's refusals and
tasks, the finish's files and record, a WAV already of that name kept, Track's finish and press handing over to the mix,
the stems, the route's five states, the file's checks of `mix`, `renders` and `measured`, and `script_unlock` taking
`measured` out; a finish whose placement moved keeps no master, one on the script as pressed keeps it; `build`'s
`room_ms` reads no WAV."""
from __future__ import annotations

import copy
import json
import math
import random
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.director import layout, lock, mix, mixfinish, place, routes, scripts, scriptshape, track
from tests.engine.test_cue_takes import cued, measured
from tests.engine.test_script_tools import on_disk
from tests.engine.test_script_track import Jobs, call, lock_only, refused, run
from tests.engine.test_script_track import ctx as track_ctx  # noqa: F401
from tests.fakes.wav import tiny_wav

T = layout.TURN_MS


def line(i: str, who: str, a: int, b: int) -> dict:
    return {"id": i, "kind": "line", "speaker": who, "start_ms": a, "end_ms": b}


def cue(i: str, kind: str, a: int, b: int) -> dict:
    return {"id": i, "kind": "cue", "cue": kind, "start_ms": a, "end_ms": b}


def tk(kept: int, lead: int = 200, file: str | None = None, **more: Any) -> dict:
    return {"file": file or f"Script 1/x{kept}-{lead}.wav", "hash": "h",
            "measured": {"speech_start_ms": lead, "speech_end_ms": lead + kept, "gain_db": 0.0, **more}}


def script(events: list[dict], shots: list[tuple[int, int]] | None = None, cast: tuple[str, ...] = ("A", "B"),
           **top: Any) -> dict:
    spans = shots or [(0, 3_000_000)]
    rows = [{"id": f"s{k + 1}", "start_ms": a, "end_ms": b, "events": [e for e in events if a <= e.get(
        "start_ms", e.get("at_ms")) < b]} for k, (a, b) in enumerate(spans)]
    return {"version": 2, "context": {"cast": [{"name": n} for n in cast]},
            "scenes": [{"title": "t", "cast": list(cast)[:8], "shots": rows}], **top}


def placed(events: list[dict], takes: dict, shots: list[tuple[int, int]] | None = None, **kw: Any) -> dict:
    return place.place(script(events, shots, **kw), takes, {})


def at(p: dict, ident: str) -> int:
    return p["clips"][ident]["at_ms"]


def rising(bp: list[tuple[int, int]]) -> bool:
    keys, vals = zip(*bp, strict=True)
    return all(x < y for x, y in zip(keys, keys[1:], strict=False)) and all(
        x <= y for x, y in zip(vals, vals[1:], strict=False))


# ---------------------------------------------------------------- the map (R54 test_place.py)
def test_right_behind_across_a_shot_boundary() -> None:
    ev = [line("l1", "A", 1000, 3000), line("l2", "B", 3000, 5000)]
    p = placed(ev, {"l1": tk(2500), "l2": tk(1500)}, [(0, 3000), (3000, 6000)])
    assert (at(p, "l1"), at(p, "l2")) == (1000, 1000 + 2500 + T)
    assert p["shots"][1]["start_ms"] == 1000 + 2500 + T, "the cut moves with the line"
    assert placed(ev, {"l1": tk(2500), "l2": tk(1500)})["clips"] == p["clips"], "shots are never read for sound"


def test_a_made_pause_kept_exactly() -> None:
    ev = [line("l1", "A", 0, 2000), line("l2", "B", 3500, 5500), line("l3", "A", 5500, 7000)]
    for kept in (1000, 2000 - T, 3000):                                     # short, as planned, long
        p = placed(ev, {"l1": tk(kept), "l2": tk(1820), "l3": tk(1000)})
        assert at(p, "l2") - (kept + T) == 1500 and at(p, "l3") == at(p, "l2") + 1820 + T


def test_a_written_overlap_at_its_share_on_its_own_lane() -> None:
    ev = [line("l1", "A", 0, 3000), line("l2", "B", 2000, 4000), line("l3", "A", 4000, 5000)]
    p = placed(ev, {"l1": tk(3600), "l2": tk(1500), "l3": tk(800)})
    assert at(p, "l2") == round(2000 * (3600 + T) / 3000) < 3600, "sounding with the line it cuts into"
    lanes = {ln["name"]: [c["take"] for c in ln["clips"]] for ln in mix.lanes(script(ev), p, None)}
    assert lanes == {"A": ["l1", "l3"], "B": ["l2"]}
    assert at(p, "l3") == max(3600, at(p, "l2") + 1500) + T and rising(p["map"])


def test_an_overlap_that_overruns_pushes_what_follows() -> None:
    ev = [line("l1", "A", 0, 3000), line("l2", "B", 2000, 2800), line("l3", "A", 3000, 4000)]
    p = placed(ev, {"l1": tk(2000), "l2": tk(2500), "l3": tk(800)})
    assert at(p, "l3") == at(p, "l2") + 2500 + T > 2000 + T


def test_an_interruption_long_or_short_never_overlaps_or_leaves_dead_air() -> None:
    ev = [line("A", "J", 0, 3000), line("B", "K", 2000, 2800), line("C", "J", 3000, 4000)]
    p = placed(ev, {"A": tk(2800), "B": tk(2500), "C": tk(800)}, cast=("J", "K"))
    assert at(p, "C") == p["measured"]["B"]["end_ms"] + T, "after the interruption's placed end"
    ev = [line("A", "J", 0, 3000), line("B", "K", 2000, 4000), line("C", "J", 4000, 5000)]
    p = placed(ev, {"A": tk(3300), "B": tk(600), "C": tk(800)}, cast=("J", "K"))
    assert at(p, "C") - max(p["measured"]["A"]["end_ms"], p["measured"]["B"]["end_ms"]) == T, "no dead air"


def test_a_line_overlapping_its_own_speaker_is_refused() -> None:
    with pytest.raises(Invalid) as e:
        placed([line("l1", "A", 0, 3000), line("l2", "A", 2000, 4000)], {"l1": tk(1000), "l2": tk(1000)})
    assert e.value.text == "l2 overlaps l1, a line of the same speaker (A): move one with event_move"


def test_an_overrun_moves_every_later_event() -> None:
    ev = [line("l1", "A", 0, 2000), line("l2", "B", 2000, 4000), line("l3", "A", 5000, 7000),
          {**cue("c1", "reaction", 4000, 5000), "anchor": {"line": "l2", "at": "end"}},
          {"id": "p1", "kind": "pose", "character": "A", "pose": "stand", "start_ms": 5000, "end_ms": 7000},
          {"id": "f1", "kind": "panel", "at_ms": 6000, "picture": None, "stale": False}]
    takes = {"l1": tk(1820), "l2": tk(1820), "l3": tk(1820), "c1": tk(800, decay_ms=300)}
    base, long = placed(ev, takes), placed(ev, {**takes, "l2": tk(1820 + 700)})
    assert at(long, "l1") == at(base, "l1")
    assert [long["measured"][i][k] - base["measured"][i][k] for i, k in (
        ("l3", "start_ms"), ("c1", "start_ms"), ("p1", "start_ms"), ("p1", "end_ms"), ("f1", "at_ms"))] == [700] * 5
    assert at(base, "c1") == base["measured"]["l2"]["end_ms"] + T, "a cue at a line's end follows its placed end"


def test_the_map_is_monotonic_on_300_random_scripts() -> None:
    rnd = random.Random(54)
    for _ in range(300):
        ev, takes, t = [], {}, 0
        for k in range(rnd.randint(1, 14)):
            t = max(0, t + rnd.choice([0, 0, 0, rnd.randint(1, 2000), -rnd.randint(1, 1500)]))
            n = rnd.randint(400, 4000)
            ev.append(line(f"l{k}", f"S{k}", t, t + n))
            takes[f"l{k}"] = tk(max(1, n + rnd.randint(-1500, 1500) - T))
            t += n
        ev += [{"id": f"f{j}", "kind": "panel", "at_ms": rnd.randint(0, t), "picture": None, "stale": False}
               for j in range(5)]
        p = placed(ev, takes, cast=tuple(f"S{k}" for k in range(14)))
        assert rising(p["map"])
        grid = [place.interp(p["map"], x) for x in range(0, t + 2000, 37)]
        assert all(x <= y for x, y in zip(grid, grid[1:], strict=False))
        shown = [p["measured"][e["id"]]["at_ms"] for e in sorted(ev[-5:], key=lambda e: e["at_ms"])]
        assert shown == sorted(shown)


def test_a_short_shot_is_held_to_one_second_pushing_the_next_cut_and_no_clip() -> None:
    ev = [line("l1", "A", 0, 2000), line("l2", "B", 2000, 4000), line("l3", "A", 4000, 6000)]
    takes = {"l1": tk(1820), "l2": tk(300), "l3": tk(1820)}
    p = placed(ev, takes, [(0, 2000), (2000, 4000), (4000, 6000)])
    s2 = p["shots"][1]
    assert s2["end_ms"] - s2["start_ms"] == layout.SHOT_MIN_MS and p["shots"][2]["start_ms"] == s2["end_ms"]
    assert p["clips"] == placed(ev, takes)["clips"] and at(p, "l3") == 1820 + T + 300 + T


def test_a_panel_held_inside_its_shot_and_the_last_shot_to_a_reactions_tail() -> None:
    ev = [line("l1", "A", 0, 2000), line("l2", "B", 2000, 3000), cue("c1", "reaction", 3000, 4000),
          {"id": "f1", "kind": "panel", "at_ms": 1900, "picture": None, "stale": False}]
    p = placed(ev, {"l1": tk(500), "l2": tk(800), "c1": tk(5000)}, [(0, 2000), (2000, 4000)])
    assert p["shots"][0]["start_ms"] <= p["measured"]["f1"]["at_ms"] <= p["shots"][0]["end_ms"] - 1
    assert p["length_ms"] == p["shots"][-1]["end_ms"] == at(p, "c1") + 5000, "the picture covers the tail"


def test_a_take_with_no_measured_sound() -> None:
    silent = {"file": "Script 1/l1-1.wav", "hash": "h", "measured": None}
    with pytest.raises(Invalid) as e:
        placed([line("l1", "A", 0, 2000)], {"l1": silent})
    assert e.value.text == "l1: its take Script 1/l1-1.wav has no measured sound: redo it (delete it from Sounds, " \
                           "then call script_track)"
    room = place.room({"room": {"file": "Script 1/room-1.wav", "hash": "h", "measured": None}}, {"room": 12_345})
    assert (room["in_ms"], room["out_ms"], room["at_ms"]) == (0, 12_345, 0), "the room kept whole"


# ---------------------------------------------------------------- lanes, fades, hash
def test_the_lanes() -> None:
    cast = tuple(f"S{k}" for k in range(16))
    ev = [line(f"l{k}", f"S{15 - k}", 3000 * k, 3000 * k + 2000) for k in range(16)]
    ev += [cue("c1", "reaction", 50_000, 52_000), cue("c2", "reaction", 53_000, 54_000), cue("c3", "music", 0, 6000)]
    takes = {**{f"l{k}": tk(1500, gain_db=2.5) for k in range(16)}, "c1": tk(2000, decay_ms=700),
             "c2": tk(1000, decay_ms=0), "c3": tk(6000), "room": tk(2000)}
    s = script(ev, cast=cast, mix={"lanes": [{"name": "reaction", "gain_db": -3.0, "duck": False},
                                             {"name": "S3", "gain_db": 4.0}]})
    p = place.place(s, takes, {})
    held = mix.lanes(s, p, place.room(takes, {}))
    assert [ln["name"] for ln in held] == [*cast, "reaction", "music", "room"], "context order; no effect lane"
    by = {ln["name"]: ln for ln in held}
    assert (by["reaction"]["gain_db"], by["reaction"]["duck"], by["music"]["duck"]) == (-3.0, False, True)
    assert by["S3"]["gain_db"] == 4.0 and not by["S3"]["duck"] and by["S0"]["clips"][0]["gain_db"] == 2.5
    room = by["room"]
    assert (room["kind"], room["duck"], room["clips"][0]["loop"]) == ("room", False, True)
    assert (room["clips"][0]["fade_in_ms"], room["clips"][0]["fade_out_ms"]) == (500, 500)
    fades = {c["take"]: (c["fade_in_ms"], c["fade_out_ms"]) for ln in held for c in ln["clips"]}
    assert fades["c1"] == (100, 350) and fades["c2"] == (100, 300) and fades["c3"] == (500, 1000)
    assert fades["l0"] == (10, 10) and len(held) == 19, "one lane per speaker and the four others, no most"
    assert mix.hashed(held, p["length_ms"]) == mix.hashed(copy.deepcopy(held), p["length_ms"])
    held[0]["clips"][0]["file"] = "Script 1/l15-2.wav"
    assert mix.hashed(held, p["length_ms"]) != mix.hashed(mix.lanes(s, p, place.room(takes, {})), p["length_ms"])


# ---------------------------------------------------------------- the job, its finish and Track's on the stand-in Hub
class MixJobs(Jobs):
    def submit(self, kind: str, params: dict) -> Any:
        if kind != mix.KIND:
            return super().submit(kind, params)
        plan = mix.job(copy.deepcopy(params), self.ctx)
        job = SimpleNamespace(id=f"j{len(self.made) + 1}", kind=f"director.{kind}", state="queued", error=None,
                              plan=plan, params=params, takes={})
        self.made.append(job)
        self.book[job.id] = job
        return job


@pytest.fixture
async def mctx(track_ctx: Any) -> Any:  # noqa: F811
    track_ctx.jobs = MixJobs(track_ctx)
    return track_ctx


async def tracked(ctx: Any) -> Any:
    """`test_script_lock`'s Script 1 with three cues, locked, Track run with every take landing: -> the mix job
    its finish submitted."""
    await cued(ctx)
    await call(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    await run(ctx, made, lambda k: measured(k, made.plan))
    assert ctx.jobs.made[-1].kind == "director.mix", "Track's finish submitted the mix"
    return ctx.jobs.made[-1]


async def land(ctx: Any, made: Any, seconds: float = 1.0) -> dict[int, str]:
    day = ctx.files.roots["sounds"] / "2026-10-21"
    day.mkdir(parents=True, exist_ok=True)
    landed = {}
    for k in range(1, len(made.plan.tasks) + 1):
        (day / f"mix{made.id}-{k}.wav").write_bytes(tiny_wav(seconds + k / 10, rate=8000))
        landed[k] = f"sounds/2026-10-21/mix{made.id}-{k}.wav"
    await made.plan.finish(landed)
    made.state = "done"
    return landed


def every_measured(s: dict) -> bool:
    return all("measured" in sh and all("measured" in ev for ev in sh["events"]) for sh in layout.shots(s))


async def test_the_job_its_tasks_and_the_finish(mctx: Any) -> None:
    made = await tracked(mctx)
    plan, before = made.plan, on_disk(mctx)
    assert plan.summary["title"] == "Mix · Script 1 · 6 lanes" and plan.model == "" and plan.lane_kind == "image"
    [task] = plan.tasks
    assert (task["kind"], task["out_kind"], task["items"], task["solo"], task["target"]) == (
        "join", "wav", [], None, {"lufs": -23.0, "true_peak_dbtp": -1.0})
    assert [ln["name"] for ln in task["lanes"]] == ["Character 7", "Character 6", "reaction", "effect", "music", "room"]
    assert routes.track_state(mctx, "Script 1", before)["state"] == "mixing"
    await land(mctx, made)
    after = on_disk(mctx)
    assert after["renders"] == {"track": "Script 1.wav",
                                "size": (mctx.files.roots["sounds"] / "Script 1.wav").stat().st_size,
                                "stems": {}}
    assert after["mix"]["note"] is None and after["mix"]["target"]["source"] == "EBU R 128 (2020)"
    assert every_measured(after) and "Script 1" not in mix.running
    plain = copy.deepcopy(after)
    for sh in layout.shots(plain):
        sh.pop("measured")
        for ev in sh["events"]:
            ev.pop("measured")
    assert plain["scenes"] == before["scenes"], "the planned times untouched"
    got = routes._one(mctx, "Script 1")["track"]
    assert got == {"state": "current", "file": "Script 1.wav", "url": mctx.files.url("sounds/Script 1.wav"),
                   "length_ms": after["mix"]["length_ms"]}
    assert (await refused(mctx, "script_track", {}))["problem"] == mix.CURRENT
    (mctx.files.roots["sounds"] / "Script 1.wav").unlink()
    assert routes._one(mctx, "Script 1")["track"] == {"state": "none"}
    answer = await call(mctx, "script_track", {})
    again = mctx.jobs.made[-1]
    assert answer["state"] == [f"Script 1 · Track: nothing to render; mixing (job {again.id})"]
    assert again.kind == "director.mix" and len(again.plan.tasks) == 1, "mixed again, nothing rendered"


async def test_the_users_wav_is_kept_and_the_scripts_own_render_replaced(mctx: Any) -> None:
    sounds = mctx.files.roots["sounds"]
    sounds.mkdir(parents=True, exist_ok=True)
    (sounds / "Script 1.wav").write_bytes(b"kept before")
    made = await tracked(mctx)
    await land(mctx, made)
    assert (sounds / "Script 1.wav").read_bytes() == b"kept before" and \
        on_disk(mctx)["renders"]["track"] == "Script 1-2.wav"
    mix.remix(mctx, "Script 1")
    await land(mctx, mctx.jobs.made[-1], 2.0)
    assert on_disk(mctx)["renders"]["track"] == "Script 1-2.wav" and not (sounds / "Script 1-3.wav").exists(), \
        "its own earlier render replaced"


async def test_nothing_written_when_the_script_changed_meanwhile(mctx: Any) -> None:
    made = await tracked(mctx)
    await call(mctx, "script_unlock", {})
    landed = await land(mctx, made)
    assert "mix" not in on_disk(mctx) and (mctx.files.roots["sounds"] / landed[1][len("sounds/"):]).is_file()
    await lock_only(mctx)
    mix.remix(mctx, "Script 1")
    made = mctx.jobs.made[-1]
    s = on_disk(mctx)
    s["takes"]["l1"]["file"] = "Script 1/l1-9.wav"
    (mctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(s), encoding="utf-8")
    await land(mctx, made)
    assert "mix" not in on_disk(mctx), "the takes are not those of the press"


# ---------------------------------------------------------------- the mix compares its own hash
async def test_a_finish_whose_placement_moved_keeps_no_master(mctx: Any) -> None:
    made = await tracked(mctx)
    s = on_disk(mctx)
    l2 = next(ev for sh in layout.shots(s) for ev in sh["events"] if ev["id"] == "l2")
    l2["start_ms"], l2["end_ms"] = l2["start_ms"] + 500, l2["end_ms"] + 500           # the same takes, placed later
    (mctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(s), encoding="utf-8")
    landed = await land(mctx, made)
    assert "mix" not in on_disk(mctx) and "renders" not in on_disk(mctx)
    assert made.plan.finish.write(landed) == mixfinish.CHANGED


async def test_a_finish_on_the_script_as_pressed_keeps_the_master(mctx: Any) -> None:
    made = await tracked(mctx)
    await land(mctx, made)
    assert on_disk(mctx)["renders"]["track"] == "Script 1.wav" and on_disk(mctx)["mix"]["hash"] == \
        made.plan.finish.made["mix"]["hash"]


async def test_build_with_the_rooms_length_reads_no_wav(mctx: Any, monkeypatch: Any) -> None:
    await tracked(mctx)
    s = on_disk(mctx)
    s["takes"]["room"]["measured"] = None

    def never(*a: Any) -> float:
        raise AssertionError("a WAV read")
    monkeypatch.setattr(mix, "sound_exact", never)
    got = mix.build(mctx, "Script 1", s, room_ms=1000)
    room = got["lanes"][-1]["clips"][0]
    assert (room["in_ms"], room["out_ms"], room["loop"]) == (0, 1000, True), "the length handed in"


async def test_the_jobs_refusals(mctx: Any) -> None:
    made = await tracked(mctx)
    s = on_disk(mctx)
    s["takes"]["l2"]["measured"]["gain_db"] = 43.0
    (mctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(s), encoding="utf-8")
    with pytest.raises(Invalid) as e:
        mix.job({"script": "Script 1"}, mctx)
    assert e.value.text == f"l2: its take {s['takes']['l2']['file']} is levelled by +43.0 dB, past the mix's +40: " \
                           "redo it (delete it from Sounds, then call script_track)"
    made.state = "done"
    got = await refused(mctx, "script_track", {})
    assert got["problem"] == e.value.text and got["fix"] == track.FIXES["mix"]
    s["takes"]["l2"]["measured"]["gain_db"] = math.nan
    (mctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(s), encoding="utf-8")
    count = len(mctx.jobs.made)
    with pytest.raises(Invalid, match="not a finite number"):
        mix.job({"script": "Script 1"}, mctx)
    s["takes"]["l2"]["measured"]["gain_db"] = 0.0
    c2 = s["takes"].pop("c2")
    (mctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(s), encoding="utf-8")
    with pytest.raises(Invalid) as e:
        mix.job({"script": "Script 1"}, mctx)
    assert e.value.text == "c2 has no current take: call script_track" and len(mctx.jobs.made) == count
    s["takes"]["c2"] = c2
    next(ev for sh in layout.shots(s) for ev in sh["events"] if ev["id"] == "c3")["words"] = "A brass sting"
    (mctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(s), encoding="utf-8")
    with pytest.raises(Invalid) as e:
        mix.job({"script": "Script 1"}, mctx)
    assert e.value.text == "c3 has no current take: call script_track", "a stale take"


async def test_a_room_take_with_no_measured_sound_is_kept_whole_at_its_files_length(mctx: Any) -> None:
    await tracked(mctx)
    s = on_disk(mctx)
    s["takes"]["room"]["measured"] = None
    (mctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(s), encoding="utf-8")
    room = mix.job({"script": "Script 1"}, mctx).tasks[0]["lanes"][-1]["clips"][0]
    assert (room["in_ms"], room["out_ms"], room["loop"]) == (0, 1000, True), "its file: 1.0 s"


async def test_tracks_finish_mixes_only_when_every_take_landed(mctx: Any) -> None:
    await cued(mctx)
    await call(mctx, "script_track", {})
    made = mctx.jobs.made[-1]
    await run(mctx, made, lambda k: None if k <= 3 else measured(k, made.plan))      # l1's three takes fail
    assert mctx.jobs.made[-1] is made and "Script 1" not in mix.failed and "Script 1" not in mix.running


async def test_tracks_finish_keeps_a_refusal_as_failed(mctx: Any) -> None:
    await cued(mctx)
    await call(mctx, "script_track", {})
    made = mctx.jobs.made[-1]
    await run(mctx, made, lambda k: {**measured(k, made.plan), "measure": {
        **measured(k, made.plan)["measure"], "lufs": -68.0}} if k == 1 else measured(k, made.plan))
    assert mctx.jobs.made[-1] is made, "no mix job"
    why = mix.failed["Script 1"]
    assert why.startswith("l1: its take Script 1/l1-") and "past the mix's +40: redo it" in why
    assert routes._one(mctx, "Script 1")["track"] == {"state": "failed", "why": why}


async def test_the_stems(mctx: Any) -> None:
    made = await tracked(mctx)
    await land(mctx, made)
    stems = mctx.files.roots["sounds"] / "Script 1" / "stems"
    stems.mkdir(parents=True)
    (stems / "Character 7.wav").write_bytes(b"kept before")
    answer = await call(mctx, "script_stems", {})
    job = mctx.jobs.made[-1]
    assert answer["state"] == [f"Script 1 · Stems: 6 lanes mixing (job {job.id})"]
    assert [t["solo"] for t in job.plan.tasks] == [None, 0, 1, 2, 3, 4, 5]
    assert all(t["target"] is None for t in job.plan.tasks[1:])
    await land(mctx, job)
    got = on_disk(mctx)["renders"]["stems"]
    assert got["Character 7"]["file"] == "Script 1/stems/Character 7-2.wav" and \
        (stems / "Character 7.wav").read_bytes() == b"kept before"
    assert got["room"]["file"] == "Script 1/stems/room.wav" and \
        got["room"]["size"] == (stems / "room.wav").stat().st_size
    await call(mctx, "script_stems", {})
    await land(mctx, mctx.jobs.made[-1], 3.0)
    assert on_disk(mctx)["renders"]["stems"]["room"]["file"] == "Script 1/stems/room.wav", "its own stem replaced"
    assert not (stems / "room-2.wav").exists() and (stems / "Character 7.wav").read_bytes() == b"kept before"


async def test_the_routes_states_note_and_why(mctx: Any) -> None:
    await cued(mctx)
    assert routes._one(mctx, "Script 1")["track"] == {"state": "none"}
    mctx.cue.pop("room")
    await call(mctx, "script_track", {})
    made = mctx.jobs.made[-1]
    await run(mctx, made, lambda k: measured(k, made.plan))
    job = mctx.jobs.made[-1]
    note = "room tone left out: room tone needs a sound model; none is in the engine's list"
    assert job.plan.finish.made["mix"]["note"] == note
    await land(mctx, job)
    assert routes._one(mctx, "Script 1")["track"]["note"] == note
    s = on_disk(mctx)
    s["takes"]["c1"]["measured"]["gain_db"] = -8.0
    (mctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(s), encoding="utf-8")
    assert routes._one(mctx, "Script 1")["track"]["state"] == "stale", "the takes changed; the WAV still plays"
    assert routes.track_state(mctx, "Script 1", {**on_disk(mctx), "lock": {"locked": False, "at": None}}) is None


# ---------------------------------------------------------------- the file
async def test_the_file_reads_and_refuses_what_the_mix_writes(mctx: Any) -> None:
    await land(mctx, await tracked(mctx))
    await call(mctx, "script_stems", {})
    await land(mctx, mctx.jobs.made[-1])
    good, chars = on_disk(mctx), routes.characters(mctx)
    assert scriptshape.read(copy.deepcopy(good), chars) == good and good["renders"]["stems"]

    def refused(change: Any) -> str:
        bad = copy.deepcopy(good)
        change(bad)
        with pytest.raises(Invalid) as e:
            scriptshape.read(bad, chars)
        return e.value.text
    first = lambda s: s["mix"]["lanes"][0]                               # noqa: E731
    assert refused(lambda s: first(s).update(duck=True)) == "mix, lane 1: the dialogue lane is never ducked"
    assert refused(lambda s: s["mix"]["lanes"][-1].update(duck=True)) == "mix, lane 6: the room lane is never ducked"
    many = copy.deepcopy(good)                                         # 21 lanes read, no most
    many["mix"]["lanes"].extend({**copy.deepcopy(first(many)), "name": f"x{k}"} for k in range(15))
    assert len(scriptshape.read(many, chars)["mix"]["lanes"]) == 21
    full = copy.deepcopy(good)                                         # 1001 clips read, no most
    first(full)["clips"] = [copy.deepcopy(first(full)["clips"][0]) for _ in range(1001)]
    assert len(first(scriptshape.read(full, chars))["clips"]) == 1001
    assert refused(lambda s: s["mix"].update(lanes={})) == "mix: lanes is a list"
    assert "gain_db" in refused(lambda s: first(s)["clips"][0].update(gain_db=41))
    assert "in ≤ out" in refused(lambda s: first(s)["clips"][0].update(in_ms=9_000))
    assert "format does not know" in refused(lambda s: first(s)["clips"][0].update(extra=1))
    assert "format does not know" in refused(lambda s: s["renders"].update(extra=1))
    assert "measured" in refused(lambda s: layout.shots(s)[0]["measured"].update(start_ms=9, end_ms=3))
    assert "measured" in refused(lambda s: layout.shots(s)[0]["events"][0]["measured"].update(start_ms=True))
    places = {"a clip": lambda s: first(s)["clips"][0], "the target": lambda s: s["mix"]["target"],
              "a shot": lambda s: layout.shots(s)[0]["measured"],
              "a stem": lambda s: next(iter(s["renders"]["stems"].values()))}
    for what, part in places.items():
        key = next(k for k, v in part(good).items() if isinstance(v, (int, float)) and not isinstance(v, bool))
        for bad in (math.nan, math.inf):
            assert "not a finite number" in refused(lambda s, f=part, k=key, b=bad: f(s).update({k: b})), what
    old = {k: v for k, v in good.items() if k not in ("context", "lock", "takes", "mix", "renders")} | {"version": 1}
    for sc in old["scenes"]:
        sc.pop("seconds", None)
        sc.pop("done", None)                                        # version 2's
    for sh in (sh for sc in old["scenes"] for sh in sc["shots"]):
        sh.pop("measured")
        sh.pop("id", None)
        sh.pop("camera", None)
        sh["events"] = [ev for ev in sh["events"] if ev["kind"] != "panel" and not ev.get("auto")]
        for ev in sh["events"]:
            ev.pop("measured")
    scriptshape.read(copy.deepcopy(old), chars)
    measured_v1 = copy.deepcopy(old)
    measured_v1["scenes"][0]["shots"][0]["measured"] = {"start_ms": 0, "end_ms": 10}
    for extra in ({"mix": good["mix"]}, {"renders": good["renders"]}):
        assert "format does not know" in refused(lambda s, e=extra: (s.clear(), s.update(copy.deepcopy(old)),
                                                                     s.update(e)))
    assert "format does not know" in refused(lambda s: (s.clear(), s.update(copy.deepcopy(measured_v1))))


async def test_unlock_takes_every_measured_out(mctx: Any) -> None:
    made = await tracked(mctx)
    await land(mctx, made)
    assert every_measured(on_disk(mctx))
    await call(mctx, "script_unlock", {})
    s = on_disk(mctx)
    assert not any("measured" in sh or any("measured" in ev for ev in sh["events"]) for sh in layout.shots(s))
    assert "mix" in s and "renders" in s and "takes" in s and lock.locked(s) is False
    assert isinstance(Path(mctx.files.roots["sounds"] / "Script 1.wav").stat().st_size, int)


# ---------------------------------------------------------------- the read shows the track; no WAV read
def _untracked(lines: list[str]) -> list[str]:
    return [ln.split(" · track ")[0] for ln in lines if not ln.startswith("track: ")]


async def test_the_read_shows_the_track_after_a_mix_and_reads_as_today_before(mctx: Any, monkeypatch: Any) -> None:
    made = await tracked(mctx)
    before = (await call(mctx, "script_read", {}))["read"]
    with monkeypatch.context() as m:
        m.setattr(routes, "track_state", lambda *a: None)              # a call with no track given
        assert (await call(mctx, "script_read", {}))["read"] == before, "before a mix, word for word"
    assert not any(" · track" in ln or ln.startswith("track: ") for ln in before)
    await land(mctx, made)
    after, s = (await call(mctx, "script_read", {}))["read"], on_disk(mctx)
    assert after[1].startswith("5 takes: 5 ok"), "the takes line right after the head"
    assert after[2] == f"track: current · Script 1.wav · {layout.secs(s['mix']['length_ms'])} s"
    assert _untracked(after) == before, "every other part of every line as before"
    for sh in layout.shots(s):
        m = sh["measured"]
        assert any(ln.startswith(f"{sh['id']} · scene ") and ln.endswith(
            f" · track {layout.secs(m['start_ms'])}–{layout.secs(m['end_ms'])} s") for ln in after), sh["id"]
        for ev in sh["events"]:
            m = ev["measured"]
            end = f" · track {layout.secs(m['at_ms'])} s" if ev["kind"] == "panel" else \
                f" · track {layout.secs(m['start_ms'])}–{layout.secs(m['end_ms'])} s"
            assert sum(ln.startswith(f"{ev['id']} ") and ln.endswith(end) for ln in after) == 1, ev["id"]


async def test_the_routes_current_check_never_reads_the_room_wav(mctx: Any, monkeypatch: Any) -> None:
    await tracked(mctx)
    s = on_disk(mctx)
    s["takes"]["room"]["measured"] = None
    (mctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(s), encoding="utf-8")
    mix.remix(mctx, "Script 1")
    await land(mctx, mctx.jobs.made[-1])
    held = on_disk(mctx)["mix"]
    assert held["room_ms"] == 1000, "the job read its file's length, and recorded it"

    def never(*a: Any) -> float:
        raise AssertionError("a WAV read on the route")
    monkeypatch.setattr(mix, "sound_exact", never)
    monkeypatch.setattr(routes, "sound_exact", never)
    assert routes._one(mctx, "Script 1")["track"]["state"] == "current"
    assert (await call(mctx, "script_read", {}))["read"][2].startswith("track: current · Script 1.wav · ")
    s = on_disk(mctx)
    s["mix"].pop("room_ms")
    (mctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(s), encoding="utf-8")
    assert routes._one(mctx, "Script 1")["track"]["state"] == "stale", "no length recorded: stale, never a read"
    s["mix"]["room_ms"] = -1
    (mctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(s), encoding="utf-8")
    with pytest.raises(Invalid, match="room_ms is a whole millisecond"):
        scriptshape.read(copy.deepcopy(s), routes.characters(mctx))


# ---------------------------------------------------------------- a mix that is not an object is named
async def test_a_mix_not_an_object_is_named_on_its_row_and_in_its_read(mctx: Any) -> None:
    await land(mctx, await tracked(mctx))
    good, chars, folder = on_disk(mctx), routes.characters(mctx), mctx.files.roots["scripts"]
    for bad in ([], "x", 3, True):
        with pytest.raises(Invalid) as e:
            scriptshape.read({**copy.deepcopy(good), "mix": bad}, chars)
        assert e.value.text == "mix: the mix is not an object", bad
    (folder / "Bad.json").write_text(json.dumps({**good, "mix": []}), encoding="utf-8")
    rows = {r["name"]: r for r in scripts.listing(folder, chars)}
    assert {"Script 1", "Bad"} <= set(rows) and rows["Script 1"]["problem"] is None
    assert rows["Bad"]["problem"] == "mix: the mix is not an object"
    assert scripts.one(folder, "Bad", chars)["problem"] == "mix: the mix is not an object"
