"""Cue and room takes (`hub/worker/adapters/soundtask.py`, `upstream.py`, `catalog.py`,
`takemeasure.py`, `joins.py`; `generate_image/models.py`, `tools.py`; `director/cuetakes.py`, `takejudge.py`,
`track.py`, `audioscript.py`): the catalog marks the cue models by kind from the facts file (Medium held back without
Flash Attention 2); Generate keeps them out of its pulldown and picks one per kind, refusing in one line; Track renders
lines, then cues by model, then the room; a cue kind with no model refuses the press, the room's absence only says
so; a cue's verdict is a gain to its kind's anchor; the finish records cues and the room, a reaction with its decay;
the decay read from `ebur128`'s verbose lines, and from a real ffmpeg on a stdlib WAV."""
from __future__ import annotations

import copy
import json
import math
import shutil
import struct
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.director import audioscript, cuetakes, routes, takejudge, track
from hub.modules.generate_image import models as gmodels
from hub.modules.generate_image import tools as gtools
from hub.worker import catalog
from hub.worker.adapters import joins, soundtask, takemeasure, upstream
from hub.worker.enginerequests import SoundRequest
from tests.engine.capture_engine import SERVER_CONFIG, CaptureEngine
from tests.engine.test_script_lock import whole
from tests.engine.test_script_tools import on_disk
from tests.engine.test_script_track import call as tcall
from tests.engine.test_script_track import ctx, lock_only, payload, refused, run  # noqa: F401
from tests.engine.test_upstream_capture import DOC
from tests.engine.test_upstream_rules import ACCEPTED, SPEECH

SFX, MUSIC, MEDIUM = "stable_audio3_small_sfx", "stable_audio3_small", "stable_audio3_medium"
PICK_SFX = {"id": SFX, "label": "Music Stable Audio 3 Small SFX", "seconds": {"min": 1, "max": 120}}
PICK_MUSIC = {"id": MUSIC, "label": "Music Stable Audio 3 Small Music", "seconds": {"min": 1, "max": 120}}
CUE = {"length_ms": 2500, "speech_start_ms": 100, "speech_end_ms": 2300, "extra_s": 0.0, "lufs": -18.0,
       "true_peak_dbtp": -9.0}


def built(monkeypatch, facts: dict | None = None) -> dict[str, dict]:
    if facts is not None:
        monkeypatch.setattr(upstream, "facts_file", lambda: facts)
    out = catalog.build(CaptureEngine(DOC, SERVER_CONFIG), "/engine", upstream.Upstream())["models"]
    return {e["id"]: e for e in out}


def test_the_catalog_marks_the_cue_models_by_kind(monkeypatch) -> None:
    monkeypatch.setattr(soundtask, "flash_ready", lambda: True)
    got = built(monkeypatch)
    sfx = got[SFX]
    assert (sfx["kind"], sfx["loras"], sfx["cues"]) == ("sound", False, {"effect": 0, "reaction": 0, "room": 0})
    assert got[MUSIC]["cues"] == {"music": 0} and "why_not" not in got[MEDIUM]
    assert got[MEDIUM]["cues"] == {"effect": 1, "reaction": 1, "room": 1, "music": 1}
    assert sfx["speech"]["seconds"]["min"] == 1 and sfx["speech"]["seconds"]["max"] == 120
    h3 = got[SPEECH]
    assert (h3["kind"], h3.get("sounds"), "cues" in h3) == ("speech", True, False), "the audience unchanged"
    assert catalog.SHAPE == 13
    facts = copy.deepcopy(upstream.facts_file.__wrapped__())
    facts.pop("cues")
    assert not {SFX, MUSIC, MEDIUM} & set(built(monkeypatch, facts)), "without the facts' cues: left out"


def test_medium_is_held_back_without_flash_attention(monkeypatch) -> None:
    monkeypatch.setattr(soundtask, "flash_ready", lambda: False)
    got = built(monkeypatch)
    assert got[MEDIUM]["kind"] == "sound" and got[MEDIUM]["why_not"] == "needs Flash Attention 2, not installed"
    assert "why_not" not in got[SFX] and "why_not" not in got[MUSIC]
    assert soundtask.cue_facts({}, SFX) == {}, "the fork's facts: no cues"


