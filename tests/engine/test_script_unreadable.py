"""A script file never breaks the list. A number too long to read, a `\\u` escape that is not a
character and a file name that is not UTF-8 are each listed with their one line, the list and the script render, and
every problem line is at most 300 characters (`hub/modules/director/scripts.py`)."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import pytest
from starlette.responses import JSONResponse

from hub.core.api import Invalid
from hub.modules.director import scripts
from tests.engine.test_script_shape import FIXTURE

EXAMPLE = json.loads(FIXTURE.read_text(encoding="utf-8"))
CHARS = {"character 7": "chars/Character 7.png", "character 6": "chars/Character 6.png"}
LONG = "The file holds a number too long to read"
ESCAPE = "The file holds a \\u escape that is not a character"
DEEP = "The file is nested too deep to read"
KIND = "Scene 1, shot 1, event c1: kind is line, cue or pose"


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    folder = tmp_path / "scripts"
    folder.mkdir()
    (folder / "Example.json").write_text(json.dumps(EXAMPLE))
    return folder


def _listed(folder: Path) -> dict[str, Any]:
    return {s["name"]: s["problem"] for s in scripts.listing(folder, CHARS)}


def _readable(folder: Path, name: str) -> str:
    with pytest.raises(Invalid) as e:
        scripts.readable(folder, name, CHARS)
    return json.loads(e.value.text)["problem"]


def test_a_number_too_long_is_listed_with_its_line(folder: Path) -> None:
    (folder / "Long.json").write_text('{"version": 2, "context": ' + "7" * 5001 + ', "scenes": []}')
    assert _listed(folder) == {"Example": None, "Long": LONG}
    assert scripts.one(folder, "Long", CHARS)["problem"] == LONG


def _surrogate(where: str) -> dict:
    script = copy.deepcopy(EXAMPLE)
    if where == "cast":
        script["context"]["cast"][0]["name"] = "Character 7\ud800"
    elif where == "words":
        script["scenes"][0]["shots"][0]["events"][4]["words"] = "Line \ud800 one"
    else:
        script["scenes"][0]["shots"][0]["events"][0]["\ud800"] = 1
    return script


@pytest.mark.parametrize("where", ["cast", "words", "key"])
def test_a_lone_surrogate_in_the_text_is_listed_with_its_line(folder: Path, where: str) -> None:
    (folder / "Odd.json").write_text(json.dumps(_surrogate(where)))       # ensure_ascii: written as `\ud800`
    assert _listed(folder) == {"Example": None, "Odd": ESCAPE}
    JSONResponse({"scripts": scripts.listing(folder, CHARS)})
    JSONResponse(scripts.one(folder, "Odd", CHARS))
    assert scripts.one(folder, "Odd", CHARS)["problem"] == ESCAPE
    assert _readable(folder, "Odd") == f"Odd does not read: {ESCAPE}"


def test_a_name_that_is_not_utf8_is_listed_and_the_list_renders(folder: Path) -> None:
    try:
        (folder / os.fsdecode(b"N\xff.json")).write_text(json.dumps(EXAMPLE))
    except OSError:
        pytest.skip("the file system refuses a name that is not UTF-8")
    listed = scripts.listing(folder, CHARS)
    assert {s["name"]: s["problem"] for s in listed} == {
        "Example": None, "N�": "The file's name is not UTF-8: rename it in the scripts folder"}
    assert [s["changed"] > 0 for s in listed] == [True, True]
    JSONResponse({"scripts": listed})
    assert scripts.names(folder) == ["Example", "N�"]
    JSONResponse({"scripts": scripts.names(folder)})
    with pytest.raises(Invalid) as e:
        scripts.one(folder, "N�", CHARS)
    assert e.value.text == "There is no script named N�"


def _long(where: str) -> dict:
    script = copy.deepcopy(EXAMPLE)
    events = script["scenes"][0]["shots"][0]["events"]
    if where == "speaker":
        events[4]["speaker"] = "S" * 5000
    elif where == "character":
        events[2]["character"] = "C" * 5000
    elif where == "anchor":
        events[5]["anchor"]["line"] = "L" * 5000
    else:
        events[0]["k" * 5000] = 1
    return script


@pytest.mark.parametrize("where", ["speaker", "character", "anchor", "key"])
def test_a_problem_line_is_cut_to_300(folder: Path, where: str) -> None:
    (folder / "Wide.json").write_text(json.dumps(_long(where)))
    problem = _listed(folder)["Wide"]
    assert len(problem) == 300
    assert problem.endswith("…")
    assert problem.startswith("Scene 1, shot 1, event ")
    assert scripts.one(folder, "Wide", CHARS)["problem"] == problem


def test_a_deep_file_and_a_short_problem_are_word_for_word(folder: Path) -> None:
    (folder / "Deep.json").write_text("[" * 100_000)
    kind = copy.deepcopy(EXAMPLE)
    kind["scenes"][0]["shots"][0]["events"][0]["kind"] = []
    (folder / "Kind.json").write_text(json.dumps(kind))
    assert _listed(folder) == {"Deep": DEEP, "Example": None, "Kind": KIND}
