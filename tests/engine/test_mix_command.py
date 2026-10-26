"""The mix's ffmpeg runs (`hub/worker/mixcmd.py`) and their hand-over in the join's runner
(`hub/worker/join.py`). Pure: each clip's chain, the tracks and groups, the duck's envelope, the master's two runs,
the graph file, a stem, the refusals, the hand-over before the empty-sequence refusal, a request without lanes byte
for byte, and `_execute` running a `then` with only the last run checked (ffmpeg stubbed). With the real ffmpeg
(skipped where none is installed), on synthetic takes made and measured as R54's `synth.py` makes and measures them
and R54's worked scene (`bench.py`), placed by the Hub's own `place.py` and `mix.lanes`, run through `join.run`: R54's
master, onsets, duck, reaction fade, room, re-mix time, lone clip and 400-clip tests, and one more: the room never
ducked."""
from __future__ import annotations

import copy
import math
import os
import re
import shutil
import subprocess
import time
import wave
from array import array
from pathlib import Path
from typing import Any

import pytest

from hub.modules.director import mix, place
from hub.worker import enginewire, join, joincmd, mixcmd
from hub.worker.enginerequests import Canvas, JoinRequest, Loudness, MixClip, MixLane

FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
real = pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="no ffmpeg")
TARGET = {"lufs": -23.0, "true_peak_dbtp": -1.0}


def clip(path: str = "/t/a.wav", at: int = 0, a: int = 200, b: int = 2200, gain: float = 0.0, fin: int = 10,
         fout: int = 10, loop: bool = False) -> dict:
    return {"path": path, "at_ms": at, "in_ms": a, "out_ms": b, "gain_db": gain, "fade_in": fin, "fade_out": fout,
            "loop": loop}


def lane(name: str, kind: str, *clips: dict, gain: float = 0.0, duck: bool | None = None) -> dict:
    return {"name": name, "kind": kind, "gain_db": gain,
            "duck": kind in ("reaction", "effect", "music") if duck is None else duck, "clips": list(clips)}


def req(*lanes: dict, length: int = 10_000, solo: int | None = None) -> dict:
    return {"lanes": list(lanes), "length_ms": length, "solo": solo, "target": None if solo is not None else TARGET}


# ---------------------------------------------------------------- pure
def test_a_clips_chain_trims_formats_levels_fades_delays_and_pads_in_samples() -> None:
    first = mixcmd.clip_chain(0, {**clip(at=1500, gain=3.5), "gain_db": 3.5 - 2.0}, 10_000, 6000, True)
    assert first == ("[0:a]atrim=start=0.200:end=2.200,asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:"
                     "channel_layouts=stereo,volume=1.50dB,afade=t=in:st=0:d=0.010,afade=t=out:st=1.990:d=0.010,"
                     "adelay=delays=1500:all=1,asetpts=N/SR/TB,apad=whole_len=288000,atrim=end_sample=288000,"
                     "asetpts=N/SR/TB[c0]")
    later = mixcmd.clip_chain(3, clip(at=6000), 10_000, 10_000, False)
    assert "adelay" not in later and later.endswith("apad=whole_len=192000,atrim=end_sample=192000,asetpts=N/SR/TB[c3]")
    request = req(lane("Character 7", "dialogue", clip(at=1500, gain=3.5)), lane("Character 8", "dialogue",
                                                                                 clip(at=4000)))
    request["lanes"][0]["gain_db"] = -2.0
    assert "volume=1.50dB" in mixcmd.premaster(request, True)[1], "the lane's gain folded into its clips"


def test_a_loop_clip_is_looped_to_the_length() -> None:
    chain = mixcmd.clip_chain(0, clip(a=0, b=2000, loop=True, fin=500, fout=500), 31_000, 31_000, True)
    assert "aloop=loop=-1:size=96000,atrim=end_sample=1488000,asetpts=N/SR/TB" in chain
    assert "afade=t=out:st=30.500:d=0.500" in chain and "adelay" not in chain


def test_a_lanes_clips_share_a_track_and_overlapping_reactions_take_two() -> None:
    inputs, graph = mixcmd.premaster(req(lane("Character 7", "dialogue", clip(at=0), clip("/t/b.wav", at=3000),
                                              clip("/t/c.wav", at=6000))), True)
    assert inputs == ["/t/a.wav", "/t/b.wav", "/t/c.wav"]
    assert "[c0][c1][c2]concat=n=3:v=0:a=1[dialogue0]" in graph and "amix" not in graph
    laid = mixcmd.groups(req(lane("reaction", "reaction", clip(at=0), clip("/t/b.wav", at=1000))))
    assert [len(t) for t in laid["plain"]] == [1, 1], "two reactions that overlap: two tracks"


