"""A sound from a prompt alone. `tasks.sound` is the sound task (the prompt as written, the length exact,
no sample); the facts file marks the speech model `sounds`, and the catalog carries it."""
from __future__ import annotations

from hub.worker import enginewire
from hub.worker.adapters import tasks, upstream
from hub.worker.engineapi import ClipRequest, PictureRequest, SoundRequest, SpeechRequest
from tests.engine.test_upstream_rules import ACCEPTED, FL2VA, SPEECH, accepted, cat, entry, sent  # noqa: F401

PROMPT = "subject_definitions:\nAn audience in a hall.\nnon_diegetic_music:\nN/A"


def test_a_sound_is_its_own_task():
    request = enginewire.request_parse(enginewire.request_wire(SoundRequest(SPEECH, PROMPT, 7, 4)))
    assert tasks.sound(request, {}) == {"model_type": SPEECH, "prompt": PROMPT, "seed": 7, "batch_size": 1,
                                        "multi_prompts_gen_type": "FG", "duration_seconds": 4,
                                        "audio_prompt_type": ""}
    assert tasks.task(request, {}) == tasks.sound(request, {}), "`task` routes a sound"


def test_a_request_with_no_seed_sends_no_seed_key(cat):  # noqa: F811
    """A request whose seed is None sends no `seed` (the engine's own default); 7 sends 7."""
    def made(seed):
        return [sent(cat, SoundRequest(SPEECH, "Prompt 1", seed, 4)),
                sent(cat, SpeechRequest(SPEECH, "Line 1.", seed, 30)),
                sent(cat, PictureRequest("flux2_klein_9b", "Prompt 1", (64, 48), seed, steps=4)),
                sent(cat, ClipRequest(FL2VA, "Prompt 1", (960, 544), seed, 141, steps=20))]
    assert all("seed" not in task for task in made(None))
    assert [task["seed"] for task in made(7)] == [7, 7, 7, 7]


def test_the_facts_key_marks_the_speech_model_sounds(cat):  # noqa: F811
    facts = upstream.facts_file()["speech"]["sounds"]
    assert facts[SPEECH] == "prompt" and "minimax_h3_handler.py:289-297" in facts["why"]
    assert "pipeline.py:794-795" in facts["why"]
    assert upstream.line_facts(None, SPEECH, {"resolution_budget": 1})["sounds"] is True
    assert "sounds" not in upstream.line_facts(None, "minimax_h3_ref2va_pruned", {"resolution_budget": 1})
    assert entry(cat, SPEECH)["sounds"] is True and entry(cat, SPEECH)["kind"] == "speech"
    assert not any(m.get("sounds") for m in cat["models"] if m["id"] != SPEECH)


def test_the_sound_task_holds_only_keys_upstream_accepts(cat):  # noqa: F811
    task = sent(cat, SoundRequest(SPEECH, PROMPT, 7, 4))
    assert set(task) <= ACCEPTED and task["prompt"] == PROMPT and task["duration_seconds"] == 4
