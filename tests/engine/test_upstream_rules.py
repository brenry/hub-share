"""The upstream adapter's rules (R16 §4), held against upstream's own H3 definitions as the
capture of 18.05 gives them (`tests/fixtures/upstream-18.05/h3.json`, written from it; `test_upstream_capture`). The
catalog is the real worker's answer for a fake root carrying those definitions (`make_engine_root(h3=True)`); a task
is the upstream adapter's for a request, as the worker builds it, checked against the fixture's accepted settings.
Each of these is held here: the size budget, `why_not`,
the longest length, the fork ids, the accepted keys, the step lock, one cut-out for every box, the sound keys, and the
native rules."""
from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.core.files import Files
from hub.modules.generate_image import build, models, rename, routes, screen
from hub.worker import catalog, enginewire, faults
from hub.worker.adapters import tasks, upstream
from hub.worker.engineapi import ClipRequest, PictureRequest, Reference, SpeechRequest
from tests.engine.helpers import ENGINE_PYTHON, HERE, UPSTREAM_H3, WORKER, FakeCtx, FakeEngine, make_engine_root

FIXTURE = json.loads(UPSTREAM_H3.read_text(encoding="utf-8"))
ACCEPTED = frozenset(FIXTURE["accepted_settings"])
DRIVEN = ("minimax_h3_fl2va", "minimax_h3_fl2va_pruned", "minimax_h3_fl2va_pdd", "minimax_h3_ref2va",
          "minimax_h3_ref2va_pruned")
FL2VA, REF2VA = "minimax_h3_fl2va_pruned", "minimax_h3_ref2va_pruned"
WHY_NOT = ("minimax_h3_control", "minimax_h3_control_pruned", "viggle_animate")
SPEECH = "minimax_h3_tts_ref2va_pruned"
KLEIN_BUDGET, H3_BUDGET = 1920 * 1088, 2048 * 2048
CAST = {"Character 11.png": (1000, 560), "Character 4.png": (600, 900), "Character 12.png": (640, 640)}


@pytest.fixture(scope="module")
def cat(tmp_path_factory) -> dict[str, Any]:
    base = tmp_path_factory.mktemp("h3")
    root = make_engine_root(base, "upstream", h3=True)
    out = base / "catalog.json"
    subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--dump-catalog", str(out)],
                   check=True, capture_output=True, timeout=60)
    return json.loads(out.read_text(encoding="utf-8"))


def entry(cat: dict, model_id: str) -> dict:
    return next(m for m in cat["models"] if m["id"] == model_id)


@pytest.fixture(autouse=True)
def accepted(monkeypatch):
    """In this process the engine's `accepted_setting_names` is the fixture's list."""
    monkeypatch.setattr(upstream, "accepted_names", lambda: ACCEPTED)


def sent(cat: dict, request: Any) -> dict:
    """What the worker submits for a request: across the wire and back, the adapter's task, then `translate`."""
    parsed = enginewire.request_parse(enginewire.request_wire(request))
    return upstream.translate(upstream.Upstream().task(parsed, entry(cat, parsed.model)), {})


def clip(model: str = FL2VA, **extra: Any) -> ClipRequest:
    fields: dict[str, Any] = {"prompt": "a shot", "size": (960, 544), "seed": 7, "frames": 141, "steps": 20, **extra}
    return ClipRequest(model, **fields)


def refused(cat: dict, request: Any) -> str:
    with pytest.raises(faults.Refused) as err:
        sent(cat, request)
    return str(err.value)


# ---------------------------------------------------------------- the catalog: native rules
def test_h3_is_listed_as_upstream_publishes_it(cat):
    facts = upstream.read_facts(upstream.FACTS)
    for model_id in DRIVEN:
        m = entry(cat, model_id)
        v, definition = m["video"], FIXTURE["models"][model_id]["definition"]
        assert m["kind"] == "video" and m["budget"] == H3_BUDGET, model_id
        assert v["frames"] == {"min": 107, "step": 17, "max": 362, "default": 124}, "17k+5, up to the official 15 s"
        assert (v["window_min"], v["window_max"]) == (124, 481), "the window floor and the hard limit"
        assert v["one_pass"] is None, "no one-pass switch upstream: the window is the clip"
        ids = [k for k in definition["system_configs"] if not k.startswith("_")]
        assert v["text_encoders"] == ids and v["text_encoder_default"] == FIXTURE["server_config"][
            "text_encoder_quantization"] and v["encoder_key"] == "config", "the encoder through `config`"
        assert m["video_task"] == {}, "no encoder is sent unless the request names one"
        assert v["tiers"] == facts["tiers"]["h3"]["tiers"]
        assert all(w * h <= m["budget"] and not w % 32 and not h % 32
                   for t in v["tiers"] for w, h in t["sizes"].values()), "every tier within the budget, block 32"


