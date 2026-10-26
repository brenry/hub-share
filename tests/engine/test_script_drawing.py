"""The sketch panels drawn one picture job at a time (`hub/modules/director/drawing.py`, Generate's
`tools.sketch_plan`): with a stand-in jobs book, bus and `sketch` service, one job for the first panel and no second
while it runs; its finish writes the picture and the next is queued; a failed panel waits for the next tool write; a
refused service queues nothing and `script_read` says why; a finish for a panel dropped meanwhile writes nothing. The
plan: the pulldown's picture model, else the last picture model picked; never a video model; 16:9, no reference, no
LoRA, the model's steps; Generate's draft only read."""
from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hub.core.api import Invalid, PictureRequest
from hub.modules.director import drawing, mix, panels, track
from hub.modules.generate_image import models, routes, screen
from hub.modules.generate_image import tools as generate
from hub.worker.enginewire import request_parse
from tests.engine.helpers import FakeCtx, FakeEngine, load_catalog
from tests.engine.test_media_characters import png_bytes
from tests.engine.test_script_tools import Ctx, call, framed, on_disk

NO_MODEL = "Pick a picture model in Generate"


class Jobs:
    """The core's book, faked: a submit builds the `panel` kind's plan (its refusal raised), keeps the job queued."""

    def __init__(self, ctx: Any) -> None:
        self.ctx, self.made, self.book = ctx, [], {}

    def submit(self, kind: str, params: dict) -> Any:
        build = {track.KIND: track.job, mix.KIND: mix.job}.get(kind, drawing.job)    # the lock presses
        plan = build(copy.deepcopy(params), self.ctx)
        job = SimpleNamespace(id=f"j{len(self.made) + 1}", kind=f"director.{kind}", state="queued", error=None,
                              plan=plan, params=params)
        self.made.append(job)
        self.book[job.id] = job
        return job

    def get(self, job_id: str) -> Any:
        return self.book.get(job_id)


class DrawCtx(Ctx):
    def __init__(self, tmp: Path) -> None:
        super().__init__(tmp)
        self.jobs = Jobs(self)
        self.sketched: list[str] = []
        self.refusal: str | None = None

    def service(self, name: str) -> Any:
        if name == "sketch":
            return self._sketch
        return super().service(name)

    def _sketch(self, prompt: str) -> Any:
        if self.refusal is not None:
            raise Invalid("model", self.refusal)
        self.sketched.append(prompt)
        return ("plan", prompt)


@pytest.fixture
async def ctx(tmp_path: Path) -> Any:
    await drawing.stop()
    drawing.waiting.clear()
    drawing.failed.clear()
    yield DrawCtx(tmp_path)
    await drawing.stop()


def finished(ctx: DrawCtx, state: str, *outputs: str) -> dict:
    job = ctx.jobs.made[-1]
    job.state = state
    for item in outputs:                     # the pictures land in Temp (a gone one is drawn again)
        path = ctx.files.roots["out"].joinpath(*item.split("/")[1:])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png_bytes())
    return {"job": job.id, "kind": job.kind, "tool": "director", "state": state, "outputs": list(outputs),
            "notes": {}}


def picture(ctx: DrawCtx, ident: str) -> Any:
    return panels.find(on_disk(ctx), ident)[2]["picture"]


async def test_one_job_at_a_time_and_its_picture_written(ctx: DrawCtx) -> None:
    await framed(ctx)
    await drawing.step(ctx)
    [job] = ctx.jobs.made
    assert job.params["script"] == "Script 1" and job.params["panel"] == "f1" and \
        job.plan == ("plan", job.params["prompt"])
    assert job.params["prompt"].startswith("Wide shot of the stage. ")
    assert job.params["prompt"].endswith(". Character 7 stand. Character 6 stand."), "no style sentence"
    await drawing.step(ctx)
    assert len(ctx.jobs.made) == 1, "no second while it runs"
    assert (await call(ctx, "script_read", {}))["read"][-2:] == [
        "f1 panel s1 0.00 (script 0.00) · drawing", "f2 panel s2 0.00 (script 1.00) · waiting"]
    sent = len(ctx.bus.sent)
    await drawing.on_finished(ctx, finished(ctx, "done", "out/2026-10-19/f1.png"))
    assert picture(ctx, "f1") == "out/2026-10-19/f1.png" and len(ctx.bus.sent) == sent + 1
    assert ctx.bus.sent[-1][:2] == ("changed", "changed") and ctx.bus.sent[-1][2]["name"] == "Script 1"
    await drawing.step(ctx)
    assert [j.params["panel"] for j in ctx.jobs.made] == ["f1", "f2"]


