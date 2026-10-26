"""The audio script (`hub/modules/director/audioscript.py`, `routes.get_script`): each line's block word for
word and as the worker writes it, the refusals, the caps, the hash and what changes it, the take each would make,
the rows of a locked script in time order, and the route's `audio` (a locked script only), nothing written."""
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import pytest

from hub.modules.director import audioscript, routes
from hub.worker.adapters import tasks
from hub.worker.enginerequests import SpeechRequest
from tests.engine.test_script_shape import EXAMPLE
from tests.engine.test_script_tools import Ctx

W = "Line one opens."
LOCK = {"locked": True, "at": "2026-10-20T09:15:02+02:00"}


def line(**over: Any) -> dict:
    ev = {"id": "l3", "kind": "line", "start_ms": 9000, "end_ms": 11300, "speaker": "Character 1",
          "words": "Line one opens.", "language": "English", "emotion": "warm and quiet", "pace": 2.6}
    return {k: v for k, v in {**ev, **over}.items() if v is not None}


def cue(**over: Any) -> dict:
    return {"id": "c1", "kind": "cue", "start_ms": 0, "end_ms": 1500, "cue": "music", "words": "A brassy sting", **over}


def test_the_block_word_for_word() -> None:
    assert audioscript.block(line()) == (
        "Speaker 1:\n[English, warm and quiet, 2.6 words per second] Line one opens.", None)
    assert audioscript.block(line(pace=3))[0] == "Speaker 1:\n[English, warm and quiet, 3 words per second] " + W
    assert audioscript.block(line(emotion=None))[0] == f"{audioscript.SPEAKER}\n[English, 2.6 words per second] {W}"
    assert audioscript.block(line(language=None, emotion=None, pace=None))[0] == "Speaker 1:\nLine one opens."


def test_the_block_is_the_workers_own() -> None:
    assert audioscript.SPEAKER == tasks.SPEAKER
    for ev in (line(), line(pace=3), line(emotion=None), line(language=None, emotion=None, pace=None)):
        request = SpeechRequest("speech", audioscript.prompt(ev), 0, audioscript.cap(ev), sample="/c/Character 1.wav")
        assert audioscript.block(ev)[0] == tasks.speech(request, {})["prompt"]


def test_a_block_that_cannot_be_sent() -> None:
    assert audioscript.block(line(words="Speaker 2: hello")) == (None, tasks.HEADER_IN_LINE)
    assert audioscript.block(line(emotion="warm] and")) == (None, audioscript.NO_BRACKETS)
    assert audioscript.block(line(language="Eng\nlish")) == (None, audioscript.NO_BRACKETS)


def test_the_caps() -> None:
    assert audioscript.cap(line(start_ms=0, end_ms=2300)) == 5
    assert audioscript.cap(cue(start_ms=0, end_ms=1500)) == 2
    assert audioscript.cap(cue(start_ms=0, end_ms=300)) == 1


def test_the_hash() -> None:
    h = audioscript.sound_hash(line())
    assert len(h) == 16 and int(h, 16) >= 0 and h == audioscript.sound_hash(line())
    for over in ({"speaker": "Character 2"}, {"words": "Hello."}, {"language": "German"}, {"emotion": "sad"},
                 {"pace": 3}):
        assert audioscript.sound_hash(line(**over)) != h, over
    for over in ({"start_ms": 0, "end_ms": 2300}, {"speaker": "CHARACTER 1"}, {"camera": "Close"}, {"pose": "sit"}):
        assert audioscript.sound_hash(line(**over)) == h, over
    assert audioscript.sound_hash(line(pace=3)) == audioscript.sound_hash(line(pace=3.0))
    c = audioscript.sound_hash(cue())
    assert audioscript.sound_hash(cue(cue="effect")) != c and audioscript.sound_hash(cue(words="Applause")) != c
    assert audioscript.sound_hash(cue(start_ms=200, end_ms=1700)) == c, "moved: its sound as it was"
    assert audioscript.sound_hash(cue(start_ms=0, end_ms=9000)) != c, "its length is in the hash"