def test_flash_ready_is_the_engines_own_test(monkeypatch) -> None:
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert soundtask.flash_ready() is False
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())

    def broken(name: str) -> Any:
        raise ImportError("libcudart.so.12: cannot open shared object file")
    monkeypatch.setattr(soundtask.importlib, "import_module", broken)
    assert soundtask.flash_ready() is False, "its import raising"
    monkeypatch.setattr(soundtask.importlib, "import_module",
                        lambda name: SimpleNamespace(flash_attn_varlen_func=lambda: None))
    assert soundtask.flash_ready() is True
    assert soundtask.flash_ready() is True


def test_a_cue_task_holds_only_keys_upstream_accepts(monkeypatch) -> None:
    monkeypatch.setattr(upstream, "accepted_names", lambda: ACCEPTED)
    request = SoundRequest(SFX, "A door slams", 7, 2, measure=True, decay=True)
    task = upstream.translate(upstream.Upstream().task(request, built(monkeypatch)[SFX]), {})
    assert set(task) <= ACCEPTED and task["prompt"] == "A door slams" and task["duration_seconds"] == 2
    assert task["audio_prompt_type"] == "" and task["model_type"] == SFX


def model(ident: str, rank: dict, status: str = "available", **extra: Any) -> dict:
    return {"id": ident, "name": ident.upper(), "family": "Music", "status": status, "kind": "sound",
            "speech": {"seconds": {"min": 1, "max": 120, "default": 30}, "references": 1}, "cues": rank, **extra}


def test_generate_keeps_them_out_of_its_pulldown_and_picks_by_rank(monkeypatch) -> None:
    h3 = {"id": SPEECH, "name": "H3", "family": "tts", "status": "available", "kind": "speech", "sounds": True}
    pic = {"id": "pic", "name": "Pic", "family": "Qwen", "status": "available", "kind": "image"}
    cat = {"models": [h3, pic, model(SFX, {"effect": 0, "room": 0}),
                      model(MEDIUM, {"effect": 1, "music": 1, "room": 1}), model(MUSIC, {"music": 0})]}
    assert [m["id"] for m in gmodels.present(cat)] == ["pic", SPEECH], "the pulldown, image_models, the sketch"
    assert gmodels.cue_maker(cat, "effect")["id"] == SFX and gmodels.cue_maker(cat, "music")["id"] == MUSIC
    cat["models"][2] = model(SFX, {"effect": 0, "room": 0}, "partial", lacks=["sa3_sfx.safetensors"])
    assert gmodels.cue_maker(cat, "effect")["id"] == MEDIUM, "a missing model skipped"
    cat["models"][3] = model(MEDIUM, {"effect": 1, "music": 1, "room": 1}, why_not=soundtask.BLOCKED)
    assert gmodels.cue_maker(cat, "effect") is None and gmodels.cue_maker(cat, "reaction") is None
    monkeypatch.setattr(gmodels, "cached", lambda: cat)
    with pytest.raises(Invalid) as e:
        gtools.cue_pick(None, "effect")
    missing = "STABLE_AUDIO3_SMALL_SFX (sa3_sfx.safetensors), not in your model folders; "
    assert e.value.text == (f"effect cues need {missing}"
                            "STABLE_AUDIO3_MEDIUM is, but needs Flash Attention 2, not installed")
    with pytest.raises(Invalid) as e:
        gtools.cue_pick(None, "room")
    assert e.value.text.startswith(f"room tone needs {missing}")
    with pytest.raises(Invalid) as e:
        gtools.cue_pick(None, "reaction")
    assert e.value.text == "reaction cues need a sound model; none is in the engine's list"
    assert gtools.cue_pick(None, "music") == {"id": MUSIC, "label": "STABLE_AUDIO3_SMALL",
                                              "seconds": {"min": 1, "max": 120}}
    cat["models"][3] = model(MEDIUM, {"effect": 1, "music": 1, "room": 1})       # Flash Attention installed
    assert gtools.cue_pick(None, "effect")["id"] == MEDIUM


async def cued(held: Any) -> None:
    """Script 1 (`test_script_lock`'s, with every line), and three cues in s1: c1 effect, c2 reaction, c3 music;
    locked."""
    await whole(held)
    for kind, words in (("effect", "A door slams"), ("reaction", "Applause"), ("music", "A sting")):
        await tcall(held, "cue_add", {"shot": "s1", "cue": kind, "words": words})
    await lock_only(held)
    held.cue = {"effect": PICK_SFX, "reaction": PICK_SFX, "room": PICK_SFX, "music": PICK_MUSIC}


def events(held: Any, kind: str) -> dict[str, dict]:
    return {ev["id"]: ev for s in on_disk(held)["scenes"][0]["shots"] for ev in s["events"] if ev["kind"] == kind}


