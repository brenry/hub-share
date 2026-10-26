"""The video sizes the size menu offers: a setting (`modules.generate-image.video_tiers`), 540p and 720p by
default, its names checked against the catalog where they are used (unknown ones ignored, never a
crash), and Settings showing the catalog's names with the ones offered, an edit reaching the size menu."""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from hub.core.runtime import Core
from hub.modules.generate_image import models
from hub.settings import validate
from tests.engine.helpers import FakeCtx, FakeEngine
from tests.engine.test_settings_live import _engine_hub

ALL = ("480p", "540p", "720p", "1080p")


def clip(model_id: str, *tiers: str) -> dict:
    return {"id": model_id, "kind": "video", "video": {"tiers": [{"name": t, "sizes": {"1:1": [i * 64 + 64] * 2}}
                                                                 for i, t in enumerate(tiers)]}}


CATALOG = {"models": [{"id": "pic", "kind": "image", "video": None}, clip("wide", *ALL),
                      clip("narrow", "540p", "720p")]}


@pytest.fixture
async def ctx(tmp_path):
    c = FakeCtx("generate-image", tmp_path / "data", FakeEngine(copy.deepcopy(CATALOG)))
    await models.catalog(c)
    return c


def offered(model_id: str) -> list[str]:
    facts = models.video(models.find(models.cached(), model_id))
    assert facts is not None
    return [t["name"] for t in facts["tiers"]]


def test_the_default_is_the_owners_menu(ctx):
    assert ctx.settings["video_tiers"] == ["540p", "720p"]
    assert offered("wide") == ["540p", "720p"] and offered("narrow") == ["540p", "720p"], "those the model has"
    assert models.video(models.find(models.cached(), "pic")) is None


@pytest.mark.parametrize(("setting", "wide", "narrow"), [
    (["720p", "1080p"], ["720p", "1080p"], ["720p"]),
    (["1080p", "540p"], ["540p", "1080p"], ["540p"]),           # the model's order, smallest first
    (["8k", "720p"], ["720p"], ["720p"]),                       # a name the catalog does not report is ignored
    (["8k"], ["480p", "540p", "720p"], ["540p", "720p"]),       # none it reports: the model's first three
    (3, ["480p", "540p", "720p"], ["540p", "720p"]),
    (1, ["480p"], ["540p", "720p"]),
])
def test_the_owners_sizes_are_checked_against_the_catalog_at_use(ctx, setting, wide, narrow):
    ctx.settings["video_tiers"] = setting
    assert (offered("wide"), offered("narrow")) == (wide, narrow)


def test_an_edit_applies_at_the_next_use_and_the_canvas_follows(ctx):
    facts = models.video(models.find(models.cached(), "wide"))
    assert models.tier_size(facts, "1:1", 1.0, 1) == (128, 128)
    ctx.settings = {**ctx.settings, "video_tiers": ["720p", "1080p"]}       # as a settings edit replaces it
    facts = models.video(models.find(models.cached(), "wide"))
    assert models.tier_size(facts, "1:1", 1.0, 1) == (192, 192) and models.tier_size(facts, "1:1", 1.0, 2) == (256, 256)


def test_odd_values_never_crash(ctx):
    for odd in (None, "540p", {"a": 1}, True):
        ctx.settings["video_tiers"] = odd
        assert offered("wide") == ["480p", "540p", "720p"], "anything else: the model's first three"
    assert models.offered_tiers(None, 2) == [] and models.offered_tiers({"models": []}, ["540p"]) == []


def view(cat: dict | None, setting: object) -> dict:
    s = validate({"modules": {"generate-image": {"video_tiers": setting}}})
    engine = SimpleNamespace(cached_catalog=lambda: cat)
    return Core._video_tiers(SimpleNamespace(engine=engine, settings=s))  # type: ignore[arg-type]


def test_settings_show_the_catalogs_names_and_the_ones_offered():
    assert view(CATALOG, 2) == {"names": list(ALL), "offered": ["480p", "540p"]}
    assert view(CATALOG, ["1080p", "8k", "540p"]) == {"names": list(ALL), "offered": ["540p", "1080p"]}
    assert view(CATALOG, ["8k"])["offered"] == ["480p", "540p", "720p"]
    assert view(None, 2) == {"names": [], "offered": []}, "no catalog read yet: nothing to pick from"
    assert Core._video_tiers(SimpleNamespace(engine=object(), settings=validate({})))["names"] == []  # type: ignore


async def test_a_settings_edit_reaches_the_size_menu(tmp_path):
    _, lane, hub = await _engine_hub(tmp_path)
    try:
        cookie = hub.pair()
        await lane.query("models")
        seen = (await hub.http("GET", "/api/settings", cookie)).json()
        names = seen["video_tiers"]["names"]
        assert seen["video_tiers_max"] == 3 and seen["video_tiers"]["offered"] == ["540p", "720p"] and len(names) >= 3
        r = await hub.http("PATCH", "/api/settings", cookie,
                           json_body={"modules": {"generate-image": {"video_tiers": [names[2], "8k"]}}})
        assert r.status == 200 and r.json()["video_tiers"]["offered"] == [names[2]], "8k: not the catalog's, ignored"
        bar = (await hub.http("GET", "/api/generate-image/models", cookie)).json()
        menus = [[t["name"] for t in m["video"]["tiers"]] for m in bar if m["kind"] == "video"]
        assert menus and all(menu == [names[2]] for menu in menus), "the size menu offers the saved pick"
        bad = await hub.http("PATCH", "/api/settings", cookie,
                             json_body={"modules": {"generate-image": {"video_tiers": ["a", "b", "c", "d"]}}})
        assert bad.status == 400 and bad.json()["field"] == "modules.generate-image.video_tiers"
    finally:
        await hub.close()
        await lane.stop()
