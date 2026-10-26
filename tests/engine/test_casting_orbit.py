"""The orbit on the real worker's catalog of upstream's H3 definitions (`test_upstream_rules.cat`).
`orbit_pick`: the pulldown's Ref2VA model, else `lastModel`'s video model when Ref2VA, else the only present
one, else one line; the pulldown and `lastModel` only read. `orbit_plan`: the pictures as identities in box order up
to the model's 9 (not the bar's 3), 124 frames, the 9:16 size nearest 704×1280, the card's steps, no detail, no
judge, then a frames request taking the six views from the clip step 1 made (kept)."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
from PIL import Image

from hub.core import jobgraph
from hub.core.api import Invalid
from hub.modules.generate_image import cast, models, orbit, routes
from hub.worker import enginewire
from tests.engine import test_upstream_rules as rules
from tests.engine.test_upstream_rules import FL2VA, REF2VA, sent

cat, accepted, ref_ctx = rules.cat, rules.accepted, rules.ref_ctx
FULL = "minimax_h3_ref2va"
PROMPT = "subject_definitions: <Subject 1> is the character shown in <Picture 1>."


def pictures(ctx, n: int, size: tuple[int, int] = (600, 900)) -> list[str]:
    folder = Path(ctx.files._real["chars"])
    for i in range(n):
        Image.new("RGB", size).save(folder / f"P{i}.png")
    return [f"chars/P{i}.png" for i in range(n)]


def only(ctx, monkeypatch, *missing: str) -> None:
    """The catalog with these models' files gone."""
    held = copy.deepcopy(models.cached())
    for m in held["models"]:
        if m["id"] in missing:
            m["status"] = "missing"
    monkeypatch.setattr(models, "_last", held)


def picked(ctx, draft: dict) -> str:
    ctx.doc(routes.DRAFT, {}).replace(draft)
    found = orbit.orbit_pick(ctx)["id"]
    assert ctx.doc(routes.DRAFT, {}).get() == draft, "the pulldown and lastModel are only read"
    return found


def test_the_pulldowns_ref2va_model_first(ref_ctx):
    assert picked(ref_ctx, {"model": REF2VA, "lastModel": {"video": FULL}}) == REF2VA


def test_else_the_last_video_model_the_user_picked_when_ref2va(ref_ctx):
    assert picked(ref_ctx, {"model": FL2VA, "lastModel": {"image": "", "video": FULL}}) == FULL


def test_else_the_only_present_ref2va_model(ref_ctx, monkeypatch):
    only(ref_ctx, monkeypatch, FULL)
    assert picked(ref_ctx, {"model": FL2VA, "lastModel": {"video": FL2VA}}) == REF2VA
    assert picked(ref_ctx, {"model": FULL}) == REF2VA, "a picked model whose files are gone is not taken"


def test_a_cast_and_its_again_send_no_seed(ref_ctx):
    """Cast and Again give no seed (`casting.routes.queue`); the clip's task has no `seed` key."""
    ref_ctx.doc(routes.DRAFT, {}).replace({"model": REF2VA})
    boxes = pictures(ref_ctx, 2)
    for plan in (orbit.orbit_plan(ref_ctx, boxes, PROMPT), orbit.orbit_plan(ref_ctx, boxes, PROMPT, None)):
        clip = plan.tasks[0]
        assert clip["seed"] is None and plan.summary["seeds"] == []
        assert "seed" not in sent(models.cached(), enginewire.request_parse(clip))


def test_else_one_line(ref_ctx, monkeypatch):
    for draft in ({"model": FL2VA, "lastModel": {"video": FL2VA}}, {}):
        with pytest.raises(Invalid) as err:
            picked(ref_ctx, draft)                       # two Ref2VA models present, neither picked
        assert (err.value.field, err.value.text) == ("model", orbit.NO_REF2VA)
    only(ref_ctx, monkeypatch, FULL, REF2VA)
    with pytest.raises(Invalid) as err:
        picked(ref_ctx, {"model": REF2VA})
    assert err.value.text == "Pick a Ref2VA video model in Generate (one that takes reference pictures)"


def test_the_request_nine_identities_124_frames_portrait_no_detail_no_judge(ref_ctx):
    ref_ctx.doc(routes.DRAFT, {}).replace({"model": REF2VA, "advancedByModel": {REF2VA: {"steps": 12}}})
    boxes = ["chars/Character 11.png", *pictures(ref_ctx, 8)]
    plan = orbit.orbit_plan(ref_ctx, boxes, PROMPT, 7)
    clip, views = plan.tasks
    assert (plan.lane_kind, plan.model, plan.inputs) == ("image", REF2VA, ({}, {"clip": (1, "kept")}))
    assert len(boxes) > cast.BOXES
    assert [(Path(r["path"]).name, r["role"], r["name"], r["cutout"]) for r in clip["references"]] == [
        (Path(b).name, "identity", None, False) for b in boxes]
    assert (clip["kind"], clip["frames"], clip["size"], clip["seed"], clip["prompt"]) == ("video", 124, [704, 1280],
                                                                                          7, PROMPT)
    assert (clip["steps"], clip["detail"], clip["judge"], clip["sound"], clip["video"], clip["voices"]) == (
        12, None, None, None, None, [])
    assert views == {"kind": "frames", "clip": "", "frames": [2, 21, 42, 63, 84, 113]}
    assert plan.summary["step_names"] == ["Orbit", "Views"] and plan.summary["seeds"] == [7]
    jobgraph.check(plan)
    task = sent(models.cached(), enginewire.request_parse(clip))
    assert task["video_prompt_type"] == "I" and [Path(p).name for p in task["image_refs"]] == [
        Path(b).name for b in boxes]
    assert enginewire.request_parse(views).frames == orbit.VIEWS


