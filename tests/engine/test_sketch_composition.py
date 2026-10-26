"""The sketch's composition (`hub/modules/director/sketch.py`): the sketch is composition, not costume, in the
script's words. On `test_script_tools`'s context with the set a hall of three elements, a moody description, a
cinematic style and a member's look and costume: a wide shot of two seated is the camera, the set's name and elements,
and each one in frame by name and pose, left to right by home, with no style, description, look, costume, gaze or
style sentence; a close-up names the one in frame alone; three in a row are left to right whoever speaks; a member
with no look and no costume is drawn; no set waits; a set with no elements is its name alone; an element's cast name
and quoted words reach the prompt as written; a costume change marks no drawn panel stale, an element change marks
the scene's; a part that ends in a mark is sent once, one with none gets a full stop."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from hub.modules.director import drawing, sketch
from tests.engine.test_script_drawing import DrawCtx
from tests.engine.test_script_stale import drawn_script, stale
from tests.engine.test_script_tools import CONTEXT, call

HALL = {"name": "Long hall", "elements": ["a long table", "chairs", "microphones"],
          "description": "Warm light, a moody evening feel"}


def context(**changes: Any) -> dict:
    held = copy.deepcopy(CONTEXT)
    held["cast"][1] = {"name": "Character 8", "look": "Look 8 text",
                       "costume": "open shirt, unbuttoned jacket",
                       "ignore": "The chair", "home": 70}
    held["set"] = copy.deepcopy(HALL)
    held["style"] = "Realistic, cinematic lighting"
    held.update(changes)
    return held


def sit(ident: str, who: str) -> dict:
    return {"id": ident, "kind": "pose", "start_ms": 0, "end_ms": 4000, "character": who, "pose": "sit"}


def line(ident: str, who: str, start: int, end: int) -> dict:
    return {"id": ident, "kind": "line", "start_ms": start, "end_ms": end, "speaker": who, "words": "Hello there."}


def prompt(held: dict, cast: list[str], camera: Any, events: list[dict], at_ms: int = 0) -> tuple:
    shot = {"id": "s1", "start_ms": 0, "end_ms": 4000, "camera": camera, "events": events}
    scene = {"title": "Scene 1", "cast": cast, "shots": [shot]}
    return sketch.prompt({"version": 2, "context": held, "scenes": [scene]}, scene, shot, at_ms)


TALK = [sit("p1", "Character 7"), sit("p2", "Character 8"), line("l1", "Character 7", 0, 3000)]


def test_a_wide_shot_of_two_seated_is_the_camera_the_set_and_each_pose() -> None:
    text, why = prompt(context(), ["Character 7", "Character 8"], "Wide shot", TALK)
    assert why is None
    assert text == "Wide shot. Long hall, a long table, chairs, microphones. Character 7 sit. Character 8 sit."
    for absent in ("Realistic", "cinematic", "Look 8", "shirt", "jacket", "Warm", "moody", "Hello", "looking"):
        assert absent not in text


def test_a_close_up_on_one_draws_that_one_alone() -> None:
    text, _ = prompt(context(), ["Character 7", "Character 8"], {"framing": "Close-up", "on": ["Character 8"]}, TALK)
    assert text == "Close-up. Long hall, a long table, chairs, microphones. Character 8 sit."


def test_three_in_a_row_are_left_to_right_by_home_whoever_speaks() -> None:
    held = context()
    held["cast"] = [{"name": n, "home": h} for n, h in (("Character 7", 10), ("Character 8", 50), ("Character 6", 90))]
    text, _ = prompt(held, ["Character 6", "Character 7", "Character 8"], "Wide shot", [])
    assert text.endswith(". Character 7 stand. Character 8 stand. Character 6 stand.")
    two = [line("l1", "Character 6", 0, 3000), line("l2", "Character 7", 500, 2000)]
    assert prompt(held, ["Character 6", "Character 7", "Character 8"], "Wide shot", two,
                  1000)[0] == text, "no gaze"


def test_a_member_with_no_look_and_no_costume_is_drawn() -> None:
    held = context()
    for key in ("look", "costume"):
        del held["cast"][1][key]
    del held["style"]
    del held["set"]["description"]
    assert prompt(held, ["Character 7", "Character 8"], "Wide shot", TALK) == prompt(context(), ["Character 7",
                                                                                                 "Character 8"],
                                                                                                 "Wide shot", TALK)


def test_no_set_waits_and_a_set_with_no_elements_is_its_name() -> None:
    held = context()
    del held["set"]
    assert prompt(held, ["Character 7", "Character 8"], "Wide shot", TALK) == (None, "the context has no set")
    held = context(set={"name": "Long hall"})
    text, _ = prompt(held, ["Character 7", "Character 8"], "Wide shot", TALK)
    assert text == "Wide shot. Long hall. Character 7 sit. Character 8 sit."


def test_an_elements_cast_name_and_quoted_words_reach_the_prompt_as_written() -> None:
    elements = ["Character 8's chair", "a sign reading \"Words 1\"", "“Words 2”"]
    text, _ = prompt(context(set={**HALL, "elements": elements}), ["Character 7", "Character 8"], "Wide shot", TALK)
    assert text == f"Wide shot. Long hall, {', '.join(elements)}. Character 7 sit. Character 8 sit."


def test_a_part_that_ends_in_a_mark_is_sent_once_and_one_with_none_gets_a_full_stop() -> None:
    """The parts' join; the set's name and elements stay joined by ", "."""
    held = context(set={"name": "Set 1", "elements": ["Element 1."]})
    text, _ = prompt(held, ["Character 7", "Character 8"], {"framing": "Framing 1."}, TALK)
    assert text == "Framing 1. Set 1, Element 1. Character 7 sit. Character 8 sit." and ".." not in text
    text, _ = prompt(context(set={"name": "Set 1"}), ["Character 7", "Character 8"], {"framing": "Framing 1?"}, TALK)
    assert text == "Framing 1? Set 1. Character 7 sit. Character 8 sit."


@pytest.fixture
async def ctx(tmp_path: Path) -> Any:
    await drawing.stop()
    drawing.waiting.clear()
    drawing.failed.clear()
    yield DrawCtx(tmp_path)
    await drawing.stop()


async def test_a_costume_marks_nothing_an_element_marks_the_scene(ctx: DrawCtx) -> None:
    await drawn_script(ctx)
    await call(ctx, "context_set", {"cast": [{"name": "Character 6", "costume": "A green coat",
                                              "look": "A tall figure"}]})
    assert not stale(ctx), "a look and a costume are not in a sketch"
    await call(ctx, "context_set", {"set": {"elements": ["Table", "Two chairs"]}})
    assert stale(ctx) == ["f1", "f2"]