def test_the_take_each_would_make() -> None:
    ev = line()
    h = audioscript.sound_hash(ev)
    assert audioscript.take("Script 1", ev, {}) == {"state": "none", "file": "Script 1/l3-1.wav"}
    f1, f2 = "Script 1/l3-1.wav", "Script 1/l3-2.wav"
    assert audioscript.take("Script 1", ev, {"l3": {"file": f2, "hash": h}}) == {"state": "ok", "file": f2}
    flagged = {"l3": {"file": f1, "hash": h, "judge": {"verdict": "flagged", "why": "a word missed"}}}
    assert audioscript.take("Script 1", ev, flagged) == {"state": "flagged", "file": f1, "why": "a word missed"}
    assert audioscript.take("Script 1", ev, {"l3": {"file": f1, "hash": "0" * 16}}) == {"state": "stale", "file": f1}


def test_the_rows_of_a_locked_script() -> None:
    script = {**copy.deepcopy(EXAMPLE), "lock": LOCK}
    rows = audioscript.plan("Script 1", script, {"character 1": "Character 1.wav"})
    assert [r["id"] for r in rows] == ["c1", "c2", "l1", "l2", "c3", "l3", "c4"]
    assert [r["shot"] for r in rows] == ["1.1", "1.1", "1.1", "1.2", "1.2", "1.3", "1.3"]
    l1, l2, c1 = rows[2], rows[3], rows[0]
    assert l1 == {"id": "l1", "kind": "line", "shot": "1.1", "start_ms": 4000, "end_ms": 7642, "who": "Character 1",
                  "text": "Speaker 1:\n[English, Emotion 1, 2.6 words per second] Word word, word. "
                          "Word word word word word word.",
                  "problem": None, "sample": "Character 1.wav", "seconds": 8, "hash": l1["hash"],
                  "take": {"state": "none", "file": "Script 1/l1-1.wav"}}
    assert l2["sample"] is None
    assert c1["who"] == "music" and c1["text"] == "Word word word word-word word" and c1["seconds"] == 3
    assert c1["sample"] is None and c1["take"]["state"] == "none"


class Request:
    def __init__(self, name: str) -> None:
        self.query_params = {"name": name}


@pytest.fixture
def ctx(tmp_path: Path) -> Ctx:
    held = Ctx(tmp_path)
    (tmp_path / "Characters" / "Character 1.wav").write_bytes(b"RIFF")
    held.files.roots["scripts"].mkdir(parents=True, exist_ok=True)
    return held


def get(ctx: Ctx, name: str, script: Any) -> tuple[dict, bool]:
    """The route's answer for `script` written as `name`; and whether the folder and the file are as they were."""
    folder = ctx.files.roots["scripts"]
    path = folder / f"{name}.json"
    path.write_text(script if isinstance(script, str) else json.dumps(script), encoding="utf-8")
    before, listing = path.read_bytes(), sorted(p.name for p in folder.rglob("*"))
    got = asyncio.run(routes.get_script(ctx, Request(name)))  # type: ignore[arg-type]
    return got, path.read_bytes() == before and sorted(p.name for p in folder.rglob("*")) == listing


def test_the_route_answers_audio_for_a_locked_or_written_script(ctx: Ctx) -> None:
    got, same = get(ctx, "Script 1", {**copy.deepcopy(EXAMPLE), "lock": LOCK})
    assert same and [r["id"] for r in got["audio"]] == ["c1", "c2", "l1", "l2", "c3", "l3", "c4"]
    assert got["audio"][2]["sample"] == "Character 1.wav" and got["audio"][3]["sample"] is None
    assert got["audio"][2]["take"] == {"state": "none", "file": "Script 1/l1-1.wav"}
    for name, script in (("Open", copy.deepcopy(EXAMPLE)), ("Opened", {**copy.deepcopy(EXAMPLE),
                                                                         "lock": {"locked": False, "at": None}})):
        got, same = get(ctx, name, script)                           # written, locked or not
        assert same and [r["id"] for r in got["audio"]] == ["c1", "c2", "l1", "l2", "c3", "l3", "c4"], name
    for name, script in (("Old", {k: v for k, v in EXAMPLE.items() if k != "context"} | {"version": 1}),
                         ("Broken", "{not json")):
        got, same = get(ctx, name, script)
        assert same and got["audio"] is None, name
    assert got["problem"] is not None and got["script"] is None
