"""Generate Image module: manifest, routes (models, draft) and what the tool server publishes from it. No tool
renders unasked: a picture is made by the Generate press, or by a generate_image call, from the
assistant's draft beside the chat; the draft never reaches the prompt box."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from hub.core import engine
from hub.core.api import Invalid
from hub.core.features import tools_of
from hub.core.files import Files
from hub.core.schema import check
from hub.modules.generate_image import build, chain, manifest, models, routes, screen, tools
from tests.engine.helpers import FakeCtx, FakeEngine, FakeRequest, load_catalog, write_lora
from tests.engine.test_engine_lane import Probes

NOT_SET_UP = "The engine's Python or folder is not set up; run hub init"
NO_ARGS = {"type": "object", "properties": {}, "additionalProperties": False}
NAMES = ["get_generate_image_settings", "set_generate_image_settings", "list_image_models", "list_characters",
         "generate_image", "direct_clip", "direct_scene", "redo_shot"]
SETTING_NAMES = ["draft", "shot", "steps", "guidance", "megapixels", "aspect", "count", "seed", "loras"]
SCRIPT = " Not for a chat started with Script:, which the script tools write."
DESCRIPTIONS = {
    "get_generate_image_settings": "Settings of the Generate Image screen: draft, shot, steps, guidance, "
                                   "megapixels, aspect, count, seed, loras.",
    "set_generate_image_settings": "Set settings of the Generate Image screen: draft, shot, steps, guidance, "
                                   "megapixels, aspect, count, seed, loras. Returns the settings after.",
    "list_image_models": "Models that can run, with default size and steps.",
    "list_characters": "Characters by name, with the notes on each, the words for its voice and whether it "
                       "has a voice sample, from the Characters folder.",
    "generate_image": "Render the draft with the screen's settings, as the Generate button does." + SCRIPT,
    "direct_clip": "Plan and render one clip from request, its words as written." + SCRIPT,
    "direct_scene": "Plan, render and cut a scene of several shots from request, its words as written."
                    + SCRIPT,
    "redo_shot": "Render one shot of a scene again on a new seed and cut the scene again with it.",
}
OWN_WORDS = "the words as typed"


def box(ctx: Any, text: str, references: list | None = None) -> None:
    """The assistant's draft and the reference boxes a Generate window holds: the session's part, never on disk.
    The prompt box holds the words as typed: no tool reads or writes it."""
    routes.session_part(ctx).update({"draft": text, "prompt": OWN_WORDS, "references": references or []})


class Bus:
    """Records what is published; `windows` is how many Generate windows presence counts (one, as a rule)."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict, str | None]] = []
        self.windows = 1

    def publish(self, lane: str, type: str, data: dict, key: str | None = None) -> None:
        self.sent.append((lane, type, data, key))

    def presence(self) -> dict:
        return {"screens": {"workspace": self.windows, "media": 0, "aux": 0}}


@pytest.fixture
def ctx(tmp_path):
    loras = tmp_path / "loras"
    write_lora(loras / "flux2_klein_9b" / "style" / "film_grain.safetensors")
    c = FakeCtx("generate-image", tmp_path / "data", FakeEngine(load_catalog("catalog_upstream.json", loras),
                                                                resident="z_image"))
    c.bus = Bus()
    return c


def test_manifest_declares_tab_sockets_routes_and_tools():
    m = manifest.MODULE
    assert (m.id, m.title, m.tab.label) == ("generate-image", "Generate Image", "Generate Image")
    assert [(s.id, s.label, s.kinds, s.max) for s in m.sockets] == [("reference", "Reference", ("image",), 6),
                                                                    ("sound", "Sound", ("audio",), 1),
                                                                    ("video", "Video", ("video",), 1)]
    assert {(r.method, r.path) for r in m.routes} == {("GET", "/models"), ("GET", "/draft"), ("PUT", "/draft"),
                                                     ("GET", "/defaults"), ("PUT", "/defaults"), ("GET", "/weights"),
                                                     ("POST", "/weights/rescan"), ("PUT", "/weights/base"),
                                                     ("POST", "/seed/random"), ("GET", "/characters"),
                                                     ("POST", "/continue"), ("GET", "/model-files"),
                                                     ("PUT", "/model-files")}
    assert m.lanes == ("changed",)
    assert (m.card.title, m.card.order) == ("Generate Image", 880)
    assert set(m.jobs) == {"image"}
    assert [s.name for s in m.screen.settings] == SETTING_NAMES
    assert [x.name for x in m.listings] == ["image_models", "characters"]
    assert [a.name for a in m.actions] == ["generate_image", "direct_clip", "direct_scene", "redo_shot"]
    assert [t.name for t in tools_of(m)] == NAMES, "the tools are generated from these, not written by hand"
    assert m.listens == {"session.ended": routes.on_session_ended, "chat.cleared": routes.on_chat_cleared,
                         "job.finished": chain.on_job_finished, "job.submitted": build.on_submitted}


