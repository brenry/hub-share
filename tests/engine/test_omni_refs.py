"""Omni's names, detail and cut-out (Stage 7): the catalog carries the detail the definition announces, each identity
box sends the engine's intent from the one constant, its character's name when it is a listed character and
`remove_background` when its cut-out is on; the card's detail reaches the task key; a picture outside 1:4 to 4:1 is
refused in one line at build and at set time. The fake engine checks every built manifest as the engine does."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.core.files import Files
from hub.modules.generate_image import build, manifest, models, routes, screen, tools
from hub.worker import catalogvideo
from hub.worker.adapters import tasks
from hub.worker.adapters.fork import FAMILIES as KEYS
from tests.engine.helpers import (
    ENGINE_PYTHON,
    FAKE_ENGINE,
    HERE,
    WORKER,
    FakeCtx,
    FakeEngine,
    FakeJobs,
    FakeRequest,
    Worker,
    engine_task,
    load_catalog,
    make_engine_root,
)

PRUNED, OMNI = "minimax_h3", "minimax_h3_ref2va"
LABEL, OMNI_LABEL = "H3 First / Last — Pruned", "H3 Omni — Pruned"
LONG = "L" * 121
CAST = {"Character 11.png": (1000, 560), "Character 4.png": (600, 900), "Tall.png": (100, 500), "Wide.png": (400, 100),
        "Thin.png": (100, 400), f"{LONG}.png": (64, 64), f"{LONG[:120]}.png": (64, 64)}
DETAIL = {"key": "minimax_h3_reference_detail", "default": "match",
          "choices": [{"value": "match", "label": "Match output (faster)"},
                      {"value": "max", "label": "High detail (official PDD recipe)"}]}
PROMPT = "subject_definitions: <Subject 1> is Character 11 from <Picture 1>."
_spec = importlib.util.spec_from_file_location("fake_manifest", FAKE_ENGINE / "shared" / "fake_manifest.py")
fake_manifest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fake_manifest)


@pytest.fixture(scope="module")
def clip_models(tmp_path_factory) -> list[dict]:
    base = tmp_path_factory.mktemp("engine")
    out = base / "catalog.json"
    subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(make_engine_root(base, "legacy")),
                    "--dump-catalog", str(out)], check=True, capture_output=True, timeout=60)
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
    folder = tmp_path / "Characters"
    folder.mkdir()
    for name, size in CAST.items():
        Image.new("RGB", size).save(folder / name)
    Image.new("RGB", (64, 64)).save(folder / "Character 11.jpg")         # an older file that shares Character 11's stem
    os.utime(folder / "Character 11.jpg", (1, 1))
    c.files = Files(tmp_path / "data", None, folder)
    # a Temp upload named like the character
    Image.new("RGB", (64, 64)).save(tmp_path / "data" / "outputs" / "Character 11.png")
    await models.catalog(c)
    return c


def saved(ctx, **extra) -> None:
    ctx.doc("draft", {}).replace({"model": OMNI, "aspect": "16:9", "size": 1, "images": 1, **extra})


def payload(refs: list[str], **extra) -> dict:
    return {"model": OMNI, "mode": "refs", "prompt": PROMPT, "loras": [], "width": 960, "height": 544, "images": 1,
            "steps": None, "guidance": None, "seed": {"mode": "fixed", "value": 7}, "frames": 124, "references": refs,
            **extra}


def engine(request: dict) -> dict:
    """The engine task the worker's adapter makes of a plan's request."""
    return engine_task(request, models.cached())


def items(ctx, refs: list[str], **extra) -> list[dict]:
    return engine(build.image_job(payload(refs, **extra), ctx).tasks[0])["minimax_h3_references"]


def refused(ctx, p: dict) -> tuple[str, str]:
    with pytest.raises(Invalid) as err:
        build.image_job(p, ctx)
    return err.value.field, err.value.text


def test_the_catalog_carries_omnis_announced_detail(clip_models):
    by = {m["id"]: m["video"]["references"] for m in clip_models}
    assert by[OMNI]["detail"] == DETAIL and "detail" not in by[PRUNED], "First / Last never has one"
    spec = json.loads((FAKE_ENGINE / "fake_engine.json").read_text())["architectures"]["minimax_h3_ref2va"]
    own = {"x_references": [], "x_reference_detail": "match"}
    tuples = {**spec, "omni_reference_detail_choices": [tuple(p) for p in spec["omni_reference_detail_choices"]]}
    assert catalogvideo.picture_refs(tuples, own, keys=KEYS)["detail"] == {**DETAIL, "key": "x_reference_detail"}
    for unannounced in ({k: v for k, v in spec.items() if k != "omni_reference_detail_choices"},
                        {**spec, "omni_reference_detail_default": "huge"}):
        assert "detail" not in catalogvideo.picture_refs(unannounced, own, keys=KEYS)
    assert "detail" not in catalogvideo.picture_refs(spec, {"x_references": []}, keys=KEYS), "no task key in settings"
    assert "detail" not in catalogvideo.picture_refs({**spec, "omni_reference": False,
                                                      "image_prompt_types_allowed": "TSE"}, own, keys=KEYS)
    assert "minimax" not in Path(catalogvideo.__file__).read_text(), "the worker names no model"


async def test_ui_model_passes_the_detail_through(ctx):
    assert models.ui_model(models.find(models.cached(), OMNI), {})["video"]["references"]["detail"] == DETAIL


def test_a_characters_box_carries_its_name(ctx):
    sent = items(ctx, ["chars/Character 11.png", "out/Character 11.png", "chars/Character 11.jpg"])
    assert [i.get("character_name") for i in sent] == ["Character 11", None,
                                                       None], "a Temp upload, an older same stem: none"
    assert [i.get("character_name") for i in items(ctx, ["chars/Character 4.png",
                                                         "chars/Character 4.png"])] == ["Character 4", "Character 4"]
    assert items(ctx, [f"chars/{LONG[:120]}.png"])[0]["character_name"] == LONG[:120]
    assert refused(ctx, payload([f"chars/{LONG}.png"])) == (
        "references", f"{LONG} is too long for {OMNI_LABEL}: names are at most 120 characters")


def test_the_intent_is_the_adapters_constant_not_the_role_word(ctx):
    assert tasks.IDENTITY == "identity" and tasks.IDENTITY in fake_manifest.IMAGE_INTENTS, "the engine's vocabulary"
    assert [i["image_intent"] for i in items(ctx, ["chars/Character 11.png",
                                                   "chars/Character 4.png"])] == [tasks.IDENTITY] * 2
    request = build.image_job(payload(["chars/Character 11.png"]), ctx).tasks[0]
    assert [r["role"] for r in request["references"]] == ["identity"], "the Hub sends its role; the adapter the intent"


def test_the_fake_engine_accepts_every_built_omni_task_and_refuses_another_intent(ctx):
    saved(ctx, advancedByModel={OMNI: {"detail": "max"}})
    for refs, cut in ((["chars/Character 11.png"], None), (["chars/Character 11.png", "out/Character 11.png",
                                                            "chars/Wide.png"], [True]),
                      (["chars/Thin.png", "chars/Character 4.png"], [False, True])):
        task = engine(build.image_job(payload(refs, cutout=cut), ctx).tasks[0])
        assert fake_manifest.check(task) is task
    bad = {"minimax_h3_references": [{"type": "image", "path": "/x.png", "image_intent": "face"}]}
    with pytest.raises(ValueError, match="has invalid image intent 'face'; expected one of: composition, identity"):
        fake_manifest.check(bad)


def test_the_cards_detail_reaches_the_task_key(ctx):
    key = DETAIL["key"]
    saved(ctx, advancedByModel={OMNI: {"detail": "max"}})
    assert engine(build.image_job(payload(["chars/Character 11.png"]), ctx).tasks[0])[key] == "max"
    saved(ctx)
    assert key not in engine(build.image_job(payload(["chars/Character 11.png"]),
                                             ctx).tasks[0]), "no card value: the factory's"
    saved(ctx, advancedByModel={OMNI: {"detail": "huge", "steps": 20}})
    assert key not in engine(build.image_job(payload(["chars/Character 11.png"]), ctx).tasks[0]), "a stale value: none"


async def test_a_stale_detail_is_dropped_by_the_next_tool_write(ctx):
    saved(ctx, advancedByModel={OMNI: {"detail": "huge"}, PRUNED: {"detail": "max"}})
    await tools.write_settings(ctx, {"steps": 12})
    adv = ctx.doc("draft", {}).get()["advancedByModel"]
    assert "detail" not in adv[OMNI] and adv[OMNI]["steps"] == 12
    saved(ctx, advancedByModel={OMNI: {"detail": "max"}})
    await tools.write_settings(ctx, {"steps": 12})
    assert ctx.doc("draft", {}).get()["advancedByModel"][OMNI]["detail"] == "max", "an announced one stays"


async def put(ctx, body: dict) -> dict:
    return await routes.put_draft(ctx, FakeRequest(body=json.dumps(body).encode()))


@pytest.mark.parametrize(("model", "value", "text"), [
    (OMNI, "huge", f"Detail must be match or max for {OMNI_LABEL}"),
    (OMNI, 2, f"Detail must be match or max for {OMNI_LABEL}"),
    (PRUNED, "max", f"{LABEL} has no detail setting"),
    ("flux2_klein_9b", "max", "Flux 2 Klein 9B has no detail setting")])
async def test_put_refuses_a_detail_the_model_does_not_announce(ctx, model, value, text):
    saved(ctx)
    before = ctx.doc("draft", {}).get()
    with pytest.raises(Invalid) as err:
        await put(ctx, {"prompt": "kept out", "advancedByModel": {model: {"steps": 9, "detail": value}}})
    assert (err.value.field, err.value.text) == ("detail", text)
    assert ctx.doc("draft", {}).get() == before and "prompt" not in routes.session_part(ctx), "nothing saved"


async def test_put_keeps_an_announced_detail_and_lets_a_saved_one_pass(ctx):
    saved(ctx, advancedByModel={PRUNED: {"detail": "old"}})
    out = await put(ctx, {"advancedByModel": {OMNI: {"detail": "max"}, PRUNED: {"detail": "old"}}})
    assert out["advancedByModel"][OMNI]["detail"] == "max", "the stale one is the builder's to ignore"


async def test_detail_is_no_tool_setting(ctx):
    saved(ctx, advancedByModel={OMNI: {"detail": "max"}})
    assert "detail" not in {s.name for s in screen.SETTINGS}
    assert "detail" not in await tools.read_settings(ctx)


def test_cutout_sets_remove_background_on_identities_only(ctx):
    sent = items(ctx, ["chars/Character 11.png", "chars/Character 4.png"], cutout=[False, True])
    assert "remove_background" not in sent[0] and sent[1]["remove_background"] is True
    assert all("remove_background" not in i for i in items(ctx, ["chars/Character 11.png"], cutout=[False]))
    assert refused(ctx, payload(["chars/Character 11.png"], model=PRUNED, cutout=[True])) == (
        "cutout", f"{LABEL} cuts out no backgrounds")
    for bad in ([True, False], ["on"], "yes"):
        assert refused(ctx, payload(["chars/Character 11.png"], cutout=bad)) == (
            "cutout", "Cut-out must be on or off for each box")


async def test_a_tool_press_carries_the_session_boxs_flag(ctx):
    ctx.jobs = FakeJobs(ctx, {"image": manifest.MODULE.jobs["image"]})
    saved(ctx)
    routes.session_part(ctx).update(draft=PROMPT, references=[
        {"id": "chars/Character 11.png", "w": 1000, "h": 560, "cutout": True}, {"id": "chars/Character 4.png", "w": 600,
                                                                                "h": 900}])
    assert await tools.generate_image(ctx, {}) == {"state": "queued"}
    [(job, params)] = ctx.jobs.jobs.values()
    assert params["cutout"] == [True, False]
    assert [i.get("remove_background") for i in engine(job.plan.tasks[0])["minimax_h3_references"]] == [True, None]
    routes.session_part(ctx)["references"] = [{"id": "chars/Character 11.png", "w": 1000, "h": 560}]
    await tools.generate_image(ctx, {})
    assert "cutout" not in list(ctx.jobs.jobs.values())[-1][1], "all off: none sent"


def test_a_picture_out_of_shape_is_refused_at_build(ctx):
    assert refused(ctx, payload(["chars/Character 11.png", "chars/Tall.png"])) == (
        "references", f"Identity 2 is 100×500: {OMNI_LABEL} takes pictures between 1:4 and 4:1")
    assert len(items(ctx, ["chars/Wide.png", "chars/Thin.png"])) == 2, "4:1 and 1:4 pass"
    one = engine(build.image_job(payload(["chars/Tall.png"], model=PRUNED), ctx).tasks[0])
    assert one["image_start"].endswith("Tall.png"), "a start frame is any shape"


@pytest.mark.parametrize("flavour", ["legacy", "upstream"])
async def test_the_manifest_reaches_the_engine_intact(ctx, tmp_path, flavour):
    saved(ctx, advancedByModel={OMNI: {"detail": "max"}})
    task = build.image_job(payload(["chars/Character 11.png", "out/Character 11.png"], cutout=[False, True]),
                           ctx).tasks[0]
    w = Worker(make_engine_root(tmp_path / flavour, flavour), tmp_path / flavour / "state")
    try:
        assert w.until(lambda m: m["ev"] in ("ready", "fatal"))[-1]["ev"] == "ready"
        w.send({"op": "run", "job": "o1", "task": 1, "request": {**task, "steps": 2}})
        assert w.until(lambda m: m["ev"] == "task_done")[-1]["ok"]
        sent = json.loads((tmp_path / flavour / "state" / "settings" / "last_task.json").read_text())
        assert sent["minimax_h3_references"] == engine(task)["minimax_h3_references"] and sent[DETAIL["key"]] == "max"
        assert [os.path.isabs(i["path"]) for i in sent["minimax_h3_references"]] == [True, True]
        assert [(i.get("character_name"), i.get("remove_background")) for i in sent["minimax_h3_references"]] == [
            ("Character 11", None), (None, True)]
    finally:
        w.close()


@pytest.mark.parametrize("flavour", ["legacy", "upstream"])
def test_an_engine_refusal_comes_back_as_one_line(ctx, tmp_path, flavour):
    """The worker's end of a refusal (restored from before step 4 through `crafted_task.py`): a manifest the engine
    refuses (an intent it does not know) comes back from the real worker as a failed task with one plain line."""
    task = engine(build.image_job(payload(["chars/Character 11.png"]), ctx).tasks[0])
    face = {**task, "num_inference_steps": 2,
            "minimax_h3_references": [{**task["minimax_h3_references"][0], "image_intent": "face"}]}
    root, crafted, out = make_engine_root(tmp_path / flavour, flavour), tmp_path / "task.json", tmp_path / "out.json"
    crafted.write_text(json.dumps(face))
    subprocess.run([ENGINE_PYTHON, "-B", str(HERE / "crafted_task.py"), str(WORKER.parent), str(root),
                    str(tmp_path / "state"), str(crafted), str(out)], check=True, capture_output=True, timeout=60)
    done = json.loads(out.read_text())["done"]
    assert not done["ok"] and done["error"]["stage"] == "generation"
    text = done["error"]["text"]
    assert "invalid image intent 'face'" in text and "\n" not in text and len(text) <= 800
