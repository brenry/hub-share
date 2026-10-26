"""The speaker's voice by conversion: with `voice_route` `convert` (the default), a clip whose
shot has one speaker, a boxed listed character with a voice sample, on a model whose clip makes its own sound, with the
Sound box empty and no clip continued, is one job of two steps: the render, in H3's own voice, then the engine's SeedVC
turning that speech into the speaker's voice from `<Name>.wav`, the room kept (`VoiceRequest`, its `clip` filled by the
lane from step 1's file, `JobPlan.inputs`). Lines by two speakers or more, one of them with a sample, are refused: one
speaker's conversion turns every voice in the clip into the speaker's (upstream `seedvc_processor/bridge.py:381`).
Anything else is one render, as `build.clip_job` plans it.

Before the render, the engine is asked whether SeedVC is on and what it lacks (`check`, the worker's `voice` query);
either refuses the queued job in that one line (`ctx.jobs.refuse`). The worker's own refusal is the backstop.
"""
from __future__ import annotations

from typing import Any

from hub.core.api import Ctx, Invalid, JobPlan, VoiceRequest, request_wire

from . import clipvoice, models, routes, voiced

STEPS = ["Render", "Voice"]
ONE_SPEAKER = "One speaker per shot when the speaker's voice is converted"


def _key(name: Any) -> str:
    return " ".join(str(name or "").split()).lower()


def speaker(ctx: Ctx, model: dict, label: str, heard: bool) -> str | None:
    """The one speaker whose voice is converted, as the speaker's sample's real path (checked, `clipvoice.sample`); None
    when the clip is rendered alone. Two speakers or more with a sample among them: refused."""
    from . import shotcheck  # late, as `clipvoice` takes it

    shot = routes.session_part(ctx).get("shot")
    if ctx.settings.get("voice_route", "convert") != "convert" or not isinstance(shot, dict) or heard:
        return None
    if not (models.video(model) or {}).get("soundtrack"):
        return None                                        # a clip that makes no sound has no voice to turn
    who = list(dict.fromkeys(_key(line.get("speaker")) for line in shot.get("lines") or [] if isinstance(line, dict)))
    boxed, listed = shotcheck.frame(ctx, model, label, shot).boxed, voiced.characters(ctx)
    sampled = [w for w in who if w in boxed and w in listed and ctx.files.character_sample(listed[w]["name"])]
    if not sampled:
        return None
    if len(who) > 1:
        raise Invalid("shot", ONE_SPEAKER)
    return clipvoice.sample(ctx, listed[sampled[0]]["name"])


def plan(ctx: Ctx, model: dict, ui: dict, task: dict, summary: dict, heard: bool) -> JobPlan:
    """The clip's job: the render alone, or the render then the voice step."""
    sample = speaker(ctx, model, ui["label"], heard)
    if sample is None:
        return JobPlan("image", model["id"], (task,), summary)
    seed = (summary.get("seeds") or [None])[0]          # the clip's seed, else none
    voice = request_wire(VoiceRequest("", sample, None if seed is None else int(seed)))
    return JobPlan("image", model["id"], (task, voice), {**summary, "step_names": list(STEPS)},
                   inputs=({}, {"clip": (1, "file")}))


async def check(ctx: Ctx, job: Any) -> None:
    """A queued job with a voice step: refused in one line when SeedVC is off in the engine or lacks a file or its
    component (`refusal`)."""
    if job is None or job.state != "queued":
        return
    if line := await refusal(ctx, job.plan):
        ctx.jobs.refuse(job.id, line)


async def refusal(ctx: Ctx, plan: JobPlan) -> str | None:
    """The engine's line when a plan with a voice step cannot run it, else None. An engine that cannot be asked leaves
    the job to the worker's own refusal."""
    if not any(t.get("kind") == "voice" for t in plan.tasks):
        return None
    try:
        answer = await ctx.engine.query("voice")
    except Exception:  # noqa: BLE001  (not asked: the worker refuses the step itself, before the engine runs it)
        return None
    return str(answer["line"]) if answer.get("line") else None