async def test_models_route_lists_ui_models(ctx):
    out = await routes.get_models(ctx, FakeRequest())
    klein = next(m for m in out if m["id"] == "flux2_klein_9b")
    assert set(klein) == {"id", "label", "family", "modes", "refCap", "defaults", "guidanceKey", "kind", "video",
                          "budget", "lockSteps"}
    present = {m["id"] for m in ctx.engine.catalog["models"] if m["status"] == "available"}
    assert len(out) == 8 and {m["id"] for m in out} == present, "only models whose files are all there"
    assert "flux_dev_umo" not in {m["id"] for m in out}
    families = [m["family"].lower() for m in out]
    assert families == sorted(families), "grouped by family"
    panel = await routes.get_weights(ctx, FakeRequest())
    assert set(panel) == {"bases", "files"} and {b["id"] for b in panel["bases"]} == present
    ctx.engine = FakeEngine(None)
    assert (await routes.get_weights(ctx, FakeRequest())).status_code == 503
    failed = await routes.get_models(ctx, FakeRequest())
    assert failed.status_code == 503
    assert json.loads(failed.body) == {"code": "unavailable", "text": NOT_SET_UP}


async def test_an_engine_that_is_down_says_so_in_its_own_words(ctx, tmp_path):
    """Every route that needs the catalog answers with the engine's one plain line, never a hub error."""
    down = {"engine": {"python": str(tmp_path / "nope"), "root": str(tmp_path / "missing"), "args": [],
                       "model_folders": []}, "gpus": []}
    ctx.engine, _ = engine.create(down, tmp_path / "down", Probes(None))
    for route in (routes.rescan, routes.get_weights, routes.get_models):
        failed = await route(ctx, FakeRequest())
        assert (failed.status_code, json.loads(failed.body)) == (503, {"code": "unavailable", "text": NOT_SET_UP})
    with pytest.raises(Invalid) as err:
        await routes.put_defaults(ctx, FakeRequest(body=b'{"text": "z_image"}'))
    assert (err.value.field, err.value.text) == ("engine", NOT_SET_UP)
    assert await routes.put_defaults(ctx, FakeRequest(body=b'{"text": null}')) == {"text": None, "refs": None,
                                                                                   "video": None}


async def test_a_model_the_hub_set_up_is_not_a_base(ctx):
    pointer = {**next(m for m in ctx.engine.catalog["models"] if m["id"] == "z_image"), "id": "auto_mine",
               "base": "z_image"}
    ctx.engine.catalog["models"].append(pointer)
    ctx.engine.files = [{"path": "/models/mine.safetensors", "status": "pointer", "model": "auto_mine"},
                        {"path": "/models/new.safetensors", "status": "unknown", "model": None}]
    for base, text in (("auto_mine", "That model is itself a file the Hub set up; pick the model it is set up like"),
                       ("flux_dev_umo", "Pick one of the models listed")):
        body = json.dumps({"path": "/models/new.safetensors", "base": base}).encode()
        with pytest.raises(Invalid) as err:
            await routes.choose_base(ctx, FakeRequest(body=body))
        assert (err.value.field, err.value.text) == ("base", text)


async def test_draft_round_trip_saves_settings_and_holds_the_session(ctx):
    assert await routes.get_draft(ctx, FakeRequest()) == {}
    draft = {"model": "flux2_klein_9b", "prompt": "cat", "lorasByModel": {}, "references": ["out/d/a.png"],
             "selected": "x", "aspect": "auto", "size": 1, "images": 2, "advancedByModel": {}}
    sent = {**draft, "mode": "refs", "editImage": "e", "anything": 1}
    draft["lastModel"] = {"image": "flux2_klein_9b", "video": ""}
    assert await routes.put_draft(ctx, FakeRequest(body=json.dumps(sent).encode())) == draft, "unknown keys drop"
    assert await routes.get_draft(ctx, FakeRequest()) == draft
    on_disk = ctx.doc(routes.DRAFT, {}).get()
    assert set(on_disk) == {"model", "lorasByModel", "aspect", "size", "images", "advancedByModel", "lastModel"}
    part = await routes.put_draft(ctx, FakeRequest(body=b'{"prompt": ""}'))
    assert part == {**draft, "prompt": ""}, "a window sends what it changed; the rest is kept, not wiped"
    assert ctx.doc(routes.DRAFT, {}).get()["size"] == 1
    await routes.on_session_ended(ctx, {})
    assert await routes.get_draft(ctx, FakeRequest()) == on_disk, "the session's part is gone, the settings stay"
    for bad in (b"[1, 2]", b"{nope"):
        with pytest.raises(Invalid):
            await routes.put_draft(ctx, FakeRequest(body=bad))


async def test_an_older_draft_with_a_prompt_is_settled_at_start(ctx):
    ctx.doc(routes.DRAFT, {}).replace({"model": "z_image", "prompt": "an old prompt", "mode": "edit",
                                       "editImage": {"id": "in/e.png"}, "references": [{"id": "in/r.png"}]})
    await manifest.start(ctx)
    for task in list(manifest._warm):
        await task
    assert ctx.doc(routes.DRAFT, {}).get() == {"model": "z_image"}
    assert await routes.get_draft(ctx, FakeRequest()) == {"model": "z_image"}


