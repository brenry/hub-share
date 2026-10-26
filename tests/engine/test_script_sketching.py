"""Sketching (`hub/modules/director/sketch.py`, `drawing.py`, `panels.py`, `tools.py`; Generate's `sketch.ready`): the
prompt is the script's words alone, a camera's quoted words and every cast name and first name as written;
the loop is woken by Generate's `sketch.ready` (its start, its model list, a model picked) and by
`script_read`; a panel Generate refuses alone is failed and the next is drawn; a refusal for every panel keeps them
all waiting; a finish is read from the job's own object whether the pass or `job.finished` comes first; a queued job
cancelled fails its panel; a picture gone from Media is drawn again."""
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.core.messages import Refused
from hub.modules.director import drawing, panels, sketch
from hub.modules.director import manifest as director
from hub.modules.generate_image import manifest as generate
from hub.modules.generate_image import models, routes
from tests.engine.helpers import FakeCtx, FakeEngine, FakeRequest, load_catalog
from tests.engine.test_script_drawing import NO_MODEL, DrawCtx, finished, picture
from tests.engine.test_script_tools import CONTEXT, call, framed, on_disk

TOO_LONG = "The prompt is over 4 000 characters"


@pytest.fixture
async def ctx(tmp_path: Path) -> Any:
    await drawing.stop()
    drawing.waiting.clear()
    drawing.failed.clear()
    yield DrawCtx(tmp_path)
    await drawing.stop()


def made(ctx: DrawCtx) -> list[str]:
    return [j.params["panel"] for j in ctx.jobs.made]


async def until(ctx: DrawCtx, n: int) -> None:
    for _ in range(200):
        if len(ctx.jobs.made) >= n:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"{n} jobs never queued")


# ---------------------------------------------------------------- the prompt
def prompt_of(cast: list[dict], camera: str, names: list[str]) -> str:
    context = {**copy.deepcopy(CONTEXT), "cast": cast}
    shot = {"id": "s1", "start_ms": 0, "end_ms": 4000, "camera": camera, "events": []}
    scene = {"title": "T", "cast": names, "shots": [shot]}
    text, why = sketch.prompt({"version": 2, "context": context, "scenes": [scene]}, scene, shot, 0)
    assert why is None
    return text


def member(name: str, home: int, look: str = "A tall figure") -> dict:
    return {"name": name, "look": look, "costume": "A navy suit", "home": home}


def test_the_prompt_ends_with_who_is_in_frame_and_no_style_sentence() -> None:
    text = prompt_of([member("Character 1", 20)], "Wide shot", ["Character 1"])
    assert text == "Wide shot. The stage, Table. Character 1 stand.", "no style sentence of the Hub's"


def test_a_cameras_quoted_words_reach_the_prompt_as_written() -> None:
    camera = "close on the sign \"Words 1\" and ‘Words 2’"
    text = prompt_of([member("Character 1", 20)], camera, ["Character 1"])
    assert text.startswith(camera + ". "), "the quotes kept"
    assert prompt_of([member("Character 1", 20)], "\"Words 3\"", ["Character 1"]).startswith("\"Words 3\". ")


def test_a_whole_name_and_its_first_name_reach_the_prompt_as_written() -> None:
    text = prompt_of([member("Character 1 Two", 80, "Look 1")], "Close on Character 1 Two as Character 1 sits",
                     ["Character 1 Two"])
    assert text == "Close on Character 1 Two as Character 1 sits. The stage, Table. Character 1 Two stand."
    assert "Look 1" not in text, "the look is not in the prompt"


def test_a_name_that_is_a_word_reaches_the_prompt_as_written() -> None:
    text = prompt_of([member("Word", 20, "Look 1")], "Word in a word's room", ["Word"])
    assert "Look 1" not in text, "the look is not in the prompt"
    assert text.startswith("Word in a word's room. ") and text.endswith(". Word stand.")


def test_a_first_name_two_members_share_reaches_the_prompt_as_written() -> None:
    camera = "Character 1 A turns to Character 1 B; Character 1 laughs"
    text = prompt_of([member("Character 1 A", 20), member("Character 1 B", 80)], camera,
                     ["Character 1 A", "Character 1 B"])
    assert text.startswith(camera + ". ") and text.endswith(". Character 1 A stand. Character 1 B stand.")


