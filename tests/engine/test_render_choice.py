"""The render side: the Director picks each shot's model from the catalog's facts alone
(`generate_image/storyclip.py` `way`), never the pulldown; a shot with nobody pictured renders; a cast member with no
picture is made from the context's words; a shot with no model that renders from words starts from a still drawn first,
chained by `inputs` (`hub/modules/director/render.py`). The branches on stubbed catalogs; the job on the H3 capture's
catalog (`test_upstream_rules.cat`). Neutral names only."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from hub.core import jobgraph
from hub.core.files import Files
from hub.modules.director import drawing, frame, render, routes, scripts, tools
from hub.modules.generate_image import models, storyclip
from hub.modules.generate_image import routes as groutes
from tests.engine import test_upstream_rules as rules
from tests.engine.helpers import FakeCtx, FakeEngine, FakeRequest
from tests.engine.test_script_render import Ctx

cat = rules.cat
NAME = "Script 1"
P1, P2, P3 = "Person 1", "Person 2", "Person 3"          # P1 and P2 have pictures in Characters; P3 has none
REF2VA, FL2VA, PAINTER = "minimax_h3_ref2va", "minimax_h3_fl2va", "flux2_klein_9b"   # each kind's first present


def stub(ident: str, refs: dict | None) -> dict:
    """A present video model of the catalog's shape, its pictures `refs` (None: it takes none)."""
    video = {"tiers": [{"name": "t1", "sizes": {"16:9": [960, 544]}}], "fps": 24, "steps": 8,
             "frames": {"min": 17, "step": 8, "max": 121, "default": 49}, **({"references": refs} if refs else {})}
    return {"id": ident, "kind": "video", "video": video}


IDS = stub("Model 1", {"role": "identity", "min": 0, "max": 3})
IDS_ONLY = stub("Model 2", {"role": "identity", "min": 1, "max": 3})
FIRST = stub("Model 3", {"role": "start", "min": 0, "max": 1})
FIRST_ONLY = stub("Model 4", {"role": "start", "min": 1, "max": 1})
WORDS = stub("Model 5", None)


def chosen(videos: list[dict], refer: bool, start: bool, painter: bool = True) -> tuple[str, str] | None:
    got = storyclip.way(videos, refer, start, painter)
    return (got[0]["id"], got[1]) if got else None


# ---------------------------------------------------------------- the choice, catalogs stubbed
def test_reference_takes_the_identity_model() -> None:
    assert chosen([FIRST, IDS], True, False) == ("Model 1", "identity")
    assert chosen([FIRST, IDS], True, True) == ("Model 1", "identity"), "anyone reference wins"


def test_frame_takes_the_first_frame_model() -> None:
    assert chosen([IDS, FIRST], False, True) == ("Model 3", "start")


def test_each_falls_to_the_other_kind_when_its_own_is_absent() -> None:
    assert chosen([FIRST], True, False) == ("Model 3", "start")
    assert chosen([IDS], False, True) == ("Model 1", "identity")


def test_nobody_pictured_renders_from_words() -> None:
    assert chosen([WORDS, FIRST, IDS], False, False) == ("Model 1", "words"), "the identity model first"
    assert chosen([WORDS, FIRST], False, False) == ("Model 3", "words")
    assert chosen([WORDS, IDS_ONLY], False, False) == ("Model 5", "words")
    assert chosen([IDS_ONLY, FIRST], True, False) == ("Model 2", "identity")


def test_no_words_model_draws_a_still_first() -> None:
    assert chosen([IDS_ONLY, FIRST_ONLY], False, False) == ("Model 4", "still")
    assert chosen([IDS_ONLY, FIRST_ONLY], False, False, painter=False) is None
    assert chosen([IDS_ONLY], False, False) is None


# ---------------------------------------------------------------- the job, on the H3 capture
@pytest.fixture
async def ctx(tmp_path: Path, cat: dict) -> Any:
    await drawing.stop()
    render.running.clear()
    chars = tmp_path / "Characters"
    chars.mkdir()
    for name in (P1, P2):
        Image.new("RGB", (600, 900), (90, 90, 90)).save(chars / f"{name}.png")
    files = Files(tmp_path / "data", None, chars)
    gen = FakeCtx("generate-image", tmp_path / "data", FakeEngine(copy.deepcopy(cat)))
    gen.files = files
    gen.doc(groutes.DRAFT, {}).replace({"model": FL2VA, "lastModel": {"video": FL2VA}})
    await models.catalog(gen)
    held = Ctx(tmp_path, gen, files)
    context = {"cast": [{"name": n, "look": f"Subject {k}", "costume": f"wardrobe {k}"}
                      for k, n in enumerate((P1, P2, P3), 1)],
             "set": {"name": "Scene 1", "description": "prop 1", "elements": [], "props": []}}
    scripts.create(routes.folder(held), NAME, {"version": 2, "context": context, "scenes": []}, routes.characters(held))
    yield held
    await drawing.stop()