def test_identities_are_reference_pictures_and_fl2va_takes_frames(cat):
    for model_id in ("minimax_h3_ref2va", REF2VA):
        v = entry(cat, model_id)["video"]
        assert v["references"] == {"role": "identity", "min": 0, "max": 9, "letters": "I", "names": False,
                                   "cutout": "all"}, "the handler's cap of 9, no names, one cut-out"
        assert (v["continues"], v["overlap"]) == (True, 18), "Ref2VA takes V"
    v = entry(cat, FL2VA)["video"]
    assert v["references"] == {"role": "start", "min": 0, "max": 2, "end": True}
    assert (v["continues"], v["overlap"]) == (True, 18)


def test_models_upstream_has_but_the_hub_cannot_drive(cat, tmp_path, monkeypatch):
    for model_id in WHY_NOT:
        m = entry(cat, model_id)
        assert m["why_not"] == "It follows a control video, which the Hub does not send" and m["video"] is None
    speech = entry(cat, SPEECH)                                        # the speech model is listed
    assert (speech["kind"], speech["video"], speech["status"]) == ("speech", None, "available")
    listed = {m["id"] for m in models.present(cat)}
    assert set(DRIVEN) <= listed and not set(WHY_NOT) & listed, "never offered as a picture model"
    ctx = FakeCtx("generate-image", tmp_path / "data", FakeEngine(cat))
    monkeypatch.setattr(models, "_last", cat)
    with pytest.raises(Invalid) as err:
        build.image_job({"model": "viggle_animate", "mode": "new", "prompt": "x"}, ctx)
    assert (err.value.field, err.value.text) == ("model", "It follows a control video, which the Hub does not send")


# ---------------------------------------------------------------- tasks: native rules
def test_every_task_holds_only_keys_upstream_accepts(cat):
    made = [sent(cat, clip()), sent(cat, clip(REF2VA, references=[Reference("/a.png", "identity")])),
            sent(cat, clip(references=[Reference("/a.png", "start"), Reference("/b.png", "end")])),
            sent(cat, clip(frames=107, references=[Reference("/c.mp4", "source")])),
            sent(cat, PictureRequest("flux2_klein_9b", "a cat", (64, 48), 7, steps=4)),
            sent(cat, SpeechRequest(SPEECH, "Hello.", 7, 300, direction="low")),
            sent(cat, SpeechRequest(SPEECH, "Hello.", 7, 300, sample="/chars/Character 8.wav"))]
    assert all(set(task) <= ACCEPTED for task in made)
    assert all(t["postprocess_audio"] == "" and "MMAudio_setting" not in t for t in made[:4]), "no audio postprocess"
    assert "MMAudio_setting" in ACCEPTED, "deprecated: accepted and ignored, so never sent rather than refused"
    for fork_key in ("minimax_h3_multi_window", "minimax_h3_text_encoder", "image_fit_mode"):
        with pytest.raises(faults.Refused, match=f"^The engine does not take the setting {fork_key}$"):
            upstream.translate({**made[0], fork_key: 0}, {})




def test_identities_go_as_I_with_the_pictures_in_box_order(cat):
    boxes = [Reference(f"/{n}.png", "identity", cutout=True) for n in ("character 11", "character 4", "character 12")]
    task = sent(cat, clip(REF2VA, references=boxes))
    assert (task["video_prompt_type"], task["image_prompt_type"]) == ("I", "")
    assert task["image_refs"] == ["/character 11.png", "/character 4.png",
                                  "/character 12.png"] and task["remove_background_images_ref"] == 1
    assert entry(cat, REF2VA)["video"]["references"]["names"] is False, "no name is sent (R16 §4 rule 8)"
    none = sent(cat, clip(REF2VA, references=[Reference("/a.png", "identity")]))
    assert none["remove_background_images_ref"] == 0
    mixed = [Reference("/a.png", "identity", cutout=True), Reference("/b.png", "identity")]
    assert refused(cat, clip(REF2VA, references=mixed)) == "Cut-out is on or off for every box on " + entry(
        cat, REF2VA)["name"], "the adapter's own line"
    ten = [Reference(f"/{i}.png", "identity") for i in range(10)]
    assert refused(cat, clip(REF2VA, references=ten)).startswith("Too many identities")


