"""A Track take measured in the worker (`hub/worker/adapters/takemeasure.py`, `joins.finish`): the
sound regions from a captured `silencedetect` stderr, the speech's boundaries snapped to them within 0.30 s / 0.50 s
of the judge's words, the sound outside them, the `ebur128` Summary parsed, ffmpeg absent; with a real ffmpeg a
stdlib WAV of silence, a 1 kHz sine and a burst read as R 128 says, and digital silence gives None, never -inf;
`joins.finish` measures only when asked."""
from __future__ import annotations

import json
import math
import shutil
import struct
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from hub.worker.adapters import joins, judge, takemeasure
from hub.worker.enginerequests import SpeechRequest

SILENCE = """[silencedetect @ 0x5] silence_start: 0
[silencedetect @ 0x5] silence_end: 0.5 | silence_duration: 0.5
size=N/A time=00:00:01.20 bitrate=N/A speed= 300x    [silencedetect @ 0x5] silence_start: 1.5
[silencedetect @ 0x5] silence_end: 2.1 | silence_duration: 0.6
[silencedetect @ 0x5] silence_start: 2.4
"""
SUMMARY = """[Parsed_ebur128_1 @ 0x6] Summary:

  Integrated loudness:
    I:         {i} LUFS
    Threshold: -33.0 LUFS

  Loudness range:
    LRA:         0.0 LU

  True peak:
    Peak:      {peak} dBFS
"""


def test_regions_from_silencedetect() -> None:
    quiet = takemeasure.silences(SILENCE, 2.7)
    assert quiet == [(0.0, 0.5), (1.5, 2.1), (2.4, 2.7)], "on a progress line; the last with no end runs to the end"
    assert takemeasure.regions(quiet, 2.7) == [(0.5, 1.5), (2.1, 2.4)]
    assert takemeasure.regions([], 2.0) == [(0.0, 2.0)]


def test_boundaries() -> None:
    spans = [(0.0, 0.4), (0.6, 2.0), (2.6, 3.0)]      # a garble region, the words, a tail sound
    assert takemeasure.bounds(spans, 3.0, 0.7, 1.9) == (0.6, 2.0), "the garble before the first word cut"
    glued = [(0.1, 2.0)]                                # a garble glued to the first word
    assert takemeasure.bounds(glued, 3.0, 0.9, 1.9) == pytest.approx((0.6, 2.0)), "cut 0.30 s before it"
    long_tail = [(0.5, 2.9)]
    assert takemeasure.bounds(long_tail, 3.0, 0.6, 1.2) == pytest.approx((0.5, 1.7)), "held to last + 0.50"
    assert takemeasure.bounds(spans, 3.0, None, None) == (0.0, 3.0), "no judge words: first and last region"
    assert takemeasure.bounds([], 3.0, None, None) == (0.0, 3.0), "no region"
    assert takemeasure.bounds(spans, 3.0, float("nan"), 1.0) == (0.0, 3.0), "a NaN word time is no time"
    assert takemeasure.outside(spans, 0.6, 2.0) == pytest.approx(0.8)


def test_the_summary_parsed() -> None:
    assert takemeasure.loudness(SUMMARY.format(i="-24.13", peak="-3.04")) == (-24.1, -3.0)
    assert takemeasure.loudness(SUMMARY.format(i="-70.0", peak="-50.0")) == (None, -50.0), "-70: the gate"
    for text in (SUMMARY.format(i="-23.0", peak="-inf"), SUMMARY.format(i="-inf", peak="nan"), "", "Summary:"):
        got = takemeasure.loudness(text)
        assert all(v is None or math.isfinite(v) for v in got), text
    assert takemeasure.loudness(SUMMARY.format(i="-23.0", peak="-inf")) == (-23.0, None)
    assert takemeasure.loudness(SUMMARY.format(i="-inf", peak="-1.0")) == (None, -1.0)


def test_measure_on_stand_ins_and_without_ffmpeg(monkeypatch) -> None:
    asked: list[list[str]] = []

    def run(args: list[str]) -> str:
        asked.append(args)
        return SILENCE if "silencedetect" in args[3] else SUMMARY.format(i="-30.0", peak="-12.0")
    got = takemeasure.measure("t.wav", {"first": 0.55, "last": 1.45}, run=run, length=lambda p: 2.7)
    assert got == {"length_ms": 2700, "speech_start_ms": 500, "speech_end_ms": 1500, "extra_s": 0.3, "lufs": -30.0,
                   "true_peak_dbtp": -12.0}
    assert asked[0][-3:] == ["-f", "null", "-"] and "atrim=start=0.500:end=1.500" in asked[1][3], "nothing written"
    short = takemeasure.measure("t.wav", {"first": 2.15, "last": 2.3}, run=run, length=lambda p: 2.7)
    assert short["lufs"] == -30.0 and short["speech_start_ms"] == 2100 and short["speech_end_ms"] == 2400
    assert asked[3][3] == "ebur128=peak=true", "a slice under 400 ms: measured over the whole take"
    monkeypatch.setattr(takemeasure.soundtail, "ffmpeg", lambda: None)
    assert takemeasure.measure("t.wav", None) == {"problem": "ffmpeg is not installed on the server"}
    from hub.worker import join
    assert takemeasure.NO_FFMPEG == join.NO_FFMPEG


