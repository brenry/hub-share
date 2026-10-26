"""Settings translation: a Generate payload -> JobPlan tasks -> what each engine flavour receives."""
from __future__ import annotations

from pathlib import Path

import pytest

from hub.core.api import Invalid
from hub.modules.generate_image import build, models
from hub.settings import DEFAULTS
from hub.worker import adapters, faults
from hub.worker.adapters import fork, tasks, upstream
from tests.engine.helpers import FakeCtx, FakeEngine, engine_task, load_catalog, write_lora

FLAVOURS = {"legacy": ("catalog_hp.json", "qwen_image_21", "qwen"),
            "upstream": ("catalog_upstream.json", "qwen_image_21_7B", "qwen21")}


@pytest.fixture(params=sorted(FLAVOURS))
async def ctx(request, tmp_path):
    name, qwen, qwen_key = FLAVOURS[request.param]
    loras = tmp_path / "loras"
    write_lora(loras / "flux2_klein_9b" / "grain.safetensors")
    write_lora(loras / "flux2_klein_9b" / "style" / "ink.safetensors")
    write_lora(loras / qwen_key / "q.safetensors")
    (tmp_path / "secret.safetensors").write_bytes(b"x")
    for n in ("r1", "r2", "r3", "r4"):
        (tmp_path / "data" / "outputs" / "day").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "outputs" / "day" / f"{n}.png").write_bytes(b"png")
    c = FakeCtx("generate-image", tmp_path / "data", FakeEngine(load_catalog(name, loras)))
    c.api, c.qwen = request.param, qwen
    await models.catalog(c)
    return c


def engine(request: dict) -> dict:
    """The engine task the worker's adapter makes of a plan's request, for the cached catalog's line."""
    return engine_task(request, models.cached())


def payload(**extra) -> dict:
    p = {"model": "flux2_klein_9b", "mode": "new", "prompt": "A grey cat\nunder a tree", "loras": [],
         "width": 1680, "height": 944, "images": 1, "steps": None, "guidance": None, "seed": {"mode": "random"}}
    p.update(extra)
    return p


def test_new_image_with_model_defaults(ctx):
    plan = build.image_job(payload(), ctx)
    assert plan.lane_kind == "image" and plan.model == "flux2_klein_9b" and len(plan.tasks) == 1
    t = engine(plan.tasks[0])
    assert t["num_inference_steps"] == 4 and "guidance_scale" not in t and "embedded_guidance_scale" not in t
    assert t["resolution"] == "1680x944" and t["image_mode"] == 1 and t["batch_size"] == 1
    assert t["video_prompt_type"] == "" and "image_refs" not in t and t["remove_background_images_ref"] == 0
    assert t["multi_prompts_gen_type"] == "FG" and t["prompt"] == "A grey cat\nunder a tree"
    assert 0 <= t["seed"] <= 999_999_999
    assert plan.summary["model"] == "Flux 2 Klein 9B" and plan.summary["count"] == 1


async def test_references(ctx):
    data = ctx.data_dir.parent / "outputs" / "day"
    refs = engine(build.image_job(payload(mode="refs", references=["out/day/r1.png", "out/day/r2.png"]), ctx).tasks[0])
    assert refs["video_prompt_type"] == "I" and refs["image_refs"] == [str(data / "r1.png"), str(data / "r2.png")]
    new = engine(build.image_job(payload(mode="new", references=["out/day/r1.png"]), ctx).tasks[0])
    assert "image_refs" not in new, "only the current mode's images are sent"
    uso = next(m for m in models.cached()["models"] if m["id"] == "flux_dev_uso")
    assert uso["ref_choices"] == ["KI", "KIJ"] and tasks.ref_letters(uso) == "KI", "the model's own choice"
    assert models.modes(uso) == ["refs"] and tasks.ref_letters({"ref_choices": []}) is None
    uso_ctx = FakeCtx("generate-image", ctx.data_dir.parent, FakeEngine({"models": [dict(uso, status="available")]}))
    await models.catalog(uso_ctx)
    plan = build.image_job(payload(model="flux_dev_uso", mode="refs", references=["out/day/r1.png"]), uso_ctx)
    task = engine(plan.tasks[0])
    assert task["video_prompt_type"] == "KI"