def test_what_a_model_does_not_take_is_refused_not_dropped(cat):
    """Never dropped: a cut-out or a name on a picture that takes none, a detail on a model with none."""
    klein = entry(cat, "flux2_klein_9b")["name"]
    cut = PictureRequest("flux2_klein_9b", "a cat", (64, 48), 7, references=[Reference("/a.png", "reference",
                                                                                         cutout=True)])
    assert refused(cat, cut) == f"{klein} cuts out no backgrounds"
    named = PictureRequest("flux2_klein_9b", "a cat", (64, 48), 7, references=[Reference("/a.png", "reference",
                                                                                           name="Character 11")])
    assert refused(cat, named) == f"{klein} takes no names with its pictures"
    ref2va = entry(cat, REF2VA)["name"]
    assert refused(cat, clip(REF2VA, references=[Reference("/a.png", "identity", name="Character 11")])) == (
        f"{ref2va} takes no names with its pictures"), "upstream binds names in the prompt (<Picture N>)"
    assert refused(cat, clip(REF2VA, detail="max", references=[Reference("/a.png", "identity")])) == (
        f"{ref2va} has no detail setting")
    start = clip(references=[Reference("/a.png", "start", cutout=True)])
    assert refused(cat, start) == f"{entry(cat, FL2VA)['name']} cuts out no backgrounds"


def test_the_engines_own_list_refuses_a_fork_key_in_the_worker(tmp_path):
    """The accepted-settings check through the real import (`shared.utils.setting_names` in the test root), in the
    worker: a task holding a fork key fails in one line before the engine sees it."""
    root = make_engine_root(tmp_path, "upstream", h3=True)
    task = {"model_type": FL2VA, "prompt": "a shot", "resolution": "960x544", "seed": 1, "image_mode": 0,
            "video_length": 107, "sliding_window_size": 124, "minimax_h3_multi_window": False,
            "num_inference_steps": 2, "batch_size": 1, "multi_prompts_gen_type": "FG", "image_prompt_type": "",
            "video_prompt_type": ""}
    crafted, out = tmp_path / "task.json", tmp_path / "out.json"
    crafted.write_text(json.dumps(task))
    subprocess.run([ENGINE_PYTHON, "-B", str(HERE / "crafted_task.py"), str(WORKER.parent), str(root),
                    str(tmp_path / "state"), str(crafted), str(out)], check=True, capture_output=True, timeout=60)
    done = json.loads(out.read_text())["done"]
    assert not done["ok"] and done["error"] == {"stage": "generation",
                                                "text": "The engine does not take the setting minimax_h3_multi_window"}
    assert not (tmp_path / "state" / "settings" / "last_task.json").exists(), "nothing reached the engine"


def test_the_encoder_goes_in_config_and_only_when_named(cat):
    assert sent(cat, clip(encoder="bf16"))["config"] == "bf16"
    assert "config" not in sent(cat, clip())


def test_one_pass_the_window_floor_and_the_continue_window(cat):
    short, longest = sent(cat, clip(frames=107)), sent(cat, clip(frames=362))
    assert (short["video_length"], short["sliding_window_size"]) == (107, 124), "never under the window floor"
    assert (longest["video_length"], longest["sliding_window_size"]) == (362, 362)
    step = sent(cat, clip(frames=362, references=[Reference("/c.mp4", "source")]))
    assert (step["sliding_window_size"], step["sliding_window_overlap"], step["image_prompt_type"]) == (379, 18, "V")
    over = clip(frames=470, references=[Reference("/c.mp4", "source")])
    assert refused(cat, over) == f"{entry(cat, FL2VA)['name']} continues at most 464 frames at a time", "N+17 <= 481"