async def test_the_loop_wakes_on_start_on_a_write_and_on_a_finish(ctx: DrawCtx, monkeypatch: Any) -> None:
    monkeypatch.setattr(drawing, "ON_HOLD", False)              # sketches on hold; the loop tested off it
    await framed(ctx)
    await drawing.start(ctx)

    async def until(n: int) -> None:
        for _ in range(200):
            if len(ctx.jobs.made) >= n:
                return
            await asyncio.sleep(0.01)
        raise AssertionError(f"{n} jobs never queued")

    await until(1)
    await drawing.on_finished(ctx, finished(ctx, "done", "out/2026-10-19/f1.png"))
    await until(2)
    await call(ctx, "shot_add", {"scene": 1, "camera": "Close on Character 7"})
    await drawing.on_finished(ctx, finished(ctx, "done", "out/2026-10-19/f2.png"))
    await until(3)
    assert [j.params["panel"] for j in ctx.jobs.made] == ["f1", "f2", "f3"]
    assert ctx.jobs.made[-1].params["prompt"].startswith("Close on Character 7. ")


async def test_a_failed_panel_waits_for_the_next_tool_write(ctx: DrawCtx) -> None:
    await framed(ctx)
    await drawing.step(ctx)
    ctx.jobs.made[0].error = "Out of memory"
    await drawing.on_finished(ctx, finished(ctx, "failed"))
    assert picture(ctx, "f1") is None
    await drawing.step(ctx)
    await drawing.on_finished(ctx, finished(ctx, "done", "out/2026-10-19/f2.png"))
    await drawing.step(ctx)
    assert [j.params["panel"] for j in ctx.jobs.made] == ["f1", "f2"], "not again at once"
    read = (await call(ctx, "script_read", {}))["read"]
    assert read[-2] == "f1 panel s1 0.00 (script 0.00) · waiting: Out of memory"
    await call(ctx, "cue_add", {"shot": "s1", "cue": "effect", "words": "A door"})
    await drawing.step(ctx)
    assert [j.params["panel"] for j in ctx.jobs.made] == ["f1", "f2", "f1"]


async def test_the_service_refusing_queues_nothing_and_read_says_why(ctx: DrawCtx) -> None:
    await framed(ctx)
    ctx.refusal = NO_MODEL
    await drawing.step(ctx)
    assert ctx.jobs.made == [] and [p["id"] for _, _, p in panels.panels(on_disk(ctx))] == ["f1", "f2"]
    read = (await call(ctx, "script_read", {}))["read"]
    assert read[-2:] == [f"f1 panel s1 0.00 (script 0.00) · waiting: {NO_MODEL}",
                         f"f2 panel s2 0.00 (script 1.00) · waiting: {NO_MODEL}"]
    ctx.refusal = None
    await call(ctx, "cue_add", {"shot": "s1", "cue": "effect", "words": "A door"})
    await drawing.step(ctx)
    assert [j.params["panel"] for j in ctx.jobs.made] == ["f1"]


async def test_a_finish_for_a_panel_dropped_meanwhile_writes_nothing(ctx: DrawCtx) -> None:
    await framed(ctx)
    await call(ctx, "pose_add", {"shot": "s1", "character": "Character 6", "pose": "sit", "start_ms": 500})
    await drawing.step(ctx)
    await drawing.on_finished(ctx, finished(ctx, "done", "out/2026-10-19/f1.png"))
    await drawing.step(ctx)
    assert ctx.jobs.made[-1].params["panel"] == "f2"
    await call(ctx, "event_remove", {"id": "p5"})
    path = ctx.files.roots["scripts"] / "Script 1.json"
    before, sent = path.read_bytes(), len(ctx.bus.sent)
    await drawing.on_finished(ctx, finished(ctx, "done", "out/2026-10-19/f2.png"))
    assert path.read_bytes() == before and len(ctx.bus.sent) == sent
    assert panels.find(on_disk(ctx), "f2") is None


