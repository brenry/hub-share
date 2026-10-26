"""Track (`hub/modules/director/track.py`, `takejudge.py`, `audioscript.py`,
`routes.py`, `lock.py`): on a test context with a stand-in Characters holding stdlib WAV samples and a stand-in speech
service, a locked script's lines rendered as takes by a stand-in lane that runs the core's take rule
(`jobgraph.runs`); the refusals; one request per take as the block says; only none or stale lines; the verdicts;
the finish filing every take and recording the best; the route's take states; the read wall on NaN and Infinity."""
from __future__ import annotations

import copy
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hub.core import jobgraph
from hub.core.api import Invalid, Take
from hub.modules.director import (
    audioscript,
    autolock,
    drawing,
    manifest,
    routes,
    scripts,
    scriptshape,
    takejudge,
    track,
)
from hub.modules.generate_image import models as gmodels
from hub.modules.generate_image import tools as gtools
from tests.engine.test_script_drawing import DrawCtx
from tests.engine.test_script_lock import whole
from tests.engine.test_script_tools import on_disk
from tests.fakes.wav import tiny_wav

MODEL = {"id": "h3", "label": "H3 Speech", "seconds": {"min": 1, "max": 30}, "takes_max": 3, "words_bar": 0.9,
         "unscripted_s": 2.5}
GOOD = {"length_ms": 3000, "speech_start_ms": 200, "speech_end_ms": 2800, "extra_s": 0.0, "lufs": -24.1,
        "true_peak_dbtp": -6.0}
HEARD = {"heard": 1.0, "first_miss": None, "first": 0.3, "last": 2.6}
BARS = {"words_bar": 0.9, "unscripted_s": 2.5, "takes_max": 3}


class Jobs:
    """The core's book, faked: a submit builds the kind's plan (its refusal raised), keeps the job queued."""

    def __init__(self, ctx: Any) -> None:
        self.ctx, self.made, self.book = ctx, [], {}

    def submit(self, kind: str, params: dict) -> Any:
        build = track.job if kind == track.KIND else drawing.job
        plan = build(copy.deepcopy(params), self.ctx)
        job = SimpleNamespace(id=f"j{len(self.made) + 1}", kind=f"director.{kind}", state="queued", error=None,
                              plan=plan, params=params, takes={})
        self.made.append(job)
        self.book[job.id] = job
        return job

    def get(self, job_id: str) -> Any:
        return self.book.get(job_id)


class TrackCtx(DrawCtx):
    def __init__(self, tmp: Path) -> None:
        super().__init__(tmp)
        self.jobs = Jobs(self)
        self.speech: dict | None = dict(MODEL)
        self.cue: dict[str, dict] = {}                 # kind -> its sound model; none by default

    def service(self, name: str) -> Any:
        if name == "speech":
            return self._speech
        if name == "cue":
            return self._cue
        return super().service(name)

    def _cue(self, kind: str) -> dict:
        if kind not in self.cue:
            lead = "room tone needs" if kind == "room" else f"{kind} cues need"
            raise Invalid("model", f"{lead} a sound model; none is in the engine's list")
        return self.cue[kind]

    def _speech(self) -> dict:
        if self.speech is None:
            raise Invalid("model", gtools.NO_SPEECH_MODEL)
        return self.speech


async def call(ctx: Any, name: str, args: dict) -> dict:
    """A director tool by name, `script_track` included (the module's actions)."""
    return await next(a.fn for a in manifest.MODULE.actions if a.name == name)(ctx, args)


async def refused(ctx: Any, name: str, args: dict) -> dict:
    """The refusal's {problem, fix, hints}; the script byte for byte as it was."""
    path = ctx.files.roots["scripts"] / "Script 1.json"
    before = path.read_bytes() if path.exists() else None
    with pytest.raises(Invalid) as e:
        await call(ctx, name, args)
    assert (path.read_bytes() if path.exists() else None) == before, "the file untouched"
    return json.loads(e.value.text)


def sample(ctx: TrackCtx, name: str, seconds: float) -> Path:
    path = ctx.files.roots["chars"] / f"{name}.wav"
    path.write_bytes(tiny_wav(seconds, rate=8000))
    return path


