"""The cast (`start.py`, `frame.py`, `tools.py`): `script_start` offers the model only the Characters names the story
names (as written, case included, a whole word, a longer name before its first word, a name's first word
alone), every name when it names none; `context_set`'s `remove: true` takes a member out (refused only
while the member has lines), refused with `to` or for a name not in the cast, the file unchanged after each refusal; the
tool lock is one per event loop."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from hub.modules.director import schemas, start, tools
from tests.engine.test_media_characters import png_bytes
from tests.engine.test_script_tools import Ctx, call, on_disk, refused


def _member(name: str, home: int) -> dict:
    return {"name": name, "look": f"{name}'s look", "costume": "A suit", "ignore": "The background", "home": home}


class Echo:
    """A stand-in model that answers with a context cast from the names its schema's enum offers."""

    def __init__(self) -> None:
        self.offered: list[list[str]] = []
        self.system: list[str] = []

    async def __call__(self, messages: list[dict], schema: dict | None = None) -> tuple[str, str]:
        if not messages:
            return "qwen3.5:9b", ""
        names = schema["properties"]["cast"]["items"]["properties"]["name"]["enum"]
        self.offered.append(names)
        self.system.append(messages[0]["content"])
        context = {"cast": [_member(n, 10 + 10 * i) for i, n in enumerate(names)],
                 "set": {"name": "The stage", "description": "A bare stage", "elements": ["Table"],
                         "props": [{"name": "Mug", "owner": names[0], "description": "A white mug"}]},
                 "style": "Bright light"}
        return "qwen3.5:9b", json.dumps(context)


@pytest.fixture
def ctx(tmp_path: Path) -> Ctx:
    made = Ctx(tmp_path)
    for name in ("Character 8", "Character 5", "Character 10", "One Two"):
        (tmp_path / "Characters" / f"{name}.png").write_bytes(png_bytes())
    made.model = Echo()
    return made


async def _start(ctx: Ctx, story: str) -> list[str]:
    await call(ctx, "script_start", {"name": "Script 1", "story": story})
    return [m["name"] for m in on_disk(ctx)["context"]["cast"]]


async def test_only_the_names_the_story_names_are_offered(ctx: Ctx) -> None:
    cast = await _start(ctx, "Character 7 meets Character 8 to character 10 it out in a character 5's kitchen")
    assert cast == ["Character 7", "Character 8"] and ctx.model.offered == [["Character 7", "Character 8"]]
    assert "only these names from Characters: Character 7, Character 8." in ctx.model.system[0]


def test_a_name_in_another_case_is_not_named() -> None:
    every = ["Character 10", "Character 5", "Character 6", "Character 7", "Character 8", "One Two"]
    assert start.named("CHARACTER 7 meets character 8 on the stage; the character 5s watch", every) == every


def test_a_first_word_alone_names_its_name() -> None:
    assert start.named("One meets Character 8", ["One Three", "Character 8"]) == ["One Three", "Character 8"]
    assert start.named("One", ["One", "One Two"]) == ["One"]
    assert start.named("The scene opens; One waves", ["One", "The Four"]) == ["One"]
    assert start.named("One's friend", ["One", "Character 8"]) == ["One"]
    assert start.named("One waves", ["One Two", "One Three", "Character 8"]) == ["One Two", "One Three"]


async def test_a_longer_name_wins_over_its_first_word(ctx: Ctx) -> None:
    assert await _start(ctx, "One Two meets Character 5") == ["Character 5", "One Two"]
    assert start.named("One Two and One", ["One", "One Two"]) == ["One", "One Two"]


async def test_a_story_naming_none_offers_every_name(ctx: Ctx) -> None:
    every = ["Character 10", "Character 5", "Character 6", "Character 7", "Character 8", "One Two"]
    assert await _start(ctx, "A figure meets another") == every and ctx.model.offered == [every]


async def _written(ctx: Ctx) -> None:
    """Script 1: Character 7, Character 8 and Character 5 in the context (Character 7 owns the mug); scene 1 cast
    Character 7, Character 8; Character 8's line l1."""
    await _start(ctx, "Character 7 meets Character 8")
    await call(ctx, "context_set", {"cast": [_member("Character 5", 80)]})
    await call(ctx, "scene_add", {"title": "The opening", "cast": ["Character 7", "Character 8"]})
    await call(ctx, "shot_add", {"scene": 1, "camera": "Wide shot of the stage"})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 8", "words": "Thank you, friend."})


async def test_remove_takes_a_member_out(ctx: Ctx) -> None:
    await _written(ctx)
    done = await call(ctx, "context_set", {"cast": [{"name": "character 5", "remove": True, "home": 5}]})
    assert done["state"][1] == "context · removed Character 5 · cast Character 7, Character 8 · set The stage · style"
    assert [m["name"] for m in on_disk(ctx)["context"]["cast"]] == ["Character 7", "Character 8"]
    kept = await call(ctx, "context_set", {"cast": [{"name": "Character 8", "home": 60, "remove": False}]})
    assert kept["state"][1] == "context · cast Character 7, Character 8 · set The stage · style"
    assert on_disk(ctx)["context"]["cast"][1] == {**_member("Character 8", 20), "home": 60}, "remove is never stored"


async def test_remove_is_refused_while_the_member_has_lines(ctx: Ctx) -> None:
    await _written(ctx)
    got = await refused(ctx, "context_set", {"cast": [{"name": "Character 8", "remove": True}]})
    assert got == {"problem": "Character 8 still has lines",
                   "fix": "Remove those lines with event_remove, then send this again", "hints": {"lines": ["l1"]}}
    done = await call(ctx, "context_set", {"cast": [{"name": "Character 7", "remove": True}]})
    assert done["state"][1].startswith("context · removed Character 7 · poses ")
    assert done["state"][1].endswith(" · scenes 1 · props Mug · cast Character 8, Character 5 · set The stage · style")
    script = on_disk(ctx)
    assert script["scenes"][0]["cast"] == ["Character 8"] and script["context"]["set"]["props"][0]["owner"] is None
    assert not [ev for ev in script["scenes"][0]["shots"][0]["events"] if ev.get("character") == "Character 7"]


async def test_remove_with_to_and_an_unknown_name_are_refused(ctx: Ctx) -> None:
    await _written(ctx)
    got = await refused(ctx, "context_set", {"cast": [{"name": "Character 5", "remove": True, "to": "Character 10"}]})
    assert got == {"problem": "remove or to, not both", "fix": "Send remove or to for a member, not both",
                   "hints": {"context_cast": ["Character 7", "Character 8", "Character 5"]}}
    got = await refused(ctx, "context_set", {"cast": [{"name": "Character 10", "remove": True}]})
    assert got == {"problem": "Character 10 is not in the context's cast",
                   "fix": "Name a member of the context's cast to remove",
                   "hints": {"context_cast": ["Character 7", "Character 8", "Character 5"]}}


def test_the_schema_and_the_description_offer_remove() -> None:
    [action] = [a for a in tools.ACTIONS if a.name == "context_set"]
    assert action.text.endswith("; remove: true takes a member out.")
    assert schemas.MEMBER["properties"]["remove"] == {"type": "boolean"}


def test_the_lock_is_one_per_event_loop() -> None:
    async def lock() -> Any:
        async with tools._guard():
            return tools._guard()
    first, second = asyncio.run(lock()), asyncio.run(lock())
    assert first is not second, "a new loop meets a new lock, never one bound to the old loop"
