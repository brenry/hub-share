"""The plan before the render. The adapter reduces the engine's preflight report; an engine without a
preflight, or one that raises, gives one error line; a continued clip's note; the fork's line; the worker's query;
the assistant's settings view carries `plan` on a video model with a draft, and the build's refusal as its one error."""
from __future__ import annotations

import sys
import types

from hub.worker.adapters import fork, plan, upstream
from tests.engine.test_generate_image import box, call
from tests.engine.test_upstream_rules import REF2VA, SPEECH, cat, ref_ctx  # noqa: F401

REPORT = {"valid": True, "diagnostics": [
    {"severity": "warning", "task": 0, "message": "3 windows are planned where 2 would cover 243 frames."},
    {"severity": "error", "task": 0, "message": "LoRAs not found in this model's catalog: ['x']"}],
    "tasks": [{"index": 0, "requested_video": {"frames": 243, "fps": 24.0, "duration_seconds": 10.125},
               "window_plan": {"windows": [
                   {"window": 1, "generated_frames": 124, "generated_seconds": 5.167, "new_frames": 124,
                    "pictures": ["<Picture 1> (Character 7.png)"], "prompt": "..."},
                   {"window": 2, "generated_frames": 124, "generated_seconds": 5.167, "new_frames": 107,
                    "new_shot": True, "pictures": [], "prompt": "..."}],
                   "total_frames": 231, "total_seconds": 9.625,
                   "note": "The output follows this plan: each window is rounded to the model's frame steps."},
               "checks_unavailable": []}],
    "limitations": ["Snapshot only"]}


def test_the_report_is_reduced_to_windows_warnings_errors_and_notes():
    out = plan.reduce(REPORT)
    assert out["valid"] is False, "an error makes the plan invalid even when the engine says valid"
    seen = [(w["n"], w["frames"], w["seconds"], w["new_frames"], w["new_shot"], w["pictures"]) for w in out["windows"]]
    assert seen == [(1, 124, 5.167, 124, False, ["<Picture 1> (Character 7.png)"]), (2, 124, 5.167, 107, True, [])]
    assert out["total_seconds"] == 9.625
    assert out["warnings"] == ["3 windows are planned where 2 would cover 243 frames."]
    assert out["errors"] == ["LoRAs not found in this model's catalog: ['x']"]
    assert out["notes"] == ["The output follows this plan: each window is rounded to the model's frame steps."]
    assert plan.reduce({}) == {"valid": False, "windows": [], "warnings": [], "errors": [], "notes": []}


def fake_preflight(monkeypatch, fn):
    shared = types.ModuleType("shared")
    mcp = types.ModuleType("shared.mcp")
    pre = types.ModuleType("shared.mcp.preflight")
    pre.preflight = fn
    shared.mcp, mcp.preflight = mcp, pre
    for name, module in (("shared", shared), ("shared.mcp", mcp), ("shared.mcp.preflight", pre)):
        monkeypatch.setitem(sys.modules, name, module)


def test_the_engine_is_asked_with_the_task_as_it_is_and_the_identity_prepare(monkeypatch):
    seen = {}

    def preflight(session, prepare, post, settings=None, media=None, process=None, parameters=None, detail="summary"):
        seen.update(session=session, prepared=prepare(settings), detail=detail)
        return REPORT
    fake_preflight(monkeypatch, preflight)
    out = plan.plan("S", {"model_type": REF2VA, "prompt": "x", "image_prompt_type": ""})
    assert seen == {"session": "S", "prepared": {"model_type": REF2VA, "prompt": "x", "image_prompt_type": ""},
                    "detail": "summary"}
    assert len(out["windows"]) == 2 and out["errors"]


def test_no_preflight_or_a_raise_is_one_line_and_a_continue_gets_the_note(monkeypatch):
    monkeypatch.setitem(sys.modules, "shared.mcp.preflight", None)
    assert plan.plan("S", {"model_type": REF2VA}) == {"valid": False, "windows": [], "warnings": [],
                                                      "errors": [plan.NO_PREFLIGHT], "notes": []}
    fake_preflight(monkeypatch, lambda *a, **k: (_ for _ in ()).throw(ValueError("resolution 1x1 is below")))
    assert plan.plan("S", {"model_type": REF2VA})["errors"] == ["resolution 1x1 is below"]
    later = ("The window plan of a continued video depends on its retained source frames and is resolved during "
             "generation.")
    fake_preflight(monkeypatch, lambda *a, **k: {"valid": True, "diagnostics": [], "tasks": [
        {"index": 0, "checks_unavailable": [later]}]})
    out = plan.plan("S", {"model_type": REF2VA, "image_prompt_type": "V"})
    assert out["windows"] == [] and out["errors"] == [] and plan.LATER in out["notes"]


