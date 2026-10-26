"""A clip in the Video box goes to Ref2VA as its one reference video. The task (the letters joined as
upstream's UI joins them, `video_guide` the clip), each refusal, FL2VA refusing, a clip without a video as today byte
for byte, the catalog fact; the press with a Clips item, a short clip and a continue refused. The catalog and the
accepted settings are upstream's own H3 capture (`test_upstream_rules`)."""
from __future__ import annotations

import copy

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.core.files import Files
from hub.modules.generate_image import build, clipvideo, models
from hub.worker import enginewire
from hub.worker.adapters import refvideo
from hub.worker.engineapi import Reference
from tests.engine import test_upstream_rules as rules
from tests.engine.continue_kit import DAY, LOOSE, put_clip, real
from tests.engine.helpers import FakeCtx, FakeEngine
from tests.engine.test_upstream_rules import ACCEPTED, CAST, FL2VA, REF2VA, clip, entry, refused, sent

cat, accepted = rules.cat, rules.accepted                 # the H3 capture's fixtures, shared
SHOW = "/clips/clip1.mp4"
CHARACTER_7 = Reference("/c/Character 7.png", "identity")


def shown(model: str = REF2VA, seconds: float = 12.0, **extra):
    return clip(model, video=SHOW, video_seconds=seconds, **extra)


# ---------------------------------------------------------------- the catalog and the task
def test_ref2va_offers_one_reference_video_and_its_15_seconds(cat):
    for model_id in ("minimax_h3_ref2va", REF2VA):
        v = entry(cat, model_id)["video"]
        assert (v["reference_video"], v["reference_video_seconds"]) == ("V-U", 362 / 24)
    assert "reference_video" not in entry(cat, FL2VA)["video"]


def test_the_video_joins_the_identity_letters_as_the_engines_ui_does(cat):
    task = sent(cat, shown(references=[CHARACTER_7]))
    assert set(task) <= ACCEPTED
    assert (task["video_prompt_type"], task["video_guide"], task["image_refs"]) == ("IV-U", SHOW,
                                                                                    ["/c/Character 7.png"])
    alone = sent(cat, shown())
    assert (alone["video_prompt_type"], alone["video_guide"]) == ("V-U", SHOW)
    assert refvideo.add_to_sequence("I", "V-U") == "IV-U" and refvideo.add_to_sequence("IV-U", "V-U") == "IV-U"


def test_without_a_video_the_task_is_todays(cat):
    assert sent(cat, clip(REF2VA, references=[CHARACTER_7])) == {
        k: v for k, v in sent(cat, shown(references=[CHARACTER_7])).items() if k != "video_guide"} | {
        "video_prompt_type": "I"}
    assert "video_guide" not in sent(cat, clip(REF2VA))


def test_each_refusal_is_one_line(cat):
    assert refused(cat, shown(FL2VA)) == f"{entry(cat, FL2VA)['name']} takes no reference video"
    assert refused(cat, shown(references=[Reference("/c.mp4", "source")])) == refvideo.VIDEO_CONTINUE
    assert refused(cat, shown(seconds=1.9)) == refvideo.VIDEO_SHORT
    plain = copy.deepcopy(entry(cat, REF2VA))
    del plain["video"]["reference_video"]
    request = enginewire.request_parse(enginewire.request_wire(shown()))
    with pytest.raises(Exception) as err:
        refvideo.merge({}, request, plain, {"source": []})
    assert str(err.value) == f"{plain['name']} takes no reference video"


# ---------------------------------------------------------------- the press
@pytest.fixture
async def ctx(tmp_path, cat):
    c = FakeCtx("generate-image", tmp_path / "data", FakeEngine(copy.deepcopy(cat)))
    folder = tmp_path / "Characters"
    folder.mkdir()
    for name, size in CAST.items():
        Image.new("RGB", size).save(folder / name)
    c.files = Files(tmp_path / "data", None, folder)
    await models.catalog(c)
    put_clip(c)
    return c


def press(model: str = REF2VA, refs: list | None = None, **extra) -> dict:
    return {"model": model, "mode": "refs", "prompt": "<Video 1> is the clip.", "loras": [],
            "references": ["chars/Character 11.png"] if refs is None else refs, "width": 960, "height": 544,
            "frames": 124,
            "steps": None, "guidance": None, "seed": {"mode": "fixed", "value": 7}, **extra}


def refusal(ctx, params: dict) -> str:
    with pytest.raises(Invalid) as err:
        build.image_job(params, ctx)
    return err.value.text


def test_the_press_sends_the_clip_where_it_is(ctx):
    plan = build.image_job(press(video=LOOSE), ctx)
    request = plan.tasks[0]
    assert request["video"] == real(ctx, LOOSE) and request["video_seconds"] == pytest.approx(124 / 24, abs=0.01)
    task = sent(models.cached(), enginewire.request_parse(request))
    assert (task["video_prompt_type"], task["video_guide"]) == ("IV-U", real(ctx, LOOSE))
    assert plan.summary["video"] == "101500-123"
    assert "video" not in build.image_job(press(), ctx).tasks[0] or build.image_job(press(), ctx).tasks[0][
        "video"] is None


def test_the_press_refuses_a_short_clip_a_continue_and_a_model_without_the_box(ctx):
    put_clip(ctx, f"clips/{DAY}/short.mp4", frames=40)
    assert refusal(ctx, press(video=f"clips/{DAY}/short.mp4")) == clipvideo.VIDEO_SHORT
    assert refusal(ctx, press(refs=[LOOSE], video=LOOSE)) == clipvideo.VIDEO_CONTINUE
    label = entry(models.cached(), FL2VA)["name"]
    assert refusal(ctx, press(FL2VA, refs=[], mode="new", video=LOOSE)) == f"{label} takes no reference video"
    assert refusal(ctx, press(video="chars/Character 11.png")) == clipvideo.NOT_A_CLIP


def test_the_assistants_press_sends_the_sound_and_video_boxes_as_the_window_does(ctx):
    """generate_image (the assistant's press) builds the params as the window's buildJob: the Video box and the
    Sound box, so a clip the assistant presses carries the voice."""
    from hub.modules.generate_image import routes, screen, tools
    ctx.doc(routes.DRAFT, {}).replace({"model": REF2VA, "aspect": "16:9", "size": 1, "images": 1})
    held = routes.session_part(ctx)
    held["references"] = [{"id": "chars/Character 11.png", "w": 64, "h": 64}]
    held["video"] = {"id": LOOSE}
    held["sound"] = {"id": "sounds/2026-10-17/character 7.wav"}
    params = tools.press_params(ctx, ctx.engine.catalog, "x")
    assert (params["video"], params["sound"]) == (LOOSE, "sounds/2026-10-17/character 7.wav")
    ctx.doc(routes.DRAFT, {}).replace({"model": FL2VA, "aspect": "16:9", "size": 1, "images": 1})
    params = tools.press_params(ctx, ctx.engine.catalog, "x")
    assert "video" not in params and params["sound"] == "sounds/2026-10-17/character 7.wav", "FL2VA keeps a sound too"
    assert screen.pick_model(ctx.engine.catalog, screen.read(ctx))["id"] == FL2VA
