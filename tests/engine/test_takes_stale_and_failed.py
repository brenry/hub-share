"""Takes and the Track job. A lengthened cue is stale; one failed take never ends a Track job, each id failing with
its own line; Flash Attention looked for at every catalog; a 400 ms slice measured over its speech; each model once per
job; a cue kind with no sound model left out in one line, at the press and at the mix."""
from __future__ import annotations

import json
import math
import shutil
import struct
import sys
import types
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hub.core import jobgraph
from hub.core.api import Take
from hub.modules.director import audioscript, mix, routes, track
from hub.worker.adapters import soundtask, takemeasure
from tests.engine.test_cue_takes import MUSIC, PICK_SFX, SFX, cued, events, measured, rows_of
from tests.engine.test_script_mix import land, mctx, track_ctx  # noqa: F401
from tests.engine.test_script_tools import on_disk
from tests.engine.test_script_track import call as tcall
from tests.engine.test_script_track import ctx, payload, refused, run  # noqa: F401
from tests.fakes.wav import tiny_wav

MUSIC_GONE = "music cues need a sound model; none is in the engine's list"
ROOM_GONE = "room tone needs a sound model; none is in the engine's list"


def write(path: Path, segs: list[tuple[float, str, float]], rate: int = 48_000) -> None:
    """`wav.py`'s writer: (seconds, "sine" | "silence", amplitude) segments, a 1 kHz sine, 16-bit mono."""
    frames = []
    for s, kind, amp in segs:
        for i in range(round(s * rate)):
            v = amp * math.sin(2 * math.pi * 1000 * i / rate) if kind == "sine" else 0.0
            frames.append(max(-32768, min(32767, round(v * 32767))))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(frames)}h", *frames))


def _save(held: Any, script: dict) -> None:
    (held.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(script), encoding="utf-8")


