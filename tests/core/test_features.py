"""The core's tool publisher: a module's screen, listings and actions become MCP tools, schemas and labels
generated from the declarations alone."""
from __future__ import annotations

from typing import Any

import pytest

from hub.core.api import Action, Ctx, Invalid, Listing, Module, Screen, Setting
from hub.core.features import NO_ARGS, lora_schema, tools_of
from hub.core.schema import check

CALLS: list[tuple[str, Any]] = []


async def read(ctx: Ctx) -> dict:
    CALLS.append(("read", ctx))
    return {"size": "m", "mp": 1.5, "steps": 4, "name": "x", "loras": [], "seed": "random"}


async def write(ctx: Ctx, changes: dict) -> dict:
    CALLS.append(("write", changes))
    return {**await read(ctx), **changes}


async def things(ctx: Ctx, args: dict) -> dict:
    CALLS.append(("things", args))
    return {"things": [args.get("model", "all")]}


async def go(ctx: Ctx, args: dict) -> dict:
    CALLS.append(("go", args))
    return {"went": args["text"]}


SETTINGS = (Setting("size", "choice", choices=("s", "m", "l"), text="Size of the thing"),
            Setting("mp", "number", choices=(1, 1.5, 2), text="Megapixels"),
            Setting("steps", "integer", lo=1, hi=50),
            Setting("name", "text", text="Name of the thing"),
            Setting("loras", "loras", lo=0, hi=2, text="Active LoRAs"),
            Setting("seed", "seed", lo=0, hi=999_999_999, text="Seed"))
MOD = Module(id="demo-thing", title="Demo Thing", screen=Screen(SETTINGS, read, write),
             listings=(Listing("things", "Things of a model.", {"model": {"type": "string"}}, things,
                               required=("model",)),
                       Listing("all_things", "Every thing.", {}, things)),
             actions=(Action("go_thing", "Go.", {"type": "object", "required": ["text"],
                                                 "properties": {"text": {"type": "string"}}}, go),))


@pytest.fixture(autouse=True)
def clear() -> None:
    CALLS.clear()


def test_names_descriptions_and_order_come_from_the_declarations() -> None:
    tools = tools_of(MOD)
    assert [t.name for t in tools] == ["get_demo_thing_settings", "set_demo_thing_settings", "list_things",
                                       "list_all_things", "go_thing"]
    assert [t.description for t in tools] == [
        "Settings of the Demo Thing screen: size, mp, steps, name, loras, seed.",
        "Set settings of the Demo Thing screen: size, mp, steps, name, loras, seed. Returns the settings after.",
        "Things of a model.", "Every thing.", "Go."]
    assert tools_of(Module(id="bare", title="Bare")) == []


def test_the_set_schema_is_built_from_the_settings() -> None:
    get, set_ = tools_of(MOD)[:2]
    assert get.input_schema == NO_ARGS
    assert set_.input_schema == {"type": "object", "additionalProperties": False, "properties": {
        "size": {"type": "string", "enum": ["s", "m", "l"], "description": "Size of the thing"},
        "mp": {"type": "number", "enum": [1, 1.5, 2], "description": "Megapixels"},
        "steps": {"type": "integer", "minimum": 1, "maximum": 50},
        "name": {"type": "string", "description": "Name of the thing"},
        "loras": {"type": "array", "items": lora_schema(0, 2), "description": "Active LoRAs"},
        "seed": {"type": "string", "minLength": 1, "maxLength": 9,
                 "description": "Seed: random, or a whole number from 0 to 999999999"}}}
    assert "required" not in set_.input_schema, "any subset"
    free = tools_of(Module(id="f", title="F", screen=Screen((Setting("model", "choice"),), read, write)))[1]
    assert free.input_schema["properties"] == {"model": {"type": "string"}}, "no choices: any text, checked live"
    small = tools_of(Module(id="f", title="F", screen=Screen((Setting("seed", "seed", lo=0, hi=99),
                                                                 Setting("loras", "loras", lo=0, hi=1.5)), read,
                                                                write)))[1]
    assert small.input_schema["properties"]["seed"] == {"type": "string", "minLength": 1, "maxLength": 2,
                                                       "description": "random, or a whole number from 0 to 99"}
    assert small.input_schema["properties"]["loras"]["items"]["properties"]["strength"] == \
        {"type": "number", "minimum": 0, "maximum": 1.5}, "the bounds are the module's, never the core's"
    short = tools_of(Module(id="f", title="F", screen=Screen((Setting("note", "text", hi=12, text="A note"),), read,
                                                            write)))[1]
    assert short.input_schema["properties"]["note"] == {"type": "string", "maxLength": 12, "description": "A note"}
    with pytest.raises(Invalid, match=r"note is too long \(at most 12 characters\)"):
        check(short.input_schema, {"note": "x" * 13})


