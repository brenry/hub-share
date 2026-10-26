"""A continued clip keeps the characters in the boxes. On Ref2VA (identities) the boxes after a clip in
box 1 go with it as identity pictures: `video_source` and `image_prompt_type` "V" with `image_refs`, the letters and
the one cut-out switch; a start or end frame beside a clip is still refused; on FL2VA any picture beside the clip is
refused; a continue with box 1 alone is today's task. The catalog and the accepted settings are upstream's own H3
capture (`test_upstream_rules`)."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.core.files import Files
from hub.modules.generate_image import build, chain, models
from hub.worker import enginewire
from hub.worker.engineapi import Reference
from tests.engine import test_upstream_rules as rules
from tests.engine.continue_kit import DAY, LOOSE, STEM, put_clip, real
from tests.engine.helpers import FakeCtx, FakeEngine
from tests.engine.test_upstream_rules import ACCEPTED, CAST, FL2VA, REF2VA, clip, entry, refused, sent

cat, accepted = rules.cat, rules.accepted                 # the H3 capture's fixtures, shared
CHARACTER_7 = "/c/Character 7.png"


def continued(model: str = REF2VA, *more: Reference):
    return clip(model, references=[Reference("/c/scene.mp4", "source"), *more])


# ---------------------------------------------------------------- the task (the worker's adapter)
def test_a_continue_with_identities_sends_them_with_the_clip(cat):
    task = sent(cat, continued(REF2VA, Reference(CHARACTER_7, "identity"), Reference("/c/Character 11.png",
                                                                                     "identity")))
    assert set(task) <= ACCEPTED
    assert (task["image_prompt_type"], task["video_source"]) == ("V", "/c/scene.mp4")
    assert (task["video_prompt_type"], task["image_refs"]) == ("I", [CHARACTER_7, "/c/Character 11.png"])
    assert task["remove_background_images_ref"] == 0
    cut = sent(cat, continued(REF2VA, Reference(CHARACTER_7, "identity", cutout=True)))
    assert cut["remove_background_images_ref"] == 1 and cut["image_prompt_type"] == "V"


def test_box_1_alone_is_todays_continue_byte_for_byte(cat):
    alone = sent(cat, continued(REF2VA))
    assert "image_refs" not in alone and "remove_background_images_ref" not in alone
    assert (alone["image_prompt_type"], alone["video_prompt_type"]) == ("V", "")
    fl2va = sent(cat, continued(FL2VA))
    assert (fl2va["image_prompt_type"], fl2va["video_prompt_type"]) == ("V", "")
    assert "image_refs" not in fl2va


def test_frames_beside_a_clip_and_any_picture_on_fl2va_are_refused(cat):
    for role in ("start", "end"):
        assert refused(cat, continued(REF2VA, Reference(CHARACTER_7,
                                                        role))) == "A continued clip takes no other picture"
        assert refused(cat, continued(FL2VA, Reference(CHARACTER_7, role))) == "A continued clip takes no other picture"
    assert refused(cat, continued(FL2VA, Reference(CHARACTER_7,
                                                   "identity"))) == "A continued clip takes no other picture"
    name = entry(cat, REF2VA)["name"]
    ten = [Reference(f"/c/{n}.png", "identity") for n in range(10)]
    assert refused(cat, continued(REF2VA, *ten)) == f"Too many identities for {name} (10 of 9)"
    mixed = [Reference(CHARACTER_7, "identity", cutout=True), Reference("/c/Character 11.png", "identity")]
    assert refused(cat, continued(REF2VA, *mixed)) == f"Cut-out is on or off for every box on {name}"


# ---------------------------------------------------------------- the press (the controller)
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
    return {"model": model, "mode": "refs", "prompt": "The rain gets louder.", "loras": [],
            "references": [LOOSE] if refs is None else refs, "width": 960, "height": 544, "frames": 124,
            "steps": None, "guidance": None, "seed": {"mode": "fixed", "value": 7}, **extra}


def refusal(ctx, params: dict) -> str:
    with pytest.raises(Invalid) as err:
        build.image_job(params, ctx)
    return err.value.text


def test_the_press_sends_box_2_and_3_as_identities_after_the_clip(ctx):
    plan = build.image_job(press(refs=[LOOSE, "chars/Character 11.png", "chars/Character 12.png"], cutout=[False, True,
                                                                                                           True]), ctx)
    request = plan.tasks[0]
    assert [r["role"] for r in request["references"]] == ["source", "identity", "identity"]
    task = sent(models.cached(), enginewire.request_parse(request))
    assert set(task) <= ACCEPTED
    assert (task["image_prompt_type"], task["video_source"]) == ("V", real(ctx, LOOSE))
    assert [Path(p).name for p in task["image_refs"]] == ["Character 11.png", "Character 12.png"]
    assert (task["video_prompt_type"], task["remove_background_images_ref"]) == ("I", 1)
    assert plan.summary["mode"] == "continue" and plan.summary["references"] == [STEM, "Character 11", "Character 12"]


def test_the_press_with_box_1_alone_is_as_before(ctx):
    plan = build.image_job(press(), ctx)
    assert [r["role"] for r in plan.tasks[0]["references"]] == ["source"]
    assert plan.summary["references"] == [STEM]


def test_source_takes_identities_up_to_the_models_maximum(ctx):
    ref2va, fl2va = (models.find(models.cached(), m) for m in (REF2VA, FL2VA))
    top = models.picture_refs(ref2va)["max"]
    boxes = [LOOSE, *(["chars/Character 11.png"] * top)]
    assert chain.source(ctx, boxes, ref2va) == LOOSE
    with pytest.raises(Invalid) as err:
        chain.source(ctx, [*boxes, "chars/Character 12.png"], ref2va)
    assert err.value.text == f"A continued clip takes at most {top} identities on {ref2va['name']}"
    for model in (fl2va, None):
        with pytest.raises(Invalid) as err:
            chain.source(ctx, [LOOSE, "chars/Character 11.png"], model)
        assert err.value.text == chain.ONLY_BOX_1
    assert chain.source(ctx, [LOOSE, ""], fl2va) == LOOSE, "empty boxes are no pictures"
    with pytest.raises(Invalid):
        chain.source(ctx, ["chars/Character 11.png", LOOSE], ref2va)


def test_fl2va_still_refuses_a_picture_beside_the_clip(ctx):
    put_clip(ctx, f"clips/{DAY}/fl.mp4")
    assert refusal(ctx, press(FL2VA, [f"clips/{DAY}/fl.mp4", "chars/Character 11.png"])) == chain.ONLY_BOX_1


def test_a_continue_sends_a_characters_views_after_the_characters_picture(ctx):
    """A character's views beside a continued clip: they go along, as on a fresh clip."""
    folder = Path(ctx.files._real["chars"])
    Image.new("RGB", (640, 640)).save(folder / "Character 11.side.png")
    request = build.image_job(press(refs=[LOOSE, "chars/Character 11.png"]), ctx).tasks[0]
    assert [(Path(r["path"]).name, r["role"]) for r in request["references"]] == [
        (Path(LOOSE).name, "source"), ("Character 11.png", "identity"), ("Character 11.side.png", "identity")]
