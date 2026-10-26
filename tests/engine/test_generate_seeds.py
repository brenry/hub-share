"""Generate's seed line (F1): the seeds a job drew become the screen's `last_seeds` when Generate pressed (its own
`ctx.jobs.submit`) or a screen did (the web press, `by` "screen"); a job another module submits, such as a
storyboard's, leaves them as they are. The builder alone writes nothing."""
from __future__ import annotations

from pathlib import Path

import pytest

from hub.core.api import Job, JobPlan
from hub.modules.generate_image import build, routes
from tests.engine.helpers import FakeCtx, FakeEngine

KIND = "generate-image.image"


@pytest.fixture
def ctx(tmp_path: Path) -> FakeCtx:
    return FakeCtx("generate-image", tmp_path / "data", FakeEngine({"models": []}))


def queued(ctx: FakeCtx, seeds: list[int], kind: str = KIND) -> dict:
    job = Job(id=f"j_{len(ctx.jobs.jobs) + 1}", kind=kind, tool=kind.split(".")[0], state="queued",
              plan=JobPlan("image", "m1", ({},), {"model_id": "m1", "seeds": seeds}))
    ctx.jobs.jobs[job.id] = (job, {})
    return {"job": job.id, "kind": kind, "tool": job.tool, "params": {}}


@pytest.mark.parametrize("by", ["generate-image", "screen"])
async def test_a_generate_press_or_a_web_press_sets_the_seed_line(ctx: FakeCtx, by: str) -> None:
    await build.on_submitted(ctx, {**queued(ctx, [11, 12]), "by": by})
    assert routes.session_part(ctx)["last_seeds"] == {"model": "m1", "seeds": [11, 12]}


async def test_another_modules_submit_leaves_the_seed_line(ctx: FakeCtx) -> None:
    await build.on_submitted(ctx, {**queued(ctx, [11]), "by": "generate-image"})
    await build.on_submitted(ctx, {**queued(ctx, [99]), "by": "storyboard"})
    await build.on_submitted(ctx, {**queued(ctx, [98]), "by": None})
    await build.on_submitted(ctx, {**queued(ctx, [97], kind="other.image"), "by": "screen"})
    await build.on_submitted(ctx, {"job": "j_gone", "kind": KIND, "by": "screen"})
    assert routes.session_part(ctx)["last_seeds"] == {"model": "m1", "seeds": [11]}
