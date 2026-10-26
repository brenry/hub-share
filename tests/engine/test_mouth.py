"""The mouth judge. The engine's opening measure from landmarks; `measure` from openings against speech
spans (a mouth that moves with the words, a still one, a line that never rests); `score` through the face judge with
a faked inspection, the speaker picked by the speaker's reference or by size; a continue's tail."""
from __future__ import annotations

import sys
import types
from pathlib import Path

from hub.worker.adapters import faces, mouth

from .test_faces import FACTS, fake_ffmpeg, fake_libs, fake_locator, fake_reader


def test_opening_is_the_engines_measure_and_none_without_landmarks():
    face = types.SimpleNamespace(kps=[[0.0, 0.0], [60.0, 0.0]], landmark_2d_106=[[0.0, 0.0]] * 106)
    face.landmark_2d_106[mouth.UPPER] = [0.0, 10.0]
    face.landmark_2d_106[mouth.LOWER] = [0.0, 22.0]
    assert mouth.opening(face) == 0.2, "12 px between the lips over 60 px between the eyes"
    assert mouth.opening(types.SimpleNamespace(kps=None, landmark_2d_106=None)) is None
    same = types.SimpleNamespace(kps=[[1.0, 1.0], [1.0, 1.0]], landmark_2d_106=face.landmark_2d_106)
    assert mouth.opening(same) is None, "no eye distance: no measure"


def test_measure_moving_with_the_words_still_and_never_resting():
    times = [(i + 0.5) / 8 for i in range(32)]                   # four seconds at 8 a second
    speech = [(1.0, 2.0), (3.0, 4.0)]
    talking = [0.3 if (1.0 <= t <= 2.0 or t >= 3.0) and i % 2 == 0 else 0.1 for i, t in enumerate(times)]
    out = mouth.measure(talking, times, speech)
    assert out["lips"] == 1.0 and out["moving"] == 1.0 and out["rest"] == 0.0 and out["speech"] == 2.0
    still = mouth.measure([0.1] * 32, times, speech)
    assert still["moving"] == 0.0 and still["talk"] == 0.0 and still["lips"] is None, "nothing moves: no ratio"
    random = [0.3 if i % 2 else 0.1 for i in range(32)]
    assert mouth.measure(random, times, speech)["lips"] == 0.5, "the same motion in and out of the words"
    whole = mouth.measure(random, times, [(0.0, 4.0)])
    assert whole["lips"] is None and whole["rest"] is None and whole["moving"] == 1.0, "a line that fills the clip"
    gaps = mouth.measure([None] * 32, times, speech)
    assert gaps["present"] == 0.0 and gaps["moving"] is None


def test_measure_gives_where_the_speech_starts_and_ends():
    """The first span's start and the last span's end; none without spans."""
    times = [(i + 0.5) / 8 for i in range(80)]
    out = mouth.measure([0.1] * 80, times, [(0.2, 3.0), (3.1, 4.9), (5.42, 9.8)])
    assert out["speech_from"] == 0.2 and out["speech_to"] == 9.8
    empty = mouth.measure([0.1] * 80, times, [])
    assert empty["speech_from"] is None and empty["speech_to"] is None


def fake_inspection(monkeypatch, spans):
    calls = []

    def speech_intervals(path, **kw):
        calls.append(path)
        return spans
    monkeypatch.setitem(sys.modules, mouth.INSPECTION, types.SimpleNamespace(speech_intervals=speech_intervals))
    return calls


def test_score_reads_the_speakers_mouth_by_the_speakers_reference(monkeypatch, tmp_path: Path):
    """Two faces in frame: the one matching Character 7's reference is read, the larger stranger is not. The fake ffmpeg
    gives 24 frames to both passes: the face judge's 12 s at 2 a second, then the mouth judge's 3 s at 8."""
    fake_ffmpeg(tmp_path, monkeypatch, frames=24)
    fake_locator(tmp_path, monkeypatch)
    fake_inspection(monkeypatch, [(0.0, 1.5)])
    character_7, other = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]
    stranger = {"e": other, "open": 0.1, "box": [300, 50, 600, 350]}
    frames = [[character_7]] + [[{"e": character_7}, stranger]] * 24      # the picture, the face judge's frames
    for i in range(24):                                       # the mouth judge's: Character 7's mouth moves to 1.5 s
        opens = 0.3 if i % 2 else 0.1
        frames.append([{"e": character_7, "open": opens if i < 12 else 0.1, "box": [100, 100, 200, 200]}, stranger])
    calls = fake_libs(monkeypatch, frames)
    out = faces.score(str(tmp_path / "c.mp4"), {"Character 7": [str(tmp_path / "j.png")]}, FACTS, speaker="character 7")
    read = out["mouth"]
    assert read["speaker"] == "Character 7" and read["speech"] == 1.5 and read["present"] == 1.0
    assert read["lips"] == 1.0 and read["moving"] == 1.0, "moves through the words (0 to 1.5 s), still after"
    assert calls["frames"] == 1 + 24 + 24, "the picture, the face judge's frames, the mouth judge's"
    assert out["face"]["Character 7"]["min"] == 1.0 and out["frame"]["Character 7"]["size"] == round(100 / 360, 3)


