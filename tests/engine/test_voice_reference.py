"""A voiced clip in one render. The catalog keeps Ref2VA's `voice_reference`; a clip with one voice sample
goes as `A` + `audio_guide`, two as `AB` + `audio_guide2`; voices beside a kept sound, on a model without the letter,
and a fourth voice are refused in one line; a clip without voices is the plain task byte for byte. The press: the
session's shot's voiced speaker sends the speaker's sample where it is, the short sample, the Sound box and too few
pictures are refused before any job. The catalog and the accepted settings are upstream's own H3 capture. This
is the `reference` voice route (`voice_route`), set for every press here."""
from __future__ import annotations

import copy
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.generate_image import clipvoice, models, routes
from hub.worker import enginewire
from hub.worker.adapters import voiceref
from hub.worker.engineapi import Reference
from tests.engine import test_upstream_rules as rules
from tests.engine.test_generate_image import call
from tests.engine.test_shotprompt import CHARACTER_7, CHARACTER_16, ctx, pick, shot  # noqa: F401
from tests.engine.test_upstream_rules import ACCEPTED, FL2VA, REF2VA, clip, entry, refused, sent
from tests.fakes.wav import tiny_wav

cat, accepted = rules.cat, rules.accepted                 # the H3 capture's fixtures, shared
CHARACTER_7_WAV, CHARACTER_16_WAV = "/c/Character 7.wav", "/c/Character 16.wav"
CHARACTER_7_PIC, CHARACTER_16_PIC = Reference("/c/Character 7.png", "identity"), Reference("/c/Character 16.png",
                                                                                           "identity")


@pytest.fixture(autouse=True)
def reference_route(request):
    """The `reference` voice route, set for every press (the default converts)."""
    if "ctx" in request.fixturenames:
        request.getfixturevalue("ctx").settings["voice_route"] = "reference"


def voiced(*voices: str, model: str = REF2VA, **extra: Any):
    pictures = {"references": [CHARACTER_7_PIC, CHARACTER_16_PIC][:max(1, len(voices))]} \
        if "references" not in extra else {}
    return clip(model, voices=list(voices), **pictures, **extra)


# ---------------------------------------------------------------- the catalog and the task
def test_ref2va_offers_one_voice_reference_letter(cat):
    for model_id in ("minimax_h3_ref2va", REF2VA):
        assert entry(cat, model_id)["video"]["voice_reference"] == "A"
    assert "voice_reference" not in entry(cat, FL2VA)["video"]


def test_one_voice_is_A_and_audio_guide_two_are_AB(cat):
    task = sent(cat, voiced(CHARACTER_7_WAV))
    assert set(task) <= ACCEPTED
    assert (task["audio_prompt_type"], task["audio_guide"]) == ("A", CHARACTER_7_WAV)
    assert "audio_guide2" not in task and task["image_refs"] == ["/c/Character 7.png"]
    two = sent(cat, voiced(CHARACTER_7_WAV, CHARACTER_16_WAV))
    assert set(two) <= ACCEPTED
    assert (two["audio_prompt_type"], two["audio_guide"], two["audio_guide2"]) == ("AB", CHARACTER_7_WAV,
                                                                                   CHARACTER_16_WAV)
    assert "lip" not in task["prompt"], "the words are in the prompt's <d> lines; no kept sound"


def test_without_voices_the_task_is_todays(cat):
    plain = sent(cat, clip(REF2VA, references=[CHARACTER_7_PIC]))
    assert plain == {k: v for k, v in sent(cat, voiced(CHARACTER_7_WAV)).items() if k not in ("audio_prompt_type",
                                                                                         "audio_guide")} | {
        k: plain[k] for k in ("audio_prompt_type",) if k in plain}
    assert "audio_guide" not in plain


def test_each_refusal_is_one_line(cat):
    assert refused(cat, voiced(CHARACTER_7_WAV, sound="/s/line.wav", sound_seconds=6.0)) == voiceref.VOICE_SOUND
    assert refused(cat, voiced(CHARACTER_7_WAV, model=FL2VA, references=[])) == (
        f"{entry(cat, FL2VA)['name']} takes no voice reference")
    assert refused(cat, voiced(CHARACTER_7_WAV, references=[Reference("/c.mp4", "source"), CHARACTER_7_PIC])) == (
        voiceref.VOICE_CONTINUE)
    four = clip(REF2VA, voices=["/1.wav", "/2.wav", "/3.wav", "/4.wav"], references=[CHARACTER_7_PIC] * 4)
    assert refused(cat, four) == f"{entry(cat, REF2VA)['name']} takes at most 3 voice references"
    plain = copy.deepcopy(entry(cat, REF2VA))
    del plain["video"]["voice_reference"]
    request = enginewire.request_parse(enginewire.request_wire(voiced(CHARACTER_7_WAV)))
    with pytest.raises(Exception) as err:
        voiceref.merge({}, request, plain, {"source": []})
    assert str(err.value) == f"{plain['name']} takes no voice reference"


