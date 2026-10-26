"""A video model in the Generate Image screen: the bar's model (kind, video facts, its pictures, no guidance), the
canvas as a tier, count 1, the clip length on the lattice, one-line refusals, and the one engine task a clip is.
The catalog entries are the real worker's answer for the fake engine's H3-like definitions."""
from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.core.features import tools_of
from hub.modules.generate_image import build, manifest, models, routes, screen, tools
from tests.engine.helpers import (
    ENGINE_PYTHON,
    WORKER,
    FakeCtx,
    FakeEngine,
    FakeJobs,
    engine_task,
    load_catalog,
    make_engine_root,
    write_lora,
)

PRUNED, FUSED = "minimax_h3", "minimax_h3_fused_turbo"
LABEL = "H3 First / Last — Pruned"


def engine(request: dict) -> dict:
    """The engine task the worker's adapter makes of a plan's request."""
    return engine_task(request, models.cached())


@pytest.fixture(scope="module")
def clip_models(tmp_path_factory) -> list[dict]:
    base = tmp_path_factory.mktemp("engine")
    root = make_engine_root(base, "legacy")
    write_lora(root / "loras" / "minimax_h3" / "turbo.safetensors")
    out = base / "catalog.json"
    subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--dump-catalog", str(out)],
                   check=True, capture_output=True, timeout=60)
    return [m for m in json.loads(out.read_text())["models"] if m["kind"] == "video"]


class Bus:
    def publish(self, *args: Any, **kwargs: Any) -> None:
        pass

    def presence(self) -> dict:
        return {"screens": {"workspace": 1}}


@pytest.fixture
async def ctx(tmp_path, clip_models):
    cat = load_catalog("catalog_upstream.json", tmp_path / "loras")
    cat["models"] += clip_models
    c = FakeCtx("generate-image", tmp_path / "data", FakeEngine(cat))
    c.bus = Bus()
    await models.catalog(c)
    return c


def entry(model_id: str) -> dict:
    return models.find(models.cached(), model_id)


def test_the_bar_sees_a_video_model(ctx):
    ui = models.ui_model(entry(PRUNED), models.ref_caps(ctx))
    assert (ui["kind"], ui["refCap"], ui["guidanceKey"], ui["modes"]) == ("video", 2, None, ["new", "refs"])
    assert ui["defaults"] == {"steps": 20, "guidance": None} and ui["label"] == LABEL
    assert set(ui["video"]) == {"fps", "frames", "steps", "tiers", "text_encoders", "text_encoder_default",
                                "text_encoder_names", "text_encoders_found", "references", "one_pass", "continues",
                                "overlap"}
    assert (ui["video"]["continues"], ui["video"]["overlap"]) == (True, 18), "passed through from the catalog"
    assert ui["video"]["one_pass"] == {"minimax_h3_multi_window": False}, "the switch that keeps a clip one pass"
    assert ui["video"]["frames"] == {"min": 124, "step": 17, "max": 345, "default": 124}
    assert [t["name"] for t in ui["video"]["tiers"]] == ["540p", "720p"], "the tiers the size menu offers"
    assert ui["video"]["tiers"][0]["sizes"]["16:9"] == [960, 544]
    assert models.ui_model(entry(FUSED), {})["defaults"]["steps"] == 4
    old = models.ui_model(entry("flux2_klein_9b"), {})
    assert (old["kind"], old["video"]) == ("image", None), "an entry from before `kind` is a picture model"
    odd = {**entry(PRUNED), "video": {**entry(PRUNED)["video"], "tiers": [
        {"name": n, "sizes": {"1:1": [32, 32]}} for n in ("a", "b", "c", "d")]}}
    assert [t["name"] for t in models.video(odd)["tiers"]] == ["a", "b", "c"], "no offered name: the first three"


@pytest.mark.parametrize(("aspect", "mp", "size"), [
    ("16:9", 1, (960, 544)), ("16:9", 1.5, (1280, 704)), ("9:16", 2, (704, 1280)), ("16:9", 4, (1280, 704)),
    ("3:2", 1, (896, 576)), ("auto", 1, (736, 736)), ("4:3", 2, (928, 704))])
def test_canvas_is_the_tier_the_megapixels_pick(ctx, aspect, mp, size):
    assert screen.canvas(aspect, mp, [], entry(PRUNED)) == size


def test_a_third_tier_takes_four_megapixels(ctx):
    ctx.settings["video_tiers"] = ["540p", "720p", "1080p"]
    assert screen.canvas("16:9", 4, [], entry(PRUNED)) == (1920, 1088)
    assert screen.canvas("16:9", 1, [], entry(PRUNED)) == (960, 544)
    assert screen.canvas("16:9", 1.5, [], None) == (1680, 944), "a picture's canvas is unchanged"


