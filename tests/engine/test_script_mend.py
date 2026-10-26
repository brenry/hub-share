"""Mending (`scriptshape.py`, `scripts.py`, `context.py`, `frame.py`, `answer.py`, `tools.py`): a script file whose
event `kind` is a list, or nested too deep, is listed with its one line and every other exception is `Invalid`; a cast
member whose picture is gone from Characters reads, every answer says so on its first line, and `context_set`'s `to`
renames the member everywhere; `script_start` still sends back a context naming someone with no picture."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.director import routes, scripts, scriptshape, start
from tests.engine.test_media_characters import png_bytes
from tests.engine.test_script_shape import FIXTURE
from tests.engine.test_script_tools import CONTEXT, Ctx, Model, call, on_disk, refused

EXAMPLE = json.loads(FIXTURE.read_text(encoding="utf-8"))
CHARS = {"character 7": "chars/Character 7.png", "character 6": "chars/Character 6.png"}
KIND = "Scene 1, shot 1, event c1: kind is line, cue or pose"
DEEP = "The file is nested too deep to read"
NO_SECOND = " · Character 2 has no picture in Characters"


@pytest.fixture
def ctx(tmp_path: Path) -> Ctx:
    return Ctx(tmp_path)


def _folder(ctx: Ctx) -> Path:
    return ctx.files.roots["scripts"]


def _broken(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "Example.json").write_text(json.dumps(EXAMPLE))
    listed = copy.deepcopy(EXAMPLE)
    listed["scenes"][0]["shots"][0]["events"][0]["kind"] = []
    (folder / "Kind.json").write_text(json.dumps(listed))
    (folder / "Deep.json").write_text("[" * 100_000)


def test_a_list_kind_and_a_deep_file_are_listed_with_their_line(ctx: Ctx) -> None:
    folder = _folder(ctx)
    _broken(folder)
    listed = {s["name"]: s["problem"] for s in scripts.listing(folder, CHARS)}
    assert listed == {"Deep": DEEP, "Example": None, "Kind": KIND}
    assert scripts.one(folder, "Kind", CHARS) == {"name": "Kind", "seconds": 0, "problem": KIND, "script": None,
                                                  "pictures": {}, "unpictured": []}
    assert scripts.one(folder, "Deep", CHARS)["problem"] == DEEP
    assert scripts.rename(folder, "Deep", "Deeper") == {"name": "Deeper"}
    scripts.delete(folder, "Deeper")
    assert [s["name"] for s in scripts.listing(folder, CHARS)] == ["Example", "Kind"]


async def test_script_read_answers_those_lines(ctx: Ctx) -> None:
    _broken(_folder(ctx))
    for name, line in (("Kind", KIND), ("Deep", DEEP)):
        got = await refused(ctx, "script_read", {"name": name}, name)
        assert got["problem"] == f"{name} does not read: {line}"


def _paths(value: Any, at: tuple = ()) -> list[tuple]:
    """Every place of a value in the script, nested ones too."""
    items = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else ()
    out = []
    for key, inner in items:
        out.append((*at, key))
        out += _paths(inner, (*at, key))
    return out


def test_the_sweep_raises_only_invalid() -> None:
    for path in _paths(EXAMPLE):
        for value in ([], {}, 1, 1.5, None, True, "x"):
            script = copy.deepcopy(EXAMPLE)
            inner = script
            for key in path[:-1]:
                inner = inner[key]
            inner[path[-1]] = value
            try:
                scriptshape.read(script, CHARS)
            except Invalid:
                pass


def _example(ctx: Ctx) -> None:
    """The fixture as `Script 1` with Character 2 owning a prop, open, Character 4 a picture in Characters, Character
    2's gone."""
    show = copy.deepcopy(EXAMPLE)
    show["context"]["set"]["props"][1]["owner"] = "Character 2"
    _folder(ctx).mkdir(parents=True, exist_ok=True)
    (_folder(ctx) / "Script 1.json").write_text(json.dumps(show))
    ctx.doc("current", {"name": None}).patch({"name": "Script 1"})
    for name in ("Character 7", "Character 6"):                    # Ctx's own pictures; the fixture's cast is numbered
        (_cast(ctx) / f"{name}.png").unlink()
    (_cast(ctx) / "Character 1.png").write_bytes(png_bytes())
    (_cast(ctx) / "Character 4.png").write_bytes(png_bytes())


