"""The default models: `PUT /defaults` keeps a text and a refs default (picture models) and a video default (a clip
model), for the Video button and fold. No tool reads them to change the pulldown."""
from __future__ import annotations

import json

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.modules.generate_image import routes, tools
from tests.engine.continue_kit import DAY, FUSED, IMAGE, PRUNED, dump_catalog, make_ctx
from tests.engine.helpers import FakeRequest

TEXT, REFS = IMAGE, "z_image"


@pytest.fixture(scope="module")
def clip_models(tmp_path_factory) -> list[dict]:
    return dump_catalog(tmp_path_factory.mktemp("engine"))


@pytest.fixture
async def ctx(tmp_path, clip_models):
    return await make_ctx(tmp_path, clip_models)


async def put(ctx, **body) -> dict:
    return await routes.put_defaults(ctx, FakeRequest(body=json.dumps(body).encode()))


async def test_the_defaults_never_move_the_users_pick(ctx):
    """The defaults are where the Video button and fold go from a model of the other kind (`switchKind`, a
    click);
    a tool call never lands on one: with every default set and a picture in the boxes, the model stays the pulldown's,
    and neither the settings nor list_image_models report the defaults any more (their one use was the words)."""
    await put(ctx, text=TEXT, refs=REFS, video=PRUNED)
    pic = ctx.files.roots["out"] / DAY / "r1.png"
    pic.parent.mkdir(parents=True)
    Image.new("RGB", (64, 64)).save(pic)
    routes.session_part(ctx)["references"] = [{"id": f"out/{DAY}/r1.png", "w": 64, "h": 64}]
    ctx.doc(routes.DRAFT, {}).replace({"model": FUSED, "aspect": "16:9"})
    after = await tools.write_settings(ctx, {"draft": "Picture 1 text", "megapixels": 2})
    assert after["model"] == FUSED and "defaults" not in after
    assert ctx.doc(routes.DRAFT, {}).get() == {"model": FUSED, "aspect": "16:9", "size": 2}, "no last pick written"
    assert ctx.bus.sent[-1][:3] == ("changed", "draft", {}), "nothing to say: nothing switched"
    assert "defaults" not in await tools.list_image_models(ctx, {})


async def test_the_video_default_is_a_present_clip_model_or_null(ctx):
    assert await routes.get_defaults(ctx, FakeRequest()) == {"text": None, "refs": None, "video": None}
    assert await put(ctx, video=PRUNED) == {"text": None, "refs": None, "video": PRUNED}
    for body, field, text in (({"video": IMAGE}, "video", "Flux 2 Klein 9B makes pictures, not clips"),
                              ({"video": "nope"}, "video", 'No model "nope" in the model folders'),
                              ({"text": PRUNED}, "text", "H3 First / Last — Pruned makes clips, not pictures"),
                              ({"refs": PRUNED}, "refs", "H3 First / Last — Pruned makes clips, not pictures"),
                              ({"clip": PRUNED}, "defaults", "The defaults are text, refs and video")):
        with pytest.raises(Invalid) as err:
            await put(ctx, **body)
        assert (err.value.field, err.value.text) == (field, text)
    assert (await routes.get_defaults(ctx, FakeRequest()))["video"] == PRUNED, "a refused change keeps the default"
    assert await put(ctx, video=None) == {"text": None, "refs": None, "video": None}