def test_the_three_groups() -> None:
    request = req(lane("Character 7", "dialogue", clip(at=0)), lane("music", "music", clip("/t/m.wav", at=0)),
                  lane("effect", "effect", clip("/t/e.wav", at=500), duck=False),
                  lane("room", "room", clip("/t/r.wav", a=0, b=2000, loop=True)))
    assert {g: [[c["path"] for c in t] for t in tracks] for g, tracks in mixcmd.groups(request).items()} == {
        "dialogue": [["/t/a.wav"]], "beds": [["/t/m.wav"]], "plain": [["/t/r.wav"], ["/t/e.wav"]]}
    graph = mixcmd.premaster(request, True)[1]
    assert "[beds]asetnsamples=n=240:p=0,volume=volume='pow(10,-0.5000*" in graph
    assert "[dialogue][ducked][plain]amix=inputs=3:duration=longest:dropout_transition=0:normalize=0,anull[pre]" \
        in graph
    alone = mixcmd.premaster(req(lane("music", "music", clip(at=0))), True)[1]
    assert "volume=volume=" not in alone and "plain" in alone, "no dialogue lane: nothing ducks it"


def test_the_envelope() -> None:
    assert mixcmd.envelope([(1000, 3400)]) == "pow(10,-0.5000*clip((t-0.800)/0.200,0,1)*clip((4.000-t)/0.600,0,1))"
    lanes = [lane("A", "dialogue", clip(at=0, a=0, b=1000), clip(at=1700, a=0, b=1000), clip(at=5000, a=0, b=500))]
    assert mixcmd.speech_spans(lanes, 800) == [(0, 2700), (5000, 5500)], "under 800 ms apart: merged"
    two = mixcmd.envelope(mixcmd.speech_spans(lanes, 800))
    assert two.startswith("pow(10,-0.5000*if(lt(t,4.050),clip((t--0.200)/0.200,0,1)")
    assert 10 ** (-0.5) == pytest.approx(10 ** (-mixcmd.DUCK["depth_db"] / 20)), "10 dB"


def test_the_masters_two_runs() -> None:
    request = req(lane("Character 7", "dialogue", clip(at=0)), length=4321)
    run = mixcmd.build(request, "/bin/ffmpeg", "/s", "j7", True)
    assert run.argv[:8] == ["/bin/ffmpeg", "-hide_banner", "-nostdin", "-v", "info", "-y", "-progress", "pipe:1"]
    graph = run.argv[run.argv.index("-filter_complex") + 1]
    assert graph.endswith(";[pre]ebur128[m]") and "peak" not in graph
    assert run.argv[-11:] == ["-map", "[m]", "-c:a", "pcm_f32le", "-ar", "48000", "-ac", "2", "-map_metadata", "-1",
                              "/s/mix-j7-pre.wav"]
    assert (run.list_file, run.listing, run.out, run.path, run.kind) == ("/s/mix-j7.graph", None, "/s/mix-j7-pre.wav",
                                                                        "encode", "wav")
    assert (run.seconds, run.expect, run.fps, run.n) == (4.321, 432, 100.0, 1)
    assert mixcmd.gain_of("t: 0.1 M: -20.0 S: -20.0\n  I: -10.0 LUFS\nSummary:\n  Integrated loudness:\n    "
                          "I:         -31.0 LUFS\n", -23.0) == 8.0, "the I: after Summary: only"
    assert mixcmd.gain_of("  I: -10.0 LUFS\n", -23.0) == 0.0 and mixcmd.gain_of("Summary:\n I: -70.0 LUFS", -23) == 0.0
    assert mixcmd.gain_of("Summary:\n I: nan LUFS", -23.0) == 0.0


