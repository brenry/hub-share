"""Continue a clip, placing it (Stage 6): `POST /continue` puts the clip in box 1 of the pulldown's model when
it continues a clip, else refuses in one line; the clip never moves, the model is never changed, open
windows are told; `last_clip` is the newest clip made; with a clip in box 1 the settings report its size and the
step."""
from __future__ import annotations

import json

import pytest

from hub.core.api import Invalid
from hub.modules.generate_image import chain, routes, screen, tools
from tests.engine.continue_kit import (
    DAY,
    FUSED,
    IMAGE,
    LOOSE,
    OMNI,
    PRUNED,
    STEM,
    dump_catalog,
    make_ctx,
    put_clip,
)
from tests.engine.helpers import FakeRequest

BOX = {"id": LOOSE, "w": 960, "h": 544, "kind": "clip", "seconds": round(124 / 24, 3)}


@pytest.fixture(scope="module")
def clip_models(tmp_path_factory) -> list[dict]:
    return dump_catalog(tmp_path_factory.mktemp("engine"))


@pytest.fixture
async def ctx(tmp_path, clip_models):
    c = await make_ctx(tmp_path, clip_models)
    put_clip(c)
    return c


async def place(ctx, clip_id: object = LOOSE) -> dict:
    return await chain.continue_clip(ctx, FakeRequest(body=json.dumps({"id": clip_id}).encode()))


async def refused(ctx, clip_id: object = LOOSE) -> str:
    with pytest.raises(Invalid) as err:
        await place(ctx, clip_id)
    return err.value.text


def bar(ctx, model: str) -> None:
    ctx.doc(routes.DRAFT, {}).replace({"model": model, "aspect": "16:9", "size": 1, "images": 2})


async def test_a_clip_goes_to_the_selected_model_or_is_refused(ctx):
    """A clip dropped on box 1, or Media's Continue: box 1 of the pulldown's model when it continues a clip; on any
    other model one line names it, the boxes and the draft as they were. The model is never changed."""
    for picked in (PRUNED, FUSED):
        bar(ctx, picked)
        label = next(m["name"] for m in ctx.engine.catalog["models"] if m["id"] == picked)
        assert await place(ctx) == {"id": LOOSE, "model": picked, "label": label}
        assert routes.session_part(ctx)["references"] == [BOX]
        assert ctx.doc(routes.DRAFT, {}).get() == {"model": picked, "aspect": "16:9", "size": 1, "images": 2}, \
            "the draft as it was: no model written, no last pick"
        assert ctx.bus.sent[-1] == ("changed", "draft", {}), "open Generate windows redraw"
    routes.session_part(ctx)["references"] = []
    for picked in (IMAGE, OMNI):
        bar(ctx, picked)
        name = next(m["name"] for m in ctx.engine.catalog["models"] if m["id"] == picked)
        sent = len(ctx.bus.sent)
        assert await refused(ctx) == f"{name} cannot continue a clip"
        assert routes.session_part(ctx)["references"] == [] and len(ctx.bus.sent) == sent
        assert ctx.doc(routes.DRAFT, {}).get()["model"] == picked, "the pulldown's pick stays"
    assert [p.name for p in (ctx.files.roots["clips"] / DAY).iterdir()] == [f"{STEM}.mp4"], "the clip stays put"
    ctx.doc(routes.DRAFT, {}).replace({})
    assert await refused(ctx) == screen.NOT_PICKED, "no model picked: none is chosen"


async def test_the_route_refusals(ctx):
    bar(ctx, PRUNED)
    assert await refused(ctx, f"clips/{DAY}/gone.mp4") == "The clip to continue is gone"
    assert await refused(ctx, "out/2026-10-14/a.png") == "The clip to continue is gone"
    assert await refused(ctx, None) == "The clip to continue is gone"
    put_clip(ctx, f"clips/{DAY}/bad.mp4", b"\0\0\0\x08free")
    assert await refused(ctx, f"clips/{DAY}/bad.mp4") == "This clip is not an MP4 the hub can read"
    put_clip(ctx, f"clips/{DAY}/short.mp4", frames=10)
    assert await refused(ctx, f"clips/{DAY}/short.mp4") == "This clip is shorter than 18 frames"
    put_clip(ctx, f"clips/{DAY}/odd.mp4", w=1000, h=500)
    assert await refused(ctx, f"clips/{DAY}/odd.mp4") == "This clip's size is not one the model makes"
    put_clip(ctx, f"clips/{DAY}/long.mp4", frames=60 * 24)
    assert await refused(ctx, f"clips/{DAY}/long.mp4") == "The scene would be 60 s; the longest is 60 s"
    assert (ctx.files.roots["clips"] / DAY / "long.mp4").is_file() and routes.session_part(ctx) == {}, "untouched"


async def test_the_assistant_cannot_place_a_clip(ctx):
    """The assistant has no Continue: `references` is no setting, so no clip id lands in box 1
    from a tool; a clip is continued from Media or by dropping it on box 1."""
    bar(ctx, PRUNED)
    assert "references" not in {s.name for s in screen.SETTINGS}
    seen = await tools.read_settings(ctx)
    assert seen["references"] == [] and "references" not in routes.session_part(ctx)


async def test_the_settings_report_the_clips_size_and_the_step(ctx):
    put_clip(ctx, f"clips/{DAY}/tall.mp4", w=544, h=960, frames=141)
    bar(ctx, PRUNED)
    await place(ctx, f"clips/{DAY}/tall.mp4")
    seen = await tools.read_settings(ctx)
    assert (seen["aspect"], seen["width"], seen["height"]) == ("16:9", 544, 960), "the clip's size, not the bar's"
    assert seen["seconds"] == round(123 / 24, 2) and seen["references"] == ["tall"]
    routes.session_part(ctx)["references"] = []
    seen = await tools.read_settings(ctx)
    assert (seen["width"], seen["height"], seen["seconds"]) == (960, 544, round(124 / 24, 2)), "as before"


async def test_last_clip_is_the_newest_clip_made(ctx):
    bar(ctx, PRUNED)
    assert (await tools.read_settings(ctx))["last_clip"] == ""
    bar(ctx, IMAGE)
    assert (await tools.read_settings(ctx))["last_clip"] == "", "for every model"
    job = ctx.jobs.submit("image", {"model": FUSED, "mode": "refs", "prompt": "on", "references": [LOOSE],
                                    "width": 960, "height": 544, "frames": 124, "seed": {"mode": "random"}})
    made = put_clip(ctx, f"clips/{DAY}/101530-001.mp4")
    for skip in ({"state": "failed"}, {"tool": "other"}, {"outputs": [f"out/{DAY}/x.png"]}):
        await chain.on_job_finished(ctx, {"job": job.id, "tool": "generate-image", "state": "done",
                                          "outputs": [made], **skip})
        assert "last_clip" not in routes.session_part(ctx), skip
    await chain.on_job_finished(ctx, {"job": job.id, "tool": "generate-image", "state": "done", "outputs": [made]})
    assert (await tools.read_settings(ctx))["last_clip"] == made
    assert "clip_models" not in routes.session_part(ctx), "no clip's model is remembered: the pulldown decides"
    bar(ctx, PRUNED)
    assert (await place(ctx, made))["model"] == PRUNED, "the pulldown's pick, not the model that made the clip"
