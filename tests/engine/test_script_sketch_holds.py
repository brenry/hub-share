"""Sketch holds (`hub/modules/director/drawing.py`, `sketch.py`): a finish holds the slot until its picture is written,
so no pass draws the same panel twice; the second reader of a finish writes nothing; a write that fails marks the panel
failed and frees the slot; a refusal for every panel (any field but the prompt) keeps them waiting, not failed;
`sketch.ready` retries failed panels; every quote form and every cast name in any case reaches the prompt as written
(CLAUDE.md: no rewording)."""
from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.director import drawing, sketch
from hub.modules.director import tools as director_tools
from tests.engine.test_script_drawing import DrawCtx, finished, picture
from tests.engine.test_script_sketching import Refusing, forgotten, made, member, prompt_of
from tests.engine.test_script_tools import CONTEXT, call, framed


@pytest.fixture
async def ctx(tmp_path: Path) -> Any:
    await drawing.stop()
    drawing.waiting.clear()
    drawing.failed.clear()
    yield DrawCtx(tmp_path)
    await drawing.stop()


def gated(monkeypatch: pytest.MonkeyPatch) -> tuple[asyncio.Event, asyncio.Event, list]:
    """`tools.drawn` waiting on a gate before the real write; (the gate, entered, each call's panel)."""
    gate, entered, calls = asyncio.Event(), asyncio.Event(), []
    real = director_tools.drawn

    async def drawn(ctx: Any, name: str, panel: str, item: str, prompt: Any = None) -> None:
        calls.append(panel)
        entered.set()
        await gate.wait()
        await real(ctx, name, panel, item, prompt)

    monkeypatch.setattr(director_tools, "drawn", drawn)
    return gate, entered, calls


# ---------------------------------------------------------------- the slot
async def test_a_finish_holds_the_slot_until_its_picture_is_written(ctx: DrawCtx, monkeypatch) -> None:
    gate, entered, calls = gated(monkeypatch)
    await framed(ctx)
    await drawing.step(ctx)
    task = asyncio.create_task(drawing.on_finished(ctx, finished(ctx, "done", "out/2026-10-20/f1.png")))
    await asyncio.wait_for(entered.wait(), 2)
    await drawing.step(ctx)
    assert made(ctx) == ["f1"], "no pass submits while the picture is being written"
    read = (await call(ctx, "script_read", {}))["read"]
    assert read[-2] == "f1 panel s1 0.00 (script 0.00) · drawing"
    gate.set()
    await task
    assert picture(ctx, "f1") == "out/2026-10-20/f1.png" and drawing.busy() is None
    await drawing.step(ctx)
    assert made(ctx) == ["f1", "f2"] and calls == ["f1"]


async def test_the_second_reader_of_a_finish_writes_nothing(ctx: DrawCtx, monkeypatch) -> None:
    gate, entered, calls = gated(monkeypatch)
    await framed(ctx)
    await drawing.step(ctx)
    data = forgotten(ctx, "done", "out/2026-10-20/f1.png")
    first = asyncio.create_task(drawing.on_finished(ctx, data))
    second = asyncio.create_task(drawing.step(ctx))
    await asyncio.wait_for(entered.wait(), 2)
    await asyncio.sleep(0.05)
    assert calls == ["f1"] and made(ctx) == ["f1"]
    gate.set()
    await asyncio.gather(first, second)
    assert calls == ["f1"], "tools.drawn called once"
    assert picture(ctx, "f1") == "out/2026-10-20/f1.png"


async def test_a_write_that_fails_marks_the_panel_failed_and_frees_the_slot(ctx: DrawCtx, monkeypatch) -> None:
    async def drawn(*_: Any) -> None:
        raise OSError("The disk is full")

    monkeypatch.setattr(director_tools, "drawn", drawn)
    await framed(ctx)
    await drawing.step(ctx)
    with pytest.raises(OSError):
        await drawing.on_finished(ctx, finished(ctx, "done", "out/2026-10-20/f1.png"))
    assert drawing.busy() is None and picture(ctx, "f1") is None
    read = (await call(ctx, "script_read", {}))["read"]
    assert read[-2] == "f1 panel s1 0.00 (script 0.00) · waiting: The disk is full"
    await drawing.step(ctx)
    assert made(ctx) == ["f1", "f2"]


# ---------------------------------------------------------------- refusals and the retry
@pytest.mark.parametrize("exc", [Invalid("mode", "Flux needs a reference image"), Invalid("width", "Choose a size"),
                                 Invalid("steps", "Flux runs 4 steps"), Invalid("params", "Nothing to run")])
async def test_a_refusal_for_every_panel_waits(tmp_path: Path, ctx: DrawCtx, exc: Invalid) -> None:
    (tmp_path / "r").mkdir()
    c = Refusing(tmp_path / "r")
    await framed(c)
    c.refuse_on, c.exc = "", exc
    await drawing.step(c)
    assert c.jobs.made == [] and drawing.failed == {} and drawing.waiting == {"Script 1": exc.text}
    read = (await call(c, "script_read", {}))["read"]
    assert read[-2:] == [f"f1 panel s1 0.00 (script 0.00) · waiting: {exc.text}",
                         f"f2 panel s2 0.00 (script 1.00) · waiting: {exc.text}"]
    c.exc = None
    await drawing.on_ready(c, {})
    await drawing.step(c)
    assert made(c) == ["f1"], "drawn on the next pick with no tool write"


