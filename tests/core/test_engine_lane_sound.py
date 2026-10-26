"""The lane records each task's own model as resident when its request names one (a scene's sound
task on the audio generator, then its shots on the clip model); a task naming none (a voice, a join) keeps the job's.
The real lane and dispatcher, the fake worker of `test_engine_graph`."""
from __future__ import annotations

from hub.core import api
from hub.worker import engineapi, enginewire
from tests.core.test_engine_graph import MODEL, clip, run, voice

SPEECH = "minimax_h3_tts_ref2va_pruned"


def sound() -> dict:
    return enginewire.request_wire(engineapi.SoundRequest(SPEECH, "a crowd laughs", 7, 4))


async def test_a_sound_tasks_own_model_is_resident_until_the_next_task(tmp_path, monkeypatch):
    plan = api.JobPlan("image", MODEL, (clip(), sound()), {"model": "H3", "kind": "clip"})
    job, lane, _, _, _, _ = await run(tmp_path, monkeypatch, plan)
    assert job.state == "done", job.error
    assert lane.held() == SPEECH, "the last task sent named the audio generator"
    assert [t["kind"] for t in lane.sup.sent] == ["video", "sound"]


async def test_a_shot_after_the_sound_makes_the_clip_model_resident(tmp_path, monkeypatch):
    plan = api.JobPlan("image", MODEL, (sound(), clip()), {"model": "H3", "kind": "clip"})
    job, lane, _, _, _, _ = await run(tmp_path, monkeypatch, plan)
    assert job.state == "done", job.error
    assert lane.held() == MODEL


async def test_a_task_naming_no_model_keeps_the_jobs(tmp_path, monkeypatch):
    plan = api.JobPlan("image", MODEL, (sound(), voice()), {"model": "H3", "kind": "clip"},
                       inputs=({}, {"clip": (1, "file")}))
    job, lane, _, _, _, _ = await run(tmp_path, monkeypatch, plan)
    assert job.state == "done", job.error
    assert lane.held() == MODEL, "a voice step names no model: the job's"