@pytest.fixture
async def ctx(tmp_path: Path) -> Any:
    await drawing.stop()
    drawing.waiting.clear()
    drawing.failed.clear()
    track.running.clear()
    track.failed.clear()
    held = TrackCtx(tmp_path)
    for name in ("Character 7", "Character 6"):
        sample(held, name, 2.5)
    yield held
    await drawing.stop()
    track.running.clear()
    track.failed.clear()
    autolock.said.clear()
    autolock.pending.clear()


async def lock_only(ctx: Any, name: str = "Script 1") -> None:
    """The script locked by the Hub as a press locks it, Track not pressed."""
    await autolock.settle(ctx, name)


async def locked(ctx: TrackCtx) -> None:
    await whole(ctx)
    await lock_only(ctx)


def payload(words: dict | None = HEARD, measure: dict | None = GOOD) -> dict:
    return {k: v for k, v in (("words", words), ("measure", measure)) if v is not None}


async def run(ctx: TrackCtx, made: Any, verdict: Any = None) -> dict[int, str]:
    """The lane, faked: each task the core's take rule runs lands a WAV in `sounds/<day>/` and is judged with
    `verdict(task)` (None: the task fails); then the plan's finish. -> the landed ids."""
    plan, landed = made.plan, {}
    day = ctx.files.roots["sounds"] / "2026-10-20"
    day.mkdir(parents=True, exist_ok=True)
    for k in range(1, len(plan.tasks) + 1):
        if not jobgraph.runs(plan, k, made.takes, landed, plan.judge):
            continue
        got = payload() if verdict is None else verdict(k)
        if got is None:
            made.takes[k] = Take(False, (), f"take failed: out of memory {k}")
            continue
        f = day / f"1200{k:02d}-000.wav"
        f.write_bytes(tiny_wav(1.0, rate=8000))
        landed[k] = f"sounds/2026-10-20/{f.name}"
        take = plan.judge.done(k, {"task": k, "ok": True, "judge": got})
        if take is not None:
            made.takes[k] = take
    await plan.finish(landed)
    return landed


def rows(ctx: TrackCtx) -> dict[str, dict]:
    got = routes._one(ctx, "Script 1")
    return {r["id"]: r for r in got["audio"] if r["kind"] == "line"}


async def test_track_refuses_what_it_cannot_render(ctx: TrackCtx) -> None:
    await whole(ctx)
    with pytest.raises(Invalid) as e:
        track.job({"script": "Script 1"}, ctx)                           # a write between press and plan
    assert e.value.text == track.CHANGED.format("Script 1")
    await lock_only(ctx)
    folder = ctx.files.roots["scripts"]
    (folder / "Audience.json").write_text(json.dumps(on_disk(ctx)), encoding="utf-8")
    with pytest.raises(Invalid) as e:
        track.job({"script": "Audience"}, ctx)
    assert e.value.text == track.AUDIENCE
    from tests.engine.test_script_shape import EXAMPLE
    old = {k: v for k, v in EXAMPLE.items() if k != "context"} | {"version": 1}
    (folder / "Old.json").write_text(json.dumps(old), encoding="utf-8")
    with pytest.raises(Invalid) as e:
        track.job({"script": "Old"}, ctx)
    assert e.value.text == track.OLD.format("Old")
    ctx.speech = None
    got = await refused(ctx, "script_track", {})
    assert got["problem"] == "Pick a speech model in Generate"
    assert got["fix"] == "Pick a speech model in Generate, then call script_track again"
    ctx.speech = dict(MODEL)
    (ctx.files.roots["chars"] / "Character 7.wav").unlink()
    got = await refused(ctx, "script_track", {})
    assert got["problem"] == "l1: Character 7 has no voice sample in Characters"
    assert got["fix"] == ("Put Character 7.wav of at least 2 s beside the speaker's picture in Characters, then call "
                          "script_track again")
    sample(ctx, "Character 7", 1.5)                              # replaced after the lock by a short one
    assert (await refused(ctx, "script_track", {}))["problem"] == "l1: Character 7's voice sample is 1.50 s, under 2 s"
    (ctx.files.roots["chars"] / "Character 7.wav").write_bytes(b"RIFF")
    assert (await refused(ctx, "script_track", {}))["problem"] == \
        "l1: Character 7's voice sample does not read as a WAV"
    assert ctx.jobs.made == [] or all(j.kind != "director.track" for j in ctx.jobs.made)