def test_the_fork_has_no_preflight():
    assert fork.Fork.plan("S", {})["errors"] == [plan.NO_PREFLIGHT]
    assert upstream.Upstream.plan is plan.plan


SCREEN = {"model": REF2VA, "aspect": "16:9", "size": 1, "images": 1, "lorasByModel": {}, "advancedByModel": {}}


async def test_the_settings_view_plans_the_draft_on_a_video_model(ref_ctx):  # noqa: F811
    ctx = ref_ctx
    ctx.doc("draft", {}).replace(SCREEN)
    box(ctx, "", [{"id": "chars/Character 11.png", "w": 1000, "h": 560}])
    assert "plan" not in await call(ctx, "get_generate_image_settings", {}), "no draft: no plan"
    box(ctx, "a fox at dawn", [{"id": "chars/Character 11.png", "w": 1000, "h": 560}])
    ctx.engine.plan = {"valid": True, "windows": [{"n": 1, "frames": 124, "seconds": 5.167, "new_frames": 124,
                                                   "new_shot": False, "pictures": []}],
                       "total_seconds": 5.167, "warnings": [], "errors": [], "notes": []}
    seen = await call(ctx, "get_generate_image_settings", {})
    assert seen["plan"] == ctx.engine.plan and ctx.engine.planned[-1]["kind"] == "video"
    ctx.engine.plan = RuntimeError("The engine stopped")
    assert (await call(ctx, "get_generate_image_settings", {}))["plan"]["errors"] == ["The engine stopped"]
    box(ctx, "Prompt 1", [{"id": "chars/Gone.png", "w": 1000, "h": 560}])  # a draft the build refuses: its one error
    refused = (await call(ctx, "get_generate_image_settings", {}))["plan"]
    assert refused["windows"] == [] and len(refused["errors"]) == 1 and ctx.engine.planned[-1]["prompt"] != "Prompt 1"
    ctx.doc("draft", {}).replace({**SCREEN, "model": SPEECH})
    box(ctx, "Stay right there!", [{"id": "chars/Character 11.png", "w": 1000, "h": 560}])
    assert "plan" not in await call(ctx, "get_generate_image_settings", {}), "a line has no windows to plan"


async def test_a_clip_press_is_planned_before_it_runs_and_a_planned_error_refuses_it(ref_ctx):  # noqa: F811
    from hub.modules.generate_image import build
    ctx = ref_ctx
    ctx.jobs.builders["image"] = build.image_job
    press = {"model": REF2VA, "mode": "refs", "prompt": "<Picture 1> waves", "loras": [], "images": 1,
             "width": 960, "height": 544, "steps": None, "guidance": None, "seed": {"mode": "random"},
             "references": ["chars/Character 11.png"]}
    ctx.engine.plan = {"valid": True, "windows": [{"n": 1, "frames": 124, "seconds": 5.167, "new_frames": 124,
                                                   "new_shot": False, "pictures": []}],
                       "total_seconds": 5.167, "warnings": ["Fewer, longer windows usually flow better."],
                       "errors": [], "notes": []}
    job = ctx.jobs.submit("image", press)
    await build.on_submitted(ctx, {"job": job.id, "kind": "generate-image.image", "tool": "generate-image",
                                   "by": "screen"})
    assert job.notes["plan"] == ctx.engine.plan and job.state == "queued", "a warning never refuses"
    ctx.engine.plan = {**ctx.engine.plan, "valid": False, "errors": ["resolution 9x9 is below the model's minimum"]}
    bad = ctx.jobs.submit("image", press)
    await build.on_submitted(ctx, {"job": bad.id, "kind": "generate-image.image", "tool": "generate-image",
                                   "by": "screen"})
    assert (bad.state, bad.error) == ("failed", "resolution 9x9 is below the model's minimum")
    ctx.engine.plan = RuntimeError("The engine stopped")
    asked = ctx.jobs.submit("image", press)
    await build.on_submitted(ctx, {"job": asked.id, "kind": "generate-image.image", "tool": "generate-image",
                                   "by": "screen"})
    assert asked.state == "queued" and asked.notes["plan"]["notes"] == ["The engine stopped"], "it runs anyway"
    ctx.settings = {**ctx.settings, "plan_before_render": False}
    off = ctx.jobs.submit("image", press)
    await build.on_submitted(ctx, {"job": off.id, "kind": "generate-image.image", "tool": "generate-image",
                                   "by": "screen"})
    assert "plan" not in off.notes, "the setting off asks nothing"