async def shots(ctx: Ctx, *ons: list[str], use: dict[str, str] | None = None) -> None:
    """One scene of the three, one shot per `ons` (who is on), then each member's `picture_use` set on disk."""
    await tools._write(ctx, lambda s, c, ch: frame.scene_add(s, {"title": "Scene 1", "cast": [P1, P2, P3]}), None,
                       NAME)
    for on in ons:
        body = json.dumps({"name": NAME, "op": "add_shot", "scene": 1, "camera": {"framing": "shot s1", "on": on}})
        assert "problem" not in await routes.post_edit(ctx, FakeRequest(body=body.encode()))
    path = routes.folder(ctx) / f"{NAME}.json"
    script = json.loads(path.read_text(encoding="utf-8"))
    for member in script["context"]["cast"]:
        if member["name"] in (use or {}):
            member["picture_use"] = use[member["name"]]   # type: ignore[index]
    path.write_text(json.dumps(script), encoding="utf-8")


def planned(ctx: Ctx) -> Any:
    got = render.press(ctx, NAME)
    assert "job" in got and got["skipped"] == [], got
    return ctx.jobs.get(got["job"]).plan


async def test_a_shot_with_nobody_and_one_with_no_picture_render(ctx: Ctx) -> None:
    await shots(ctx, [], [P3])
    plan = planned(ctx)
    empty, alone, _ = plan.tasks
    assert empty["model"] == alone["model"] == REF2VA and empty["references"] == alone["references"] == []
    assert "Subject 3" in alone["prompt"] and "wardrobe 3" in alone["prompt"], "made from the context's words"
    assert ctx.gen.doc(groutes.DRAFT, {}).get()["model"] == FL2VA, "the pulldown never read nor changed"


async def test_a_pictured_member_beside_one_with_none(ctx: Ctx) -> None:
    await shots(ctx, [P1, P3])
    task = planned(ctx).tasks[0]
    assert task["model"] == REF2VA and task["references"] and all(r["role"] == "identity" for r in task["references"])
    assert all(P3 not in r["path"] for r in task["references"]) and "Subject 3" in task["prompt"]


async def test_frame_starts_from_the_picture_and_none_uses_no_picture(ctx: Ctx) -> None:
    await shots(ctx, [P1], [P2], use={P1: "frame", P2: "none"})
    first, second, _ = planned(ctx).tasks
    assert first["model"] == FL2VA and [r["role"] for r in first["references"]] == ["start"]
    assert first["references"][0]["path"].endswith(f"{P1}.png")
    assert second["model"] == REF2VA and second["references"] == []


async def test_the_still_is_chained_before_its_clip(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storyclip, "from_words", lambda m: False)     # no model renders from words alone
    await shots(ctx, [], [P1])
    plan = planned(ctx)
    still, clip, pictured, join = plan.tasks
    assert still["kind"] == "image" and still["model"] == PAINTER and still["references"] == []
    assert "shot s1" in still["prompt"] and "Scene 1" in still["prompt"] and "prop 1" in still["prompt"]
    assert clip["model"] == FL2VA and clip["references"] == [{"path": "", "role": "start", "name": None,
                                                              "cutout": False}]
    assert pictured["model"] == REF2VA
    assert plan.inputs == ({}, {"references.0.path": (1, "file")}, {},
                           {"items.0.path": (2, "kept"), "items.1.path": (3, "kept")})
    jobgraph.check(plan)
    assert jobgraph.between(plan) == {1}, "the still is the clip's, never kept"
    sent = jobgraph.fill(clip, plan.inputs[1], {1: "/x/still.png"}, 2)
    assert sent["references"][0]["path"] == "/x/still.png" and clip["references"][0]["path"] == ""
    assert len(plan.summary["step_names"]) == len(plan.tasks) and "first frame" in plan.summary["step_names"][0]
    assert plan.finish.clips == [2, 3]
