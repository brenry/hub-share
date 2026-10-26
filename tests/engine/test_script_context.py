"""The scene context of a version-2 script (`hub/modules/director/context.py`): the neutral fixture
reads with Characters holding both members and keeps the example's counts; the example as version 1 reads with no
Characters at all; every check refuses with one line naming where."""
from __future__ import annotations

import copy
import json
from collections.abc import Callable

import pytest

from hub.core.api import Invalid
from hub.modules.director import context, scriptshape
from tests.engine.test_script_shape import FIXTURE

EXAMPLE = json.loads(FIXTURE.read_text(encoding="utf-8"))
CHARS = {"character 1", "character 2"}


def version_1(script: dict) -> dict:
    """The example as version 1: the same scenes, no context."""
    return {"version": 1, "scenes": copy.deepcopy(script["scenes"])}


def events(script: dict) -> list[dict]:
    return [ev for sc in script["scenes"] for shot in sc["shots"] for ev in shot["events"]]


def test_the_shipped_example_is_version_2_and_reads() -> None:
    assert list(EXAMPLE) == ["version", "context", "scenes"], "the context before the scenes"
    script = scriptshape.read(copy.deepcopy(EXAMPLE), CHARS)
    held = script["context"]
    assert [(m["name"], m["home"]) for m in held["cast"]] == [("Character 1", 30), ("Character 2", 70)]
    assert [p["name"] for p in held["set"]["props"]] == ["Prop 1", "Prop 2"]
    assert held["set"]["name"] == "Set 1" and held["set"]["plate"] is None
    assert held["style"] == "Style 1"
    assert scriptshape.length_ms(script) == 24_000
    assert scriptshape.counts(script) == {"scenes": 1, "shots": 3, "lines": 3}
    kinds = [ev["kind"] for ev in events(script)]
    assert (kinds.count("line"), kinds.count("cue"), kinds.count("pose")) == (3, 4, 11)
    assert context.read(EXAMPLE["context"], {"CHARACTER 1".casefold(), "character 2"}) == {
        "character 1": "Character 1", "character 2": "Character 2"}


def test_a_version_1_script_reads_with_no_characters() -> None:
    old = version_1(EXAMPLE)
    assert scriptshape.read(old, ()) is old
    assert scriptshape.counts(old) == {"scenes": 1, "shots": 3, "lines": 3}


def test_a_context_being_written_reads() -> None:
    script = copy.deepcopy(EXAMPLE)
    script["context"] = {"cast": [{"name": "character 1"}, {"name": "Character 2"}]}       # any case
    assert scriptshape.read(script, CHARS) is script
    script["context"]["set"] = {"name": "Stage"}
    assert scriptshape.read(script, CHARS) is script


def top(s: dict) -> dict:
    return s


def bib(s: dict) -> dict:
    return s["context"]


def first_member(s: dict) -> dict:
    return s["context"]["cast"][0]


def stage(s: dict) -> dict:
    return s["context"]["set"]


def cup(s: dict) -> dict:
    return s["context"]["set"]["props"][0]


def set_(path: Callable[[dict], dict], key: str, value: object) -> Callable[[dict], None]:
    def change(s: dict) -> None:
        path(s)[key] = value
    return change


def drop(path: Callable[[dict], dict], key: str) -> Callable[[dict], None]:
    def change(s: dict) -> None:
        del path(s)[key]
    return change


def as_v1_with_context(s: dict) -> None:
    s["version"] = 1


def extra_scene_name(s: dict) -> None:
    s["scenes"][0]["cast"].append("Character 5")