# ---------------------------------------------------------------- the wakes
@pytest.fixture
async def gen(tmp_path: Path) -> FakeCtx:
    cat = load_catalog("catalog_upstream.json", tmp_path / "loras")
    return FakeCtx("generate-image", tmp_path / "data", FakeEngine(cat))


async def test_generate_says_ready_at_its_start_its_list_and_a_pick(gen: FakeCtx) -> None:
    await generate.start(gen)
    assert (models.READY, {}) in gen.events, "at its start"
    gen.events.clear()
    await models.catalog(gen)
    assert gen.events == [(models.READY, {})], "the engine answered"
    gen.events.clear()
    await routes.put_draft(gen, FakeRequest(body=json.dumps({"prompt": "x"}).encode()))
    assert models.READY not in [e for e, _ in gen.events], "no model in the draft: nothing"
    await routes.put_draft(gen, FakeRequest(body=json.dumps({"model": "flux2_klein_9b"}).encode()))
    assert models.READY in [e for e, _ in gen.events], "a model picked"
    assert director.MODULE.listens[drawing.READY] is drawing.on_ready and drawing.READY == models.READY


async def test_after_a_start_with_no_model_list_ready_draws_with_no_tool_write(ctx: DrawCtx, monkeypatch: Any) -> None:
    monkeypatch.setattr(drawing, "ON_HOLD", False)              # sketches on hold; the loop tested off it
    await framed(ctx)
    ctx.refusal = NO_MODEL                   # a Hub start: Generate has no model list yet
    await drawing.start(ctx)
    for _ in range(50):
        if drawing.waiting:
            break
        await asyncio.sleep(0.01)
    assert drawing.waiting == {"Script 1": NO_MODEL} and ctx.jobs.made == []
    path = ctx.files.roots["scripts"] / "Script 1.json"
    before, sent = path.read_bytes(), len(ctx.bus.sent)
    ctx.refusal = None
    await drawing.on_ready(ctx, {})
    await until(ctx, 1)
    assert made(ctx) == ["f1"] and path.read_bytes() == before and len(ctx.bus.sent) == sent


async def test_script_read_wakes_the_drawing(ctx: DrawCtx, monkeypatch: Any) -> None:
    monkeypatch.setattr(drawing, "ON_HOLD", False)              # sketches on hold; the loop tested off it
    await framed(ctx)
    ctx.refusal = NO_MODEL
    await drawing.start(ctx)
    for _ in range(50):
        if drawing.waiting:
            break
        await asyncio.sleep(0.01)
    ctx.refusal = None
    await call(ctx, "script_read", {})
    await until(ctx, 1)
    assert made(ctx) == ["f1"]


# ---------------------------------------------------------------- refusals
class Refusing(DrawCtx):
    """The `sketch` service refusing the prompts that hold `self.refuse_on` with `self.exc`."""

    refuse_on: str = ""
    exc: Exception | None = None

    def _sketch(self, prompt: str) -> Any:
        if self.exc is not None and self.refuse_on in prompt:
            raise self.exc
        return super()._sketch(prompt)


async def test_a_panel_refused_alone_is_failed_and_the_next_is_drawn(tmp_path: Path, ctx: DrawCtx) -> None:
    (tmp_path / "r").mkdir()
    c = Refusing(tmp_path / "r")
    await framed(c)
    c.refuse_on, c.exc = "Wide shot", Invalid("prompt", TOO_LONG)
    await drawing.step(c)
    assert made(c) == ["f2"], "the next panel in the same pass"
    read = (await call(c, "script_read", {}))["read"]
    assert read[-2:] == [f"f1 panel s1 0.00 (script 0.00) · waiting: {TOO_LONG}",
                         "f2 panel s2 0.00 (script 1.00) · drawing"]


@pytest.mark.parametrize("exc", [Refused("unavailable", "Engine is offline"), Invalid("model", NO_MODEL)])
async def test_a_refusal_for_every_panel_keeps_them_all_waiting(tmp_path: Path, ctx: DrawCtx, exc: Exception) -> None:
    (tmp_path / "r").mkdir()
    c = Refusing(tmp_path / "r")
    await framed(c)
    c.refuse_on, c.exc = "", exc
    await drawing.step(c)
    assert c.jobs.made == [] and drawing.failed == {} and drawing.waiting == {"Script 1": exc.text}
    read = (await call(c, "script_read", {}))["read"]
    assert read[-2:] == [f"f1 panel s1 0.00 (script 0.00) · waiting: {exc.text}",
                         f"f2 panel s2 0.00 (script 1.00) · waiting: {exc.text}"]


