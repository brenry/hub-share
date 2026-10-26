"""The last-picked model of each kind (`lastModel` in the draft): the server keeps it whenever the
draft's model changes (a window's PUT: the pulldown, the Video button, the fold); switching kinds never clears
a model's LoRAs or Advanced. No tool changes the model: the assistant writes for the pulldown's model."""
from __future__ import annotations

import json

import pytest

from hub.core.api import Invalid
from hub.core.features import tools_of
from hub.core.schema import check
from hub.modules.generate_image import manifest, routes
from tests.engine.continue_kit import FUSED, IMAGE, PRUNED, dump_catalog, make_ctx
from tests.engine.helpers import FakeRequest

REFS = "z_image"
LORA = [{"id": f"{IMAGE}/style/film_grain.safetensors", "strength": 0.65}]


@pytest.fixture(scope="module")
def clip_models(tmp_path_factory) -> list[dict]:
    return dump_catalog(tmp_path_factory.mktemp("engine"))


@pytest.fixture
async def ctx(tmp_path, clip_models):
    return await make_ctx(tmp_path, clip_models)


async def put_draft(ctx, **body) -> dict:
    return await routes.put_draft(ctx, FakeRequest(body=json.dumps(body).encode()))


async def put_defaults(ctx, **body) -> dict:
    return await routes.put_defaults(ctx, FakeRequest(body=json.dumps(body).encode()))


def uninstall(ctx, model_id: str) -> None:
    """The model's files are gone (a copy: the clip models are shared by the module's tests)."""
    ctx.engine.catalog["models"] = [{**m, "status": "missing"} if m["id"] == model_id else m
                                    for m in ctx.engine.catalog["models"]]


async def test_the_draft_keeps_a_pick_of_each_kind_and_every_models_settings(ctx):
    await put_draft(ctx, model=IMAGE, lorasByModel={IMAGE: LORA},
                    advancedByModel={IMAGE: {"steps": 6, "guidance": None, "seed": {"mode": "random"}}})
    assert ctx.doc(routes.DRAFT, {}).get()["lastModel"] == {"image": IMAGE, "video": ""}
    after = await put_draft(ctx, model=PRUNED, lastModel={"image": "nope", "video": "nope"})
    assert after["lastModel"] == {"image": IMAGE, "video": PRUNED}, "a video model: .video set, .image kept"
    after = await put_draft(ctx, model=REFS)
    assert after["lastModel"] == {"image": REFS, "video": PRUNED}, "a picture model: .image set, .video kept"
    assert after["lorasByModel"] == {IMAGE: LORA} and after["advancedByModel"][IMAGE]["steps"] == 6, "nothing cleared"
    assert (await put_draft(ctx, prompt="a fox"))["lastModel"] == {"image": REFS, "video": PRUNED}, "no model: kept"


async def test_a_clip_placed_in_box_1_is_the_last_video_pick(ctx):
    draft = {"model": IMAGE}
    routes.pick(draft, ctx.engine.catalog, PRUNED)
    assert draft == {"model": PRUNED, "lastModel": {"image": IMAGE, "video": PRUNED}}, "the model it leaves too"
    routes.pick(draft, ctx.engine.catalog, "gone")
    assert draft == {"model": "gone", "lastModel": {"image": IMAGE, "video": PRUNED}}, "an unknown id: not kept"


async def call(ctx, name: str, args: dict) -> dict:
    """A generated tool as the tool server runs it: the argument check, then the function."""
    tool = next(t for t in tools_of(manifest.MODULE) if t.name == name)
    return await tool.fn(ctx, check(tool.input_schema, args))


async def test_the_assistant_cannot_change_the_model(ctx):
    """With a video model picked, no tool takes `model`: every value (`{model: "image"}` included) is refused by
    the schema, the draft and its last picks untouched, nothing told; the settings the assistant may set land on the
    pulldown's model."""
    await put_defaults(ctx, text=IMAGE, video=FUSED)
    await put_draft(ctx, model=REFS)
    await put_draft(ctx, model=PRUNED)
    before = ctx.doc(routes.DRAFT, {}).get()
    sent = ctx.bus.sent
    sent.clear()
    for value in ("image", "video", REFS, IMAGE, FUSED):
        with pytest.raises(Invalid, match="unknown argument model"):
            await call(ctx, "set_generate_image_settings", {"model": value, "draft": "Picture 1 text"})
    assert ctx.doc(routes.DRAFT, {}).get() == before and sent == []
    assert "draft" not in routes.session_part(ctx), "refused as a whole: the draft did not land either"
    after = await call(ctx, "set_generate_image_settings", {"steps": 5})
    assert after["model"] == PRUNED and sent[-1][1:] == ("draft", {}), "the pulldown's pick, and no switch to say"
    assert ctx.doc(routes.DRAFT, {}).get()["lastModel"] == before["lastModel"], "the last picks are not touched"
    assert not {"defaults", "lastModel"} & set(after), "no `defaults` or `lastModel` reported"
    assert (await call(ctx, "get_generate_image_settings", {}))["model"] == PRUNED


def test_the_last_speech_pick_is_kept_across_picture_picks():
    """A speech model picked, then two picture models: `lastModel.speech` is still the speech model,
    `image` the last picture; a draft with no speech pick has no `speech` key."""
    cat = {"models": [{"id": "h3", "kind": "speech"}, {"id": "flux"}, {"id": "krea"}]}
    draft: dict = {"model": "flux"}
    routes.pick(draft, cat, "krea")
    assert draft["lastModel"] == {"image": "krea", "video": ""}, "no speech pick: no speech key"
    for model_id in ("h3", "flux", "krea"):
        routes.pick(draft, cat, model_id)
    assert draft == {"model": "krea", "lastModel": {"image": "krea", "video": "", "speech": "h3"}}