async def test_cue_lengthened_keeps_its_too_short_take(ctx: Any) -> None:  # noqa: F811
    """C3 planned at 9 s after its take: stale, another hash, rendered again at 9 s."""
    await cued(ctx)
    await tcall(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    await run(ctx, made, lambda k: measured(k, made.plan))
    takes = on_disk(ctx)["takes"]
    script = on_disk(ctx)
    for shot in script["scenes"][0]["shots"]:
        for ev in shot["events"]:
            if ev["id"] == "c3":
                ev["end_ms"] = ev["start_ms"] + 9_000
                shot["end_ms"] = max(shot["end_ms"], ev["end_ms"])
    _save(ctx, script)
    c3 = events(ctx, "cue")["c3"]
    assert audioscript.cap(c3) == 9 and audioscript.sound_hash(c3) != takes["c3"]["hash"]
    assert audioscript.take("Script 1", c3, takes, present={takes["c3"]["file"]})["state"] == "stale"
    assert rows_of(ctx)["c3"]["take"]["state"] == "stale"
    got = await tcall(ctx, "script_track", {})
    again = ctx.jobs.made[-1].plan
    assert [(t["prompt"], t["seconds"]) for t in again.tasks] == [("A sting", 9)]
    assert got["state"][0].startswith("Script 1 · Track: 1 cue rendering (job ")


async def _engine(held: Any, made: Any, fails: set[int]) -> dict[int, str]:
    """The lane as the core runs it (`engine.py`): a task of `fails` fails, and the job ends unless
    `jobgraph.absorbs` says it is a failed take (then its line is the fake lane's, `test_script_track.run`)."""
    plan, landed = made.plan, {}
    day = held.files.roots["sounds"] / "2026-10-20"
    day.mkdir(parents=True, exist_ok=True)
    for k in range(1, len(plan.tasks) + 1):
        if not jobgraph.runs(plan, k, made.takes, landed, plan.judge):
            continue
        if k in fails:
            assert jobgraph.absorbs(plan, k, landed, plan.judge), f"task {k}: a failed take, not a failed job"
            made.takes[k] = Take(False, (), f"take failed: out of memory {k}")
            continue
        f = day / f"1200{k:02d}-000.wav"
        f.write_bytes(tiny_wav(1.0, rate=8000))
        landed[k] = f"sounds/2026-10-20/{f.name}"
        made.takes[k] = plan.judge.done(k, {"task": k, "ok": True, "judge": measured(k, plan)})
    await plan.finish(landed)
    return landed


async def test_a_failed_cue_or_line_ends_the_whole_job(ctx: Any) -> None:  # noqa: F811
    """The first cue's task and every take of l1 fail: every other task runs, each id fails with its own line."""
    await cued(ctx)
    await tcall(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    plan = made.plan
    assert plan.summary["step_names"][6] == "c1"
    assert jobgraph.absorbs(plan, 7, {}, plan.judge) and jobgraph.absorbs(plan, 3, {}, plan.judge)
    generate = SimpleNamespace(again=lambda shot, take: False)            # Generate's shot takes: no `alone`
    assert not jobgraph.absorbs(plan, 7, {}, generate) and not jobgraph.absorbs(plan, 3, {}, generate)
    landed = await _engine(ctx, made, {1, 2, 3, 7})
    assert sorted(landed) == [4, 8, 9, 10], "l2's first take, c2, the room and c3 all ran"
    assert set(on_disk(ctx)["takes"]) == {"l2", "c2", "c3", "room"}
    assert track.state("Script 1") == {"l1": ("failed", "take failed: out of memory 3"),
                                   "c1": ("failed", "take failed: out of memory 7")}, "each its own line"


def test_flash_ready_is_cached_for_the_worker_life(monkeypatch) -> None:
    """Installed after a first False, found at the next call; `cue_facts` of a `flash` model then not blocked."""
    monkeypatch.delitem(sys.modules, "flash_attn", raising=False)
    facts = {"cues": {"effect": ["m"], "flash": ["m"]}}
    if soundtask.flash_ready():
        pytest.skip("Flash Attention is installed here")
    assert soundtask.cue_facts(facts, "m") == {"cues": {"effect": 0}, "blocked": soundtask.BLOCKED}
    fake = types.ModuleType("flash_attn")
    fake.flash_attn_varlen_func = lambda *a: None                         # type: ignore[attr-defined]
    fake.__spec__ = SimpleNamespace(name="flash_attn", loader=None, submodule_search_locations=None, parent="",
                                    has_location=False, origin=None, cached=None)    # type: ignore[assignment]
    monkeypatch.setitem(sys.modules, "flash_attn", fake)
    assert soundtask.flash_ready() is True and not hasattr(soundtask.flash_ready, "cache_clear")
    assert soundtask.cue_facts(facts, "m") == {"cues": {"effect": 0}}


SUMMARY = ("[Parsed_ebur128_0 @ 0x2] Summary:\n  Integrated loudness:\n    I:  -23.0 LUFS\n  True peak:\n"
           "    Peak: -20.0 dBFS")


def test_a_400_ms_slice_is_measured_over_its_speech() -> None:
    """Silencedetect puts the speech at 0.500021-0.9 s: the slice is 400 ms as the record writes it."""
    calls: list[list[str]] = []

    def stand_in(args: list[str]) -> str:
        calls.append(args)
        if any("silencedetect" in a for a in args):
            return "silence_start: 0\nsilence_end: 0.500021\nsilence_start: 0.9\nsilence_end: 1.4\n"
        return SUMMARY
    got = takemeasure.measure("t.wav", None, run=stand_in, length=lambda p: 1.4)
    assert (got["speech_start_ms"], got["speech_end_ms"]) == (500, 900)
    assert calls[1][3].startswith("atrim=start=0.500:end=0.900,ebur128")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="no ffmpeg here")
def test_a_real_400_ms_tone_reads_its_level(tmp_path: Path, monkeypatch) -> None:
    """With a real ffmpeg: a 400 ms tone between 0.5 s silences reads -23.0 ± 0.2 LUFS over its slice; a 380 ms
    one is measured over the whole take."""
    monkeypatch.setattr(takemeasure.soundtail, "ffmpeg", lambda: shutil.which("ffmpeg"))
    seen: list[list[str]] = []
    real = takemeasure._ffmpeg

    def spy(program: str) -> Any:
        inner = real(program)
        return lambda args: seen.append(args) or inner(args)
    monkeypatch.setattr(takemeasure, "_ffmpeg", spy)
    for ms, sliced in ((400, True), (380, False)):
        path = tmp_path / f"tone{ms}.wav"
        write(path, [(0.5, "silence", 0), (ms / 1000, "sine", 0.1), (0.5, "silence", 0)])
        got = takemeasure.measure(str(path), None)
        assert ("atrim=" in seen[-1][seen[-1].index("-af") + 1]) is sliced, ms
        if sliced:
            assert got["speech_end_ms"] - got["speech_start_ms"] == 400 and abs(got["lufs"] - -23.0) <= 0.2


async def test_each_model_loads_once_and_the_room_beside_its_cues(ctx: Any) -> None:  # noqa: F811
    """C1 effect and c2 reaction on the sfx model, c3 music on the music model, the room on the sfx model."""
    await cued(ctx)
    await tcall(ctx, "script_track", {})
    plan = ctx.jobs.made[-1].plan
    assert [t["model"] for t in plan.tasks[6:]] == [SFX, SFX, SFX, MUSIC]
    assert plan.summary["step_names"][6:] == ["c1", "c2", "room", "c3"]
    assert plan.takes[2:] == (((7,),), ((8,),), ((9,),), ((10,),)) and plan.judge.kinds == {
        3: "effect", 4: "reaction", 5: "room", 6: "music"}, "each its own one-take group, judged by its kind"
    track.running.clear()
    ctx.cue["room"] = {**PICK_SFX, "id": "room_model", "label": "Room"}
    await tcall(ctx, "script_track", {})
    again = ctx.jobs.made[-1].plan
    assert [t["model"] for t in again.tasks[6:]] == [SFX, SFX, MUSIC, "room_model"], "a model no cue uses: last"
    assert again.summary["step_names"][6:] == ["c1", "c2", "c3", "room"]


async def test_a_cue_kind_with_no_model_is_left_out_in_one_line(ctx: Any) -> None:  # noqa: F811
    """The lines, the other cues and the room render; the music cue is
    left out, said in one line; then at the mix, the same."""
    await cued(ctx)
    ctx.cue.pop("music")
    answer = await tcall(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    assert answer["state"] == [f"Script 1 · Track: 2 lines, 2 cues and the room rendering, up to 3 takes per line "
                               f"(job {made.id})", f"music left out: {MUSIC_GONE}"]
    assert made.plan.summary["step_names"][6:] == ["c1", "c2", "room"]
    assert "c3" not in track.running["Script 1"]["ids"] and rows_of(ctx)["c3"]["take"]["state"] == "none"
    await run(ctx, made, lambda k: measured(k, made.plan))
    assert "c3" not in on_disk(ctx)["takes"] and rows_of(ctx)["c3"]["take"]["state"] == "none", "it stays none"


async def test_every_kind_left_out_goes_to_the_mix_and_says_so(mctx: Any) -> None:  # noqa: F811
    """Music and the room refused; once the lines and the other cues are in, nothing is left to
    render: the press mixes, the mix's note the two lines; once that mix is current, `CURRENT` with them."""
    await cued(mctx)
    mctx.cue.pop("music")
    mctx.cue.pop("room")
    answer = await tcall(mctx, "script_track", {})
    assert answer["state"][1:] == [f"music left out: {MUSIC_GONE}", f"room tone left out: {ROOM_GONE}"]
    made = mctx.jobs.made[-1]
    await run(mctx, made, lambda k: measured(k, made.plan))
    after = mctx.jobs.made[-1]
    assert after.kind == "director.mix", "the finish mixed: every take of a kind with a model is in"
    after.state = "failed"                                       # that mix ended without landing
    mctx.cue.clear()                                             # every cue kind and the room refused now
    note = f"music left out: {MUSIC_GONE}; room tone left out: {ROOM_GONE}"
    got = await tcall(mctx, "script_track", {})
    mixing = mctx.jobs.made[-1]
    assert got["state"] == [f"Script 1 · Track: nothing to render; mixing (job {mixing.id})", note]
    await land(mctx, mixing)
    script = on_disk(mctx)
    assert script["mix"]["note"] == note
    assert not any(c["take"] == "c3" for lane in script["mix"]["lanes"] for c in lane["clips"])
    assert "music" not in [lane["name"] for lane in script["mix"]["lanes"]]
    assert "measured" in events(mctx, "cue")["c3"], "mapped through the placement as a pose is"
    assert routes.current(mctx, "Script 1", script)
    assert (await refused(mctx, "script_track", {}))["problem"] == f"{mix.CURRENT}; {note}"