@pytest.mark.parametrize(("extra", "field", "text"), [
    ({"mode": "refs"}, "references", "Add at least one reference"),
    ({"mode": "refs", "references": [f"out/day/r{i}.png" for i in (1, 2, 3, 4)]}, "references",
     "Too many references for this model (4 of 3)"),
    ({"mode": "refs", "references": ["out/day/gone.png"]}, "references", "An image is missing; add it again"),
    ({"mode": "refs", "references": ["out/../../etc/passwd"]}, "references", "An image is missing; add it again"),
    ({"prompt": "   "}, "prompt", "Write a prompt"),
    ({"model": "nope"}, "model", "Choose a model"),
    ({"model": "flux_dev_umo"}, "model", "Choose a model"),
    ({"images": 7}, "images", "Choose 1 to 6 images"),
    ({"steps": 0}, "steps", "Steps must be 1 to 100"),
    ({"width": 100}, "width", "Choose a size"),
    ({"seed": {"mode": "fixed", "value": -1}}, "seed", "Seed must be 0 to 999,999,999"),
    ({"loras": [{"id": "flux2_klein_9b/../../secret.safetensors", "strength": 1}]}, "loras",
     'LoRA "flux2_klein_9b/../../secret.safetensors" was not found for this model'),
    ({"loras": [{"id": "z_image/grain.safetensors", "strength": 1}]}, "loras",
     'LoRA "z_image/grain.safetensors" was not found for this model'),
    ({"loras": [{"id": "flux2_klein_9b/grain.safetensors", "strength": 2.5}]}, "loras", "LoRA strength must be 0 to 2"),
])
def test_refusals_are_one_plain_line(ctx, extra, field, text):
    with pytest.raises(Invalid) as err:
        build.image_job(payload(**extra), ctx)
    assert (err.value.field, err.value.text) == (field, text)


def test_a_prompt_over_4000_goes_to_the_task_whole(ctx):
    task = engine(build.image_job(payload(prompt="x" * 4213), ctx).tasks[0])     # no cap of the Hub's
    assert task["prompt"] == "x" * 4213


def test_seeds_are_resolved_per_image(ctx):
    fixed = build.image_job(payload(images=3, seed={"mode": "fixed", "value": 123456}), ctx)
    assert [t["seed"] for t in fixed.tasks] == [123456, 123457, 123458] and fixed.summary["seeds"] == [123456, 123457,
                                                                                                        123458]
    random = build.image_job(payload(images=6), ctx)
    seeds = [t["seed"] for t in random.tasks]
    assert len(set(seeds)) == 6 and all(isinstance(s, int) and 0 <= s <= 999_999_999 for s in seeds)


def test_guidance_key_and_block_rounding(ctx):
    base = engine(build.image_job(payload(model="flux2_klein_base_9b"), ctx).tasks[0])
    assert base["guidance_scale"] == 4 and base["num_inference_steps"] == 30
    qwen = engine(build.image_job(payload(model=ctx.qwen, guidance=2.5, steps=20), ctx).tasks[0])
    assert qwen["guidance_scale"] == 2.5 and qwen["num_inference_steps"] == 20
    assert qwen["resolution"] == "1664x928", "Qwen 2.1 needs multiples of 32"


def test_loras_and_multipliers(ctx):
    stack = [{"id": "flux2_klein_9b/grain.safetensors", "strength": 0.8},
             {"id": "flux2_klein_9b/off.safetensors", "strength": 0},
             {"id": "flux2_klein_9b/grain.safetensors", "strength": 1.25}]
    t = engine(build.image_job(payload(loras=stack), ctx).tasks[0])
    assert t["activated_loras"] == ["grain.safetensors", "grain.safetensors"] and t["loras_multipliers"] == "0.8 1.25"
    sub = [{"id": "flux2_klein_9b/style/ink.safetensors", "strength": 1}]
    if ctx.api == "upstream":
        assert engine(build.image_job(payload(loras=sub), ctx).tasks[0])["activated_loras"] == ["style/ink.safetensors"]
    else:
        with pytest.raises(Invalid):
            build.image_job(payload(loras=sub), ctx)