def test_card_says_the_seed(ctx):
    assert routes.card(ctx).summary == "Random seed"
    fixed = {"z_image": {"seed": {"mode": "fixed", "value": 7}}}
    ctx.doc("draft", {}).replace({"model": "z_image", "advancedByModel": fixed})
    assert (routes.card(ctx).summary, routes.card(ctx).status) == ("Seed 7", "ok")


async def test_start_warms_the_model_list(ctx):
    await manifest.start(ctx)
    for task in list(manifest._warm):
        await task
    assert ctx.engine.calls == 1


def test_generated_tools_say_what_the_screen_has_and_nothing_about_when():
    generated = {t.name: t for t in tools_of(manifest.MODULE)}
    assert {n: t.description for n, t in generated.items()} == DESCRIPTIONS, "labels only; no rule for the model"
    assert generated["list_image_models"].input_schema == NO_ARGS
    assert generated["get_generate_image_settings"].input_schema == NO_ARGS
    setter = generated["set_generate_image_settings"].input_schema
    assert setter["additionalProperties"] is False and "required" not in setter, "any subset of the settings"
    props = setter["properties"]
    assert list(props) == SETTING_NAMES
    assert props["draft"] == {"type": "string",                       # no length cap of the Hub's
                              "description": "The assistant's draft prompt, shown beside the chat"}
    assert "prompt" not in props, "the prompt box is no setting"
    assert "model" not in props and "references" not in props, "the model and the boxes are the screen's alone"
    assert props["steps"] == {"type": "integer", "minimum": 1, "maximum": 100, "description": "Steps the model runs"}
    assert (props["guidance"]["type"], props["guidance"]["minimum"], props["guidance"]["maximum"]) == ("number", 0, 50)
    assert props["megapixels"]["enum"] == [1, 1.5, 2, 4] and props["megapixels"]["type"] == "number"
    assert props["aspect"]["enum"] == ["auto", "1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16"]
    assert (props["count"]["minimum"], props["count"]["maximum"]) == (1, 6)
    assert props["seed"] == {"type": "string", "minLength": 1, "maxLength": 9,
                             "description": "Seed of the first picture: random, or a whole number from 0 to 999999999"}
    assert props["loras"]["type"] == "array" and props["loras"]["items"]["required"] == ["id", "strength"]
    assert props["loras"]["items"]["properties"]["strength"] == {"type": "number", "minimum": 0, "maximum": 2}
    assert generated["list_characters"].input_schema == NO_ARGS
    assert generated["generate_image"].input_schema == NO_ARGS, "the render takes nothing: the words are the draft's"
    assert "push_draft" not in generated and not hasattr(tools, "push_draft"), "the draft never reaches the box"
    for name, t in generated.items():
        for text in (t.description, *descriptions(t.input_schema)):
            for word in ("when", "only", "if ", "should", "must", "never", "always"):
                assert word not in text.lower(), f"{name}: no sentence about when to call a tool, in no label"


def descriptions(schema: Any) -> list[str]:
    """Every `description` in a schema, its properties and its items, at any depth."""
    if not isinstance(schema, dict):
        return []
    own = [schema["description"]] if isinstance(schema.get("description"), str) else []
    below = [*schema.get("properties", {}).values(), schema.get("items")]
    return own + [d for sub in below for d in descriptions(sub)]


async def call(ctx: Any, name: str, args: Any) -> Any:
    """A generated tool as the tool server runs it: the argument check, then the function."""
    tool = next(t for t in tools_of(manifest.MODULE) if t.name == name)
    return await tool.fn(ctx, check(tool.input_schema, args))


async def test_list_image_models(ctx):
    out = await tools.list_image_models(ctx, {})
    ids = [m["id"] for m in out["models"]]
    assert "flux_dev_umo" not in ids and len(ids) == 8
    z = next(m for m in out["models"] if m["id"] == "z_image")
    assert z == {"id": "z_image", "name": "Z-Image Turbo 6B", "size": "1024x1024", "steps": 8, "loaded": True}


SCREEN = {"model": "flux2_klein_9b", "aspect": "16:9", "size": 1.5, "images": 3,
          "lorasByModel": {"flux2_klein_9b": [{"id": "flux2_klein_9b/style/film_grain.safetensors", "strength": 0.65}]},
          "advancedByModel": {"flux2_klein_9b": {"steps": 8, "guidance": None, "seed": {"mode": "random"}}}}


async def test_get_settings_reports_the_screen_and_the_draft(ctx):
    ctx.doc("draft", {}).replace(SCREEN)
    seen = await call(ctx, "get_generate_image_settings", {})
    lora = {"id": "flux2_klein_9b/style/film_grain.safetensors", "file": "style/film_grain.safetensors"}
    assert seen == {"draft": "", "shot": None, "model": "flux2_klein_9b", "model_name": seen["model_name"],
                    "loras": [{**lora, "strength": 0.65}], "steps": 8, "guidance": None, "aspect": "16:9",
                    "megapixels": 1.5, "width": 1680, "height": 944, "count": 3, "seed": "random", "last_seeds": [],
                    "references": [], "last_clip": ""}
    box(ctx, "a fox at dawn")
    assert (await call(ctx, "get_generate_image_settings", {}))["draft"] == "a fox at dawn", "the draft as it is"
    assert "prompt" not in seen, "the prompt box is not read"
    assert ctx.bus.sent == [], "reading publishes nothing"