# ---------------------------------------------------------------- Generate's `sketch` service
@pytest.fixture
async def gen(tmp_path: Path) -> FakeCtx:
    cat = load_catalog("catalog_upstream.json", tmp_path / "loras")
    clip = next(m for m in cat["models"] if m["id"] == "flux2_klein_4b")
    cat["models"].append({**copy.deepcopy(clip), "id": "a_clip", "name": "A clip", "kind": "video"})
    next(m for m in cat["models"] if m["id"] == "z_image")["budget"] = 600_000
    c = FakeCtx("generate-image", tmp_path / "data", FakeEngine(cat))
    await models.catalog(c)
    return c


def draft(c: FakeCtx, **value: Any) -> dict:
    c.doc(routes.DRAFT, {}).replace(value)
    return copy.deepcopy(value)


def test_the_pulldowns_picture_model_with_no_lora_and_its_own_steps(gen: FakeCtx) -> None:
    held = draft(gen, model="flux2_klein_9b", lastModel={"image": "z_image", "video": "a_clip"},
                 lorasByModel={"flux2_klein_9b": [{"id": "grain", "strength": 1.0}]},
                 advancedByModel={"flux2_klein_9b": {"steps": 12}}, aspect="1:1", size=4)
    plan = generate.sketch_plan(gen, "A bare stage. pencil sketch")
    assert plan.model == "flux2_klein_9b" and len(plan.tasks) == 1 and plan.lane_kind == "image"
    s = plan.summary
    assert (s["mode"], s["count"], s["loras"], s["prompt"]) == ("new", 1, [], "A bare stage. pencil sketch")
    assert s["steps"] == 4, "the model's default steps, not the draft's"
    assert (s["width"], s["height"]) == generate.SKETCH == (576, 320), "no budget, the sketch size"
    task = plan.tasks[0]
    assert type(request_parse(task)) is PictureRequest and task["references"] == [] and task["loras"] == []
    assert gen.doc(routes.DRAFT, {}).get() == held and gen.doc(routes.DRAFT, {}).writes == 1, "only read"


def test_else_the_last_picture_model_within_its_budget(gen: FakeCtx) -> None:
    draft(gen, model="a_clip", lastModel={"image": "z_image", "video": "a_clip"})
    plan = generate.sketch_plan(gen, "x")
    assert plan.model == "z_image" and (plan.summary["width"], plan.summary["height"]) == (576, 320), \
        "a budget above 576x320 leaves the sketch size"


def test_a_small_budget_shrinks_the_sketch_never_above_it(gen: FakeCtx) -> None:
    next(m for m in models.cached()["models"] if m["id"] == "z_image")["budget"] = 150_000
    draft(gen, model="z_image")
    s = generate.sketch_plan(gen, "x").summary
    assert (s["width"], s["height"]) == (512, 288) and s["width"] * s["height"] <= 150_000
    assert s["width"] % 16 == 0 and s["height"] % 16 == 0 and s["width"] <= 576 and s["height"] <= 320


def test_generates_own_canvas_is_unchanged(gen: FakeCtx) -> None:
    model = models.find(models.cached(), "flux2_klein_9b")
    assert screen.canvas("16:9", screen.MEGAPIXELS[0], [], model) == (1360, 768), "Generate's menu"


@pytest.mark.parametrize("value", [
    {"model": "a_clip", "lastModel": {"image": "", "video": "a_clip"}},
    {"model": "a_clip", "lastModel": {"image": "flux"}},        # a picture model whose files are not there
    {},
])
def test_a_video_only_pick_is_refused(gen: FakeCtx, value: dict) -> None:
    draft(gen, **value)
    with pytest.raises(Invalid) as e:
        generate.sketch_plan(gen, "x")
    assert e.value.text == NO_MODEL
