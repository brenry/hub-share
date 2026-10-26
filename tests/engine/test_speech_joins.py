"""The turns of a spoken line flow into each other. On WAVs made here: the engine's join runs (exactly
0.18 s of zeros, upstream dialogue.py:22) taken out and the sides crossfaded at equal power (`joins.smooth`); a count
other than turns - 1, an overlap of 0, or a format it does not mix leaves the bytes as they were; mono, stereo,
16-bit, 24-bit and float; `finish` smooths only a line sent as more than one turn; the setting's range."""
from __future__ import annotations

import math
import struct
from pathlib import Path

import pytest

from hub import settings as cfg
from hub.worker.adapters import joins
from hub.worker.engineapi import SpeechRequest

RATE = 8_000
PAUSE = round(0.18 * RATE)                          # 1440 frames
FADE = round(0.10 * RATE)                           # 800 frames
LEVELS = (0.25, -0.5, 0.4)                          # each turn a steady level, so the fade reads off directly


def _wav(data: bytes, tag: int, channels: int, bits: int) -> bytes:
    align = channels * bits // 8
    fmt = struct.pack("<HHIIHH", tag, channels, RATE, RATE * align, align, bits)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _sample(v: float, tag: int, bits: int) -> bytes:
    if tag == 3:
        return struct.pack("<f" if bits == 32 else "<d", v)
    top = 1 << (bits - 1)
    return round(v * top).to_bytes(bits // 8, "little", signed=True)


def line(path: Path, turns: int, tag: int = 1, channels: int = 1, bits: int = 16, frames: int = 4_000,
         pause: int = PAUSE) -> Path:
    """`turns` steady turns of `frames` frames, joined as the engine joins them: `pause` frames of zeros."""
    zero = b"\x00" * (channels * bits // 8) * pause
    parts = [_sample(LEVELS[k % 3], tag, bits) * channels * frames for k in range(turns)]
    path.write_bytes(_wav(zero.join(parts), tag, channels, bits))
    return path


def data_of(path: Path) -> bytes:
    raw = path.read_bytes()
    return dict(joins._chunks(raw))[b"data"]


def values(path: Path, tag: int = 1, bits: int = 16) -> list[float]:
    return joins._decode(data_of(path), tag, bits // 8)


@pytest.mark.parametrize("turns", [2, 3])
def test_the_joins_go_and_the_line_is_shorter_by_pause_and_overlap(tmp_path, turns):
    path = line(tmp_path / "line.wav", turns)
    before = len(data_of(path)) // 2
    assert joins.smooth(str(path), turns, 0.10) is True
    after = len(data_of(path)) // 2
    assert before - after == (turns - 1) * (PAUSE + FADE), "(turns - 1) × (0.18 + overlap) s"
    assert joins.runs(data_of(path), 2, PAUSE) == [] and b"\x00\x00" * 10 not in data_of(path), "no silence left"
    assert not list(tmp_path.glob(".*")), "no temp file left beside it"


def test_in_the_overlap_the_sides_follow_cos_and_sin(tmp_path):
    path = line(tmp_path / "line.wav", 2)
    joins.smooth(str(path), 2, 0.10)
    got, start = values(path), 4_000 - FADE
    a, b = LEVELS[0], LEVELS[1]
    for k in (0, FADE // 4, FADE // 2, FADE - 1):
        t = (k + 0.5) / FADE * math.pi / 2
        assert got[start + k] == pytest.approx(a * math.cos(t) + b * math.sin(t), abs=2 / 32768), k
    assert got[start - 1] == pytest.approx(a, abs=1 / 32768) and got[start + FADE] == pytest.approx(b, abs=1 / 32768)


def test_another_count_or_no_overlap_leaves_the_bytes_as_they_were(tmp_path):
    path = line(tmp_path / "line.wav", 3)
    raw = path.read_bytes()
    assert joins.smooth(str(path), 2, 0.10) is False, "two runs found, one expected"
    assert joins.smooth(str(path), 4, 0.10) is False
    assert joins.smooth(str(path), 3, 0.0) is False
    assert path.read_bytes() == raw
    longer = line(tmp_path / "longer.wav", 2, pause=PAUSE + 1)
    raw = longer.read_bytes()
    assert joins.smooth(str(longer), 2, 0.10) is False and longer.read_bytes() == raw, "only the engine's exact run"
    eight = tmp_path / "eight.wav"
    eight.write_bytes(_wav(b"\x80" * 9_000, 1, 1, 8))
    raw = eight.read_bytes()
    assert joins.smooth(str(eight), 2, 0.10) is False and eight.read_bytes() == raw, "a format it does not mix"


@pytest.mark.parametrize(("tag", "channels", "bits"), [(1, 2, 16), (3, 1, 32), (3, 2, 32), (1, 1, 24), (1, 2, 32)])
def test_stereo_float_24_and_32_bit(tmp_path, tag, channels, bits):
    path = line(tmp_path / "line.wav", 3, tag, channels, bits)
    align = channels * bits // 8
    before = len(data_of(path)) // align
    assert joins.smooth(str(path), 3, 0.10) is True
    assert before - len(data_of(path)) // align == 2 * (PAUSE + FADE)
    got = values(path, tag, bits)
    mid = (4_000 - FADE + FADE // 2) * channels
    t = (FADE // 2 + 0.5) / FADE * math.pi / 2
    want = LEVELS[0] * math.cos(t) + LEVELS[1] * math.sin(t)
    assert got[mid:mid + channels] == pytest.approx([want] * channels, abs=1e-4)


def test_the_overlap_is_never_more_than_the_engines_pad(tmp_path):
    path = line(tmp_path / "line.wav", 2)
    before = len(data_of(path)) // 2
    joins.smooth(str(path), 2, 0.5)
    assert before - len(data_of(path)) // 2 == PAUSE + round(0.14 * RATE)


def test_finish_smooths_only_a_line_sent_as_turns(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(joins, "smooth", lambda *a: calls.append(a))
    request = SpeechRequest("m", "Hello.", 7, 300, turn_seconds=5.0, join_seconds=0.1)
    joins.finish(request, {"prompt": "Speaker 1:\nHello."}, ["/a.wav"])
    assert calls == [], "a one-turn line never calls smooth"
    joins.finish(request, {"prompt": "Speaker 1:\nOne.\nSpeaker 1:\nTwo.\nSpeaker 1:\nThree."}, ["/a.wav"])
    assert calls == [("/a.wav", 3, 0.1)]
    calls.clear()
    joins.finish(SpeechRequest("m", "x", 7, 300, join_seconds=None), {"prompt": "Speaker 1:\na\nSpeaker 1:\nb"},
                 ["/a.wav"])
    assert calls == [], "0 or no setting: the engine's join untouched"


def test_finish_leaves_a_file_it_cannot_read(tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not a wav")
    request = SpeechRequest("m", "x", 7, 300, join_seconds=0.1)
    joins.finish(request, {"prompt": "Speaker 1:\na\nSpeaker 1:\nb"}, [str(bad), str(tmp_path / "gone.wav")])
    assert bad.read_bytes() == b"not a wav"


@pytest.mark.parametrize("value", [0, 0.0, 0.05, 0.14])
def test_the_join_takes_seconds_from_0_to_0_14(value):
    s = cfg.validate({"modules": {"generate-image": {"speech_join_seconds": value}}})
    assert s["modules"]["generate-image"]["speech_join_seconds"] == float(value)
    assert cfg.validate({})["modules"]["generate-image"]["speech_join_seconds"] == 0.10


@pytest.mark.parametrize("value", [-0.01, 0.15, True, "0.1", None])
def test_a_join_outside_0_to_0_14_is_refused(value):
    with pytest.raises(cfg.SettingsError) as err:
        cfg.validate({"modules": {"generate-image": {"speech_join_seconds": value}}})
    assert str(err.value) == ("settings.json: modules.generate-image.speech_join_seconds: must be a number from 0.0 "
                              "to 0.14")