async def test_set_draft_writes_the_panel_of_every_window_and_never_the_disk_or_the_box(ctx):
    """The draft setting is the assistant's panel beside the chat: GET /draft hands it to a window, draft.json
    never holds it, the prompt box is never touched, and the one `changed` makes every open Generate
    window redraw the panel."""
    ctx.doc("draft", {}).replace(SCREEN)
    writes = ctx.docs["draft"].writes
    box(ctx, "the old draft")
    after = await call(ctx, "set_generate_image_settings", {"draft": "a grape orchard under a volcano"})
    assert after["draft"] == "a grape orchard under a volcano" and after["count"] == 3, "the rest as it was"
    handed = await routes.get_draft(ctx, FakeRequest())
    assert (handed["draft"], handed["prompt"]) == ("a grape orchard under a volcano", OWN_WORDS)
    assert ctx.doc("draft", {}).get() == SCREEN and ctx.docs["draft"].writes == writes, "the disk is not touched"
    assert [x[:3] for x in ctx.bus.sent] == [("changed", "draft", {})]
    assert (await call(ctx, "set_generate_image_settings", {"draft": ""}))["draft"] == ""
    assert routes.session_part(ctx)["draft"] == ""
    for bad, text in ((7, "draft must be text"),):
        with pytest.raises(Invalid) as err:
            await tools.write_settings(ctx, {"draft": bad})   # the screen's own check, under the schema's
        assert (err.value.field, err.value.text) == ("draft", text)
    assert routes.session_part(ctx)["draft"] == "", "refused: the panel is as it was"
    assert (await call(ctx, "set_generate_image_settings", {"draft": "x" * 4001}))["draft"] == "x" * 4001
    both = await call(ctx, "set_generate_image_settings", {"draft": "with a moon", "count": 2})
    assert (both["draft"], both["count"], ctx.doc("draft", {}).get()["images"]) == ("with a moon", 2, 2)
    assert routes.session_part(ctx)["prompt"] == OWN_WORDS, "the prompt box, through it all"
    await routes.on_session_ended(ctx, {})
    assert (await call(ctx, "get_generate_image_settings", {}))["draft"] == "", "the session ended: the draft is gone"


async def test_a_window_copies_or_clears_the_draft_through_put_draft(ctx):
    """A window sends `draft` (Clear empties it) and `prompt` (its own box) like any session field."""
    ctx.doc("draft", {}).replace(SCREEN)
    box(ctx, "a grape orchard")
    copied = await routes.put_draft(ctx, FakeRequest(body=b'{"prompt": "a grape orchard"}'))
    assert (copied["prompt"], copied["draft"]) == ("a grape orchard", "a grape orchard")
    cleared = await routes.put_draft(ctx, FakeRequest(body=b'{"draft": ""}'))
    assert (cleared["prompt"], cleared["draft"]) == ("a grape orchard", "")
    assert (await call(ctx, "get_generate_image_settings", {}))["draft"] == ""
    assert ctx.doc("draft", {}).get() == SCREEN


async def test_set_draft_needs_a_generate_window(ctx):
    """With no Generate window connected there is no panel to write: refused with one line, nothing held for a
    later session, nothing published; the saved settings still take."""
    ctx.bus.windows = 0
    ctx.doc("draft", {}).replace({"model": "z_image"})
    with pytest.raises(Invalid) as err:
        await call(ctx, "set_generate_image_settings", {"draft": "a grape orchard", "count": 2})
    assert (err.value.field, err.value.text) == ("draft", "No Generate window is open")
    assert routes.session_part(ctx) == {} and ctx.bus.sent == [] and ctx.doc("draft", {}).get() == {"model": "z_image"}
    assert (await call(ctx, "set_generate_image_settings", {"count": 2}))["count"] == 2
    ctx.bus.windows = 1
    assert (await call(ctx, "set_generate_image_settings", {"draft": "an orchard"}))["draft"] == "an orchard"


async def test_set_settings_round_trip_through_the_generated_tools(ctx):
    """What set returns, get returns too; the draft on disk takes the web screen's form; every open Generate window
    hears one `changed` so its bar follows at once."""
    ctx.doc("draft", {}).replace({"model": "flux2_klein_9b"})
    lora = {"id": "flux2_klein_9b/style/film_grain.safetensors", "strength": 0.65}
    after = await call(ctx, "set_generate_image_settings", {"steps": 12, "megapixels": 2, "aspect": "3:2", "count": 2,
                                                            "seed": "7", "loras": [lora]})
    assert after == await call(ctx, "get_generate_image_settings", {})
    assert {k: after[k] for k in ("model", "steps", "guidance", "aspect", "megapixels", "width", "height", "count",
                                  "seed")} == {"model": "flux2_klein_9b", "steps": 12, "guidance": None,
                                               "aspect": "3:2", "megapixels": 2, "width": 1776, "height": 1184,
                                               "count": 2, "seed": "7"}
    assert after["loras"] == [{**lora, "file": "style/film_grain.safetensors"}]
    draft = ctx.doc("draft", {}).get()
    assert draft == {"model": "flux2_klein_9b", "aspect": "3:2", "size": 2, "images": 2,
                     "lorasByModel": {"flux2_klein_9b": [lora]},
                     "advancedByModel": {"flux2_klein_9b": {"steps": 12, "guidance": None,
                                                           "seed": {"mode": "fixed", "value": 7}}}}
    assert [x[:3] for x in ctx.bus.sent] == [("changed", "draft", {})], "told once, to the Generate windows"
    back = await call(ctx, "set_generate_image_settings", {"seed": "random", "loras": []})
    assert (back["seed"], back["loras"]) == ("random", [])
    assert ctx.doc("draft", {}).get()["advancedByModel"]["flux2_klein_9b"]["seed"] == {"mode": "random"}
    ctx.doc("draft", {}).patch({"model": "flux2_klein_base_9b"})          # another model picked
    other = await call(ctx, "set_generate_image_settings", {"guidance": 3.5})
    assert (other["model"], other["steps"], other["guidance"]) == ("flux2_klein_base_9b", 30, 3.5), \
        "the pulldown's pick: its own settings, the model's defaults where nothing was set"
    assert ctx.doc("draft", {}).get()["advancedByModel"]["flux2_klein_9b"]["steps"] == 12, "the other model's stay"


