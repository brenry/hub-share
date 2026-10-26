"""The press with `voice_route` `convert` (the default) is the render then the voice step, one
job; `reference` is the one render with the speaker's sample as `<Audio 1>`. No sample, a sound in the Sound box,
a continued clip, no lines: one render, as today. Two speakers with a sample among them: refused. Before the render,
SeedVC off or lacking refuses the queued job in the engine's one line."""
from __future__ import annotations

from typing import Any

import pytest

from hub.core.api import Invalid, JobPlan
from hub.modules.generate_image import build, chain, clipconvert, routes
from tests.engine.test_generate_image import call
from tests.engine.test_shotprompt import CHARACTER_7, CHARACTER_16, ctx, pick, shot  # noqa: F401
from tests.engine.test_upstream_rules import REF2VA, cat  # noqa: F401
from tests.engine.test_voice_reference import sample


async def press(ctx: Any, value: dict, params: dict | None = None):  # noqa: F811
    await call(ctx, "set_generate_image_settings", {"shot": value})
    await call(ctx, "generate_image", params or {})
    [(job, _)] = ctx.jobs.jobs.values()
    ctx.jobs.jobs.clear()
    return job


def character_7_alone(**extra: Any) -> dict:
    return shot(subjects=[{"name": "Character 7"}], **extra)


async def test_convert_is_the_render_then_the_voice_step(ctx):  # noqa: F811
    character_7 = sample(ctx, "Character 7")
    pick(ctx, REF2VA, CHARACTER_7)
    seen = await call(ctx, "set_generate_image_settings", {"shot": character_7_alone()})
    assert "<Audio" not in seen["draft"] and "(S1) <Subject 1> says <d>" in seen["draft"]
    job = await press(ctx, character_7_alone())
    render, voice = job.plan.tasks
    assert render["kind"] == "video" and render["voices"] == [] and "<Audio" not in render["prompt"]
    assert voice == {"kind": "voice", "clip": "", "sample": character_7, "seed": render["seed"]}
    assert job.plan.inputs == ({}, {"clip": (1, "file")}) and job.plan.summary["step_names"] == ["Render", "Voice"]
    assert job.plan.model == REF2VA and render["judge"] == "cpu", "the judges stay on the render"


async def test_job_byte_for_byte(ctx):  # noqa: F811
    character_7 = sample(ctx, "Character 7")
    pick(ctx, REF2VA, CHARACTER_7)
    ctx.settings["voice_route"] = "reference"
    seen = await call(ctx, "set_generate_image_settings", {"shot": character_7_alone()})
    assert "<Audio 1> is the voice-timbre reference for <Subject 1> (S1)." in seen["draft"]
    job = await press(ctx, character_7_alone())
    (render,) = job.plan.tasks
    assert render["voices"] == [character_7] and job.plan.inputs == () and "step_names" not in job.plan.summary
    assert job.plan == JobPlan("image", REF2VA, (render,), job.plan.summary), "one task, no inputs: one render"


@pytest.mark.parametrize("case", ["no sample", "no lines", "sound box", "a speaker without a box"])
async def test_one_render_as_today(ctx, case):  # noqa: F811
    if case != "no sample":
        sample(ctx, "Character 7")
    value = character_7_alone()
    if case == "no lines":
        value = character_7_alone(lines=[])
    if case == "sound box":
        value = character_7_alone(lines=[])
        pick(ctx, REF2VA, CHARACTER_7, sound={"id": "sounds/line.wav", "seconds": 6.0})
    elif case == "a speaker without a box":
        pick(ctx, REF2VA, CHARACTER_16)
        value = shot(subjects=[{"name": "Character 16"}, {"name": "Speaker 2"}],
                     lines=[{"speaker": "Speaker 2", "words": "Line 2?"}])
    else:
        pick(ctx, REF2VA, CHARACTER_7)
    if case == "sound box":                 # lines beside a kept sound are refused; no lines: no speaker
        assert routes.session_part(ctx)["sound"]
        assert clipconvert.speaker(ctx, models_of(ctx), "H3", heard=True) is None
        return
    job = await press(ctx, value)
    assert len(job.plan.tasks) == 1 and job.plan.inputs == () and "step_names" not in job.plan.summary