# ---------------------------------------------------------------- a finish read before a job is taken for lost
def forgotten(ctx: DrawCtx, state: str, *outputs: str) -> dict:
    """The job finished on its own object and the book forgot it (no screen open) before `job.finished` ran."""
    data = finished(ctx, state, *outputs)
    job = ctx.jobs.made[-1]
    job.outputs = list(outputs)
    del ctx.jobs.book[job.id]
    return data


async def test_a_finish_the_book_forgot_is_written_when_the_pass_comes_first(ctx: DrawCtx) -> None:
    await framed(ctx)
    await drawing.step(ctx)
    data = forgotten(ctx, "done", "out/2026-10-19/f1.png")
    await drawing.step(ctx)
    assert picture(ctx, "f1") == "out/2026-10-19/f1.png" and made(ctx) == ["f1", "f2"]
    await drawing.on_finished(ctx, data)
    assert picture(ctx, "f1") == "out/2026-10-19/f1.png" and made(ctx) == ["f1", "f2"], "the finish does nothing"
    assert (ctx.jobs.made[1].params["panel"], drawing.busy()["panel"]) == ("f2", "f2")


async def test_a_finish_the_book_forgot_is_written_when_the_finish_comes_first(ctx: DrawCtx) -> None:
    await framed(ctx)
    await drawing.step(ctx)
    await drawing.on_finished(ctx, forgotten(ctx, "done", "out/2026-10-19/f1.png"))
    assert picture(ctx, "f1") == "out/2026-10-19/f1.png" and drawing.busy() is None
    await drawing.step(ctx)
    assert made(ctx) == ["f1", "f2"] and picture(ctx, "f1") == "out/2026-10-19/f1.png"


async def test_a_queued_job_cancelled_fails_its_panel(ctx: DrawCtx) -> None:
    await framed(ctx)
    await drawing.step(ctx)
    job = ctx.jobs.made[0]
    job.state = "cancelled"                  # cancelled while queued: no `job.finished`
    del ctx.jobs.book[job.id]
    await drawing.step(ctx)
    assert made(ctx) == ["f1", "f2"] and picture(ctx, "f1") is None
    assert drawing.failed == {("Script 1", "f1"): "The sketch job was cancelled"}


# ---------------------------------------------------------------- a picture gone from Media
async def test_a_picture_deleted_from_media_is_drawn_again(ctx: DrawCtx) -> None:
    await framed(ctx)
    await drawing.step(ctx)
    await drawing.on_finished(ctx, finished(ctx, "done", "out/2026-10-19/f1.png"))
    await drawing.step(ctx)
    await drawing.on_finished(ctx, finished(ctx, "done", "out/2026-10-19/f2.png"))
    (ctx.files.roots["out"] / "2026-10-19" / "f1.png").unlink()
    sent = len(ctx.bus.sent)
    await drawing.step(ctx)
    assert picture(ctx, "f1") is None and picture(ctx, "f2") == "out/2026-10-19/f2.png"
    assert len(ctx.bus.sent) == sent + 1, "published once"
    assert made(ctx) == ["f1", "f2", "f1"]
    assert [p["id"] for _, _, p in panels.panels(on_disk(ctx))] == ["f1", "f2"], "the same panel, its id kept"


def test_forget_names_the_panels_set_not_drawn() -> None:
    script = {"scenes": [{"shots": [{"events": [
        {"id": "f1", "kind": "panel", "at_ms": 0, "picture": "out/a.png", "stale": False},
        {"id": "f2", "kind": "panel", "at_ms": 9, "picture": "out/b.png", "stale": False},
        {"id": "f3", "kind": "panel", "at_ms": 20, "picture": None, "stale": False}]}]}]}
    assert panels.forget(script, lambda item: item == "out/b.png") == ["f1"]
    assert [p["picture"] for _, _, p in panels.panels(script)] == [None, "out/b.png", None]