J, G = "Cast and set, cast Character 1", "Cast and set, cast Character 2"
SET, CUP = "Cast and set, set", "Cast and set, set, prop Prop 1"
TEXT = "is text, not blank"
CASES = [
    (drop(top, "context"), "The script has no context"),
    (as_v1_with_context, "A version 1 script has no context; a context is version 2"),
    (set_(bib, "notes", "x"), "Cast and set: the context has a key the format does not know: notes"),
    (set_(bib, "cast", {"name": "Character 1"}), "Cast and set: the cast is a list"),
    (set_(first_member, "name", " "), f"Cast and set, cast 1: the name {TEXT}"),
    (set_(first_member, "voice", "x"), f"{J}: a cast member has a key the format does not know: voice"),
    (set_(first_member, "home", -1), f"{J}: home is a whole number from 0 to 100"),
    (set_(first_member, "home", 101), f"{J}: home is a whole number from 0 to 100"),
    (set_(first_member, "home", 30.5), f"{J}: home is a whole number from 0 to 100"),
    (set_(first_member, "home", True), f"{J}: home is a whole number from 0 to 100"),
    (set_(first_member, "look", ""), f"{J}: look {TEXT}"),
    (set_(first_member, "ignore", 3), f"{J}: ignore {TEXT}"),
    (lambda s: s["context"]["cast"][1].update(name="CHARACTER 1"),
     "Cast and set, cast CHARACTER 1: CHARACTER 1 is in the cast twice"),
    (extra_scene_name, "Scene 1: Character 5 is not in the context's cast"),
    (lambda s: s["context"]["cast"].pop(1), "Scene 1: Character 2 is not in the context's cast"),
    (set_(stage, "lights", "warm"), f"{SET}: the set has a key the format does not know: lights"),
    (drop(stage, "name"), f"{SET}: the set has no name"),
    (set_(stage, "name", ""), f"{SET}: the name {TEXT}"),
    (set_(stage, "description", " "), f"{SET}: the description {TEXT}"),
    (set_(stage, "elements", "x"), f"{SET}: elements is a list"),
    (set_(stage, "elements", [""]), f"{SET}: an element {TEXT}"),
    (set_(stage, "props", "x"), f"{SET}: props is a list"),
    (set_(stage, "plate", "chars/stage.png"), f"{SET}: plate is null in this version"),
    (set_(cup, "colour", "white"), f"{CUP}: a prop has a key the format does not know: colour"),
    (set_(cup, "description", ""), f"{CUP}: the description {TEXT}"),
    (lambda s: s["context"]["set"]["props"][1].update(name="prop 1"),
     "Cast and set, set, prop prop 1: another prop has this name"),
    (set_(bib, "style", " "), f"Cast and set: the style {TEXT}"),
]


@pytest.mark.parametrize(("change", "line"), CASES)
def test_every_check_refuses_with_where(change: Callable[[dict], None], line: str) -> None:
    script = copy.deepcopy(EXAMPLE)
    change(script)
    with pytest.raises(Invalid) as e:
        scriptshape.read(script, CHARS)
    assert e.value.text == line


def test_the_contexts_text_of_any_length_reads() -> None:
    """A costume, a set's description, an element, a prop's description and the style of any length."""
    script = copy.deepcopy(EXAMPLE)
    for change in (set_(first_member, "costume", "x" * 601), set_(stage, "description", "x" * 601),
                   set_(stage, "elements", ["x" * 121]), set_(cup, "description", "x" * 301),
                   set_(bib, "style", "x" * 201)):
        change(script)
    read = scriptshape.read(script, CHARS)["context"]
    assert (len(read["cast"][0]["costume"]), len(read["style"]), len(read["set"]["elements"][0])) == (601, 201, 121)


def test_a_cast_of_seventeen_and_a_set_of_thirty_one_read() -> None:
    """No count of the Hub's on a context's cast, a set's elements or its props."""
    script = copy.deepcopy(EXAMPLE)
    script["context"]["cast"] += [{"name": f"Character {k}"} for k in range(3, 18)]
    script["context"]["set"]["elements"] = [f"Element {k}" for k in range(1, 32)]
    script["context"]["set"]["props"] = [{"name": f"Prop {k}"} for k in range(1, 32)]
    read = scriptshape.read(script, CHARS)["context"]
    assert (len(read["cast"]), len(read["set"]["elements"]), len(read["set"]["props"])) == (17, 31, 31)


def test_a_name_without_a_picture_and_the_folder_unset() -> None:
    """`read` reads it; `unpictured` names it; `pictured` raises the line `read` raised before."""
    script = scriptshape.read(copy.deepcopy(EXAMPLE), {"character 1"})
    assert context.unpictured(script["context"], {"character 1"}) == ["Character 2"]
    with pytest.raises(Invalid) as e:
        context.pictured(script["context"], {"character 1"})
    assert e.value.text == f"{G}: Character 2 has no picture in Characters"
    scriptshape.read(copy.deepcopy(EXAMPLE), ())
    assert context.unpictured(EXAMPLE["context"], ()) == ["Character 1", "Character 2"], \
        "the folder unset counts as none"
    with pytest.raises(Invalid) as e:
        context.pictured(EXAMPLE["context"], ())
    assert e.value.text == f"{J}: Character 1 has no picture in Characters"
    renamed = copy.deepcopy(EXAMPLE)
    renamed["context"]["cast"][0]["name"] = "Character 4"
    with pytest.raises(Invalid) as e:
        context.pictured(renamed["context"], CHARS)
    assert e.value.text == "Cast and set, cast Character 4: Character 4 has no picture in Characters"


def test_an_owner_may_be_null() -> None:
    script = copy.deepcopy(EXAMPLE)
    script["context"]["set"]["props"][0]["owner"] = None
    assert scriptshape.read(script, CHARS) is script