def models_of(ctx: Any) -> dict:  # noqa: F811
    from hub.modules.generate_image import models
    return models.find(models.cached(), REF2VA)


async def test_a_continued_clip_is_one_render(ctx, monkeypatch):  # noqa: F811
    sample(ctx, "Character 7")
    pick(ctx, REF2VA, CHARACTER_7)
    await call(ctx, "set_generate_image_settings", {"shot": character_7_alone()})
    one = JobPlan("image", REF2VA, ({"kind": "video"},), {"kind": "clip"})
    monkeypatch.setattr(chain, "source", lambda *a: ("clips/x.mp4", 5.0))
    monkeypatch.setattr(chain, "plan", lambda *a: one)
    monkeypatch.setattr(clipconvert, "plan", lambda *a: pytest.fail("a continue is not converted"))
    params = {"model": REF2VA, "mode": "refs", "references": ["chars/Character 7.png"], "prompt": "x", "frames": None,
              "seed": {"mode": "fixed", "value": 7}, "width": 960, "height": 544}
    model = models_of(ctx)
    from hub.modules.generate_image import models
    assert build.clip_job(params, ctx, model, models.ui_model(model, models.ref_caps(ctx))) is one


async def test_two_speakers_with_a_sample_among_them_are_refused(ctx):  # noqa: F811
    sample(ctx, "Character 7")
    pick(ctx, REF2VA, CHARACTER_7, CHARACTER_16)
    two = shot(lines=[{"speaker": "Character 7", "words": "Hi."}, {"speaker": "Character 16", "words": "Hello."}])
    await call(ctx, "set_generate_image_settings", {"shot": two})
    with pytest.raises(Invalid) as err:
        await call(ctx, "generate_image", {})
    assert err.value.text == "One speaker per shot when the speaker's voice is converted" and not ctx.jobs.jobs


class Asked:
    def __init__(self, answer: dict | Exception) -> None:
        self.answer, self.asked = answer, []

    async def query(self, what: str, **args: Any) -> dict:
        self.asked.append(what)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


async def test_seedvc_off_or_lacking_refuses_the_queued_job_in_one_line(ctx):  # noqa: F811
    sample(ctx, "Character 7")
    pick(ctx, REF2VA, CHARACTER_7)
    await call(ctx, "set_generate_image_settings", {"shot": character_7_alone()})
    await call(ctx, "generate_image", {})
    [(job, _)] = ctx.jobs.jobs.values()
    refused: list[tuple[str, str]] = []
    ctx.jobs.refuse = lambda job_id, text: refused.append((job_id, text))
    lacks = "Voice conversion lacks, in your model folders: seed-vc (2 files), whisper-small (11 files)"
    ctx.engine = Asked({"on": True, "lacking": ["seed-vc (2 files)", "whisper-small (11 files)"], "line": lacks})
    job.state = "queued"
    await clipconvert.check(ctx, job)
    assert refused == [(job.id, lacks)] and ctx.engine.asked == ["voice"]
    ctx.engine = Asked({"on": True, "lacking": [], "line": ""})
    await clipconvert.check(ctx, job)
    assert len(refused) == 1, "everything there: the job runs"
    ctx.engine = Asked(RuntimeError("no engine"))
    await clipconvert.check(ctx, job)
    assert len(refused) == 1, "not asked: the worker refuses the step itself"
    plain = JobPlan("image", REF2VA, ({"kind": "video"},), {})
    ctx.engine = Asked({"line": "x"})
    await clipconvert.check(ctx, type("J", (), {"plan": plain, "state": "queued", "id": "j"})())
    assert ctx.engine.asked == [], "a job without a voice step asks nothing"
