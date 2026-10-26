"""A clip model's pictures (Stage 4): the catalog names each model's role from its definition (a start frame, or
identities up to the engine's cap), the bar's caps and modes follow it, the boxes are set by character name, Auto
follows a start frame, and the clip task carries box 1 as `image_start` or every box in the reference list, with
absolute paths. The catalog entries are the real worker's answer for the fake engine's H3-like definitions."""
from __future__ import annotations

import copy
import functools
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.core.files import Files
from hub.modules.generate_image import build, cast, manifest, models, routes, tools
from hub.worker import catalogvideo
from hub.worker.adapters.fork import FAMILIES as KEYS
from tests.engine.helpers import (
    ENGINE_PYTHON,
    WORKER,
    FakeCtx,
    FakeEngine,
    FakeJobs,
    engine_task,
    load_catalog,
    make_engine_root,
)

PRUNED, OMNI, TEXT, START = "minimax_h3", "minimax_h3_ref2va", "text_only", "start_only"
LABEL, OMNI_LABEL = "H3 First / Last — Pruned", "H3 Omni — Pruned"
CAST = {"Character 11.png": (1000, 560), "Character 4.png": (600, 900), "Character 12.png": (64, 64),
        "Character 13.png": (64, 64)}
PROMPT = "integrated_multimodal_description: [Shot 1] A lighthouse."


def engine(request: dict) -> dict:
    """The engine task the worker's adapter makes of a plan's request."""
    return engine_task(request, models.cached())


@pytest.fixture(scope="module")
def clip_models(tmp_path_factory) -> list[dict]:
    base = tmp_path_factory.mktemp("engine")
    root = make_engine_root(base, "legacy")
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
    pruned = next(m for m in clip_models if m["id"] == PRUNED)
    text = {**copy.deepcopy(pruned), "id": TEXT, "name": "Text Only"}
    text["video"]["references"] = None                     # a clip model that takes no picture
    start = {**copy.deepcopy(pruned), "id": START, "name": "Start Only"}
    start["video"]["references"] = {"role": "start", "min": 0, "max": 1, "end": False}   # no "E"
    cat["models"] += [*clip_models, text, start]
    cat["engine"]["api"] = "legacy"                        # the clip models' own line (`clip_models`): its adapter
    c = FakeCtx("generate-image", tmp_path / "data", FakeEngine(cat))
    c.bus = Bus()
    folder = tmp_path / "Characters"
    folder.mkdir()
    for name, size in CAST.items():
        Image.new("RGB", size).save(folder / name)
    c.files = Files(tmp_path / "data", None, folder)
    await models.catalog(c)
    return c


def ui(model_id: str) -> dict:
    return models.ui_model(models.find(models.cached(), model_id), {})


def saved(ctx, **extra) -> None:
    ctx.doc("draft", {}).replace({"model": PRUNED, "aspect": "16:9", "size": 1, "images": 1, **extra})


def real(ctx, item: str) -> str:
    return str(Path(ctx.files.resolve(item)).resolve())


def test_the_catalog_names_each_models_pictures_from_its_definition(clip_models):
    by = {m["id"]: m["video"]["references"] for m in clip_models}
    assert by[PRUNED] == {"role": "start", "min": 0, "max": 2, "end": True}, "S: a start frame; E: a last one too"
    assert by[OMNI] == {"role": "identity", "min": 1, "max": 9, "key": "minimax_h3_references", "names": True,
                        "detail": {
        "key": "minimax_h3_reference_detail", "default": "match",
        "choices": [{"value": "match", "label": "Match output (faster)"},
                    {"value": "max", "label": "High detail (official PDD recipe)"}]}}, "the engine's cap and detail"
    assert "minimax_h3_legacy" not in by, "a sidecar runtime stays out"