async def test_set_settings_writes_advanced_only_when_it_touches_steps_guidance_or_seed(ctx):
    """As the web screen: aspect, megapixels, count or LoRAs alone leave advancedByModel as it is."""
    ctx.doc("draft", {}).replace({"model": "flux2_klein_9b"})
    lora = {"id": "flux2_klein_9b/style/film_grain.safetensors", "strength": 1}
    for change in ({"aspect": "4:3"}, {"megapixels": 1.5}, {"count": 3}, {"loras": []}, {"loras": [lora]}, {}):
        seen = await call(ctx, "set_generate_image_settings", change)
        assert "advancedByModel" not in ctx.doc("draft", {}).get(), change
        assert seen["steps"] == 4 and seen["seed"] == "random", "the defaults"
    assert ctx.doc("draft", {}).get() == {"model": "flux2_klein_9b", "aspect": "4:3", "size": 1.5, "images": 3,
                                          "lorasByModel": {"flux2_klein_9b": [lora]}}
    await call(ctx, "set_generate_image_settings", {"steps": 6})
    assert ctx.doc("draft", {}).get()["advancedByModel"] == {"flux2_klein_9b": {"steps": 6, "guidance": None,
                                                                              "seed": {"mode": "random"}}}


@pytest.mark.parametrize("args, text", [
    ({"steps": 0}, "steps must be at least 1"),
    ({"steps": 2.5}, "steps must be a whole number"),
    ({"guidance": 51}, "guidance must be at most 50"),
    ({"guidance": 3.5}, "Flux 2 Klein 9B has no guidance setting"),
    ({"megapixels": 3}, "megapixels must be one of: 1, 1.5, 2, 4"),
    ({"aspect": "5:4"}, "aspect must be one of: auto, 1:1, 4:3, 3:4, 3:2, 2:3, 16:9, 9:16"),
    ({"count": 7}, "count must be at most 6"),
    ({"count": True}, "count must be a whole number"),
    ({"seed": "abc"}, "seed must be random or a whole number from 0 to 999999999"),
    ({"seed": "1234567890"}, "seed is too long (at most 9 characters)"),
    ({"seed": 7}, "seed must be text"),
    ({"loras": [{"id": "flux2_klein_9b/nope.safetensors", "strength": 1}]},
     'No LoRA "flux2_klein_9b/nope.safetensors" in this model\'s folder'),
    ({"loras": [{"id": "flux2_klein_9b/style/film_grain.safetensors", "strength": 3}]},
     "strength must be at most 2"),
    ({"loras": [{"id": "flux2_klein_9b/style/film_grain.safetensors"}]}, "strength is required"),
    ({"loras": [{"id": "flux2_klein_9b/style/film_grain.safetensors", "strength": 1}] * 2},
     'A LoRA is listed twice: "flux2_klein_9b/style/film_grain.safetensors"'),
    ({"model": "z_image"}, "unknown argument model"),
    ({"references": []}, "unknown argument references"),
    ({"draft": 7}, "draft must be text"),
    ({"prompt": "x"}, "unknown argument prompt"),
    ({"text": "x"}, "unknown argument text"),
])
async def test_set_settings_refuses_a_bad_value_with_one_line(ctx, args, text):
    ctx.doc("draft", {}).replace(SCREEN)
    with pytest.raises(Invalid) as err:
        await call(ctx, "set_generate_image_settings", args)
    assert err.value.text == text
    assert ctx.doc("draft", {}).get() == SCREEN and ctx.bus.sent == [], "nothing changed, nothing told"