def saved(ctx, **extra) -> None:
    ctx.doc("draft", {}).replace({"model": PRUNED, "aspect": "16:9", "size": 2, "images": 4, **extra})


@pytest.mark.parametrize(("frames", "want"), [(130, 141), (141, 141), (1000, 345), (10, 124), ("x", 124)])
async def test_view_reports_one_clip_of_the_cards_length(ctx, frames, want):
    saved(ctx, advancedByModel={PRUNED: {"frames": frames, "seed": {"mode": "fixed", "value": 3}}})
    seen = await tools.read_settings(ctx)
    assert (seen["model"], seen["width"], seen["height"], seen["count"]) == (PRUNED, 1280, 704, 1)
    assert seen["frames"] == want and seen["seconds"] == round(want / 24, 2) and seen["guidance"] is None
    assert seen["seed"] == "3" and seen["steps"] == 20


async def test_apply_keeps_a_clip_to_one_and_the_length_on_the_lattice(ctx):
    saved(ctx, advancedByModel={PRUNED: {"frames": 130}})
    after = await tools.write_settings(ctx, {"steps": 30, "count": 1, "megapixels": 1})
    assert (after["steps"], after["count"], after["frames"], after["width"]) == (30, 1, 141, 960)
    draft = ctx.doc("draft", {}).get()
    assert draft["images"] == 4, "the pictures' count is kept for the picture models"
    want = {"frames": 141, "steps": 30, "guidance": None, "seed": {"mode": "random"}}
    assert draft["advancedByModel"][PRUNED] == want, "the card's length is kept, snapped onto the lattice"
    ctx.doc("draft", {}).patch({"model": FUSED})                          # another clip model picked
    fused = await tools.write_settings(ctx, {"steps": 6})
    assert (fused["model"], fused["steps"], fused["frames"]) == (FUSED, 6, 243)


@pytest.mark.parametrize(("model", "args", "field", "text"), [
    (PRUNED, {"count": 3}, "count", f"{LABEL} makes one clip at a time"),
    (PRUNED, {"guidance": 3}, "guidance", f"{LABEL} has no guidance setting"),
    (FUSED, {"steps": 12}, "steps", "steps must be a whole number from 4 to 8"),
])
async def test_apply_refuses_what_a_clip_cannot_take(ctx, model, args, field, text):
    saved(ctx, model=model)
    before = ctx.doc("draft", {}).get()
    with pytest.raises(Invalid) as err:
        await tools.write_settings(ctx, args)
    assert (err.value.field, err.value.text) == (field, text) and ctx.doc("draft", {}).get() == before


def payload(**extra) -> dict:
    p = {"model": PRUNED, "mode": "new", "prompt": "integrated_multimodal_description: [Shot 1] A lighthouse.",
         "loras": [], "width": 960, "height": 544, "images": 4, "steps": None, "guidance": None,
         "seed": {"mode": "fixed", "value": 7}, "frames": 130}
    p.update(extra)
    return p


def test_a_clip_is_one_task_key_by_key(ctx):
    plan = build.image_job(payload(), ctx)
    assert (plan.lane_kind, plan.model, len(plan.tasks)) == ("image", PRUNED, 1)
    assert engine(plan.tasks[0]) == {
        "model_type": PRUNED, "image_mode": 0, "prompt": payload()["prompt"], "resolution": "960x544",
        "video_length": 141, "sliding_window_size": 141, "minimax_h3_multi_window": False,
        "num_inference_steps": 20, "seed": 7, "batch_size": 1, "multi_prompts_gen_type": "FG",
        "image_prompt_type": "", "video_prompt_type": "", "minimax_h3_text_encoder": "nvfp4_awq"}
    s = plan.summary
    assert (s["kind"], s["frames"], s["seconds"], s["count"], s["seeds"]) == ("clip", 141, 5.88, 1, [7])
    assert (s["width"], s["height"], s["model"], s["steps"], s["guidance"]) == (960, 544, LABEL, 20, None)
    assert "last_seeds" not in routes.session_part(ctx), "the builder alone keeps none (F1: `on_submitted` does)"


