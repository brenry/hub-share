"""The words judge. The adapter scores a transcript against the written words with the engine's own
aligner (copied into the test from upstream dialogue.py:224-265): every word heard, three missing from 5.4 s, a wrong
word; the engine absent → None; `finish` returns the verdict only when the request asks, after the joins.
Whisper is loaded once per worker and handed to every take as `prepared_model`."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from hub.worker.adapters import joins, judge, turns
from hub.worker.engineapi import SpeechRequest

LINE = "Line 1 is said. Line 2 is said. Line 3 is said too."


def _fuzzy(left: str, right: str) -> bool:
    """The engine's own word match (upstream dialogue.py:224-237), copied for the test: Levenshtein ratio ≥ 0.55."""
    if left == right:
        return True
    if not left or not right:
        return False
    distances = list(range(len(right) + 1))
    for row, lc in enumerate(left, 1):
        diagonal, distances[0] = distances[0], row
        for column, rc in enumerate(right, 1):
            previous = distances[column]
            distances[column] = diagonal if lc == rc else 1 + min(diagonal, distances[column], distances[column - 1])
            diagonal = previous
    return 1.0 - distances[-1] / max(len(left), len(right)) >= 0.55


def align(transcribed: list[str], expected: list[str]) -> list[tuple[str, int | None]]:
    """The engine's aligner (upstream dialogue.py:241-265), copied for the test: the labels the judge reads."""
    rows, columns, gap = len(transcribed), len(expected), -1
    scores = [[0] * (columns + 1) for _ in range(rows + 1)]
    for row in range(1, rows + 1):
        scores[row][0] = scores[row - 1][0] + gap
    for column in range(1, columns + 1):
        scores[0][column] = scores[0][column - 1] + gap
    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            diagonal = scores[row - 1][column - 1] + (2 if _fuzzy(transcribed[row - 1], expected[column - 1]) else -1)
            scores[row][column] = max(diagonal, scores[row - 1][column] + gap, scores[row][column - 1] + gap)
    aligned: list[tuple[str, int | None]] = []
    row, column = rows, columns
    while row or column:
        match_score = 2 if row and column and _fuzzy(transcribed[row - 1], expected[column - 1]) else -1
        if row and column and scores[row][column] == scores[row - 1][column - 1] + match_score:
            aligned.append(("match" if match_score == 2 else "substitution", column - 1))
            row -= 1
            column -= 1
        elif row and scores[row][column] == scores[row - 1][column] + gap:
            aligned.append(("insertion", None))
            row -= 1
        else:
            column -= 1
    return list(reversed(aligned))


def heard_of(words: list[str], start: float = 0.5, each: float = 0.3) -> list[tuple[str, float, float]]:
    return [(w, round(start + i * each, 2), round(start + i * each + 0.25, 2)) for i, w in enumerate(words)]


def test_every_word_heard_scores_one_with_no_miss_and_the_true_span():
    expected = turns._words(LINE)
    out = judge.score(heard_of(expected), expected, align)
    assert out == {"heard": 1.0, "first_miss": None, "span": round(0.3 * (len(expected) - 1) + 0.25, 3),
                   "words": len(expected), "first": 0.5, "last": round(0.5 + 0.3 * (len(expected) - 1) + 0.25, 2)}


def test_missing_words_lower_the_share_and_name_the_second_of_the_first_miss():
    expected = turns._words(LINE)
    kept = expected[:5] + expected[8:]                        # "sit down let's" never came out
    out = judge.score(heard_of(kept), expected, align)
    assert out["heard"] == round((len(expected) - 3) / len(expected), 4)
    assert out["first_miss"] == heard_of(kept)[4][2], "the end of the last word heard before the gap"
    assert out["words"] == len(expected)
    assert judge.score([], expected, align) == {"heard": 0.0, "first_miss": 0.0, "span": 0.0, "words": len(expected),
                                                "first": None, "last": None}
    assert judge.score(heard_of(["x"]), [], align)["words"] == 0


def test_first_and_last_are_where_the_line_sits_not_the_garble_around_it():
    """Speech that is not the line (heard but matching no written word) moves neither."""
    expected = turns._words(LINE)
    garble = [("blah", 0.2, 0.5), ("mumble", 0.6, 1.0)]
    out = judge.score(garble + heard_of(expected, start=5.0) + [("uh", 9.9, 10.0)], expected, align)
    assert out["heard"] == 1.0 and out["first"] == 5.0
    assert out["last"] == round(5.0 + 0.3 * (len(expected) - 1) + 0.25, 2)
    assert out["span"] == round(10.0 - 0.2, 3), "the span as today: every heard word"


