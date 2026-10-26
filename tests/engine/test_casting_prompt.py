"""A cast's prompt. A in the engine's labelled form (the subject line, the Description as
typed, a line per picture's keep and ignore), then, when the Prompt box holds text, "\n\n" and the box byte for byte;
an empty box sends A alone. The box is never written. Over 4000 characters: refused with the count over."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub.modules.casting import prompt, routes, state
from tests.engine import test_casting_module as module

ctx, no_drafts = module.ctx, module.no_drafts                 # the fixtures

WORKFLOW = Path(__file__).parents[2] / "docs/video-plan/research/R51-workflows/H3_CharSheetMaker_6_Panel_10Sept.json"
HEAD = {"keep": "", "ignore": ""}
BOX = "Prompt 1"


def node(n: int) -> str:
    nodes = json.loads(WORKFLOW.read_text(encoding="utf-8"))["nodes"]
    return next(x for x in nodes if x["id"] == n)["widgets_values"][0]


def test_the_subject_line_is_the_labelled_forms():
    assert prompt.SUBJECT in node(138)


def test_the_labelled_form_with_facts_and_a_line_per_picture():
    pictures = [HEAD, {"keep": "the headphones", "ignore": "the hand holding them"},
                {"keep": "  the shirt,\n\tits print ", "ignore": ""}]
    a = prompt.a_text(pictures, {"age": "50", "build": "heavy"})
    assert a.splitlines() == [            # the fields as typed, no Age, no fixed lines
        "subject_definitions: <Subject 1> is the character shown in <Picture 1>. heavy",
        "<Picture 2>: the headphones",
        "<Picture 3>: the shirt, its print",
        "",
        "retention_analysis: <Picture 2>: the hand holding them",
    ]


@pytest.mark.parametrize(("facts", "said"), [({"age": "50"}, ""),                # no Age, no wrapper
                                             ({"build": "heavy"}, "heavy"),
                                             ({"age": " ", "build": ""}, ""), (None, "")])
def test_the_facts_sentence_only_when_given(facts, said):
    first = prompt.a_text([HEAD], facts).splitlines()[0]
    assert first == f"subject_definitions: {' '.join(t for t in (prompt.SUBJECT, said) if t)}"


def test_a_then_two_newlines_then_the_box():
    text = prompt.prompt([HEAD], {"age": "50", "build": "heavy"}, BOX)
    a = prompt.a_text([HEAD], {"age": "50", "build": "heavy"})
    assert text == a + "\n\n" + BOX and not a.endswith("\n")


@pytest.mark.parametrize("box", ["", "   \n\t ", None])
def test_an_empty_box_sends_a_alone(box):
    assert prompt.prompt([HEAD], None, box) == prompt.a_text([HEAD], None)
    assert prompt.costume([], None, "Costume 1", box) == prompt.costume_a([], None, "Costume 1")


def test_the_box_goes_byte_for_byte():
    box = "  Line 1\n\n[Window 1]  Line 2\r\n\tLine 3  \n"
    assert prompt.prompt([HEAD], None, box) == prompt.a_text([HEAD], None) + "\n\n" + box
    assert prompt.costume([], None, "", box).endswith("\n\n" + box)


def test_a_prompt_over_4000_is_sent_whole():
    base = len(prompt.prompt([HEAD], None, BOX))                     # no length cap of the Hub's
    extra = {"keep": "x" * (4003 - base - len("\n<Picture 2>: ")), "ignore": ""}
    text = prompt.prompt([HEAD, extra], None, BOX)
    assert len(text) == 4003 and text.endswith(prompt.SEPARATOR + BOX) and extra["keep"] in text
    assert prompt.prompt([HEAD], None, "y" * 5000).endswith(prompt.SEPARATOR + "y" * 5000)


async def test_the_box_is_never_written(ctx):
    box = "Prompt 1 held in memory only"
    answer = await module.call(routes.post_cast, ctx, body=module.cast_body(prompt=box))
    assert ctx.service("orbit").calls[-1][1].endswith("\n\n" + box)
    assert (await module.call(routes.get_draft, ctx, {"name": "Character 11"}))["prompt"] == box
    await module.finish(ctx, answer["job"], module.land(ctx))
    assert "approved" in await module.call(routes.post_approve, ctx, body={"name": "Character 11"})
    data, chars = Path(ctx.files.data_dir), Path(ctx.files.roots["chars"])
    held = [f for root in (data, chars) for f in root.rglob("*") if f.is_file() and box.encode() in f.read_bytes()]
    assert held == [] and any(chars.rglob("casting.json"))
    state.clear()                                                   # a restart empties it
    assert (await module.call(routes.get_draft, ctx, {"name": "Character 11"}))["prompt"] == ""