def test_a_role_the_model_does_not_take_is_refused_never_dropped(cat):
    name = entry(cat, FL2VA)["name"]
    assert refused(cat, clip(references=[Reference("/a.png", "identity")])) == f"{name} takes no identity picture"
    assert refused(cat, clip(REF2VA, references=[Reference("/a.png", "start")])).endswith("takes no start frame")
    assert refused(cat, clip(references=[Reference("/b.png", "end")])) == tasks.LAST_ALONE
    two = [Reference("/a.png", "start"), Reference("/b.png", "start")]
    assert refused(cat, clip(references=two)) == tasks.ONE_EACH.format(name)
    both = [Reference("/c.mp4", "source"), Reference("/a.png", "start")]
    assert refused(cat, clip(references=both)) == tasks.SOURCE_ALONE
    assert sent(cat, clip(REF2VA, references=[Reference("/c.mp4", "source")]))["image_prompt_type"] == "V", "continues"
    z_image = PictureRequest("z_image", "a cat", (64, 48), 7, references=[Reference("/a.png", "reference")])
    assert refused(cat, z_image) == f"{entry(cat, 'z_image')['name']} takes no reference picture"


def test_the_wire_refuses_an_unknown_role_and_one_the_kind_does_not_take():
    picture = enginewire.request_wire(PictureRequest("m", "p", (1, 1), 1, references=[Reference("/a", "start")]))
    with pytest.raises(ValueError, match=r"^request.references\[0\]: a picture request takes no start picture$"):
        enginewire.request_parse(picture)
    odd = enginewire.request_wire(clip(references=[Reference("/a", "face")]))
    with pytest.raises(ValueError, match=r"^request.references\[0\]: unknown role 'face'$"):
        enginewire.request_parse(odd)
    whole = enginewire.request_parse(enginewire.request_wire(PictureRequest("m", "p", (1, 1), 1, guidance=4)))
    assert type(whole.guidance) is int and whole.guidance == 4, "a whole number stays one"


def test_a_refusal_is_one_line_without_a_frame():
    try:
        raise faults.Refused(tasks.SOURCE_ALONE)
    except faults.Refused as exc:
        assert faults.failure([exc], False) == {"stage": "generation", "text": tasks.SOURCE_ALONE}


# ---------------------------------------------------------------- the size budget
def test_each_model_publishes_its_budget(cat):
    assert {m["id"]: m["budget"] for m in cat["models"] if m["kind"] == "image"} == dict.fromkeys(
        ("flux2_klein_9b", "flux2_klein_base_9b", "krea2_turbo_edit", "qwen_image_21_7B", "qwen_image_21_turbo_7B",
         "z_image"), KLEIN_BUDGET)
    assert upstream.budget(None, {"resolution_budget": "2048x2048"}) == H3_BUDGET
    assert upstream.budget(None, {}) == KLEIN_BUDGET, "upstream's default, 1920x1088"
    assert upstream.pixels(5) == 5 and upstream.pixels("nope") is None
    assert catalog.line_facts(None, type("Fork", (), {"line_facts": staticmethod(lambda *a: {})}), "m", {}) == {}


@pytest.mark.parametrize("aspect", sorted(screen.ASPECTS))
def test_the_canvas_shrinks_to_the_budget(aspect):
    klein = {"id": "k", "budget": KLEIN_BUDGET}
    for mp in (2, 4):
        w, h = screen.canvas(aspect, mp, [], klein)
        assert w * h <= KLEIN_BUDGET and not w % 16 and not h % 16, (aspect, mp)
        assert w * h > 0.97 * KLEIN_BUDGET, "the largest canvas of that shape"
    assert screen.canvas(aspect, 1.5, [], klein) == screen.canvas(aspect, 1.5, []), "below it: unchanged"
    assert screen.canvas(aspect, 4, [], {"id": "f"}) == screen.canvas(aspect, 4, []), "no budget: unchanged (fork)"
    krea = {"id": "krea", "budget": H3_BUDGET}
    w, h = screen.canvas(aspect, 4, [], krea)
    assert w * h <= H3_BUDGET and (aspect != "1:1" or (w, h) == (2048, 2048))