def test_score_without_a_reference_takes_the_largest_face_and_says_no_speech(monkeypatch, tmp_path: Path):
    fake_ffmpeg(tmp_path, monkeypatch, frames=8)
    fake_locator(tmp_path, monkeypatch)
    fake_inspection(monkeypatch, [])
    fake_libs(monkeypatch, [[[1.0, 0.0, 0.0]]])
    out = faces.score(str(tmp_path / "c.mp4"), {"Character 7": [str(tmp_path / "j.png")]}, FACTS)
    assert out["mouth"] is None and out["mouth_why"] == mouth.NO_SPEECH
    np = sys.modules["numpy"]
    small = types.SimpleNamespace(bbox=[0, 0, 10, 10], normed_embedding=np.asarray([0.0, 1.0, 0.0]))
    large = types.SimpleNamespace(bbox=[0, 0, 100, 100], normed_embedding=np.asarray([0.0, 0.0, 1.0]))
    assert mouth._pick([small, large], np, None) is large
    # one character in the boxes but another named as the speaker: the largest face, named by the speaker
    fake_inspection(monkeypatch, [(0.0, 1.0)])
    fake_libs(monkeypatch, [[[1.0, 0.0, 0.0]]] + [[{"e": [0.0, 1.0, 0.0], "open": 0.1 + 0.2 * (i % 2),
                                                      "box": [0, 0, 400, 400]}] for i in range(40)])
    out = faces.score(str(tmp_path / "c.mp4"), {"Character 7": [str(tmp_path / "j.png")]}, FACTS,
                      speaker="Character 21")
    assert out["mouth"]["speaker"] == "Character 21" and out["mouth"]["moving"] == 1.0, \
        "Character 21's line is not read off Character 7"
    alone = faces.score(str(tmp_path / "c.mp4"), {"Character 7": [str(tmp_path / "j.png")]}, FACTS)
    assert alone["mouth"]["speaker"] == "Character 7", "nobody named, one character: that one"
    assert mouth._pick([small, large], np, np.asarray([0.0, 1.0, 0.0])) is small, "the reference decides"
    assert mouth._pick([], np, None) is None


def test_a_continue_judges_the_mouth_of_its_tail_only(monkeypatch, tmp_path: Path):
    """A 4 s clip (the Hub's reader says so) continued by 12 frames at 24 fps: its last 0.5 s; both judges decode
    from 3.5 s on (the fake ffmpeg gives 32 frames less the seek: one at 2 a second, four at 8), and a span that
    ended before 3.5 s is never read."""
    fake_ffmpeg(tmp_path, monkeypatch, frames=32)
    fake_locator(tmp_path, monkeypatch)
    fake_reader(monkeypatch, seconds=4.0)
    fake_inspection(monkeypatch, [(0.0, 0.4)])
    fake_libs(monkeypatch, [[[1.0, 0.0, 0.0]]])
    out = faces.score(str(tmp_path / "c.mp4"), {"J": [str(tmp_path / "j.png")]}, FACTS, new_frames=12)
    assert out["mouth"] is None and out["mouth_why"] == mouth.NO_SPEECH, "the speech was in the source's part"
    assert not any("fps=8" in line for line in (tmp_path / "ffmpeg.log").read_text().splitlines()), "nothing decoded"
    fake_inspection(monkeypatch, [(3.0, 3.9)])
    out = faces.score(str(tmp_path / "c.mp4"), {"J": [str(tmp_path / "j.png")]}, FACTS, new_frames=12)
    lines = (tmp_path / "ffmpeg.log").read_text().splitlines()
    decodes = [line for line in lines if "fps=8" in line and "-frames:v" not in line]
    assert decodes and all("-ss 3.500 -i" in line for line in decodes), decodes
    assert out["mouth"]["speech"] == 0.4 and out["mouth"]["present"] == 1.0, "the span cut to the judged part"