def test_run_two_reads_run_ones_err_file(tmp_path: Path) -> None:
    run = mixcmd.build(req(lane("Character 7", "dialogue", clip(at=0)), length=5000), "/bin/ffmpeg", str(tmp_path),
                       "j1",
                       True)
    err = tmp_path / "join-j1.err"
    err.write_text("[Parsed_ebur128_9] Summary:\n\n  Integrated loudness:\n    I:         -26.5 LUFS\n")
    second = run.then(str(err))
    assert second.argv == ["/bin/ffmpeg", *joincmd.HEAD, "-i", str(tmp_path / "mix-j1-pre.wav"), "-af",
                           f"volume=3.50dB,aresample=192000,alimiter=limit={10 ** (-1.5 / 20):.4f}:attack=5:release=50:"
                           "level=0:latency=1,aresample=48000,atrim=end=5.000", "-c:a", "pcm_s16le", "-ar", "48000",
                           "-ac", "2", "-map_metadata", "-1", str(tmp_path / "outbox" / "join-j1.wav")]
    assert second.list_file == str(tmp_path / "mix-j1-pre.wav") and second.then is None, "the runner removes it"
    assert run.out == second.out == str(tmp_path / "outbox" / "join-j1.wav"), "the chain's file is the one sent"
    assert (second.seconds, second.expect, second.fps, second.n) == (5.0, 500, 100.0, 1)


def test_a_long_graph_goes_through_a_file_and_a_stem_has_no_master() -> None:
    many = lane("Character 7", "dialogue", *[clip(f"/t/{k}.wav", at=3000 * k) for k in range(400)])
    run = mixcmd.build(req(many, lane("music", "music", clip("/t/m.wav", at=0)), length=1_300_000), "/f", "/s", "j2",
                       True)
    assert run.listing is not None and len(run.listing) > mixcmd.ARG_SAFE and "-filter_complex" not in run.argv
    assert run.argv[run.argv.index("-filter_complex_script") + 1] == run.list_file == "/s/mix-j2.graph"
    stem = mixcmd.build(req(lane("Character 7", "dialogue", clip(at=0)), lane("music", "music", clip("/t/m.wav")),
                            solo=1),
                        "/f", "/s", "j3", True)
    text = " ".join(stem.argv)
    assert stem.then is None and "ebur128" not in text and "alimiter" not in text and "pcm_f32le" not in text
    assert stem.argv[1:8] == list(joincmd.HEAD) and stem.out == "/s/outbox/join-j3.wav"
    assert "/t/a.wav" not in stem.argv and "volume=volume='pow(10" in text, "only lane 1 heard, still ducked"


def test_without_normalize_amix_is_followed_by_its_volume() -> None:
    graph = mixcmd.premaster(req(lane("Character 7", "dialogue", clip(at=0)), lane("room", "room", clip(loop=True))),
                             False)[1]
    assert "[dialogue][plain]amix=inputs=2:duration=longest:dropout_transition=0,volume=2,anull[pre]" in graph
    asked: list[str] = []
    one = req(lane("Character 7", "dialogue", clip(at=0)))
    one["lanes"][0]["clips"][0]["path"] = __file__
    mixcmd.prepare("j", one, "/s", "/f", lambda f: asked.append(f) or True)
    assert asked == [], "no amix: not asked"


def test_the_refusals(tmp_path: Path) -> None:
    take = tmp_path / "a.wav"
    take.write_bytes(b"RIFF")
    good = req(lane("Character 7", "dialogue", clip(str(take), at=0)), lane("room", "room", clip(str(take), loop=True)))

    def refused(request: dict) -> str:
        with pytest.raises(ValueError) as e:
            mixcmd.prepare("j", request, str(tmp_path), "/f", lambda f: True)
        return str(e.value)
    gone = copy.deepcopy(good)
    gone["lanes"][0]["clips"][0]["path"] = str(tmp_path / "no.wav")
    assert refused(gone) == mixcmd.GONE_TAKE == "A take of the mix is gone from Sounds"
    nan = copy.deepcopy(good)
    nan["lanes"][0]["clips"][0]["gain_db"] = math.nan
    assert "gain" in refused(nan)
    for k, kind in ((1, "room"), (0, "dialogue")):
        ducked = copy.deepcopy(good)
        ducked["lanes"][k]["duck"] = True
        assert refused(ducked) == f"The {kind} lane is never ducked"
    assert refused({**good, "length_ms": 0}) == refused({**good, "lanes": []}) == mixcmd.EMPTY


def test_join_hands_a_mix_over_before_its_empty_sequence_refusal(monkeypatch: pytest.MonkeyPatch,
                                                                 tmp_path: Path) -> None:
    monkeypatch.setattr(join, "programs", lambda: ("/f/ffmpeg", "/f/ffprobe"))
    got: list[tuple] = []
    monkeypatch.setattr(mixcmd, "prepare", lambda *a: got.append(a) or "RUN")
    request = {**enginewire.request_wire(JoinRequest([], Canvas(0, 0, 1000.0), [], 18, "medium", "wav")),
               **req(lane("Character 7", "dialogue", clip(at=0)))}
    assert join.prepare("j1", request, str(tmp_path)) == ("RUN", [])
    assert got[0][:4] == ("j1", request, str(tmp_path), "/f/ffmpeg") and got[0][4] is join.amix_normalize
    monkeypatch.setattr(mixcmd, "prepare", lambda *a: (_ for _ in ()).throw(ValueError("one line")))
    with pytest.raises(join.Failed, match="one line"):
        join.prepare("j1", request, str(tmp_path))
    with pytest.raises(join.Failed, match="The sequence is empty"):
        join.prepare("j1", {**request, "lanes": []}, str(tmp_path))


