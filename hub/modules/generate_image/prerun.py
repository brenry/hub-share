"""What the Hub asks the engine of a clip's job before it runs: its plan and, for a job with a voice step,
whether SeedVC can run it. `build.on_submitted` asks it of a queued press; the Director of the
plan it built, before that plan becomes its job's."""
from __future__ import annotations

from hub.core.api import Ctx, JobPlan

from . import clipconvert, models


async def engine_plan(ctx: Ctx, plan: JobPlan) -> dict | None:
    """A clip's plan by the engine, None for any other job or with `plan_before_render` off."""
    if plan.summary.get("kind") != "clip" or not ctx.settings.get("plan_before_render", True):
        return None
    try:
        return await ctx.engine.query("plan", request=plan.tasks[0])
    except Exception as exc:  # noqa: BLE001  (the engine's one line: the plan could not be asked, the job runs)
        return {"valid": False, "windows": [], "warnings": [], "errors": [], "notes": [models.reason(exc)]}


async def preflight(ctx: Ctx, plan: JobPlan) -> tuple[dict | None, str | None]:
    """What `on_submitted` asks of a queued press, for a plan not yet queued: (the engine's plan for the notes, the
    first refusal line: the plan's error, then the voice check's; None when there is none)."""
    planned = await engine_plan(ctx, plan)
    if planned is not None and planned.get("errors"):
        return planned, str(planned["errors"][0])
    return planned, await clipconvert.refusal(ctx, plan)