def _cast(ctx: Ctx) -> Path:
    return ctx.data_dir.parents[1] / "Characters"


async def test_a_missing_picture_reads_is_said_and_renamed_away(ctx: Ctx) -> None:
    _example(ctx)
    one = scripts.one(_folder(ctx), "Script 1", routes.characters(ctx))
    assert one["problem"] is None and one["unpictured"] == ["Character 2"] and list(one["pictures"]) == ["Character 1"]
    added = await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 2", "words": "Thank you."})
    assert added["state"][0].endswith(NO_SECOND)
    read = await call(ctx, "script_read", {})
    assert read["read"][0].endswith(NO_SECOND)
    got = await refused(ctx, "context_set", {"cast": [{"name": "Character 5"}]})
    assert got == {"problem": "Cast and set, cast Character 5: Character 5 has no picture in Characters",
                   "fix": "Cast only names that have a picture in Characters", "hints": {"characters": ["Character 1",
                                                                                                        "Character 4"]}}
    kept = await call(ctx, "context_set", {"cast": [{"name": "Character 2", "costume": "A blue dress"}]})
    assert kept["state"][0].endswith(NO_SECOND), "a field of a member without a picture is changed"
    got = await refused(ctx, "context_set", {"cast": [{"name": "Character 2", "to": "Character 5"}]})
    assert got == {"problem": "Cast and set, cast Character 5: Character 5 has no picture in Characters",
                   "fix": "Cast only names that have a picture in Characters", "hints": {"characters": ["Character 1",
                                                                                                        "Character 4"]}}
    got = await refused(ctx, "context_set", {"cast": [{"name": "Character 2", "to": "character 1"}]})
    assert got == {"problem": "character 1 is in the context's cast already", "fix": "Rename to a name not in the cast",
                   "hints": {"context_cast": ["Character 1", "Character 2"]}}
    done = await call(ctx, "context_set", {"cast": [{"name": "Character 2", "to": "Character 4", "home": 75}]})
    assert done["state"][0] == "Script 1 · 1 scenes · 3 shots · " + done["state"][0].split(" · ")[3]
    assert done["state"][1].startswith("context · Character 2 → Character 4 · cast Character 1, Character 4")
    show = on_disk(ctx)
    assert [m["name"] for m in show["context"]["cast"]] == ["Character 1", "Character 4"]
    assert show["context"]["cast"][1]["home"] == 75
    assert show["context"]["cast"][1]["costume"] == "A blue dress"
    assert show["context"]["set"]["props"][1]["owner"] == "Character 4" and \
        show["scenes"][0]["cast"] == ["Character 1", "Character 4"]
    events = [ev for shot in show["scenes"][0]["shots"] for ev in shot["events"]]
    names = {ev.get("speaker") or ev.get("character") for ev in events} - {None}
    assert names == {"Character 1", "Character 4"}
    read = await call(ctx, "script_read", {})
    assert "no picture" not in read["read"][0]


async def test_the_picture_back_clears_the_problem(ctx: Ctx) -> None:
    _example(ctx)
    (_cast(ctx) / "Character 2.png").write_bytes(png_bytes())
    read = await call(ctx, "script_read", {})
    assert "no picture" not in read["read"][0]


async def test_script_start_still_sends_back_a_context_naming_someone_with_no_picture(ctx: Ctx) -> None:
    extra = {**CONTEXT, "cast": [*CONTEXT["cast"],
                                 {"name": "Character 4", "look": "x", "costume": "x", "ignore": "x", "home": 5}]}
    ctx.model = Model(json.dumps(extra), json.dumps(CONTEXT))
    await call(ctx, "script_start", {"name": "Script 1", "story": "Character 7 meets Character 6"})
    assert on_disk(ctx)["context"] == CONTEXT
    assert ctx.model.sent[1][-1]["content"] == start.SEND_BACK.format(
        "Cast and set, cast Character 4: Character 4 has no picture in Characters")