def test_picture_refs_read_the_definition_alone(tmp_path):
    spec = json.loads((make_engine_root(tmp_path) / "fake_engine.json").read_text())["architectures"]
    omni, own = spec["minimax_h3_ref2va"], {"x_references": [], "y_references": "no"}
    refs = functools.partial(catalogvideo.picture_refs, keys=KEYS)
    facts = functools.partial(catalogvideo.video_facts, keys=KEYS)
    assert refs(omni, own) == {"role": "identity", "min": 1, "max": 9, "key": "x_references", "names": True}
    assert refs({**omni, "omni_reference_limits": {"image": 0}}, own) is None, "no cap: not usable"
    assert refs(omni, {"y_references": "no"}) is None, "no reference list named: not usable"
    assert refs({"image_prompt_types_allowed": "TS"}, {}) == {"role": "start", "min": 0, "max": 1, "end": False}
    assert refs({"image_prompt_types_allowed": "TSE"}, {}) == {"role": "start", "min": 0, "max": 2, "end": True}
    assert refs({"image_prompt_types_allowed": "TEV"}, {}) is None, "no S: no start frame"
    assert facts(omni, {"video_length": 0}) is None, "a manifest model with no list it names"
    assert facts({**omni, "settings": own}, {})["references"]["key"] == "x_references"


def test_the_bar_takes_the_engines_cap_and_the_image_modes(ctx):
    pruned, omni, text = ui(PRUNED), ui(OMNI), ui(TEXT)
    assert (pruned["modes"], pruned["refCap"], pruned["video"]["references"]["role"]) == (["new", "refs"], 2, "start")
    assert pruned["video"]["references"]["end"] is True and ui(START)["refCap"] == 1, "box 2 is the last frame"
    assert (omni["modes"], omni["video"]["references"]["role"]) == (["refs"], "identity")
    assert (text["modes"], text["refCap"]) == (["new"], 0)
    assert models.ui_model(models.find(models.cached(), OMNI), {"minimax": 2})["refCap"] == 3, "not `ref_caps`"


def test_the_cap_is_no_more_than_the_bars_boxes(ctx):
    pruned, omni = ui(PRUNED), ui(OMNI)
    assert models.picture_refs(models.find(models.cached(), OMNI))["max"] == 9, "the engine's cap is kept as it is"
    assert (omni["refCap"], omni["video"]["references"]["max"]) == (3, 3) == (cast.BOXES, cast.BOXES)
    assert (pruned["refCap"], pruned["video"]["references"]["max"]) == (2, 2), "a start and a last frame"


@pytest.mark.parametrize(("model", "aspect", "names", "size"), [
    (PRUNED, "auto", [], (736, 736)), (PRUNED, "auto", ["Character 11"], (960, 544)), (PRUNED, "auto", ["Character 4"],
                                                                                       (576, 896)),
    (PRUNED, "16:9", ["Character 4"], (960, 544)), (OMNI, "auto", ["Character 11"], (736, 736))])
async def test_auto_snaps_to_a_start_frames_shape(ctx, model, aspect, names, size):
    saved(ctx, model=model, aspect=aspect)
    routes.session_part(ctx)["references"] = [
        # placed in the boxes
        {"id": f"chars/{n}.png", "w": CAST[f"{n}.png"][0], "h": CAST[f"{n}.png"][1]} for n in names]
    seen = await tools.read_settings(ctx)
    assert (seen["width"], seen["height"]) == size, "the tier's shape nearest the start frame; identities never"


def payload(**extra) -> dict:
    p = {"model": PRUNED, "mode": "new", "prompt": PROMPT, "loras": [], "width": 960, "height": 544, "images": 1,
         "steps": None, "guidance": None, "seed": {"mode": "fixed", "value": 7}, "frames": 124}
    return {**p, **extra}


BASE = {"model_type": PRUNED, "image_mode": 0, "prompt": PROMPT, "resolution": "960x544", "video_length": 124,
        "sliding_window_size": 124, "minimax_h3_multi_window": False, "num_inference_steps": 20, "seed": 7,
        "batch_size": 1, "multi_prompts_gen_type": "FG", "video_prompt_type": "",
        "minimax_h3_text_encoder": "nvfp4_awq"}


def test_a_start_frame_is_box_one_as_image_start(ctx):
    plan = build.image_job(payload(mode="refs", references=["chars/Character 11.png"]), ctx)
    assert engine(plan.tasks[0]) == {**BASE, "image_prompt_type": "S", "image_start": real(ctx,
                                                                                           "chars/Character 11.png"),
                             "image_fit_mode": "crop"}
    assert os.path.isabs(engine(plan.tasks[0])["image_start"])
    s = plan.summary
    assert (s["kind"], s["frames"], s["seconds"], s["mode"], s["references"]) == ("clip", 124, 5.17, "refs",
                                                                                  ["Character 11"])
    plain = build.image_job(payload(references=["chars/Character 11.png"]), ctx)
    assert engine(plain.tasks[0]) == {**BASE, "image_prompt_type": ""}, "New: text"
    assert plain.summary["references"] == []