def test_a_names_setting_is_a_list_of_at_most_hi_names() -> None:
    cast = tools_of(Module(id="f", title="F", screen=Screen((Setting("references", "names", hi=3,
                                                                     text="Characters in the boxes"),), read,
                                                             write)))[1]
    assert cast.input_schema["properties"]["references"] == {
        "type": "array", "maxItems": 3, "items": {"type": "string", "minLength": 1, "maxLength": 120},
        "description": "Characters in the boxes"}, "the names themselves are checked live by the screen's write"
    check(cast.input_schema, {"references": []})
    check(cast.input_schema, {"references": ["Character 42", "Character 36"]})
    for bad in ({"references": ["a", "b", "c", "d"]}, {"references": [""]}, {"references": ["x" * 121]},
                {"references": "Character 42"}, {"references": [7]}):
        with pytest.raises(Invalid):
            check(cast.input_schema, bad)


def test_listing_and_action_schemas() -> None:
    _, _, things_, all_, go_ = tools_of(MOD)
    assert things_.input_schema == {"type": "object", "additionalProperties": False,
                                    "properties": {"model": {"type": "string"}}, "required": ["model"]}
    assert all_.input_schema == {"type": "object", "additionalProperties": False, "properties": {}}
    assert go_.input_schema is MOD.actions[0].schema, "an action's schema is published as it is"


@pytest.mark.parametrize("args, error", [
    ({"size": "xl"}, "size must be one of: s, m, l"),
    ({"mp": 3}, "mp must be one of: 1, 1.5, 2"),
    ({"steps": 0}, "steps must be at least 1"),
    ({"steps": "4"}, "steps must be a whole number"),
    ({"name": 1}, "name must be text"),
    ({"loras": [{"id": "a"}]}, "strength is required"),
    ({"loras": [{"id": "a", "strength": 2.5}]}, "strength must be at most 2"),
    ({"loras": [{"id": "a", "strength": 1, "name": "x"}]}, "unknown argument name"),
    ({"seed": ""}, "seed must not be empty"),
    ({"seed": "1234567890"}, "seed is too long (at most 9 characters)"),
    ({"seed": 5}, "seed must be text"),
    ({"other": 1}, "unknown argument other"),
])
def test_the_generated_schema_refuses_bad_values_with_one_line(args: dict, error: str) -> None:
    set_ = tools_of(MOD)[1]
    with pytest.raises(Invalid) as err:
        check(set_.input_schema, args)
    assert err.value.text == error


async def test_the_generated_tools_call_the_declared_functions() -> None:
    get, set_, things_, all_, go_ = tools_of(MOD)
    ctx: Any = object()
    seen = await get.fn(ctx, check(get.input_schema, {}))
    assert seen["size"] == "m" and CALLS == [("read", ctx)]
    changed = await set_.fn(ctx, check(set_.input_schema, {"size": "l", "seed": "7", "loras": [{"id": "a",
                                                                                                  "strength": 1}]}))
    assert (changed["size"], changed["seed"], changed["loras"]) == ("l", "7", [{"id": "a", "strength": 1}])
    assert CALLS[1] == ("write", {"size": "l", "seed": "7", "loras": [{"id": "a", "strength": 1}]}), "as given"
    assert await set_.fn(ctx, check(set_.input_schema, {})) == await get.fn(ctx, {}), "nothing to set: as is"
    assert await things_.fn(ctx, check(things_.input_schema, {"model": "m"})) == {"things": ["m"]}
    assert await all_.fn(ctx, check(all_.input_schema, {})) == {"things": ["all"]}
    assert await go_.fn(ctx, check(go_.input_schema, {"text": "t"})) == {"went": "t"}
    with pytest.raises(Invalid, match="model is required"):
        check(things_.input_schema, {})