def test_a_picture_above_the_budget_is_refused_at_build(cat, tmp_path, monkeypatch):
    ctx = FakeCtx("generate-image", tmp_path / "data", FakeEngine(cat))
    monkeypatch.setattr(models, "_last", cat)
    p = {"model": "flux2_klein_9b", "mode": "new", "prompt": "a cat", "loras": [], "images": 1, "steps": None,
         "guidance": None, "seed": {"mode": "random"}}
    with pytest.raises(Invalid) as err:
        build.image_job({**p, "width": 1456, "height": 1456}, ctx)
    assert err.value.text == f"1456×1456 is more than Flux 2 Klein 9B makes ({KLEIN_BUDGET:,} pixels at most)"
    assert build.image_job({**p, "width": 1440, "height": 1440}, ctx).summary["width"] == 1440
    assert models.ui_model(entry(cat, "flux2_klein_9b"), {})["budget"] == KLEIN_BUDGET


# ---------------------------------------------------------------- the fork's ids
def test_the_fork_ids_find_the_same_model(cat):
    renamed = models.renamed(cat)
    assert renamed == {"minimax_h3": FL2VA, "minimax_h3_full": "minimax_h3_fl2va",
                       "minimax_h3_ref2va": REF2VA, "minimax_h3_ref2va_full": "minimax_h3_ref2va",
                       "qwen_image_21": "qwen_image_21_7B"}, "the facts file's map, the one place it is written"
    assert models.find(cat, "minimax_h3")["id"] == FL2VA
    assert models.find(cat, "qwen_image_21")["id"] == "qwen_image_21_7B"
    assert models.find(cat, "minimax_h3_ref2va")["id"] == "minimax_h3_ref2va", "a live id is the line's own"
    assert models.find(cat, "minimax_h3_fused_turbo") is None, "no upstream model: none"


def test_saved_fork_ids_are_brought_over_once(cat, tmp_path):
    ctx = FakeCtx("generate-image", tmp_path / "data", FakeEngine(cat))
    draft = {"model": "minimax_h3_ref2va", "lastModel": {"image": "qwen_image_21", "video": "minimax_h3_ref2va"},
             "advancedByModel": {"minimax_h3_ref2va": {"steps": 5}, "minimax_h3_ref2va_full": {"steps": 6}},
             "lorasByModel": {"minimax_h3": []}, "size": 1}
    ctx.doc(routes.DRAFT, {}).replace(copy.deepcopy(draft))
    ctx.doc(routes.DEFAULTS, routes.NO_DEFAULTS).replace({"text": "z_image", "refs": None, "video": "minimax_h3"})
    rename.adopt(ctx, cat)
    after = ctx.doc(routes.DRAFT, {}).get()
    assert after["model"] == REF2VA and after["lastModel"] == {"image": "qwen_image_21_7B", "video": REF2VA}
    assert after["advancedByModel"] == {REF2VA: {"steps": 5}, "minimax_h3_ref2va": {"steps": 6}}, "the trap"
    assert after["lorasByModel"] == {FL2VA: []} and after["engine"] == "upstream" and after["size"] == 1
    assert routes.defaults(ctx) == {"text": "z_image", "refs": None, "video": FL2VA}
    ctx.doc(routes.DRAFT, {}).replace({**after, "model": "minimax_h3_ref2va"})     # the 33B picked now
    rename.adopt(ctx, cat)
    assert ctx.doc(routes.DRAFT, {}).get()["model"] == "minimax_h3_ref2va", "once: an id saved after is its own"
    fork = {"engine": {"api": "legacy"}, "models": [{"id": "minimax_h3_ref2va"}]}
    other = FakeCtx("generate-image", tmp_path / "other", FakeEngine(fork))
    other.doc(routes.DRAFT, {}).replace(copy.deepcopy(draft))
    rename.adopt(other, fork)
    assert other.doc(routes.DRAFT, {}).get() == draft, "a line that renames nothing changes nothing, nor tags it"
    rename.adopt(ctx, fork)                                   # back to the fork: its Omni is picked there
    assert ctx.doc(routes.DRAFT, {}).get()["engine"] == "legacy", "the line is recorded over another line's name"
    ctx.doc(routes.DRAFT, {}).replace({**ctx.doc(routes.DRAFT, {}).get(), "model": "minimax_h3_ref2va"})
    rename.adopt(ctx, cat)                                    # and forward again: the fork's id is brought over
    assert ctx.doc(routes.DRAFT, {}).get()["model"] == REF2VA, "no 33B after a round trip"