def test_a_request_without_lanes_is_joincmds_byte_for_byte(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(join, "programs", lambda: ("/f/ffmpeg", "/f/ffprobe"))
    take = tmp_path / "a.wav"
    take.write_bytes(b"RIFF")
    item = {"path": str(take), "in": 0, "out": 1000, "fps": 1000.0, "w": 0, "h": 0, "frames": 1000, "audio": True,
            "sound": True}
    old = {"items": [item], "canvas": {"w": 0, "h": 0, "fps": 1000.0}, "audio": [], "crf": 18, "preset": "medium",
           "out_kind": "wav", "duck": {"threshold": 0.05, "ratio": 6.0, "attack": 50.0, "release": 400.0}}
    new = {**old, "lanes": [], "target": None, "solo": None, "length_ms": 0}
    assert enginewire.wire(enginewire.request_parse({"kind": "join", **new})) == new, "the wire carries the fields"
    assert join.prepare("j", new, str(tmp_path))[0] == joincmd.build(old, [], "/f/ffmpeg", str(tmp_path), "j", True)


def test_the_mix_types_cross_the_wire() -> None:
    sent = JoinRequest([], Canvas(0, 0, 1000.0), [], 18, "medium", "wav",
                       lanes=[MixLane("Character 7", "dialogue", 0.0, False,
                                      [MixClip("/t/a.wav", 0, 200, 2200, 1.5, 10, 10)])],
                       target=Loudness(-23.0, -1.0), length_ms=4000)
    wired = enginewire.request_wire(sent)
    assert wired["lanes"][0]["clips"][0] == clip(gain=1.5) and wired["target"] == TARGET
    assert enginewire.request_parse(wired) == sent


def test_execute_runs_the_then_and_checks_only_the_last(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "outbox").mkdir()
    started: list[list[str]] = []
    checked: list[Any] = []

    class Proc:
        stdout: list[str] = ["out_time_us=1000000\n"]

        def wait(self) -> int:
            return 0

        def poll(self) -> int:
            return 0

    def start(job: str, cmd: Any, err: Any) -> Proc:
        started.append(cmd.argv)
        err.write(b"Summary:\n  I: -29.0 LUFS\n")
        Path(cmd.argv[-1]).write_bytes(b"x")
        return Proc()
    monkeypatch.setattr(join, "_start", start)
    monkeypatch.setattr(join, "check", checked.append)
    run = mixcmd.build(req(lane("Character 7", "dialogue", clip(at=0)), length=3000), "/f", str(tmp_path), "j9", True)
    sent: list[dict] = []
    join._execute("j9", run, {"job": "j9", "task": 1}, sent.append)
    assert len(started) == 2 and "volume=6.00dB" in " ".join(started[1])
    assert checked == [run.next] and run.next.then is None
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["join-j9.wav"], \
        "the pre-master, the graph and the err file removed by the runner"
    assert [m["steps"] for m in sent] == [300, 300]


# ---------------------------------------------------------------- the real ffmpeg (R54's synth.py and bench.py)
_START, _END = re.compile(r"silence_start:\s*(-?[0-9.]+)"), re.compile(r"silence_end:\s*(-?[0-9.]+)")
_PEAK = re.compile(r"True peak:\s*\n\s*Peak:\s*(\S+)\s*dBFS")
LEVELS = {"line": -23.0, "effect": -27.0, "reaction": -27.0, "music": -33.0, "room": -45.0}   # each kind's anchor


def ff(*args: str) -> str:
    done = subprocess.run([str(FFMPEG), "-hide_banner", "-nostdin", "-v", "info", "-y", *args], capture_output=True,
                          timeout=300, check=False)
    text = done.stderr.decode("utf-8", "replace")
    assert done.returncode == 0, text.strip().splitlines()[-1:]
    return text


def voice(path: Path, freq: float, lead: int, speech: int, tail: int, amp: float) -> Path:
    a, b, total = lead / 1000, (lead + speech) / 1000, (lead + speech + tail) / 1000
    expr = f"if(between(t\\,{a}\\,{b})\\,{amp}*sin(2*PI*{freq}*t)*(0.55+0.45*sin(2*PI*3.7*(t-{a})))\\,0)"
    ff("-f", "lavfi", "-i", f"aevalsrc=exprs={expr}:s=24000:d={total}", "-c:a", "pcm_s16le", str(path))
    return path


def noise(path: Path, color: str, ms: int, amp: float, lead: int = 0, decay: int = 0, tail: int = 0) -> Path:
    af = [f"afade=t=out:st={(ms - decay) / 1000}:d={decay / 1000}"] if decay else []
    af += [f"adelay=delays={lead}:all=1"] if lead else []
    af += [f"apad=pad_dur={tail / 1000}"] if tail else []
    ff("-f", "lavfi", "-i", f"anoisesrc=color={color}:amplitude={amp}:d={ms / 1000}:sample_rate=48000:seed=7",
       *(["-af", ",".join(af)] if af else []), "-ac", "2", "-c:a", "pcm_s16le", str(path))
    return path


def music(path: Path, ms: int, amp: float = 0.2) -> Path:
    expr = f"{amp}*(sin(2*PI*330*t)+sin(2*PI*415*t)+sin(2*PI*494*t))/3"
    ff("-f", "lavfi", "-i", f"aevalsrc=exprs={expr}|{expr}:s=48000:d={ms / 1000}", "-c:a", "pcm_s16le", str(path))
    return path


def clicks(path: Path, ms: int, every: int = 4800, amp: float = 0.99) -> Path:
    expr = f"if(lt(mod(n\\,{every})\\,2)\\,{amp}\\,0)"
    ff("-f", "lavfi", "-i", f"aevalsrc=exprs={expr}:s=48000:d={ms / 1000}", "-ac", "2", "-c:a", "pcm_s16le", str(path))
    return path


def ebur(path: Path, trim: tuple[float, float] | None = None) -> tuple[float, float]:
    af = (f"atrim=start={trim[0]:.3f}:end={trim[1]:.3f}," if trim else "") + "ebur128=peak=true"
    text = ff("-i", str(path), "-af", af, "-f", "null", "-")
    tail = text[text.rfind("Summary:"):]
    i, pk = mixcmd._I.search(tail), _PEAK.search(tail)
    assert i and pk
    return float(i.group(1)), float(pk.group(1))


def silences(path: Path, noise_db: str = "-45dB", d: float = 0.15) -> list[tuple[float, float | None]]:
    out: list[tuple[float, float | None]] = []
    start = None
    for line in ff("-i", str(path), "-af", f"silencedetect=noise={noise_db}:d={d}", "-f", "null", "-").splitlines():
        for m in _START.finditer(line):
            start = float(m.group(1))
        for m in _END.finditer(line):
            out.append((start if start is not None else 0.0, float(m.group(1))))
            start = None
    return out + ([(start, None)] if start is not None else [])


def seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def measure(path: Path, kind: str, decay_ms: int | None = None) -> dict:
    """The take's record as the line and cue takes write it (R54 `synth.measure`)."""
    length = seconds(path)
    at, spans = 0.0, []
    for a, b in sorted((a, length if b is None else b) for a, b in silences(path)):
        if a > at:
            spans.append((at, a))
        at = max(at, b)
    if at < length:
        spans.append((at, length))
    start, end = spans[0][0], spans[-1][1]
    lufs, tp = ebur(path, (start, end))
    m = {"speech_start_ms": round(start * 1000), "speech_end_ms": round(end * 1000), "lufs": lufs,
         "true_peak_dbtp": tp, "gain_db": round(LEVELS[kind] - lufs, 1)}
    return {**m, "decay_ms": decay_ms} if decay_ms is not None else m


def onsets(path: Path) -> list[int]:
    quiet = silences(path, "-50dB", 0.05)
    out = [round(b * 1000) for a, b in quiet if b is not None]
    return ([0] if not quiet or quiet[0][0] > 0.001 else []) + out


def rms_db(path: Path, a_ms: int, b_ms: int) -> float:
    with wave.open(str(path)) as w:
        rate = w.getframerate()
        w.setpos(round(a_ms * rate / 1000))
        data = array("h", w.readframes(round((b_ms - a_ms) * rate / 1000)))
    mean = sum(x * x for x in data) / len(data) if data else 0
    return 10 * math.log10(mean / 32768 ** 2) if mean > 0 else -200.0


# (id, speaker, planned start, end, take: lead, speech, tail ms, amp): R54's bench.LINES
LINES = [("l1", "Character 7", 500, 2700, (300, 2000, 400, 0.30)), ("l2", "Character 8", 2700, 4900, (250, 2400, 300,
                                                                                                      0.08)),
         ("l3", "Character 7", 4900, 6900, (200, 1600, 500, 0.50)), ("l4", "Character 8", 8400, 10600, (300, 2000, 300,
                                                                                                        0.20)),
         ("l5", "Character 7", 10600, 12800, (200, 2000, 200, 0.30)), ("l6", "Character 8", 12000, 14000, (300, 1800,
                                                                                                           300, 0.25)),
         ("l7", "Character 7", 14000, 16200, (300, 2000, 300, 0.30)), ("l8", "Character 8", 17200, 19400, (300, 2000,
                                                                                                           300, 0.12)),
         ("l9", "Character 7", 19400, 21600, (200, 2600, 200, 0.30)), ("l10", "Character 8", 21600, 23800, (300, 2000,
                                                                                                            300, 0.30)),
         ("l11", "Character 7", 24800, 27000, (300, 2000, 300, 0.40)), ("l12", "Character 8", 27000, 29200, (300, 1800,
                                                                                                             300,
                                                                                                             0.30))]
SHOTS = [(0, 6900), (6900, 12800), (12800, 21600), (21600, 30000)]
CUES = [{"id": "c1", "kind": "cue", "cue": "music", "start_ms": 0, "end_ms": 30000},
        {"id": "c2", "kind": "cue", "cue": "reaction", "start_ms": 6900, "end_ms": 8400},
        {"id": "c3", "kind": "cue", "cue": "reaction", "start_ms": 16200, "end_ms": 17200}]


def script_of(events: list[dict], shots: list[tuple[int, int]], before: list[dict] | None = None) -> dict:
    rows = [{"id": f"s{k + 1}", "start_ms": a, "end_ms": b, "events": [e for e in events if a <= e.get(
        "start_ms", e.get("at_ms", 0)) < b or (k == len(shots) - 1 and e.get("start_ms", 0) >= b)]}
        for k, (a, b) in enumerate(shots)]
    return {"version": 2, "context": {"cast": [{"name": "Character 7"}, {"name": "Character 8"}]},
            "scenes": [{"shots": rows}],
            **({"mix": {"lanes": before}} if before else {})}


@pytest.fixture(scope="module")
def scene(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[dict], dict]:
    """R54's worked scene, with the room and a click effect in the made pause."""
    if not (FFMPEG and FFPROBE):
        pytest.skip("no ffmpeg")
    d = tmp_path_factory.mktemp("takes")
    events, takes = [], {}
    for ident, who, a, b, (lead, speech, tail, amp) in LINES:
        events.append({"id": ident, "kind": "line", "speaker": who, "start_ms": a, "end_ms": b})
        path = voice(d / f"{ident}.wav", 220 if who == "Character 7" else 330, lead, speech, tail, amp)
        takes[ident] = {"file": str(path), "measured": measure(path, "line")}
    events += copy.deepcopy(CUES)
    takes["c1"] = {"file": str(music(d / "c1.wav", 31000)), "measured": measure(d / "c1.wav", "music")}
    takes["c2"] = {"file": str(noise(d / "c2.wav", "pink", 1400, 0.4, 100, 600, 200))}
    takes["c2"]["measured"] = measure(d / "c2.wav", "reaction", 600)
    takes["c3"] = {"file": str(noise(d / "c3.wav", "pink", 1000, 0.4, 100, 0, 200))}
    takes["c3"]["measured"] = measure(d / "c3.wav", "reaction", 0)
    takes["room"] = {"file": str(noise(d / "room.wav", "brown", 2000, 0.05)), "measured": measure(d / "room.wav",
                                                                                                 "room")}
    takes["e1"] = {"file": str(clicks(d / "e1.wav", 2000)), "measured": measure(d / "e1.wav", "effect")}
    return d, events, takes


def request_of(events: list[dict], takes: dict, solo: str | None = None, before: list[dict] | None = None,
               shots: list[tuple[int, int]] = SHOTS, only: str | None = None) -> tuple[dict, dict]:
    """(the wire request mix.py sends, the placement) for these rows, by the Hub's own place.py and mix.lanes."""
    script = script_of(events, shots, before)
    placed = place.place(script, takes, {})
    held = mix.lanes(script, placed, place.room(takes, {}) if "room" in takes else None)
    if only is not None:
        held = [ln for ln in held if ln["name"] == only]
    wire = {**enginewire.request_wire(JoinRequest([], Canvas(0, 0, 1000.0), [], 18, "medium", "wav")),
            "lanes": [{"name": ln["name"], "kind": ln["kind"], "gain_db": ln["gain_db"], "duck": ln["duck"],
                       "clips": [{"path": c["file"], "at_ms": c["at_ms"], "in_ms": c["in_ms"], "out_ms": c["out_ms"],
                                  "gain_db": c["gain_db"], "fade_in": c["fade_in_ms"], "fade_out": c["fade_out_ms"],
                                  "loop": c["loop"]} for c in ln["clips"]]} for ln in held],
            "length_ms": placed["length_ms"], "target": TARGET, "solo": None}
    if solo is not None:
        wire.update(solo=next(k for k, ln in enumerate(held) if ln["name"] == solo), target=None)
    enginewire.request_parse(wire)
    return wire, {**placed, "lanes": held}


def render(tmp: Path, name: str, wire: dict) -> Path:
    """The request through the join's runner (`join.run`), as the worker runs it; the runner's own files gone."""
    state = tmp / f"state-{name}"
    state.mkdir()
    done = join.run(f"m{name}", 1, wire, lambda m: None, None, str(state))
    assert done["ok"], done
    out = state / "outbox" / f"join-m{name}.wav"
    assert sorted(p.name for p in state.rglob("*") if p.is_file()) == [out.name], "pre-master, graph, err removed"
    return out


@pytest.fixture
def ffmpeg_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FFMPEG_BINARY", str(FFMPEG))
    monkeypatch.setenv("FFPROBE_BINARY", str(FFPROBE))
    monkeypatch.setattr(join, "_normalize", None)


def ducking(placed: dict, path: Path) -> tuple[float, float]:
    """R54 `bench.ducking`: the stem's mean level inside the placed speech and in the gaps, clear of the ramps."""
    spans = mixcmd.speech_spans(placed["lanes"], 800)
    inside = [rms_db(path, a + 100, b - 100) for a, b in spans if b - a > 400]
    gaps = [(b1 + 700, a2 - 300) for (_, b1), (a2, _) in zip(spans, spans[1:], strict=False)]
    between = [rms_db(path, a, b) for a, b in gaps if b - a >= 200]
    return sum(inside) / len(inside), sum(between) / len(between)


@real
def test_master_meets_r128_with_a_peak_to_limit(scene: Any, tmp_path: Path, ffmpeg_env: None) -> None:
    d, events, takes = scene
    m = takes["e1"]["measured"]
    assert m["true_peak_dbtp"] + m["gain_db"] > 1.0, "the levelled clicks peak over 0 dBTP"
    wire, placed = request_of(events + [{"id": "e1", "kind": "cue", "cue": "effect", "start_ms": 7600,
                                         "end_ms": 9600}], takes, before=[{"name": "Character 7", "gain_db": 6.0}])
    out = render(tmp_path, "master", wire)
    i, tp = ebur(out)
    assert abs(i - TARGET["lufs"]) <= 1.0 and tp <= TARGET["true_peak_dbtp"], (i, tp)
    assert abs(seconds(out) - placed["length_ms"] / 1000) < 0.001


@real
def test_speech_onsets_at_the_placed_times(scene: Any, tmp_path: Path, ffmpeg_env: None) -> None:
    d, events, takes = scene
    lines = [e for e in events if e["kind"] == "line"]
    wire, placed = request_of(lines, {k: v for k, v in takes.items() if k.startswith("l")})
    found = onsets(render(tmp_path, "onsets", wire))
    expected, sounding = [], -1000
    for a, b in sorted((c["at_ms"], c["at_ms"] + c["out_ms"] - c["in_ms"]) for c in placed["clips"].values()):
        if a - sounding >= 60:
            expected.append(a)
        sounding = max(sounding, b)
    assert len(expected) >= 10
    for a in expected:
        assert min(abs(a - f) for f in found) <= 20, (a, found)


@real
def test_music_ducked_by_the_stated_depth(scene: Any, tmp_path: Path, ffmpeg_env: None) -> None:
    d, events, takes = scene
    wire, placed = request_of(events, takes, solo="music")
    out = render(tmp_path, "music", wire)
    inside, between = ducking(placed, out)
    assert abs((between - inside) - 10.0) <= 0.5, (inside, between)
    spans = mixcmd.speech_spans(placed["lanes"], 800)
    assert max(rms_db(out, a, a + 150) for a, _ in spans) <= between - 10.0 + 0.5, "down when each line starts"


@real
def test_reaction_fade_reads_decay(scene: Any, tmp_path: Path, ffmpeg_env: None) -> None:
    d, events, takes = scene
    wire, placed = request_of(events, takes, solo="reaction", before=[{"name": "reaction", "duck": False}])
    c3 = next(c for ln in placed["lanes"] for c in ln["clips"] if c["take"] == "c3")
    assert c3["fade_out_ms"] == 300, "a dead cut: the 300 ms floor"
    out = render(tmp_path, "reaction", wire)
    end = c3["at_ms"] + c3["out_ms"] - c3["in_ms"]
    assert rms_db(out, c3["at_ms"] + 300, end - 300) - rms_db(out, end - 50, end) >= 15.0


@real
def test_room_present_is_steady_and_not_ducked_absent_is_left_out(scene: Any, tmp_path: Path, ffmpeg_env: None) -> None:
    d, events, takes = scene
    wire, placed = request_of(events, takes, solo="room")
    out = render(tmp_path, "room", wire)
    assert abs(seconds(out) - placed["length_ms"] / 1000) < 0.001
    windows = [rms_db(out, a, a + 1000) for a in range(1000, placed["length_ms"] - 1000, 1000)]
    assert max(windows) - min(windows) <= 3.0, windows
    alone, _ = request_of(events, takes, only="room")
    alone["solo"], alone["target"] = 0, None
    single = render(tmp_path, "room-alone", alone)
    for a, b in mixcmd.speech_spans(placed["lanes"], 800):              # the room is never ducked
        assert abs(rms_db(out, a, b) - rms_db(single, a, b)) <= 0.1, (a, b)
    without, _ = request_of(events, {k: v for k, v in takes.items() if k != "room"})
    assert all(ln["kind"] != "room" for ln in without["lanes"])
    assert abs(ebur(render(tmp_path, "noroom", without))[0] - TARGET["lufs"]) <= 1.0


@real
def test_remix_of_30_s_12_lines_4_lanes_in_seconds(scene: Any, tmp_path: Path, ffmpeg_env: None) -> None:
    d, events, takes = scene
    t0 = time.monotonic()
    wire, placed = request_of(events, {k: v for k, v in takes.items() if k not in ("room", "e1")})
    render(tmp_path, "timed", wire)
    took = time.monotonic() - t0
    assert len(wire["lanes"]) == 4 and sum(len(ln["clips"]) for ln in wire["lanes"][:2]) == 12
    assert 29_000 <= placed["length_ms"] <= 32_000 and took < 5.0, took


@real
def test_a_lone_clip_late_in_the_mix_lands_whole(scene: Any, tmp_path: Path, ffmpeg_env: None) -> None:
    """R54's finding: `adelay` then `atrim=end` lost a lone clip at 27.587 s; the WAV is 31.000 s."""
    d, events, takes = scene
    m = takes["l12"]["measured"]
    kept = m["speech_end_ms"] - m["speech_start_ms"]
    wire = {**req(lane("Character 8", "dialogue", clip(takes["l12"]["file"], 27_587, m["speech_start_ms"],
                                                 m["speech_end_ms"])), length=31_000, solo=0),
            "items": [], "canvas": {"w": 0, "h": 0, "fps": 1000.0}, "audio": [], "crf": 18, "preset": "medium",
            "out_kind": "wav"}
    out = render(tmp_path, "lone", wire)
    assert seconds(out) == 31.0
    assert rms_db(out, 27_587 + 100, 27_587 + kept - 100) > -40.0 and rms_db(out, 1000, 27_000) == -200.0


@real
def test_400_clips_go_through_a_graph_file(scene: Any, tmp_path: Path, ffmpeg_env: None) -> None:
    d, events, takes = scene
    many = [{"id": f"l{k}", "kind": "line", "speaker": "Character 7" if k % 2 else "Character 8", "start_ms": 3000 * k,
             "end_ms": 3000 * k + 2000} for k in range(399)]
    many.append({"id": "m1", "kind": "cue", "cue": "music", "start_ms": 0, "end_ms": 30000})
    held = {**{f"l{k}": copy.deepcopy(takes["l1"]) for k in range(399)}, "m1": takes["c1"]}
    wire, placed = request_of(many, held, shots=[(0, 1_200_000)])
    assert len(mixcmd.premaster(wire, True)[1]) > 131_072 > mixcmd.ARG_SAFE
    assert abs(ebur(render(tmp_path, "big", wire))[0] - TARGET["lufs"]) <= 1.0
    assert os.path.getsize(takes["l1"]["file"]) > 0
