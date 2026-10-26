"""Ducking on a real ffmpeg (skipped where none is installed): a 3 s voice track (silence, a 1 s tone, silence) and a
bed under it, saved once ducked and once plain. Both files are as long as track 1; under the voice the ducked file is
quieter than the plain one by more than the compressor's floor; where the voice is silent at the start they are the
same; the bed's level and fades land too."""
from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import pytest

from hub.worker import joincmd

RATE = 48000
FFMPEG = shutil.which("ffmpeg")


def tone(path: Path, seconds: float, hz: float, amp: float, on: tuple[float, float] | None = None) -> None:
    """A mono 16-bit WAV: a tone of `amp`, the whole length or only between `on`."""
    n = int(seconds * RATE)
    frames = bytearray()
    for i in range(n):
        t = i / RATE
        v = amp * math.sin(2 * math.pi * hz * t) if on is None or on[0] <= t < on[1] else 0.0
        frames += struct.pack("<h", int(v * 32767))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))


def rms(path: Path, lo: float, hi: float) -> float:
    with wave.open(str(path), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (2, 2, RATE)
        w.setpos(int(lo * RATE))
        raw = w.readframes(int((hi - lo) * RATE))
    values = struct.unpack(f"<{len(raw) // 2}h", raw)
    return math.sqrt(sum(v * v for v in values) / len(values)) / 32767


def length(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def save(tmp_path: Path, job: str, voice: Path, bed: dict) -> Path:
    state = tmp_path / f"state-{job}"
    (state / "outbox").mkdir(parents=True)
    req = {"items": [{"path": str(voice), "in": 0, "out": 3000, "fps": 1000.0, "w": 0, "h": 0, "frames": 3000,
                      "audio": True, "sound": True}],
           "canvas": {"w": 0, "h": 0, "fps": 1000.0}, "audio": [bed], "crf": 18, "preset": "medium",
           "out_kind": "wav", "duck": {"threshold": 0.05, "ratio": 6.0, "attack": 50.0, "release": 400.0}}
    cmd = joincmd.build(req, [], FFMPEG, str(state), job, True)
    done = subprocess.run(cmd.argv, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return Path(cmd.out)


@pytest.mark.skipif(FFMPEG is None, reason="no ffmpeg installed here")
def test_a_ducked_bed_steps_back_under_the_voice_and_the_file_keeps_track_1s_length(tmp_path: Path):
    voice, bed = tmp_path / "voice.wav", tmp_path / "bed.wav"
    tone(voice, 3.0, 440.0, 0.6, on=(1.0, 2.0))
    tone(bed, 4.0, 110.0, 0.3)                                       # longer than the file: cut at 3 s
    item = {"path": str(bed), "at_ms": 0, "in": 0, "out": 4000, "fps": 1000.0}
    plain = save(tmp_path, "plain", voice, item)
    ducked = save(tmp_path, "duck", voice, {**item, "duck": True})
    assert abs(length(plain) - 3.0) < 0.01 and abs(length(ducked) - 3.0) < 0.01, "track 1's length, both"
    assert abs(rms(plain, 0.2, 0.8) - rms(ducked, 0.2, 0.8)) < 0.01, "no voice yet: the bed is as loud"
    bed_alone = rms(plain, 0.2, 0.8) ** 2                            # the bed's energy where track 1 is silent
    lost = rms(plain, 1.3, 1.9) ** 2 - rms(ducked, 1.3, 1.9) ** 2       # the voice is in both: what differs is the bed
    assert lost > 0.8 * bed_alone, (lost, bed_alone)                  # the bed under the voice lost over 80 % (−7 dB+)
    assert rms(ducked, 2.6, 2.95) ** 2 > 0.5 * bed_alone, "the bed comes back after the voice (release 400 ms)"


@pytest.mark.skipif(FFMPEG is None, reason="no ffmpeg installed here")
def test_a_beds_level_and_fades_land(tmp_path: Path):
    voice, bed = tmp_path / "voice.wav", tmp_path / "bed.wav"
    tone(voice, 3.0, 440.0, 0.0)                                      # a silent track 1
    tone(bed, 3.0, 110.0, 0.4)
    item = {"path": str(bed), "at_ms": 0, "in": 0, "out": 3000, "fps": 1000.0}
    plain = save(tmp_path, "plain", voice, item)
    shaped = save(tmp_path, "shaped", voice, {**item, "level": 0.5, "fade_in": 1000, "fade_out": 1000})
    middle_plain, middle_shaped = rms(plain, 1.4, 1.6), rms(shaped, 1.4, 1.6)
    assert abs(middle_shaped - middle_plain * 0.5) < 0.02, (middle_plain, middle_shaped)
    assert rms(shaped, 0.0, 0.2) < middle_shaped * 0.4 and rms(shaped, 2.8, 3.0) < middle_shaped * 0.4, "faded ends"
    assert abs(rms(plain, 0.0, 0.2) - middle_plain) < 0.02, "the plain bed starts at full level"