# ---------------------------------------------------------------- the press
def sample(ctx: Any, name: str, seconds: float = 3.0) -> str:  # noqa: F811
    path = ctx.files.existing_media(f"chars/{name}.png").with_suffix(".wav")
    path.write_bytes(tiny_wav(seconds=seconds))
    return str(path.resolve())


async def test_the_press_sends_the_speakers_sample_where_it_is(ctx):  # noqa: F811
    character_7 = sample(ctx, "Character 7")
    pick(ctx, REF2VA)                                                   # no box: cast by name
    seen = await call(ctx, "set_generate_image_settings", {"shot": shot(subjects=[{"name": "Character 7"}])})
    assert "<Audio 1> is the voice-timbre reference for <Subject 1> (S1)." in seen["draft"]
    await call(ctx, "generate_image", {})
    [(job, params)] = ctx.jobs.jobs.values()
    request = job.plan.tasks[0]
    assert request["voices"] == [character_7] and request["sound"] is None
    assert [(r["path"], r["role"]) for r in request["references"]] == [
        (str(ctx.files.existing_media("chars/Character 7.png").resolve()), "identity")]
    task = sent(models.cached(), enginewire.request_parse(request))
    assert (task["audio_prompt_type"], task["audio_guide"]) == ("A", character_7)
    assert job.plan.summary["kind"] == "clip" and "then" not in job.plan.summary


async def test_two_voiced_speakers_go_in_audio_order_and_an_unvoiced_one_as_today(ctx):  # noqa: F811
    character_7, character_16 = sample(ctx, "Character 7"), sample(ctx, "Character 16")
    pick(ctx, REF2VA, CHARACTER_16, CHARACTER_7)                         # the box order: Character 16 is <Subject 1>
    two = shot(lines=[{"speaker": "Character 7", "words": "Hi."}, {"speaker": "Character 16", "words": "Hello."}])
    seen = await call(ctx, "set_generate_image_settings", {"shot": two})
    assert "<Audio 1> is the voice-timbre reference for <Subject 2> (S1). <Audio 2> is the voice-timbre reference " \
           "for <Subject 1> (S2)." in seen["draft"]
    await call(ctx, "generate_image", {})
    [(job, _)] = ctx.jobs.jobs.values()
    assert job.plan.tasks[0]["voices"] == [character_7, character_16], "audio-number order: the lines' order"
    ctx.jobs.jobs.clear()
    ctx.files.existing_media("chars/Character 16.png").with_suffix(".wav").unlink()
    seen = await call(ctx, "set_generate_image_settings", {"shot": two})
    assert "(S2) <Subject 1> says <d>Hello.</d>." in seen["draft"], "no sample: H3's own voice"
    await call(ctx, "generate_image", {})
    [(job, _)] = ctx.jobs.jobs.values()
    assert job.plan.tasks[0]["voices"] == [character_7]


async def refusal(ctx: Any, params: dict) -> str:  # noqa: F811
    with pytest.raises(Invalid) as err:
        await call(ctx, "generate_image", params)
    return err.value.text


async def test_the_press_refuses_a_short_sample_a_sound_and_too_few_pictures(ctx):  # noqa: F811
    sample(ctx, "Character 7", seconds=1.5)
    pick(ctx, REF2VA, CHARACTER_7)
    await call(ctx, "set_generate_image_settings", {"shot": shot(subjects=[{"name": "Character 7"}])})
    assert await refusal(ctx, {}) == "Character 7's voice sample is under 2 s"
    sample(ctx, "Character 7")
    model = models.find(models.cached(), REF2VA)
    ui = models.ui_model(model, models.ref_caps(ctx))
    with pytest.raises(Invalid) as err:
        clipvoice.voices(ctx, model, ui, heard=True, pictures=1)
    assert err.value.text == clipvoice.VOICE_SOUND
    with pytest.raises(Invalid) as err:
        clipvoice.voices(ctx, model, ui, heard=False, pictures=0)
    assert err.value.text == "1 voiced speakers need 1 pictures in the boxes; there are 0"
    assert clipvoice.voices(ctx, model, ui, heard=False, pictures=1) == [sample(ctx, "Character 7")]
    assert not ctx.jobs.jobs, "nothing queued"


async def test_with_the_sound_box_filled_the_speaker_is_not_voiced(ctx):  # noqa: F811
    sample(ctx, "Character 7")
    pick(ctx, REF2VA, CHARACTER_7, sound={"id": "sounds/line.wav", "seconds": 6.0})
    seen = await call(ctx, "set_generate_image_settings", {"shot": shot(subjects=[{"name": "Character 7"}], lines=[])})
    assert "<Audio" not in seen["draft"] and "audio reuse" in seen["draft"]
    routes.session_part(ctx)["sound"] = None
    seen = await call(ctx, "set_generate_image_settings", {"shot": shot(subjects=[{"name": "Character 7"}])})
    assert "<Audio 1>" in seen["draft"]