def test_finish_measures_only_when_asked(monkeypatch, tmp_path: Path) -> None:
    heard = {"heard": 1.0, "first_miss": None, "span": 1.0, "words": 3, "first": 0.5, "last": 1.5}
    monkeypatch.setattr(judge, "words", lambda path, text, language=None: dict(heard))
    monkeypatch.setattr(takemeasure, "measure", lambda path, words: {"measured": path, "first": words["first"]})
    path = str(tmp_path / "line.wav")
    line = SpeechRequest("m", "Hello there, Character 6.", 7, 8, judge=True)
    assert joins.finish(line, {"prompt": "Speaker 1:\nx"}, [path]) == {"words": heard}, "a Generate line: words"
    track = SpeechRequest("m", "Hello there, Character 6.", 7, 8, judge=True, measure=True)
    assert joins.finish(track, {"prompt": "Speaker 1:\nx"}, [path]) == {
        "words": heard, "measure": {"measured": path, "first": 0.5}}
    assert joins.finish(track, {"prompt": "Speaker 1:\nx"}, []) is None


def _wav(path: Path, parts: list[tuple[float, float]], rate: int = 48_000) -> None:
    frames = []
    for seconds, amp in parts:
        frames += [amp * math.sin(2 * math.pi * 1000 * k / rate) for k in range(int(seconds * rate))]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", round(v * 32767)) for v in frames))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="no ffmpeg here")
def test_a_real_take_with_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("FFMPEG_BINARY", raising=False)       # the engine's search, as test_soundtail's
    path = tmp_path / "take.wav"
    _wav(path, [(0.5, 0.0), (1.0, 0.1), (0.6, 0.0), (0.3, 0.5), (0.3, 0.0)])
    got = takemeasure.measure(str(path), {"first": 0.55, "last": 1.45})
    assert abs(got["speech_start_ms"] - 500) <= 20 and abs(got["speech_end_ms"] - 1500) <= 20, got
    assert got["extra_s"] == pytest.approx(0.3, abs=0.05) and got["length_ms"] == 2700
    assert got["lufs"] == pytest.approx(-23.0, abs=0.5) and got["true_peak_dbtp"] == pytest.approx(-20.0, abs=0.5)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="no ffmpeg here")
def test_digital_silence_is_none_never_infinity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("FFMPEG_BINARY", raising=False)
    path = tmp_path / "silent.wav"
    _wav(path, [(1.5, 0.0)])
    got = takemeasure.measure(str(path), None)
    assert got["lufs"] is None and got["true_peak_dbtp"] is None
    json.dumps(got, allow_nan=False)


def test_the_loudness_is_read_at_log_level_info(monkeypatch) -> None:
    """Ffmpeg prints ebur128's Summary only at info or verbose; a call at `-v error` would
    read every take unmeasured. The stand-in ffmpeg prints the Summary only when not asked for `-v error`/`quiet`,
    and a 100 ms line holding `I:` before it, which is never read."""
    calls: list[list[str]] = []

    def fake(argv: list[str], **kw: object) -> object:
        calls.append(argv)
        level = argv[argv.index("-v") + 1] if "-v" in argv else "info"
        quiet = level in ("quiet", "panic", "fatal", "error", "warning")
        text = "" if quiet or "silencedetect" in " ".join(argv) else (
            "[Parsed_ebur128_0 @ 0x1] t: 0.4 TARGET:-23 LUFS M: -99.0 S:-120.7 I: -99.0 LUFS LRA: 0.0 LU\n"
            + SUMMARY.format(i="-21.5", peak="-4.0"))
        return SimpleNamespace(returncode=0, stderr=text.encode())
    monkeypatch.setattr(takemeasure.soundtail, "ffmpeg", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(takemeasure.subprocess, "run", fake)
    got = takemeasure.measure("t.wav", {"first": 0.5, "last": 1.5}, length=lambda p: 2.0)
    assert got["lufs"] == -21.5 and got["true_peak_dbtp"] == -4.0, got
    assert all(c[c.index("-v") + 1] in ("info", "verbose") for c in calls)