async def test_track_renders_lines_then_cues_by_model_then_the_room(ctx: Any) -> None:  # noqa: F811
    await cued(ctx)
    answer = await tcall(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    assert answer["state"] == [f"Script 1 · Track: 2 lines, 3 cues and the room rendering, up to 3 takes per line "
                               f"(job {made.id})"]
    plan, cues, script = made.plan, events(ctx, "cue"), on_disk(ctx)
    assert [t["kind"] for t in plan.tasks] == ["speech"] * 6 + ["sound"] * 4 and plan.model == "h3"
    assert plan.takes[2:] == (((7,),), ((8,),), ((9,),), ((10,),)), "each cue and the room one take"
    sounds = plan.tasks[6:]
    assert [t["model"] for t in sounds] == [SFX, SFX, SFX, MUSIC], "grouped by model; the room with its model's cues"
    for task, ident in zip([*sounds[:2], sounds[3]], ("c1", "c2", "c3"), strict=True):
        ev = cues[ident]
        assert task["prompt"] == ev["words"] and task["seconds"] == min(120, max(1, audioscript.cap(ev)))
        assert task["measure"] is True and task["decay"] is (ev["cue"] == "reaction")
    room = sounds[2]
    stage = script["context"]["set"]
    assert room["prompt"] == f"{' '.join(stage['name'].split())}. {' '.join(stage['description'].split())}."
    assert room["measure"] is True and room["decay"] is False
    length = max(s["end_ms"] for sc in script["scenes"] for s in sc["shots"]) / 1000
    assert room["seconds"] == max(10, math.ceil(1.25 * length))
    assert plan.summary["step_names"][6:] == ["c1", "c2", "room", "c3"]
    assert track.state("Script 1")["c2"] == ("rendering", None)
    assert not plan.judge.again(3, 2) and not plan.judge.again(6, 2), "a cue or the room never re-takes"
    assert plan.judge.again(1, 2), "a line does"


def measured(k: int, plan: Any) -> dict | None:
    sound = plan.tasks[k - 1]["kind"] == "sound"
    decay = {"decay_ms": 640} if plan.tasks[k - 1].get("decay") else {}
    return payload(None, {**CUE, **decay}) if sound else payload()


async def test_the_finish_records_cues_and_the_room_and_only_stale_ones_render_again(ctx: Any) -> None:  # noqa: F811
    await cued(ctx)
    await tcall(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    await run(ctx, made, lambda k: measured(k, made.plan))
    takes = on_disk(ctx)["takes"]
    assert set(takes) == {"l1", "l2", "c1", "c2", "c3", "room"}
    c1, c2, c3, room = takes["c1"], takes["c2"], takes["c3"], takes["room"]
    assert c1["file"] == "Script 1/c1-1.wav" and room["file"] == "Script 1/room-1.wav" and c1["tries"] == 1
    assert c1["hash"] == audioscript.sound_hash(events(ctx, "cue")["c1"]) and room["hash"] == cuetakes.room_hash(
        on_disk(ctx))
    assert c1["measured"] == {"speech_start_ms": 100, "speech_end_ms": 2300, "length_ms": 2500, "lufs": -18.0,
                              "true_peak_dbtp": -9.0, "gain_db": -9.0}
    assert c2["measured"]["decay_ms"] == 640 and "decay_ms" not in c1["measured"]
    assert c3["measured"]["gain_db"] == -15.0 and room["measured"]["gain_db"] == -27.0
    assert c1["judge"] == {"heard": None, "first_miss_ms": None, "extra_speech": None, "verdict": "ok", "why": None}
    rows = {r["id"]: r for r in routes._one(ctx, "Script 1")["audio"]}
    assert "room" not in rows, "the room has no row"
    assert rows["c2"]["take"]["state"] == "ok" and rows["c2"]["take"]["file"] == "Script 1/c2-1.wav", "the file reads"
    mixing = ctx.jobs.made[-1]                                    # the finish submitted the mix
    assert (await refused(ctx, "script_track", {}))["problem"] == f"Script 1 is mixing (job {mixing.id})"
    script = on_disk(ctx)
    for shot in script["scenes"][0]["shots"]:
        for ev in shot["events"]:
            if ev["id"] == "c3":
                ev["words"] = "A brass sting"
        shot["end_ms"] += 5_000                                   # the script lengthens: the room is still current
    (ctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(script), encoding="utf-8")
    assert rows_of(ctx)["c3"]["take"]["state"] == "stale"
    got = await tcall(ctx, "script_track", {})
    again = ctx.jobs.made[-1].plan
    assert [t["prompt"] for t in again.tasks] == ["A brass sting"] and got["state"][0].startswith(
        "Script 1 · Track: 1 cue rendering (job ")
    await run(ctx, ctx.jobs.made[-1], lambda k: payload(None, CUE))
    script = on_disk(ctx)
    script["context"]["set"]["description"] += ", now at night"
    (ctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(script), encoding="utf-8")
    got = await tcall(ctx, "script_track", {})
    alone = ctx.jobs.made[-1].plan
    assert len(alone.tasks) == 1 and alone.tasks[0]["prompt"].endswith(", now at night.")
    assert alone.model == SFX and got["state"] == [f"Script 1 · Track: the room rendering (job {ctx.jobs.made[-1].id})"]


def rows_of(held: Any) -> dict[str, dict]:
    return {r["id"]: r for r in routes._one(held, "Script 1")["audio"]}


async def test_the_room_without_its_model_is_left_out_in_one_line(ctx: Any) -> None:  # noqa: F811
    await cued(ctx)
    ctx.cue.pop("room")
    answer = await tcall(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    assert answer["state"] == [
        f"Script 1 · Track: 2 lines and 3 cues rendering, up to 3 takes per line (job {made.id})",
        "room tone left out: room tone needs a sound model; none is in the engine's list"]
    assert [t["kind"] for t in made.plan.tasks] == ["speech"] * 6 + ["sound"] * 3
    await run(ctx, made, lambda k: measured(k, made.plan))
    assert "room" not in on_disk(ctx)["takes"]
    mixing = ctx.jobs.made[-1]                                    # the finish submitted the mix
    assert (await refused(ctx, "script_track", {}))["problem"] == f"Script 1 is mixing (job {mixing.id})", \
        "nothing else to render: the mix runs"


async def test_the_room_is_the_sets_words_alone(ctx: Any) -> None:  # noqa: F811
    """The room's prompt is the set's name and description as typed, whitespace closed up, joined by
    the parts' join (a part that ends in a mark is sent as written, one with none gets one full stop);
    a set with neither gives no room task and one line."""
    await cued(ctx)
    script = on_disk(ctx)
    script["context"]["set"].update(name="  Set   1 ", description="Description\n of  Set 1")
    (ctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(script), encoding="utf-8")
    await tcall(ctx, "script_track", {})
    rooms = [t for t, kind in zip(ctx.jobs.made[-1].plan.tasks[6:], ("c1", "c2", "room", "c3"), strict=True)
             if kind == "room"]
    assert [t["prompt"] for t in rooms] == ["Set 1. Description of Set 1."]
    script["context"]["set"].update(name="Set 1.", description="Description 1!")
    assert cuetakes._room(ctx, script, {}, set(), cuetakes.More())[1] == "Set 1. Description 1!", "no '..'"
    stage = {"name": " ", "description": ""}
    more = cuetakes.More()
    held = {**script, "context": {**script["context"], "set": stage}}
    assert cuetakes._room(ctx, held, {}, set(), more) is None
    assert more.notes == ["room tone left out: the set has no name or description"]


def test_a_cues_verdict_is_a_gain_to_its_kinds_anchor() -> None:
    v = takejudge.cue_verdict
    assert v(CUE, "effect").measured["gain_db"] == -9.0 and v(CUE, "music").measured["gain_db"] == -15.0
    assert v(CUE, "room").measured["gain_db"] == -27.0 and v(CUE, "reaction").judge["verdict"] == "ok"
    far = v({**CUE, "lufs": -60.0, "true_peak_dbtp": -50.0}, "effect")
    assert far.judge["verdict"] == "ok" and far.measured["gain_db"] == 33.0, "a far-off level is only a gain"
    silent = v({**CUE, "lufs": None, "true_peak_dbtp": None}, "effect")
    assert silent.judge["why"] == "level: too short or silent to measure" and silent.take.passes
    clip = v({**CUE, "lufs": -40.0, "true_peak_dbtp": -10.0}, "effect")
    assert clip.judge["why"] == "level: peaks at +3.0 dBTP after +13.0 dB" and clip.take.passes
    lost = v({"problem": "ffmpeg is not installed on the server"}, "music")
    assert lost.measured is None and lost.judge["why"] == "not measured: ffmpeg is not installed on the server"
    assert v(None, "effect").judge["why"] == takejudge.NOT_MEASURED
    react = v({**CUE, "decay_ms": 812}, "reaction").measured
    assert react["decay_ms"] == 812 and "decay_ms" not in v({**CUE, "decay_ms": 812}, "effect").measured


def test_the_take_record_accepts_decay_and_the_room() -> None:
    ident = __import__("re").compile(r"[A-Za-z0-9_-]{1,24}")
    good = {"file": "Script 1/room-1.wav", "hash": "ab", "tries": 1, "measured": {"gain_db": -3.0, "decay_ms": 500},
            "judge": {"heard": None, "verdict": "ok", "why": None}}
    audioscript.check_takes({"room": good}, ident)
    for bad in (-1, 1.5, True):
        with pytest.raises(Invalid):
            audioscript.check_takes({"c2": {**good, "measured": {"decay_ms": bad}}}, ident)


VERBOSE = "\n".join([
    "[aist#0:0/pcm_s16le @ 0x1] Guessed Channel Layout: mono",
    *(f"[Parsed_ebur128_0 @ 0x2] t: {t / 10:g}  TARGET:-23 LUFS    M:{m} S:-20.0     I: -20.0 LUFS       LRA:   0.0 LU"
      for t, m in ((5, "-120.7"), (6, "-11.0"), (7, " -9.0"), (8, "-12.0"), (9, "-18.9"), (10, "-19.5"),
                   (11, "-30.0"), (12, "-40.0"))),
    "[Parsed_ebur128_0 @ 0x2] Summary:", "", "  Integrated loudness:", "    I:         -14.0 LUFS",
    "  True peak:", "    Peak:       -6.0 dBFS"])


def test_the_decay_from_verbose_ebur128_lines() -> None:
    assert takemeasure.decay_of(VERBOSE, 1.6) == 700, "the last M within 10 dB of the loudest (-9.0): t 0.9"
    assert takemeasure.decay_of("no lines", 1.0) is None
    assert takemeasure.decay_of(VERBOSE, 0.5) == 0, "at least 0"
    calls: list[list[str]] = []

    def stand_in(args: list[str]) -> str:
        calls.append(args)
        return "" if any("silencedetect" in a for a in args) else VERBOSE
    got = takemeasure.measure("r.wav", None, run=stand_in, length=lambda p: 1.6, decay=True)
    assert got["decay_ms"] == 700 and got["lufs"] == -14.0 and calls[1][:2] == ["-v", "verbose"]
    plain = takemeasure.measure("r.wav", None, run=stand_in, length=lambda p: 1.6)
    assert "decay_ms" not in plain and calls[-1][0] == "-i"


def _wav(path: Path, rate: int = 48_000) -> None:
    """0.2 s silence, a 0.5 s 1 kHz burst at -6 dBFS, then a 1.0 s tail from -26 to -40 dBFS, then 0.5 s silence."""
    frames = []
    for k in range(int(2.2 * rate)):
        t = k / rate
        amp = 0.5 if 0.2 <= t < 0.7 else 0.05 * 10 ** (-(t - 0.7) * 14 / 20) if 0.7 <= t < 1.7 else 0.0
        frames.append(round(32767 * amp * math.sin(2 * math.pi * 1000 * t)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(frames)}h", *frames))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="no ffmpeg here")
def test_a_real_reactions_decay_with_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(takemeasure.soundtail, "ffmpeg", lambda: shutil.which("ffmpeg"))
    path = tmp_path / "applause.wav"
    _wav(path)
    got = takemeasure.measure(str(path), None, decay=True)
    assert abs(got["speech_start_ms"] - 200) <= 30 and abs(got["speech_end_ms"] - 1700) <= 60
    assert abs(got["decay_ms"] - 700) <= 150, "the momentary block's 400 ms reads the tail from about t 1.0"


def test_finish_measures_a_sound_only_when_asked(monkeypatch, tmp_path: Path) -> None:
    seen: list[tuple] = []
    monkeypatch.setattr(takemeasure, "measure", lambda path, words, decay=False: seen.append(
        (path, words, decay)) or {"lufs": -20.0})
    path = str(tmp_path / "c2.wav")
    audience = SoundRequest(SPEECH, "An audience in a hall.", 7, 4)
    assert joins.finish(audience, {}, [path]) is None and seen == [], "the audience task unchanged"
    cue = SoundRequest(SFX, "Applause", 7, 4, measure=True, decay=True)
    assert joins.finish(cue, {}, [path]) == {"measure": {"lufs": -20.0}} and seen == [(path, None, True)]
    assert joins.finish(cue, {}, []) is None