def test_the_models_own_steps_without_a_card(ref_ctx):
    ref_ctx.doc(routes.DRAFT, {}).replace({"model": REF2VA})
    plan = orbit.orbit_plan(ref_ctx, ["chars/Character 11.png"], PROMPT, 1)
    assert plan.tasks[0]["steps"] == rules.entry(models.cached(), REF2VA)["video"]["steps"] == 20


def test_more_than_the_models_nine_and_a_bit_outside_1_4_are_refused(ref_ctx):
    ref_ctx.doc(routes.DRAFT, {}).replace({"model": REF2VA})
    label = rules.entry(models.cached(), REF2VA)["name"]
    with pytest.raises(Invalid) as err:
        orbit.orbit_plan(ref_ctx, ["chars/Character 11.png", *pictures(ref_ctx, 9)], PROMPT, 1)
    assert err.value.text == f"{label} takes 9 pictures; this cast has 10"
    thin = pictures(ref_ctx, 1, (100, 500))
    with pytest.raises(Invalid) as err:
        orbit.orbit_plan(ref_ctx, ["chars/Character 11.png", *thin], PROMPT, 1)
    assert err.value.text == f"Identity 2 is 100×500: {label} takes pictures between 1:4 and 4:1"
    with pytest.raises(Invalid) as err:
        orbit.orbit_plan(ref_ctx, ["chars/Character 11.png", "chars/Gone.png"], PROMPT, 1)
    assert err.value.text == "An image is missing; add it again"


def test_the_9_16_size_nearest_704x1280_within_the_budget():
    facts = {"tiers": [{"name": "a", "sizes": {"9:16": [480, 864]}}, {"name": "b", "sizes": {"9:16": [704, 1280]}},
                       {"name": "c", "sizes": {"9:16": [1088, 1920], "16:9": [1920, 1088]}}]}
    assert orbit.portrait({"name": "M"}, facts) == (704, 1280)
    assert orbit.portrait({"name": "M", "budget": 500_000}, facts) == (480, 864)
    with pytest.raises(Invalid) as err:
        orbit.portrait({"name": "M"}, {"tiers": [{"name": "a", "sizes": {"16:9": [864, 480]}}]})
    assert err.value.text == "M makes no 9:16 clip"


def test_an_extras_107_frames_and_four_views(ref_ctx):
    """Frames and views from the caller; 107 is on the lattice (17k+5) and runs as it is."""
    ref_ctx.doc(routes.DRAFT, {}).replace({"model": REF2VA})
    plan = orbit.orbit_plan(ref_ctx, ["chars/Character 11.png"], PROMPT, 3, 107, [2, 21, 63, 84])
    clip, views = plan.tasks
    assert clip["frames"] == 107 and plan.summary["frames"] == 107
    assert views == {"kind": "frames", "clip": "", "frames": [2, 21, 63, 84]}
    assert enginewire.request_parse(views).frames == (2, 21, 63, 84)
    jobgraph.check(plan)


@pytest.mark.parametrize("views", [[], [21, 2], [2, 2], [2, 107], [-1, 2], [2.0], [True], "2", None])
def test_views_not_rising_or_past_the_orbit_are_refused(ref_ctx, views):
    ref_ctx.doc(routes.DRAFT, {}).replace({"model": REF2VA})
    with pytest.raises(Invalid) as err:
        orbit.orbit_plan(ref_ctx, ["chars/Character 11.png"], PROMPT, 3, 107, views)
    assert (err.value.field, err.value.text) == ("views", "The views must lie inside the orbit")


def test_the_three_argument_call(ref_ctx):
    ref_ctx.doc(routes.DRAFT, {}).replace({"model": REF2VA})
    clip, views = orbit.orbit_plan(ref_ctx, ["chars/Character 11.png"], PROMPT, 3).tasks
    assert clip["frames"] == orbit.ORBIT == 124 and views["frames"] == list(orbit.VIEWS)


def test_the_service_offered_takes_three_or_five_arguments(ref_ctx):
    from hub.modules.generate_image import manifest as gmanifest
    text = Path(gmanifest.__file__).read_text(encoding="utf-8")
    assert 'ctx.offer("orbit", lambda *args: orbit.orbit_plan(ctx, *args))' in text