def test_an_entry_the_model_already_has_under_its_new_id_is_kept(cat, tmp_path):
    ctx = FakeCtx("generate-image", tmp_path / "data", FakeEngine(cat))
    ctx.doc(routes.DRAFT, {}).replace({"advancedByModel": {"qwen_image_21": {"steps": 9},
                                                           "qwen_image_21_7B": {"steps": 40}}})
    rename.adopt(ctx, cat)
    assert ctx.doc(routes.DRAFT, {}).get()["advancedByModel"] == {"qwen_image_21_7B": {"steps": 40}}


# ---------------------------------------------------------------- a step lock
def test_qwen_turbo_runs_eight_steps(cat, tmp_path, monkeypatch):
    assert upstream.line_facts(None, "qwen_image_21_turbo_7B", {}) == {"budget": KLEIN_BUDGET, "lock_steps": True,
                                                                     "steps": 8}
    turbo = entry(cat, "qwen_image_21_turbo_7B")       # the engine's own definition locks nothing: the facts file does
    assert (turbo["lock_steps"], turbo["steps"]) == (True, 8)
    ctx = FakeCtx("generate-image", tmp_path / "data", FakeEngine(copy.deepcopy(cat)))
    monkeypatch.setattr(models, "_last", cat)
    p = {"model": turbo["id"], "mode": "new", "prompt": "a cat", "loras": [], "images": 1, "width": 1024,
         "height": 1024, "guidance": None, "seed": {"mode": "random"}}
    assert build.image_job({**p, "steps": None}, ctx).summary["steps"] == 8
    assert build.image_job({**p, "steps": 8}, ctx).summary["steps"] == 8
    with pytest.raises(Invalid) as err:
        build.image_job({**p, "steps": 20}, ctx)
    assert (err.value.field, err.value.text) == ("steps", f"{turbo['name']} runs 8 steps")
    assert models.ui_model(turbo, {})["lockSteps"] is True and models.locked_steps(entry(cat, FL2VA)) is None
    pdd = entry(cat, "minimax_h3_fl2va_pdd")
    assert (pdd["lock_steps"], pdd["steps"], models.locked_steps(pdd)) == (True, 8, 8), "a definition's own lock"


# ---------------------------------------------------------------- one cut-out for every box (the Hub's line)
@pytest.fixture
async def ref_ctx(tmp_path, cat):
    ctx = FakeCtx("generate-image", tmp_path / "data", FakeEngine(copy.deepcopy(cat)))
    folder = tmp_path / "Characters"
    folder.mkdir()
    for name, size in CAST.items():
        Image.new("RGB", size).save(folder / name)
    ctx.files = Files(tmp_path / "data", None, folder)
    await models.catalog(ctx)
    return ctx


def press(**extra: Any) -> dict:
    return {"model": REF2VA, "mode": "refs", "prompt": "<Picture 1> waves", "loras": [], "images": 1,
            "width": 960, "height": 544, "steps": None, "guidance": None, "seed": {"mode": "random"}, **extra}


def test_mixed_cut_out_boxes_are_refused_on_a_line_with_one_switch(ref_ctx):
    boxes = ["chars/Character 11.png", "chars/Character 4.png"]
    label = entry(models.cached(), REF2VA)["name"]
    for cut in ([True], [True, False], [False, True]):
        with pytest.raises(Invalid) as err:
            build.image_job(press(references=boxes, cutout=cut), ref_ctx)
        assert (err.value.field, err.value.text) == ("cutout", f"Cut-out is on or off for every box on {label}")
    for cut in ([True, True], [False, False], None):
        request = build.image_job(press(references=boxes, cutout=cut), ref_ctx).tasks[0]
        assert [r["role"] for r in request["references"]] == ["identity", "identity"]
        task = sent(models.cached(), enginewire.request_parse(request))
        assert task["remove_background_images_ref"] == int(cut == [True, True])


def test_the_built_clip_is_what_upstream_takes(ref_ctx):
    """From the press to the task: the identities in box order with no name, the window at the clip."""
    request = build.image_job(press(references=["chars/Character 11.png", "chars/Character 12.png"], frames=107),
                              ref_ctx).tasks[0]
    task = sent(models.cached(), enginewire.request_parse(request))
    assert set(task) <= ACCEPTED and task["video_prompt_type"] == "I" and task["sliding_window_size"] == 124
    assert [Path(p).name for p in task["image_refs"]] == ["Character 11.png",
                                                          "Character 12.png"] and task["prompt"] == "<Picture 1> waves"