async def test_ready_retries_a_failed_panel(ctx: DrawCtx) -> None:
    await framed(ctx)
    await drawing.step(ctx)
    ctx.jobs.made[0].error = "Out of memory"
    await drawing.on_finished(ctx, finished(ctx, "failed"))
    await drawing.step(ctx)
    await drawing.on_finished(ctx, finished(ctx, "done", "out/2026-10-20/f2.png"))
    await drawing.step(ctx)
    assert made(ctx) == ["f1", "f2"]
    await drawing.on_ready(ctx, {})
    await drawing.step(ctx)
    assert made(ctx) == ["f1", "f2", "f1"]


# ---------------------------------------------------------------- quotes as written
@pytest.mark.parametrize("camera", [
    'the sign "Words 1" here', "the sign “Words 1” here", "the sign „Words 1“ here",
    "the sign „Words 1” here", "the sign ”Words 1” here", "the sign «Words 1» here",
    "the sign »Words 1« here", "the sign ‹Words 1› here", "the sign ›Words 1‹ here",
    "the sign 「Words 1」 here", "the sign 『Words 1』 here", "the sign 《Words 1》 here",
    "the sign 〈Words 1〉 here", "the sign `Words 1` here", "the sign 'Words 1' here",
    "the sign ‘Words 1’ here", "the sign ‚Words 1‘ here", "the sign ‛Words 1’ here",
    "the sign ＂Words 1＂ here",
])
def test_every_quote_form_reaches_the_prompt_as_written(camera: str) -> None:
    assert prompt_of([member("Character 1", 20)], camera, ["Character 1"]).startswith(camera + ". ")


@pytest.mark.parametrize("text", [
    'the sign "Words 1 and more', "the sign «Words 1 and more", "Character 1's table", "Character 1’s table",
    "the speakers' chairs", "a sign reading 'Words 1'", "‘Words 2’",
])
def test_an_unclosed_quote_and_an_apostrophe_reach_the_prompt_as_written(text: str) -> None:
    assert prompt_of([member("Character 1", 20)], text, ["Character 1"]).startswith(text + ". ")


def test_every_context_field_reaches_the_prompt_with_its_quotes() -> None:
    cast = [{"name": "Character 1", "look": "Look «Words 1»", "costume": '"Words 2"', "home": 20}]
    context = {**copy.deepcopy(CONTEXT), "cast": cast, "style": "Style 'Words 3'",
               "set": {**CONTEXT["set"], "name": "Set «Words 4»", "description": "Description “Words 5”",
                       "elements": ["Element 1", "Element 'Words 6'"]}}
    shot = {"id": "s1", "start_ms": 0, "end_ms": 4000, "camera": "Wide shot", "events": []}
    scene = {"title": "T", "cast": ["Character 1"], "shots": [shot]}
    text, why = sketch.prompt({"version": 2, "context": context, "scenes": [scene]}, scene, shot, 0)
    assert why is None
    assert text == "Wide shot. Set «Words 4», Element 1, Element 'Words 6'. Character 1 stand."
    for word in ("Words 1", "Words 2", "Words 3", "Words 5"):
        assert word not in text, "no look, costume, style or description"


def test_a_costume_all_quoted_is_left_out_of_the_characters_part() -> None:
    cast = [{"name": "Character 1", "look": "Look 1", "costume": "«Words 1»", "home": 20}]
    text = prompt_of(cast, "Wide shot", ["Character 1"])
    assert text == "Wide shot. The stage, Table. Character 1 stand."
    assert "Words 1" not in text and "Look 1" not in text, "no look, no costume"


# ---------------------------------------------------------------- names as written
def test_a_name_in_any_case_reaches_the_prompt_as_written() -> None:
    camera = "Close on CHARACTER 1 with character 1 on the cap"
    assert prompt_of([member("Character 1", 20)], camera, ["Character 1"]).startswith(camera + ". ")
    pair = [member("Character 1 A", 20), member("character 1 B", 80)]
    text = prompt_of(pair, "CHARACTER 1 laughs", ["Character 1 A", "character 1 B"])
    assert text == "CHARACTER 1 laughs. The stage, Table. Character 1 A stand. character 1 B stand."


def test_a_name_with_an_article_reaches_the_prompt_as_written() -> None:
    cast = [member("The Character 1", 20)]
    text = prompt_of(cast, "Close on THE CHARACTER 1 at the table", ["The Character 1"])
    assert text == "Close on THE CHARACTER 1 at the table. The stage, Table. The Character 1 stand."


def test_a_name_like_a_word_of_the_camera_reaches_the_prompt_as_written() -> None:
    text = prompt_of([member("White", 20)], "Wide on a figure in white", ["White"])
    assert text == "Wide on a figure in white. The stage, Table. White stand."


def test_a_name_like_a_pose_word_reaches_the_prompt_as_written() -> None:
    text = prompt_of([member("Left", 20), member("Sit 1", 80)], "Wide shot", ["Left", "Sit 1"])
    assert text == "Wide shot. The stage, Table. Left stand. Sit 1 stand."