@pytest.fixture(autouse=True)
def _no_kept_whisper(monkeypatch):
    """Each test starts as a fresh worker: no Whisper kept."""
    monkeypatch.setattr(judge, "_kept", [])


def fake_engine(monkeypatch, report, fail=False, loader=True, load_fail=False):
    """The engine's transcription module: a loader that counts its calls (`loads`, each giving a new object) and a
    `transcribe_media` that pops `prepared_model` as the engine does (upstream transcription.py:227), recording the
    keywords as given (`seen`) and every model it was handed (`given`)."""
    tr = types.ModuleType("shared.deepy.transcription")
    tr.torch = types.SimpleNamespace(device=lambda name: ("device", name))
    loads: list[object] = []
    def _load_whisper_medium(device):
        if load_fail:
            raise FileNotFoundError("whisper_medium/model.safetensors")
        assert device == ("device", "cpu")
        loads.append(object())
        return loads[-1]
    def transcribe_media(path, **kw):
        prepared = kw.get("prepared_model")
        transcribe_media.seen = (path, {**kw, "prepared_model": list(prepared)} if prepared is not None else dict(kw))
        if prepared is not None:
            assert len(prepared) == 1, "a one-item list"
            transcribe_media.given.append(prepared.pop())
        if fail:
            raise FileNotFoundError("line.wav: no audio stream")
        return report
    transcribe_media.given = []
    transcribe_media.loads = loads
    tr.transcribe_media = transcribe_media
    if loader:
        tr._load_whisper_medium = _load_whisper_medium
    dl = types.ModuleType("models.minimax_h3.dialogue")
    dl._normalize_words, dl._align_words = turns._words, align
    for name, mod in (("shared.deepy.transcription", tr), ("models.minimax_h3.dialogue", dl)):
        monkeypatch.setitem(sys.modules, name, mod)
    return transcribe_media


def test_the_judge_hears_a_file_through_the_engine_on_cpu_with_word_timestamps(monkeypatch, tmp_path: Path):
    expected = turns._words(LINE)
    words = [{"word": " " + w.capitalize(), "start": 0.5 + i * 0.3, "end": 0.75 + i * 0.3, "probability": 0.9}
             for i, w in enumerate(expected)]
    tm = fake_engine(monkeypatch, {"text": LINE, "segments": [{"start": 0.5, "end": 4.0, "words": words}]})
    out = judge.words(str(tmp_path / "line.wav"), f"[calm] {LINE}")
    assert out["heard"] == 1.0 and out["first_miss"] is None and out["words"] == len(expected)
    assert tm.seen[0] == str(tmp_path / "line.wav")
    assert tm.seen[1] == {"timestamp_type": "word", "model_name": "medium", "device": "cpu", "language": None,
                          "prepared_model": tm.loads}
    monkeypatch.setattr(judge, "_kept", [])
    fake_engine(monkeypatch, {}, load_fail=True)
    assert judge.words(str(tmp_path / "line.wav"), LINE) is None, "no files: no verdict, no crash"
    monkeypatch.setitem(sys.modules, "shared.deepy.transcription", None)
    assert judge.words(str(tmp_path / "line.wav"), LINE) is None


def test_finish_returns_the_verdict_only_when_the_request_asks(monkeypatch, tmp_path: Path):
    expected = turns._words(LINE)
    words = [{"word": w, "start": i * 0.3, "end": i * 0.3 + 0.2} for i, w in enumerate(expected)]
    fake_engine(monkeypatch, {"segments": [{"words": words}]})
    path = tmp_path / "line.wav"
    path.write_bytes(b"RIFF")                                   # not a WAV: the smoothing leaves it, the judge is faked
    asked = SpeechRequest("m", LINE, 7, 300, judge=True, join_seconds=0.1)
    assert joins.finish(asked, {"prompt": "Speaker 1:\nx\nSpeaker 1:\ny"}, [str(path)]) == {
        "words": {"heard": 1.0, "first_miss": None, "span": round(0.3 * (len(expected) - 1) + 0.2, 3),
                  "words": len(expected), "first": 0.0, "last": round(0.3 * (len(expected) - 1) + 0.2, 2)}}
    quiet = SpeechRequest("m", LINE, 7, 300, judge=False)
    assert joins.finish(quiet, {"prompt": "Speaker 1:\nx"}, [str(path)]) is None
    assert joins.finish(asked, {"prompt": "Speaker 1:\nx"}, []) is None


