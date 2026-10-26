"""Stage 9 closing (part A): the storyboard never runs a model by a saved id that
another model had on the line before; a window that loaded the draft before the ids moved has its own old ids brought
over; the accepted-settings check never switches itself off; the upstream facts file is read once."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.generate_image import models, routes
from hub.modules.storyboard import screen as board
from hub.worker import faults
from hub.worker.adapters import upstream
from tests.engine.helpers import FakeCtx, FakeEngine, FakeRequest

PRUNED, FULL = "minimax_h3_ref2va_pruned", "minimax_h3_ref2va"
VIDEO = {"tiers": [{"name": "540p", "sizes": {"16:9": [960, 544]}}], "frames": {"min": 107, "step": 17, "max": 362,
                                                                                 "default": 124}, "fps": 24}


def clip_model(model_id: str, was: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    out = {"id": model_id, "name": model_id, "family": "H3", "status": "available", "kind": "video",
           "video": copy.deepcopy(VIDEO), **extra}
    return {**out, "was": was} if was else out


def picture_model(model_id: str, **extra: Any) -> dict[str, Any]:
    return {"id": model_id, "name": model_id, "family": "Qwen", "status": "available", "kind": "image", "video": None,
            "steps": 40, "guidance": 4, "guidance_key": "guidance_scale", "modes": ["new", "refs"], "block": 32,
            **extra}


CAT = {"engine": {"api": "upstream"}, "models": [
    clip_model(PRUNED, was=[FULL]), clip_model(FULL, was=["minimax_h3_ref2va_full"]),
    clip_model("minimax_h3_fl2va_pruned", was=["minimax_h3"]),
    picture_model("qwen_image_21_7B", was=["qwen_image_21"]),
    {"id": "viggle_animate", "name": "Viggle", "family": "H3", "status": "available", "kind": "video", "video": None,
     "why_not": "It follows a control video, which the Hub does not send"}]}


# ---------------------------------------------------------------- A.1: the storyboard's saved ids
@pytest.mark.parametrize(("saved", "clip", "text"), [
    (FULL, True, "Choose the clip model again in the storyboard settings"),
    ("minimax_h3", True, "Choose the clip model again in the storyboard settings"),
    ("qwen_image_21", False, "Choose the picture model again in the storyboard settings"),
])
def test_the_storyboard_refuses_an_id_another_model_had_before(saved, clip, text):
    with pytest.raises(Invalid) as err:
        board.find(CAT, saved, clip)
    assert (err.value.field, err.value.text) == ("model" if clip else "picture_model", text)
    assert board.find(CAT, PRUNED, True)["id"] == PRUNED and board.find(CAT, "qwen_image_21_7B", False)


def test_the_storyboards_picture_model_is_never_a_model_the_hub_cannot_drive():
    with pytest.raises(Invalid) as err:
        board.find(CAT, "viggle_animate", False)
    assert (err.value.field, err.value.text) == ("picture_model", "No picture model with the id viggle_animate can run")


# ---------------------------------------------------------------- A.2: windows and the move
@pytest.fixture
async def ctx(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(models, "_last", None)
    monkeypatch.setattr(models, "_ctx", None)
    return FakeCtx("generate-image", tmp_path / "data", FakeEngine(copy.deepcopy(CAT)))


def fork_draft() -> dict[str, Any]:
    return {"model": FULL, "lastModel": {"image": "qwen_image_21", "video": FULL},
            "advancedByModel": {FULL: {"steps": 5}, "minimax_h3": {"steps": 7}}, "size": 1}


async def put(ctx: FakeCtx, body: dict[str, Any]) -> dict[str, Any]:
    return await routes.put_draft(ctx, FakeRequest(body=json.dumps(body).encode()))


async def test_a_save_that_starts_the_move_does_not_write_the_old_draft_back(ctx):
    """The race fixed in 0c904a1: the catalog this save fetches makes the move; the save then reads the moved draft."""
    ctx.doc(routes.DRAFT, {}).replace(fork_draft())
    after = await put(ctx, {"model": "minimax_h3_fl2va_pruned"})
    assert after["engine"] == "upstream" and after["model"] == "minimax_h3_fl2va_pruned"
    assert after["advancedByModel"] == {PRUNED: {"steps": 5}, "minimax_h3_fl2va_pruned": {"steps": 7}}
    assert after["lastModel"] == {"image": "qwen_image_21_7B", "video": "minimax_h3_fl2va_pruned"}


async def test_a_window_that_loaded_before_the_move_has_its_ids_brought_over(ctx):
    ctx.doc(routes.DRAFT, {}).replace(fork_draft())
    await models.catalog(ctx)                                      # the move
    stale = {"advancedByModel": {FULL: {"steps": 9}, "minimax_h3": {"steps": 11}}, "lorasByModel": {FULL: []}}
    after = await put(ctx, stale)                                  # no `engine`: loaded before the move
    assert after["advancedByModel"] == {PRUNED: {"steps": 9}, "minimax_h3_fl2va_pruned": {"steps": 11}}
    assert after["lorasByModel"] == {PRUNED: []} and after["engine"] == "upstream"
    fresh = await put(ctx, {"advancedByModel": {FULL: {"steps": 30}}, "engine": "upstream", "model": FULL})
    assert fresh["advancedByModel"] == {FULL: {"steps": 30}} and fresh["model"] == FULL, "the 33B, picked on upstream"


async def test_a_window_on_the_line_the_draft_names_is_taken_as_it_is(ctx, monkeypatch):
    """No move yet (the draft names no line): nothing is renamed, whatever the window sends."""
    ctx.doc(routes.DRAFT, {}).replace({"size": 1})
    monkeypatch.setattr(models, "_last", {"engine": {"api": "legacy"}, "models": []})
    after = await put(ctx, {"advancedByModel": {FULL: {"steps": 3}}})
    assert after["advancedByModel"] == {FULL: {"steps": 3}} and "engine" not in after


# ---------------------------------------------------------------- A.3, A.4: the upstream adapter
def test_a_root_that_does_not_say_which_settings_it_accepts_is_refused_before_it_opens(tmp_path):
    (tmp_path / "shared" / "utils").mkdir(parents=True)
    with pytest.raises(faults.Unready) as err:
        upstream.Upstream().prepare(str(tmp_path))
    assert str(err.value) == "This engine does not say which settings it accepts"
    (tmp_path / "shared" / "utils" / "setting_names.py").write_text("def accepted_setting_names():\n    return []\n")
    upstream.Upstream().prepare(str(tmp_path))


def test_a_missing_list_is_refused_each_time_and_never_kept(monkeypatch):
    monkeypatch.setattr(upstream, "_accepted", [])
    monkeypatch.setattr(upstream, "ACCEPTED", ("hub_no_such_module.setting_names", "accepted_setting_names"))
    for _ in range(2):
        with pytest.raises(faults.Refused, match="^This engine does not say which settings it accepts$"):
            upstream.translate({"model_type": "m", "image_mode": 1}, {})
    assert upstream._accepted == [], "a miss is never kept"


def test_the_facts_file_is_read_once(monkeypatch):
    calls: list[str] = []
    upstream.facts_file.cache_clear()
    real = upstream.read_facts
    monkeypatch.setattr(upstream, "read_facts", lambda path: calls.append(path) or real(path))
    for model_type in ("qwen_image_21_turbo_7B", "minimax_h3_fl2va_pruned", "flux2_klein_9b"):
        upstream.line_facts(None, model_type, {})
    assert len(calls) == 1
    upstream.facts_file.cache_clear()
    facts = upstream.Upstream().facts()
    facts["renamed"]["ids"].clear()
    assert upstream.facts_file()["renamed"]["ids"], "a caller's copy, never the cached file"