def test_a_clip_length_comes_from_the_card_when_the_press_has_none(ctx):
    assert engine(build.image_job(payload(frames=None), ctx).tasks[0])["video_length"] == 124, "the model's default"
    saved(ctx, advancedByModel={PRUNED: {"frames": 200}})
    assert engine(build.image_job(payload(frames=None), ctx).tasks[0])["video_length"] == 209
    fused = engine(build.image_job(payload(model=FUSED, frames=None, steps=None), ctx).tasks[0])
    assert (fused["video_length"], fused["num_inference_steps"]) == (243, 4)


def test_loras_only_when_active(ctx):
    lora = {"id": "minimax_h3/turbo.safetensors", "strength": 0.8}
    task = engine(build.image_job(payload(loras=[lora]), ctx).tasks[0])
    assert task["activated_loras"] == ["turbo.safetensors"] and task["loras_multipliers"] == "0.8"
    assert "activated_loras" not in engine(build.image_job(payload(loras=[{**lora, "strength": 0}]), ctx).tasks[0])


@pytest.mark.parametrize(("extra", "field", "text"), [
    ({"mode": "refs"}, "references", "Add at least one reference"),
    ({"mode": "refs", "references": ["out/a.png", "out/b.png", "out/c.png"]}, "references",
     "Too many references for this model (3 of 2)"),
    ({"mode": "edit"}, "mode", "Choose New or References"),
    ({"width": 1024, "height": 1024}, "width", "Choose a size the model can make"),
    ({"width": 1920, "height": 1088}, "width", "Choose a size the model can make"),
    ({"frames": 100}, "frames", "Choose 124 to 345 frames"),
    ({"frames": 346}, "frames", "Choose 124 to 345 frames"),
    ({"steps": 0}, "steps", "Steps must be 1 to 50"),
    ({"model": FUSED, "steps": 12}, "steps", "Steps must be 4 to 8"),
    ({"model": FUSED, "loras": [{"id": "minimax_h3/turbo.safetensors", "strength": 1}]}, "loras",
     'LoRA "minimax_h3/turbo.safetensors" was not found for this model'),
    ({"prompt": " "}, "prompt", "Write a prompt"),
    ({"seed": {"mode": "fixed", "value": -1}}, "seed", "Seed must be 0 to 999,999,999"),
])
def test_a_clip_refuses_in_one_line(ctx, extra, field, text):
    with pytest.raises(Invalid) as err:
        build.image_job(payload(**extra), ctx)
    assert (err.value.field, err.value.text) == (field, text)


async def test_generate_image_renders_one_clip_with_the_unchanged_tools(ctx):
    ctx.jobs = FakeJobs(ctx, {"image": manifest.MODULE.jobs["image"]})
    saved(ctx, size=1, advancedByModel={PRUNED: {"frames": 150}})
    routes.session_part(ctx)["draft"] = "integrated_multimodal_description: [Shot 1] Waves."
    assert await tools.generate_image(ctx, {}) == {"state": "queued"}
    [(job, params)] = ctx.jobs.jobs.values()
    assert (params["width"], params["height"], params["images"], params["frames"]) == (960, 544, 1, 158)
    assert job.kind == "image" and job.plan.summary["kind"] == "clip" and len(job.plan.tasks) == 2
    assert job.plan.takes == (((1,), (2,)),), "take 1 and its re-take"
    assert [a.name for a in manifest.MODULE.actions] == ["generate_image", "direct_clip",
                                                         "direct_scene", "redo_shot"]
    assert [s.name for s in screen.SETTINGS] == ["draft", "shot", "steps", "guidance", "megapixels", "aspect", "count",
                                                 "seed", "loras"]


@pytest.mark.parametrize(("saved_as", "sent"), [(None, "nvfp4_awq"), ("gguf_q2_k", "gguf_q2_k"), ("int8", "int8"),
                                                ("gone", "nvfp4_awq")])
def test_a_clip_takes_the_cards_text_encoder_else_the_definitions(ctx, saved_as, sent):
    saved(ctx, advancedByModel={PRUNED: {"text_encoder": saved_as} if saved_as else {}})
    assert engine(build.image_job(payload(), ctx).tasks[0])["minimax_h3_text_encoder"] == sent


async def test_the_text_encoder_is_the_cards_alone_never_a_tool_setting(ctx):
    """The tools neither report nor set a clip's text encoder: the six tools' schema is as it was."""
    saved(ctx, model=PRUNED)
    seen = await tools.read_settings(ctx)
    assert "text_encoder" not in seen and "text_encoders" not in seen
    setter = next(t for t in tools_of(manifest.MODULE) if t.name == "set_generate_image_settings")
    assert "text_encoder" not in setter.input_schema["properties"]
    assert "text_encoder" not in (ctx.doc("draft", {}).get().get("advancedByModel") or {}).get(PRUNED, {})