def test_a_clip_with_words_is_heard_beside_its_faces(monkeypatch, tmp_path: Path):
    """A clip request with `words` and `judge` has its soundtrack heard as a line is."""
    from hub.worker.engineapi import ClipRequest
    expected = turns._words(LINE)
    fake_engine(monkeypatch, {"segments": [{"words": [{"word": w, "start": i * 0.3, "end": i * 0.3 + 0.2}
                                                      for i, w in enumerate(expected)]}]})
    monkeypatch.setattr(joins, "_faces", lambda request, sent, files: {"face": {"Character 6": {"median": 0.4}}})
    clip = str(tmp_path / "take.mp4")
    heard = ClipRequest("m", "a shot", (960, 544), 7, 124, judge="cpu", words=LINE)
    out = joins.finish(heard, {}, [clip])
    assert out["face"] == {"Character 6": {"median": 0.4}} and out["words"]["heard"] == 1.0
    assert joins.finish(ClipRequest("m", "a shot", (960, 544), 7, 124, judge="cpu"), {}, [clip]) == {
        "face": {"Character 6": {"median": 0.4}}}, "without words: as today"
    fake_engine(monkeypatch, {}, fail=True)
    assert "words" not in joins.finish(heard, {}, [clip]), "a transcription that fails: no words"
    monkeypatch.setattr(joins, "_faces", lambda request, sent, files: None)
    fake_engine(monkeypatch, {"segments": []})
    assert joins.finish(heard, {}, [clip]) == {"words": {"heard": 0.0, "first_miss": 0.0, "span": 0.0,
                                                          "words": len(expected), "first": None, "last": None}}


def _report(text: str = LINE) -> dict:
    return {"segments": [{"words": [{"word": w, "start": i * 0.3, "end": i * 0.3 + 0.2}
                                    for i, w in enumerate(turns._words(text))]}]}


def test_whisper_is_loaded_once_across_takes(monkeypatch, tmp_path: Path):
    tm = fake_engine(monkeypatch, _report())
    for take in ("take1.wav", "take2.wav", "take3.wav"):
        assert judge.words(str(tmp_path / take), LINE)["heard"] == 1.0
    assert len(tm.loads) == 1, "one load for three takes"
    assert tm.given == [tm.loads[0]] * 3, "every take was handed the same kept model"


def test_a_line_and_a_clip_share_one_load(monkeypatch, tmp_path: Path):
    from hub.worker.engineapi import ClipRequest
    tm = fake_engine(monkeypatch, _report())
    monkeypatch.setattr(joins, "_faces", lambda request, sent, files: None)
    line = tmp_path / "line.wav"
    line.write_bytes(b"RIFF")
    assert joins.finish(SpeechRequest("m", LINE, 7, 300, judge=True, join_seconds=0.1),
                        {"prompt": "Speaker 1:\nx"}, [str(line)])["words"]["heard"] == 1.0
    clip = ClipRequest("m", "a shot", (960, 544), 7, 124, judge="cpu", words=LINE)
    assert joins.finish(clip, {}, [str(tmp_path / "take.mp4")])["words"]["heard"] == 1.0
    assert len(tm.loads) == 1 and tm.given == [tm.loads[0]] * 2


def test_a_failed_load_keeps_nothing_and_the_next_take_tries_again(monkeypatch, tmp_path: Path):
    fake_engine(monkeypatch, _report(), load_fail=True)
    assert judge.words(str(tmp_path / "take1.wav"), LINE) is None
    assert judge._kept == [], "nothing kept"
    tm = fake_engine(monkeypatch, _report())                    # the files are there now
    assert judge.words(str(tmp_path / "take2.wav"), LINE)["heard"] == 1.0
    assert len(tm.loads) == 1 and judge._kept == tm.loads


def test_a_failed_transcription_keeps_the_model(monkeypatch, tmp_path: Path):
    tm = fake_engine(monkeypatch, _report(), fail=True)
    assert judge.words(str(tmp_path / "take1.wav"), LINE) is None
    assert judge._kept == tm.loads and len(tm.loads) == 1
    again = fake_engine(monkeypatch, _report())
    assert judge.words(str(tmp_path / "take2.wav"), LINE)["heard"] == 1.0
    assert again.loads == [], "the next take loads nothing"
    assert again.given == tm.loads


def test_an_engine_without_the_loader_hears_as_today(monkeypatch, tmp_path: Path):
    tm = fake_engine(monkeypatch, _report(), loader=False)
    assert judge.words(str(tmp_path / "take.wav"), LINE)["heard"] == 1.0
    assert tm.seen[1] == {"timestamp_type": "word", "model_name": "medium", "device": "cpu", "language": None}
    assert judge._kept == []