def test_identities_are_the_reference_list_in_box_order(ctx):
    plan = build.image_job(payload(model=OMNI, mode="refs", references=["chars/Character 4.png",
                                                                        "chars/Character 11.png"]), ctx)
    task = engine(plan.tasks[0])
    assert task == {**BASE, "model_type": OMNI, "image_prompt_type": "", "minimax_h3_references": [
        {"type": "image", "path": real(ctx, "chars/Character 4.png"), "image_intent": "identity",
         "character_name": "Character 4"},
        {"type": "image", "path": real(ctx, "chars/Character 11.png"), "image_intent": "identity",
         "character_name": "Character 11"}]}
    assert all(os.path.isabs(r["path"]) for r in task["minimax_h3_references"])
    assert "image_start" not in task and plan.summary["references"] == ["Character 4", "Character 11"]


def test_box_two_is_the_last_frame_on_a_model_that_allows_one(ctx):
    plan = build.image_job(payload(mode="refs", references=["chars/Character 11.png", "chars/Character 4.png"]), ctx)
    assert engine(plan.tasks[0]) == {**BASE, "image_prompt_type": "SE", "image_start": real(ctx,
                                                                                            "chars/Character 11.png"),
                             "image_end": real(ctx, "chars/Character 4.png"), "image_fit_mode": "crop"}
    assert os.path.isabs(engine(plan.tasks[0])["image_end"]) and plan.summary["references"] == ["Character 11",
                                                                                                "Character 4"]
    one = engine(build.image_job(payload(mode="refs", references=["chars/Character 11.png"]), ctx).tasks[0])
    assert one["image_prompt_type"] == "S" and "image_end" not in one, "box 1 alone stays a start frame"


@pytest.mark.parametrize(("extra", "field", "text"), [
    ({"mode": "refs", "references": ["", "chars/Character 4.png"]}, "references", build.LAST_ALONE),
    ({"mode": "refs", "references": ["chars/Character 11.png"] * 3}, "references",
     "Too many references for this model (3 of 2)"),
    ({"model": START, "mode": "refs", "references": ["chars/Character 11.png", "chars/Character 4.png"]}, "references",
     "Too many references for this model (2 of 1)"),
    ({"model": OMNI}, "references", f"{OMNI_LABEL} needs at least one image reference"),
    ({"model": OMNI, "mode": "refs"}, "references", f"{OMNI_LABEL} needs at least one image reference"),
    ({"model": OMNI, "mode": "refs", "references": ["chars/Character 11.png"] * 10}, "references",
     "Too many references for this model (10 of 3)"),
    ({"mode": "refs", "references": ["chars/Gone.png"]}, "references", "An image is missing; add it again"),
    ({"mode": "refs", "references": "chars/Character 11.png"}, "references", "References must be a list"),
    ({"model": TEXT, "mode": "refs", "references": ["chars/Character 11.png"]}, "mode",
     "Text Only can't use reference images"),
])
def test_a_clips_pictures_refused_in_one_line(ctx, extra, field, text):
    with pytest.raises(Invalid) as err:
        build.image_job(payload(**extra), ctx)
    assert (err.value.field, err.value.text) == (field, text)


async def test_generate_image_sends_the_boxes_with_the_unchanged_tools(ctx):
    ctx.jobs = FakeJobs(ctx, {"image": manifest.MODULE.jobs["image"]})
    saved(ctx, model=OMNI, aspect="auto")
    routes.session_part(ctx)["draft"] = "subject_definitions: <Subject 1> (S1) is from <Picture 1>."
    with pytest.raises(Invalid) as err:
        await tools.generate_image(ctx, {})
    assert err.value.text == f"{OMNI_LABEL} needs at least one image reference"
    # Character 11 placed
    routes.session_part(ctx)["references"] = [{"id": "chars/Character 11.png", "w": 1000, "h": 560}]
    assert await tools.generate_image(ctx, {}) == {"state": "queued"}
    [(job, params)] = ctx.jobs.jobs.values()
    assert (params["mode"], params["references"], params["width"], params["height"]) == (
        "refs", ["chars/Character 11.png"], 736, 736)
    assert engine(job.plan.tasks[0])["minimax_h3_references"][0]["path"] == real(ctx, "chars/Character 11.png")