async def test_set_takes_back_what_get_reported_with_one_value_changed(ctx):
    """The second change of a conversation: a model often hands back the settings the last call returned, one value
    changed. Open WebUI drops the keys the schema does not name (model_name, width, height) and passes the rest,
    `guidance: null` included, which is how get reports a model without guidance. A null is the same as leaving the
    setting out: the change lands, nothing is refused, and `steps: 15.0` is 15."""
    ctx.doc("draft", {}).replace(SCREEN)
    box(ctx, "a fox")
    before = await call(ctx, "get_generate_image_settings", {})
    assert before["guidance"] is None and before["steps"] == 8
    echo = {k: v for k, v in before.items() if k in SETTING_NAMES}
    after = await call(ctx, "set_generate_image_settings", {**echo, "steps": 15})
    assert after["steps"] == 15 and after["loras"] == before["loras"] and after["draft"] == "a fox"
    assert ctx.doc("draft", {}).get()["advancedByModel"]["flux2_klein_9b"]["steps"] == 15
    again = await call(ctx, "set_generate_image_settings", {**echo, "steps": 22.0, "guidance": None, "draft": None})
    assert again["steps"] == 22 and (await call(ctx, "get_generate_image_settings", {}))["draft"] == "a fox"


async def test_get_settings_reports_width_and_height_as_the_bar_would_render_them(ctx):
    """Aspect and megapixels from the saved draft; Auto follows reference 1's shape (0.4-2.5), else 1:1, as the
    window's canvas does; the prompt box is never part of what a tool sees."""
    ctx.doc("draft", {}).replace(SCREEN)
    ctx.doc("defaults", {}).replace({"text": "z_image", "refs": "krea2_turbo"})
    box(ctx, "a fox")
    seen = await call(ctx, "get_generate_image_settings", {})
    assert (seen["width"], seen["height"], seen["model"]) == (1680, 944, "flux2_klein_9b"), "16:9 at 1.5 MP"
    assert "prompt" not in seen and OWN_WORDS not in json.dumps(seen)
    ctx.doc("draft", {}).replace({**SCREEN, "aspect": "auto", "size": 2})
    auto = await call(ctx, "get_generate_image_settings", {})
    assert (auto["width"], auto["height"]) == (1456, 1456), "auto is 1:1: no reference image to follow"
    box(ctx, "the fox, as reference 1", [{"id": "out/d/r1.png", "w": 1200, "h": 800}])
    seen = await call(ctx, "get_generate_image_settings", {})
    assert (seen["width"], seen["height"]) == (1776, 1184), "auto follows reference 1's shape, as the bar shows"
    assert screen.auto_ratio([{"w": 10, "h": 1}]) == 2.5 and screen.auto_ratio([{"w": 1, "h": 10}]) == 0.4
    assert screen.auto_ratio([{"id": "x"}]) == 1.0 and screen.auto_ratio([]) == 1.0, "kept within 0.4-2.5"
    assert ctx.bus.sent == [] and ctx.jobs.jobs == {}, "reading publishes nothing and renders nothing"


async def test_no_tool_writes_the_owners_prompt_box(ctx):
    """No `push_draft` tool or function. Every tool leaves the prompt box untouched."""
    ctx.doc("draft", {}).replace(SCREEN)
    box(ctx, "a fox at dawn, in the assistant's words")
    assert "push_draft" not in {t.name for t in tools_of(manifest.MODULE)} and not hasattr(tools, "push_draft")
    await call(ctx, "get_generate_image_settings", {})
    await call(ctx, "set_generate_image_settings", {"draft": "a second draft", "steps": 9})
    await call(ctx, "list_image_models", {})
    await call(ctx, "list_characters", {})
    part = routes.session_part(ctx)
    assert (part["prompt"], part["draft"]) == (OWN_WORDS, "a second draft"), "the draft moved, the box did not"


async def test_new_chat_empties_the_prompt_box_and_the_draft_and_keeps_the_references(ctx):
    """The assistant module's `chat.cleared` (New chat): the session's prompt and draft go, the reference boxes and
    the selection stay, and every open Generate window redraws."""
    ref = {"id": "out/d/r1.png", "w": 1200, "h": 800}
    box(ctx, "a fox at dawn", [ref])
    routes.session_part(ctx)["selected"] = "x"
    await routes.on_chat_cleared(ctx, {})
    assert routes.session_part(ctx) == {"prompt": "", "draft": "", "references": [ref], "selected": "x"}
    assert await routes.get_draft(ctx, FakeRequest()) == {"prompt": "", "draft": "", "references": [ref],
                                                         "selected": "x"}
    assert [x[:3] for x in ctx.bus.sent] == [("changed", "draft", {})]
    assert ctx.docs["draft"].writes == 0 and ctx.doc("draft", {}).get() == {}, "the disk is not written"
    await routes.on_chat_cleared(ctx, {})
    assert [x[:3] for x in ctx.bus.sent] == [("changed", "draft", {})], "already empty: nothing changes, nothing told"
    await routes.on_session_ended(ctx, {})
    await routes.on_chat_cleared(ctx, {})
    assert ctx.data_dir not in routes._session and len(ctx.bus.sent) == 1, "nothing held: no part made, nothing told"
    assert await routes.get_draft(ctx, FakeRequest()) == {}