def test_flavour_translation_keeps_the_forced_values(ctx, monkeypatch):
    plan = build.image_job(payload(loras=[{"id": "flux2_klein_9b/grain.safetensors", "strength": 0.8}]), ctx)
    keys = frozenset(engine(plan.tasks[0])) | set(upstream.FORCED_TASK)   # the check's own tests: test_upstream_rules
    monkeypatch.setattr(upstream, "accepted_names", lambda: keys)
    factory = {"num_inference_steps": 30, "guidance_scale": 5, "embedded_guidance_scale": 6.0, "flow_shift": 5.0,
               "resolution": "832x480", "multi_prompts_gen_type": 0, "remove_background_images_ref": 1,
               "prompt_enhancer": "T", "negative_prompt": "ugly"}
    sent = adapters.by_flavour(ctx.api).translate(engine(plan.tasks[0]), factory)
    if ctx.api == "legacy":
        assert sent["multi_prompts_gen_type"] == 2 and sent["flow_shift"] == 5.0
        assert sent["num_inference_steps"] == 4 and sent["remove_background_images_ref"] == 0
    else:
        assert sent == {**engine(plan.tasks[0]), **upstream.FORCED_TASK} and "flow_shift" not in sent
    assert sent["activated_loras"] == ["grain.safetensors"] and sent["loras_multipliers"] == "0.8"
    assert sent["prompt_enhancer"] == "" and sent["negative_prompt"] == "" and sent["alt_prompt"] == ""
    assert sent["output_filename"] == "{date}-{seed}", "whatever the engine's defaults say, nothing is added"
    nested = fork.translate({"activated_loras": ["style/ink.safetensors"]}, {})
    assert nested["activated_loras"] == ["ink.safetensors"]


def test_ui_models_from_the_catalog(ctx):
    ui = {m["id"]: m for m in (models.ui_model(m, models.ref_caps(ctx)) for m in models.cached()["models"])}
    assert ui["flux2_klein_9b"] == {"id": "flux2_klein_9b", "label": "Flux 2 Klein 9B", "family": "Flux 2",
                                    "modes": ["new", "refs"], "refCap": 3,
                                    "defaults": {"steps": 4, "guidance": None}, "guidanceKey": None,
                                    "kind": "image", "video": None, "budget": None, "lockSteps": False}
    assert ui["z_image"]["modes"] == ["new"] and ui["z_image"]["refCap"] == 0
    assert ui["flux_dev_umo"]["modes"] == ["refs"] and ui["flux_dev_umo"]["guidanceKey"] == "embedded_guidance_scale"
    assert ui[ctx.qwen]["refCap"] == 6 and ui["krea2_turbo_edit"]["refCap"] == 2
    assert ui["flux2_klein_base_9b"]["defaults"] == {"steps": 30, "guidance": 4}


def test_reference_caps_are_the_owners_table_and_a_pointer_takes_its_base_cap(ctx):
    caps = models.ref_caps(ctx)
    assert caps == DEFAULTS["modules"]["generate-image"]["ref_caps"], "settings.json holds the table, not the code"
    qwen = models.find(models.cached(), ctx.qwen)
    pointer = {**qwen, "id": "auto_my_qwen_tune", "base": ctx.qwen}
    assert models.ui_model(pointer, caps)["refCap"] == 6, "set up like Qwen: Qwen's cap"
    assert models.ui_model({**pointer, "base": None}, caps)["refCap"] == models.DEFAULT_REF_CAP
    assert models.ui_model(pointer, {**caps, ctx.qwen: 4})["refCap"] == 4, "the longest prefix wins"
    names = {k.rstrip("_") for k in caps} | {"qwen", "krea", "flux", "klein"}
    assert not [n for n in names if n in Path(models.__file__).read_text().lower()]


def test_failure_lines():
    class E:
        def __init__(self, message: str, stage: str | None = None) -> None:
            self.message, self.stage = message, stage
    assert faults.failure([E("Generation was cancelled", "cancelled")], False)["stage"] == "cancelled"
    assert faults.failure([E("CUDA out of memory. Tried 2 GiB", "generation")], False) == {
        "stage": "oom", "text": "Out of GPU memory"}
    assert faults.failure([E("bad thing\ntraceback...", "validation")], False) == {
        "stage": "generation", "text": "bad thing"}, "an engine's own stage word reads in the Hub's words"
    assert faults.failure([], False) == {"stage": "generation", "text": "The engine could not make the image"}