async def test_one_request_per_take_as_the_block_says(ctx: TrackCtx) -> None:
    await locked(ctx)
    sent = len(ctx.bus.sent)
    answer = await call(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    assert answer == {"script": "Script 1", "state": [   # lines, cues and the room counted; the room left out
        f"Script 1 · Track: 2 lines rendering, up to 3 takes per line (job {made.id})",
        "room tone left out: room tone needs a sound model; none is in the engine's list"]}
    assert len(ctx.bus.sent) == sent + 1, "published once submitted: the tab shows rendering"
    plan, script = made.plan, on_disk(ctx)
    assert plan.lane_kind == "image" and plan.model == "h3" and len(plan.tasks) == 6
    assert plan.takes == (((1,), (2,), (3,)), ((4,), (5,), (6,)))
    assert plan.summary["prompt"] == "Track · Script 1" and plan.summary["count"] == 2
    lines = sorted((ev for s in script["scenes"][0]["shots"] for ev in s["events"] if ev["kind"] == "line"),
                   key=lambda ev: ev["start_ms"])
    for k, task in enumerate(plan.tasks):
        ev = lines[k // 3]
        block = audioscript.block(ev)[0]
        assert task["kind"] == "speech" and task["prompt"] == block[len("Speaker 1:\n"):]
        assert task["turn_seconds"] is None and task["pace"] is None and task["join_seconds"] is None
        assert task["judge"] is True and task["measure"] is True and task["direction"] is None
        assert task["seconds"] == audioscript.cap(ev)
        assert task["sample"] == str((ctx.files.roots["chars"] / f"{ev['speaker']}.wav").absolute())
        assert task["seed"] is None and task == plan.tasks[k // 3 * 3], "a line's takes, one request again"
    assert track.state("Script 1") == {"l1": ("rendering", None), "l2": ("rendering", None)}
    assert rows(ctx)["l1"]["take"] == {"state": "rendering", "file": "Script 1/l1-1.wav"}
    assert (await refused(ctx, "script_track", {}))["problem"] == f"Script 1's takes are rendering (job {made.id})"
    await run(ctx, made)
    ctx.speech = {**MODEL, "seconds": {"min": 1, "max": 6}}
    script = on_disk(ctx)
    script.pop("takes")
    (ctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(script), encoding="utf-8")
    held = await call(ctx, "script_track", {})
    assert held["state"][0].startswith("Script 1 · Track: 2 lines")
    assert {t["seconds"] for t in ctx.jobs.made[-1].plan.tasks} <= {6}, "the cap held to the model's most"


async def test_the_finish_files_every_take_and_records_the_best(ctx: TrackCtx) -> None:
    await locked(ctx)
    old = ctx.files.roots["sounds"] / "Script 1"
    old.mkdir(parents=True)
    (old / "l1-1.wav").write_bytes(tiny_wav(1.0, rate=8000))          # one there already: never overwritten
    await call(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    under = payload({"heard": 0.5, "first_miss": 1.4, "first": 0.3, "last": 2.6})
    judged = {1: under, 2: payload(), 4: payload(measure={**GOOD, "lufs": -40.0, "true_peak_dbtp": -20.0})}
    sent = len(ctx.bus.sent)
    landed = await run(ctx, made, lambda k: judged[k])
    assert sorted(landed) == [1, 2, 4], "l1 taken again under the bar; l2's level flags, never re-takes"
    assert sorted(p.name for p in old.iterdir()) == ["l1-1.wav", "l1-2.wav", "l1-3.wav", "l2-1.wav"]
    assert not list((ctx.files.roots["sounds"] / "2026-10-20").iterdir()), "every take moved"
    takes = on_disk(ctx)["takes"]
    assert on_disk(ctx)["lock"]["locked"] is True, "a locked script takes its take record"
    voice = ctx.files.roots["chars"] / "Character 7.wav"
    facts = [voice.stat().st_size, int(voice.stat().st_mtime)]
    l1 = next(ev for s in on_disk(ctx)["scenes"][0]["shots"] for ev in s["events"] if ev["id"] == "l1")
    assert takes["l1"] == {"file": "Script 1/l1-3.wav", "hash": audioscript.sound_hash(l1, facts), "tries": 2,
                           "measured": {"speech_start_ms": 200, "speech_end_ms": 2800, "length_ms": 3000,
                                        "lufs": -24.1, "true_peak_dbtp": -6.0, "gain_db": 1.1},
                           "judge": {"heard": 1.0, "first_miss_ms": None, "extra_speech": 0.0, "verdict": "ok",
                                     "why": None}}
    assert takes["l2"]["judge"]["verdict"] == "flagged" and takes["l2"]["judge"]["why"] == "level: -40.0 LUFS"
    assert takes["l2"]["tries"] == 1 and takes["l2"]["measured"]["gain_db"] == 17.0
    assert len(ctx.bus.sent) == sent + 1 and "Script 1" not in track.running
    got = rows(ctx)
    assert got["l1"]["take"]["state"] == "ok" and got["l1"]["take"]["url"] == ctx.files.url("sounds/Script 1/l1-3.wav")
    assert got["l2"]["take"] == {"state": "flagged", "file": "Script 1/l2-1.wav", "why": "level: -40.0 LUFS",
                                 "url": ctx.files.url("sounds/Script 1/l2-1.wav"), "measured": takes["l2"]["measured"],
                                 "judge": takes["l2"]["judge"]}
    mixing = ctx.jobs.made[-1]                                    # the finish submitted the mix
    assert (mixing.kind, mixing.params) == ("director.mix", {"script": "Script 1", "stems": False})
    assert (await refused(ctx, "script_track", {}))["problem"] == f"Script 1 is mixing (job {mixing.id})"
    (old / "l2-1.wav").unlink()
    assert rows(ctx)["l2"]["take"] == {"state": "none", "file": "Script 1/l2-1.wav"}, "a missing file is none"
    await call(ctx, "script_track", {})
    assert ctx.jobs.made[-1].plan.summary["count"] == 1, "only the line whose take is gone"


async def test_a_changed_line_and_a_replaced_sample_render_alone(ctx: TrackCtx) -> None:
    await locked(ctx)
    await call(ctx, "script_track", {})
    await run(ctx, ctx.jobs.made[-1])
    script = on_disk(ctx)
    l2 = next(ev for s in script["scenes"][0]["shots"] for ev in s["events"] if ev["id"] == "l2")
    l2["words"] = l2["words"].replace("lovely", "grand")
    (ctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(script), encoding="utf-8")
    assert rows(ctx)["l2"]["take"]["state"] == "stale" and rows(ctx)["l1"]["take"]["state"] == "ok"
    await call(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    assert made.plan.summary["count"] == 1 and "Thank you" in made.plan.tasks[0]["prompt"]
    await run(ctx, made)
    assert sorted(p.name for p in (ctx.files.roots["sounds"] / "Script 1").iterdir()) == [
        "l1-1.wav", "l2-1.wav", "l2-2.wav"], "the old take kept"
    assert on_disk(ctx)["takes"]["l2"]["file"] == "Script 1/l2-2.wav"
    voice = sample(ctx, "Character 7", 3.0)                     # other bytes, another size
    os.utime(voice, (time.time() + 5, time.time() + 5))
    assert rows(ctx)["l1"]["take"]["state"] == "stale" and rows(ctx)["l2"]["take"]["state"] == "ok"
    await call(ctx, "script_track", {})
    assert [t["prompt"] for t in ctx.jobs.made[-1].plan.tasks][0].endswith(
        next(ev["words"] for s in script["scenes"][0]["shots"] for ev in s["events"] if ev["id"] == "l1"))
    assert ctx.jobs.made[-1].plan.summary["count"] == 1


async def test_a_line_with_no_take_landed_is_failed_until_the_next_press(ctx: TrackCtx) -> None:
    await locked(ctx)
    await call(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    made.error = "Out of memory"
    await run(ctx, made, lambda k: None if k <= 3 else payload())
    assert track.state("Script 1") == {"l1": ("failed", "take failed: out of memory 3")}
    assert rows(ctx)["l1"]["take"] == {"state": "failed", "why": "take failed: out of memory 3"}, \
        "no take landed, no file named"
    assert "l1" not in on_disk(ctx)["takes"] and on_disk(ctx)["takes"]["l2"]["file"] == "Script 1/l2-1.wav"
    await call(ctx, "script_track", {})
    assert track.state("Script 1") == {"l1": ("rendering", None)}, "cleared by the next press"


async def test_the_script_gone_records_nothing(ctx: TrackCtx) -> None:
    await locked(ctx)
    await call(ctx, "script_track", {})
    (ctx.files.roots["scripts"] / "Script 1.json").unlink()
    await run(ctx, ctx.jobs.made[-1])
    assert sorted(p.name for p in (ctx.files.roots["sounds"] / "Script 1").iterdir()) == ["l1-1.wav", "l2-1.wav"]
    assert "Script 1" not in track.running


def test_the_verdicts() -> None:
    v = takejudge.verdict
    ok = v(HEARD, GOOD, BARS)
    assert ok.take.passes and ok.judge["verdict"] == "ok" and ok.measured["gain_db"] == 1.1
    assert ok.take.line == "heard 100 % · -24.1 LUFS · gain +1.1 dB"
    under = v({**HEARD, "heard": 0.82, "first_miss": 1.4}, GOOD, BARS)
    assert not under.take.passes and under.judge["why"] == "heard 82 %, first miss at 1.4 s"
    assert under.judge["first_miss_ms"] == 1400
    extra = v(HEARD, {**GOOD, "extra_s": 3.1}, BARS)
    assert not extra.take.passes and extra.judge["why"] == "3.1 s of sound outside the words"
    loud = v(HEARD, {**GOOD, "lufs": -35.2, "true_peak_dbtp": -8.0}, BARS)
    assert loud.take.passes and loud.judge["verdict"] == "flagged", "a level flags, never re-takes"
    assert loud.judge["why"] == "level: -35.2 LUFS; level: peaks at +4.2 dBTP after +12.2 dB"
    peak = v(HEARD, {**GOOD, "lufs": -30.0, "true_peak_dbtp": -5.7}, BARS)
    assert peak.judge["why"] == "level: peaks at +1.3 dBTP after +7.0 dB" and peak.take.passes
    unheard = v(None, GOOD, BARS)
    assert unheard.take.passes and unheard.judge["verdict"] == "flagged" and unheard.judge["why"] == takejudge.NOT_HEARD
    lost = v(HEARD, {"problem": "ffmpeg is not installed on the server"}, BARS)
    assert lost.measured is None and lost.judge["why"] == "not measured: ffmpeg is not installed on the server"
    assert ok.take.rank > loud.take.rank > under.take.rank
    j = takejudge.TrackJudge(((1,), (2,), (3,)), BARS)
    assert j.again(1, 3) and not j.again(1, 4)


def test_a_silent_take_and_numbers_that_are_not_finite() -> None:
    silent = takejudge.verdict(HEARD, {**GOOD, "speech_start_ms": 0, "speech_end_ms": 1200, "lufs": None,
                                       "true_peak_dbtp": None}, BARS)
    assert silent.judge["verdict"] == "flagged" and silent.judge["why"] == "silent"
    assert silent.measured["gain_db"] == 0.0 and silent.measured["lufs"] is None
    short = takejudge.verdict(HEARD, {**GOOD, "speech_end_ms": 500, "lufs": None}, BARS)
    assert short.judge["why"] == "level: too short to measure"
    for bad in (float("nan"), float("-inf"), float("inf")):
        got = takejudge.verdict({**HEARD, "heard": bad}, {**GOOD, "lufs": bad, "true_peak_dbtp": bad,
                                                          "extra_s": bad}, BARS)
        assert got.judge["heard"] is None and got.measured["lufs"] is None and got.measured["true_peak_dbtp"] is None
        assert got.judge["verdict"] == "flagged" and got.judge["extra_speech"] is None
        json.dumps({"measured": got.measured, "judge": got.judge}, allow_nan=False)


async def test_nan_never_reaches_the_file(ctx: TrackCtx) -> None:
    await locked(ctx)
    await call(ctx, "script_track", {})
    nan = payload(measure={**GOOD, "lufs": float("nan"), "true_peak_dbtp": float("-inf")})
    await run(ctx, ctx.jobs.made[-1], lambda k: nan)
    text = (ctx.files.roots["scripts"] / "Script 1.json").read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text
    took = on_disk(ctx)["takes"]["l1"]
    assert took["measured"]["lufs"] is None and took["measured"]["true_peak_dbtp"] is None
    assert took["judge"]["why"] == "silent"


@pytest.mark.parametrize(("key", "raw"), [("measured", '"lufs": NaN'), ("measured", '"lufs": -Infinity'),
                                          ("judge", '"heard": Infinity')])
async def test_the_read_wall_refuses_nan_and_infinity(ctx: TrackCtx, key: str, raw: str) -> None:
    await locked(ctx)
    script = on_disk(ctx)
    name = raw.split('"')[1]
    script["takes"] = {"l1": {"file": "Script 1/l1-1.wav", "hash": "0" * 16, "tries": 1, key: {name: "X"}}}
    text = json.dumps(script).replace(f'"{name}": "X"', raw)
    (ctx.files.roots["scripts"] / "Script 1.json").write_text(text, encoding="utf-8")
    with pytest.raises(Invalid) as e:
        scriptshape.read(json.loads(text), routes.characters(ctx))
    assert e.value.text == f"takes, l1: {key}.{name} is not a finite number"
    listed = scripts.listing(routes.folder(ctx), routes.characters(ctx))
    assert next(s for s in listed if s["name"] == "Script 1")["problem"] == e.value.text
    got = routes._one(ctx, "Script 1")
    assert got["script"] is None and got["problem"] == e.value.text and got["audio"] is None
    json.dumps(got, allow_nan=False)


@pytest.mark.parametrize(("take", "line"), [
    ({"measured": {"seconds": 3.4}}, "takes, l1: measured has a key the format does not know: seconds"),
    ({"measured": {"lufs": "loud"}}, "takes, l1: measured.lufs is a number or null"),
    ({"judge": {"heard": 1.5}}, "takes, l1: judge.heard is a number from 0 to 1 or null"),
    ({"judge": {"first_miss_ms": 1.5}}, "takes, l1: judge.first_miss_ms is a whole number of 0 or more or null"),
    ({"judge": {"extra_speech": -1}}, "takes, l1: judge.extra_speech is a number of 0 or more or null"),
    ({"judge": {"seed": 1}}, "takes, l1: judge has a key the format does not know: seed"),
    ({"judge": {"why": "x" * 301}}, "takes, l1: a judge's why is at most 300 characters"),
])
def test_a_malformed_record_is_refused(take: dict, line: str) -> None:
    from tests.engine.test_script_shape import CHARS, EXAMPLE
    value = {**copy.deepcopy(EXAMPLE), "takes": {"l1": {"file": "Script 1/l1-1.wav", "hash": "ab", **take}}}
    with pytest.raises(Invalid) as e:
        scriptshape.read(value, CHARS)
    assert e.value.text == line


def test_the_sample_in_the_hash() -> None:
    ev = {"id": "l3", "kind": "line", "start_ms": 0, "end_ms": 2300, "speaker": "Character 7", "words": "Hello there.",
          "language": "English", "emotion": "warm", "pace": 2.6}
    plain = audioscript.sound_hash(ev)
    with_voice = audioscript.sound_hash(ev, [44_000, 1_760_000_000])
    assert with_voice != plain and audioscript.sound_hash(ev, None) == plain
    assert audioscript.sound_hash(ev, [44_002, 1_760_000_000]) != with_voice, "another size"
    assert audioscript.sound_hash(ev, [44_000, 1_760_000_001]) != with_voice, "another whole second"
    assert audioscript.sound_hash(ev, [44_000, 1_760_000_000]) == with_voice, "the same second, read again"


async def test_the_modified_time_inside_one_second_keeps_the_hash(ctx: TrackCtx) -> None:
    await locked(ctx)
    voice = ctx.files.roots["chars"] / "Character 7.wav"
    os.utime(voice, (1_760_000_000.2, 1_760_000_000.2))
    before = rows(ctx)["l1"]["hash"]
    os.utime(voice, (1_760_000_000.9, 1_760_000_000.9))
    assert rows(ctx)["l1"]["hash"] == before == rows(ctx)["l1"]["hash"]


async def test_the_lock_refuses_a_short_sample(ctx: TrackCtx) -> None:
    """The press locks the script, then Track's own sample line is its refusal."""
    await whole(ctx)
    sample(ctx, "Character 7", 1.5)
    with pytest.raises(Invalid) as e:
        await call(ctx, "script_lock", {})
    assert json.loads(e.value.text)["problem"] == "l1: Character 7's voice sample is 1.50 s, under 2 s"
    assert on_disk(ctx)["lock"]["locked"] is True
    assert not [j for j in ctx.jobs.made if j.kind == "director.track"]


def test_the_speech_pick(monkeypatch, tmp_path: Path) -> None:
    from tests.engine.test_script_tools import Ctx
    held = Ctx(tmp_path)
    held.settings = {"speech_takes_max": 2, "speech_words_bar": 0.85, "scene_unscripted_seconds": 3.0}
    speech = {"id": "h3", "name": "H3 Speech", "family": "H3", "kind": "speech", "status": "available",
              "speech": {"seconds": {"min": 2, "max": 40, "default": 20}, "references": 1}}
    picture = {"id": "flux", "name": "Flux", "family": "Flux", "status": "available"}
    other = {**speech, "id": "h4", "name": "H4 Speech"}
    monkeypatch.setattr(gmodels, "_last", {"models": [speech, other, picture]})
    with pytest.raises(Invalid) as e:
        gtools.speech_pick(held)
    assert (e.value.field, e.value.text) == ("model", "Pick a speech model in Generate"), "two, none picked"
    held.doc("draft", {}).replace({"model": "flux"})
    with pytest.raises(Invalid):
        gtools.speech_pick(held)
    held.doc("draft", {}).replace({"model": "h3"})
    assert gtools.speech_pick(held) == {"id": "h3", "label": "H3 Speech", "seconds": {"min": 2, "max": 40},
                                        "takes_max": 2, "words_bar": 0.85, "unscripted_s": 3.0}
    assert held.doc("draft", {}).get() == {"model": "h3"}, "only read"
    # with a picture model in the pulldown, the last speech pick, else the only one, else one line
    draft = {"model": "flux", "lastModel": {"image": "flux", "video": "", "speech": "h4"}}
    held.doc("draft", {}).replace(draft)
    assert gtools.speech_pick(held)["id"] == "h4" and held.doc("draft", {}).get() == draft, "the last, only read"
    held.doc("draft", {}).replace({"model": "flux", "lastModel": {"image": "flux", "video": "", "speech": "gone"}})
    with pytest.raises(Invalid) as e:
        gtools.speech_pick(held)
    assert e.value.text == "Pick a speech model in Generate", "a last pick not present: two, none picked"
    monkeypatch.setattr(gmodels, "_last", {"models": [speech, picture]})
    held.doc("draft", {}).replace({"model": "flux"})
    assert gtools.speech_pick(held)["id"] == "h3" and held.doc("draft", {}).get() == {"model": "flux"}, "the only"
    monkeypatch.setattr(gmodels, "_last", {"models": [{**speech, "status": "missing"}, picture]})
    with pytest.raises(Invalid) as e:
        gtools.speech_pick(held)
    assert (e.value.field, e.value.text) == ("speech", "no speech model in your model folders")
    assert held.doc("draft", {}).get() == {"model": "flux"}


async def test_track_says_when_no_speech_model_is_there(ctx: TrackCtx) -> None:
    """The pick's `speech` refusal carries its own fix."""
    await locked(ctx)
    ctx.speech = None

    def none() -> dict:
        raise Invalid("speech", gtools.NO_SPEECH_THERE)
    ctx._speech = none                                    # type: ignore[method-assign]
    got = await refused(ctx, "script_track", {})
    assert got["problem"] == "no speech model in your model folders"
    assert got["fix"] == "Put a speech model in your model folders, Rescan, then call script_track again"


async def test_a_job_that_ended_without_its_finish_does_not_hold_the_script(ctx: TrackCtx) -> None:
    await locked(ctx)
    await call(ctx, "script_track", {})
    ctx.jobs.made[-1].state = "cancelled"                   # a queued job cancelled: no finish ran
    assert rows(ctx)["l1"]["take"]["state"] == "none"
    again = await call(ctx, "script_track", {})
    assert again["state"][0].endswith(f"(job {ctx.jobs.made[-1].id})") and ctx.jobs.made[-1].state == "queued"


def test_a_take_is_present_by_existence_alone(tmp_path: Path) -> None:
    """The reload checks a take's file exists, never reads the WAV whole."""
    from tests.engine.test_script_tools import Ctx
    held = Ctx(tmp_path)
    folder = held.files.roots["sounds"] / "Script 1"
    folder.mkdir(parents=True)
    (folder / "l1-1.wav").write_bytes(b"RIFF")             # not a WAV that reads: present all the same
    takes = {"l1": {"file": "Script 1/l1-1.wav"}, "l2": {"file": "Script 1/l2-1.wav"},
             "l3": {"file": "../scripts/x.wav"}}
    held.files.sound_facts = lambda item: (_ for _ in ()).throw(AssertionError("read"))   # type: ignore[method-assign]
    assert routes.present(held, takes) == {"Script 1/l1-1.wav"}