async def test_route_and_mcp_list_models_whose_main_files_are_present(ctx):
    cat = ctx.engine.catalog
    statuses = {"flux2_klein_9b": "available", "z_image": "partial", "flux": "missing"}
    for m in cat["models"]:
        m["status"] = statuses.get(m["id"], "missing")
    cat["models"].append({**next(m for m in cat["models"] if m["id"] == "flux2_klein_9b"),
                          "id": "flux2_klein_4b", "name": "Flux 2 Klein 4B"})
    route = [m["id"] for m in await routes.get_models(ctx, FakeRequest())]
    tool = [m["id"] for m in (await tools.list_image_models(ctx, {}))["models"]]
    assert route == tool == ["flux2_klein_4b", "flux2_klein_9b", "z_image"], "missing models are not listed"
    ctx.doc("draft", {}).replace({"model": "flux"})
    for name, args in (("get_generate_image_settings", {}), ("set_generate_image_settings", {"count": 2}),
                       ("generate_image", {})):
        box(ctx, "a fox")
        with pytest.raises(Invalid) as err:
            await call(ctx, name, args)
        assert (err.value.field, err.value.text) == ("model", screen.NOT_PICKED), \
            f"{name}: the pulldown's model's files are missing; no other model is chosen"
    assert ctx.doc("draft", {}).get() == {"model": "flux"} and ctx.jobs.jobs == {}, "nothing changed, nothing queued"
    for m in cat["models"]:
        m["status"] = "missing"
    assert await routes.get_models(ctx, FakeRequest()) == []
    assert await tools.list_image_models(ctx, {}) == {"models": []}


async def test_defaults_route_keeps_present_models_only(ctx):
    assert await routes.get_defaults(ctx, FakeRequest()) == {"text": None, "refs": None, "video": None}
    put = await routes.put_defaults(ctx, FakeRequest(body=b'{"text": "z_image", "refs": "flux2_klein_9b"}'))
    assert put == {"text": "z_image", "refs": "flux2_klein_9b", "video": None} == await routes.get_defaults(
        ctx, FakeRequest())
    cleared = await routes.put_defaults(ctx, FakeRequest(body=b'{"text": null}'))
    assert cleared == {"text": None, "refs": "flux2_klein_9b", "video": None}
    for bad, text in ((b'{"refs": "flux"}', 'No model "flux" in the model folders'),
                      (b'{"img": "z_image"}', "The defaults are text, refs and video"),
                      (b"[1]", "The defaults must be a JSON object"), (b"{no", "The defaults is not valid JSON")):
        with pytest.raises(Invalid) as err:
            await routes.put_defaults(ctx, FakeRequest(body=bad))
        assert err.value.text == text
    assert await routes.get_defaults(ctx, FakeRequest()) == {"text": None, "refs": "flux2_klein_9b", "video": None}


async def test_generate_image_renders_the_draft_as_the_generate_button_does(ctx):
    """The assistant's render, a generate_image call: a press of the Generate button — the draft (never the prompt
    box) with the screen's references and settings, queued at once; an empty draft is one line and renders nothing."""
    from tests.engine.helpers import FakeJobs
    ctx.jobs = FakeJobs(ctx, {"image": manifest.MODULE.jobs["image"]})
    ctx.doc("draft", {}).replace(SCREEN)
    box(ctx, "")
    with pytest.raises(Invalid) as err:
        await call(ctx, "generate_image", {})
    assert (err.value.field, err.value.text) == ("draft", "The draft is empty") and ctx.jobs.jobs == {}
    box(ctx, "a lighthouse at dawn, low fog over the rocks")
    assert await call(ctx, "generate_image", {}) == {"state": "queued"}
    [(job, params)] = ctx.jobs.jobs.values()
    assert params["prompt"] == "a lighthouse at dawn, low fog over the rocks", "the draft, not the prompt box"
    assert (params["model"], params["mode"], params["images"], params["steps"]) == ("flux2_klein_9b", "new", 3, 8)
    assert params["loras"] == [{"id": "flux2_klein_9b/style/film_grain.safetensors", "strength": 0.65}]
    assert params["seed"] == {"mode": "random"} and "references" not in params
    assert job.plan.summary["prompt"] == params["prompt"]
    assert routes.session_part(ctx)["prompt"] == OWN_WORDS, "the prompt box is untouched"
    for extra in ({"prompt": "x"}, {"draft": "x"}):
        with pytest.raises(Invalid, match="unknown argument"):
            await call(ctx, "generate_image", extra)


async def test_a_prompt_of_5000_characters_reaches_the_task_whole(ctx):
    """No length cap of the Hub's on a prompt; Generate's press sends it as typed."""
    from tests.engine.helpers import FakeJobs
    ctx.jobs = FakeJobs(ctx, {"image": manifest.MODULE.jobs["image"]})
    ctx.doc("draft", {}).replace(SCREEN)
    box(ctx, "Prompt 1 " + "x" * 4991)
    assert await call(ctx, "generate_image", {}) == {"state": "queued"}
    [(job, params)] = ctx.jobs.jobs.values()
    assert params["prompt"] == "Prompt 1 " + "x" * 4991 and len(job.plan.summary["prompt"]) == 5000


# ---------------------------------------------------------------- the reference boxes by character name
def cast_folder(ctx: Any, tmp_path: Path, names: dict[str, tuple[int, int]]) -> Path:
    """A Characters folder with these pictures (file name -> size), behind real media roots."""
    folder = tmp_path / "Characters"
    folder.mkdir(exist_ok=True)
    for name, size in names.items():
        Image.new("RGB", size).save(folder / name)
    ctx.files = Files(tmp_path / "data", None, folder)
    return folder


