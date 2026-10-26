"""A spoken line from request to engine: the task the adapter makes of a `SpeechRequest` (the
dialogue script, the voice as a sample or in words) and the real worker running it on the fake engine root that
stands in for upstream 18.05, where the line comes back as one WAV."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub.worker import enginewire
from hub.worker.adapters import tasks, upstream
from hub.worker.engineapi import Reference, SpeechRequest
from hub.worker.faults import Refused
from tests.engine.helpers import Worker, make_engine_root
from tests.engine.test_upstream_rules import ACCEPTED, SPEECH

ENTRY = {"id": SPEECH, "name": "TTS", "kind": "speech", "speech": {"seconds": {"min": 4, "max": 300, "default": 15}}}


def test_a_line_without_a_sample_is_spoken_in_the_words_for_the_voice():
    task = tasks.task(SpeechRequest(SPEECH, "Who goes there?", 7, 300, direction="low, slow"), ENTRY)
    assert task == {"model_type": SPEECH, "prompt": "Speaker 1:\n[low, slow] Who goes there?", "seed": 7,
                    "batch_size": 1, "multi_prompts_gen_type": "FG", "duration_seconds": 300, "audio_prompt_type": ""}


def test_a_line_with_a_sample_is_spoken_in_that_voice_and_the_words_are_not_sent():
    request = SpeechRequest(SPEECH, "[angry] Stay right there!", 7, 300, sample="/chars/Character 8.wav",
                            direction="low, slow")
    task = tasks.task(request, ENTRY)
    assert (task["prompt"], task["audio_prompt_type"], task["audio_guide"]) == (
        "Speaker 1:\n[angry] Stay right there!", "A", "/chars/Character 8.wav"), \
        "the speaker's own [...] stays; the words do not"
    assert "image_mode" not in task, "the model's own; never the clip's forced sound (upstream.translate)"


def test_an_invented_voice_has_no_direction_and_no_sample():
    task = tasks.task(SpeechRequest(SPEECH, "Hello.", 7, 300), ENTRY)
    assert (task["prompt"], task["audio_prompt_type"]) == ("Speaker 1:\nHello.", "")


def test_upstream_takes_the_task_as_it_is(monkeypatch):
    monkeypatch.setattr(upstream, "accepted_names", lambda: ACCEPTED)
    task = upstream.translate(tasks.task(SpeechRequest(SPEECH, "Hello.", 7, 300, sample="/s.wav"), ENTRY), {})
    assert task["audio_prompt_type"] == "A" and task["output_filename"] == "{date}-{seed}", "no prompt in the name"


def test_a_line_takes_no_picture_on_the_wire():
    wire = enginewire.request_wire(SpeechRequest(SPEECH, "Hello.", 7, 300))
    assert enginewire.request_parse(wire) == SpeechRequest(SPEECH, "Hello.", 7, 300)
    with pytest.raises(ValueError, match="unknown field references"):
        enginewire.request_parse({**wire, "references": [enginewire.wire(Reference("/a.png", "reference"))]})


@pytest.fixture
def worker(tmp_path):
    root = make_engine_root(tmp_path, "upstream", h3=True)
    for name in upstream.facts_file()["companions"]["models"][SPEECH]:   # the Whisper the speech model loads
        (root / "ckpts" / name).parent.mkdir(parents=True, exist_ok=True)
        (root / "ckpts" / name).write_bytes(b"w")
    w = Worker(root, tmp_path / "state")
    w.root, w.state = root, tmp_path / "state"
    yield w
    w.close()


def speak(w: Worker, request: SpeechRequest) -> list[dict]:
    w.until(lambda m: m["ev"] in ("ready", "fatal"))
    w.send({"op": "run", "job": "j1", "task": 1, "request": enginewire.request_wire(request)})
    return w.until(lambda m: m["ev"] == "task_done", timeout=60)


def test_the_worker_speaks_a_line_into_one_wav(worker, tmp_path):
    sample = tmp_path / "Character 8.wav"
    sample.write_bytes(b"RIFF")
    got = speak(worker, SpeechRequest(SPEECH, "Stay right there!", 7, 300, sample=str(sample)))
    assert got[-1]["ok"] is True, got[-1]
    [out] = [m["file"] for m in got if m["ev"] == "output"]
    assert out.endswith(".wav") and Path(out).read_bytes().startswith(b"RIFF") and "there" not in Path(out).name
    sent = json.loads((worker.state / "settings" / "last_task.json").read_text())
    assert (sent["prompt"], sent["audio_prompt_type"], sent["audio_guide"], sent["duration_seconds"]) == (
        "Speaker 1:\nStay right there!", "A", str(sample), 300)


def test_a_missing_whisper_refuses_the_line_in_one_line(worker):
    for name in upstream.facts_file()["companions"]["models"][SPEECH]:
        (worker.root / "ckpts" / name).unlink()
    done = speak(worker, SpeechRequest(SPEECH, "Hello.", 7, 300))[-1]
    assert not done["ok"] and done["error"]["text"] == "The engine lacks a companion file: config.json"


@pytest.mark.parametrize("line", ["Speaker 1: The light is ours tonight.", "Speaker 1:\nThe light is ours tonight.",
                                  "speaker 1 {calm}: The light is ours tonight."])
def test_line_with_speaker_header_refused(line):
    with pytest.raises(Refused, match="^A line is the spoken words only, no Speaker header$"):
        tasks.task(SpeechRequest(SPEECH, line, 7, 300), ENTRY)


def test_a_long_line_with_a_header_is_refused_before_any_split():
    line = "word word word word word word. word word word word word word word word. " * 4
    with pytest.raises(Refused, match="^A line is the spoken words only, no Speaker header$"):
        tasks.task(SpeechRequest(SPEECH, f"{line}\nSpeaker 2: {line}", 7, 300, turn_seconds=5.0), ENTRY)


@pytest.mark.parametrize("line", ["[The light is ours tonight.]", "\"[calm]\"", "  "])
def test_line_all_in_brackets_refused(line):
    with pytest.raises(Refused, match=r"^A line needs words outside \[ \]$"):
        tasks.task(SpeechRequest(SPEECH, line, 7, 300, direction="low, slow"), ENTRY)