async def test_the_assistant_cannot_set_the_boxes(ctx, tmp_path):
    """The boxes are the screen's: the tools report them by name and never set them; a call that sends
    `references` is refused by the schema, the boxes and the disk as they were, nothing told."""
    cast_folder(ctx, tmp_path, {"Character 24.png": (120, 80), "character 23.jpg": (40, 100)})
    ctx.doc("draft", {}).replace(SCREEN)
    hero = {"id": "chars/Character 24.png", "w": 120, "h": 80}
    box(ctx, "a fox", [hero])
    for names in (["character 23"], [], ["Character 24", "character 23"]):
        with pytest.raises(Invalid, match="unknown argument references"):
            await call(ctx, "set_generate_image_settings", {"references": names, "steps": 9})
    assert routes.session_part(ctx)["references"] == [hero] and ctx.bus.sent == []
    assert ctx.doc("draft", {}).get() == SCREEN
    assert (await call(ctx, "get_generate_image_settings", {}))["references"] == ["Character 24"]


async def test_the_boxes_the_user_placed_drive_auto_aspect(ctx, tmp_path):
    cast_folder(ctx, tmp_path, {"Wide.png": (1200, 800)})
    ctx.doc("draft", {}).replace({**SCREEN, "aspect": "auto", "size": 2})
    box(ctx, "", [{"id": "chars/Wide.png", "w": 1200, "h": 800}])
    seen = await call(ctx, "get_generate_image_settings", {})
    assert seen["references"] == ["Wide"] and (seen["width"], seen["height"]) == (1776, 1184), "reference 1's shape"


async def test_handing_back_what_get_reported_keeps_the_boxes(ctx, tmp_path):
    """The echo: get's whole result handed back with one value changed. Open WebUI drops what the schema does not
    name (`references` among it): the boxes stay exactly as placed."""
    cast_folder(ctx, tmp_path, {"Character 24.png": (64, 64)})
    ctx.doc("draft", {}).replace(SCREEN)
    dropped = {"id": "out/2026-10-12/r1.png", "w": 1200, "h": 800}
    hero = {"id": "chars/Character 24.png", "w": 64, "h": 64, "cutout": True}
    box(ctx, "a fox", [dropped, hero])
    before = await call(ctx, "get_generate_image_settings", {})
    assert before["references"] == ["r1", "Character 24"]
    echo = {k: v for k, v in before.items() if k in SETTING_NAMES}
    after = await call(ctx, "set_generate_image_settings", {**echo, "steps": 15})
    assert after["steps"] == 15 and after["references"] == ["r1", "Character 24"]
    assert routes.session_part(ctx)["references"] == [dropped, hero], "the boxes as they were, sizes and all"


async def test_list_characters_and_the_names_route(ctx, tmp_path):
    cast_folder(ctx, tmp_path, {"Character 24.png": (8, 8), "character 20.jpg": (8, 8), ".hidden.png": (8, 8)})
    assert await call(ctx, "list_characters", {}) == {"characters": [{"name": "character 20"},
                                                                     {"name": "Character 24"}]}
    tiles = (await routes.get_characters(ctx, FakeRequest()))["items"]
    assert [(t["name"], t["id"], t["w"], t["h"], t["thumb"].split("?")[0]) for t in tiles] == [
        ("character 20", "chars/character 20.jpg", 8, 8, "/thumbs/chars/character%2020.jpg/336"),
        ("Character 24", "chars/Character 24.png", 8, 8, "/thumbs/chars/Character%2024.png/336")]
    ctx.files.character_notes("chars/Character 24.png", "Note 1; note 2; note 3.")
    assert await call(ctx, "list_characters", {}) == {"characters": [
        {"name": "character 20"}, {"name": "Character 24", "notes": "Note 1; note 2; note 3."}]}, \
        "notes only where there are"
    assert [set(t) for t in (await routes.get_characters(ctx, FakeRequest()))["items"]] == \
        [{"name", "id", "w", "h", "thumb"}] * 2, "Tab: never the notes"
    with pytest.raises(Invalid, match="unknown argument"):
        await call(ctx, "list_characters", {"name": "x"})
    ctx.files = Files(tmp_path / "data")
    assert await call(ctx, "list_characters", {}) == {"characters": []}, "no folder chosen: no characters"
    assert await routes.get_characters(ctx, FakeRequest()) == {"items": []}


def test_a_partial_model_is_listed_unless_a_file_it_needs_is_still_missing():
    """The engine's "partial" (a file not where it looks) is listed when the Hub finds every file (in the model
    folders, by name); one the Hub would refuse (Krea 2 Identity Edit without its LoRA) is not."""
    cat = {"models": [{"id": "mine", "name": "mine", "family": "Krea 2", "status": "partial", "lacks": []},
                      {"id": "edit", "name": "edit", "family": "Krea 2", "status": "partial",
                       "lacks": ["krea2_identity_edit_v1_2.safetensors"]},
                      {"id": "old", "name": "old", "family": "Krea 2", "status": "partial"}]}
    assert [m["id"] for m in models.present(cat)] == ["mine", "old"]
