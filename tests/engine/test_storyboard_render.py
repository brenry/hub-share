"""Rendering a storyboard and drawing a cell (Stage 8, S3 and S4) through Generate Image's real job builder: the
params a cell submits pass `build.image_job` as they are, one clip waits at a time and the next cell goes when it
finishes, a clip is filed under the storyboard by its cell's number, a failed cell stops the drip and names the cell,
and a drawn picture becomes its cell with the cell's text."""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from hub.core.api import Invalid, frames_for
from hub.core.features import tools_of
from hub.core.messages import Refused
from hub.modules.storyboard import cells, manifest
from hub.modules.storyboard import render as rendering
from tests.engine.continue_kit import dump_catalog
from tests.engine.storyboard_kit import clear, clip, finished, make, pixels, submitted, temp_picture

START, OMNI, IMAGE = "minimax_h3", "minimax_h3_ref2va", "flux2_klein_9b"
TOOL = {t.name: t for t in tools_of(manifest.MODULE)}


@pytest.fixture(scope="module")
def clip_models(tmp_path_factory) -> list[dict]:
    return dump_catalog(tmp_path_factory.mktemp("engine"))


@pytest.fixture(autouse=True)
def _fresh():
    clear()
    yield
    clear()


@pytest.fixture
async def ctx(tmp_path: Path, clip_models):
    c = await make(tmp_path, clip_models)
    for n in (1, 2, 3):
        await call(c, "put_cell", storyboard="Film", cell=n, picture="Character 11" if n != 2 else "Character 4",
                   text=f"seconds: {n + 4}\ncamera: still\ncast: Character 11, Character 4\n\n"
                        f"Shot {n}: the lamp turns.")
    await call(c, "set_storyboard_settings", storyboard="Film", model=START, tier="540p", aspect="16:9", seed="100")
    return c


async def call(ctx, name: str, **args):
    return await TOOL[name].fn(ctx, args)


async def test_a_render_drips_one_clip_at_a_time_and_files_each_by_its_cell(ctx, clip_models) -> None:
    started = await call(ctx, "render_storyboard", storyboard="Film")
    assert started == {"storyboard": "Film", "cells": [1, 2, 3], "job": "j_1", "state": "queued"}
    facts = rendering.clip_facts(next(m for m in clip_models if m["id"] == START))
    first = submitted(ctx)
    assert first == [{"model": START, "mode": "refs", "prompt": "Shot 1: the lamp turns.", "width": 960,
                      "height": 544, "frames": frames_for(facts, 5), "steps": None,
                      "seed": {"mode": "fixed", "value": 100}, "loras": [],
                      "references": ["drive/Storyboards/Film/01.png"]}], "the start frame is the cell picture"
    assert first[0]["frames"] == 124 and ctx.jobs.jobs["j_1"][0].plan.summary["seconds"] == 5.17
    for n, job in ((1, "j_1"), (2, "j_2"), (3, "j_3")):
        assert len(ctx.jobs.jobs) == n, "one clip waits at a time"
        await rendering.on_finished(ctx, finished(job, outputs=[clip(ctx, f"12000{n}-000")]))
    assert [p["seed"]["value"] for p in submitted(ctx)] == [100, 101, 102]
    assert [p["frames"] for p in submitted(ctx)] == [frames_for(facts, s) for s in (5, 6, 7)] == [124, 158, 175]
    assert cells.DRIP == {} and len(ctx.jobs.jobs) == 3
    listed = (await call(ctx, "list_storyboard_cells", storyboard="Film"))["cells"]
    assert [re.sub(r"^clips/\d{4}-\d\d-\d\d \d{6} - ", "", c["clip"]) for c in listed] == [  # c1573bb: flat names
        f"Film 0{n}.mp4" for n in (1, 2, 3)]


async def test_a_redo_gets_its_own_name_and_the_cell_shows_the_newest(ctx) -> None:
    for job, stem in (("j_1", "120001-000"), ("j_2", "120002-000")):
        await call(ctx, "render_storyboard", storyboard="Film", cells=[2])
        await rendering.on_finished(ctx, finished(job, outputs=[clip(ctx, stem)]))
    assert [p["references"] for p in submitted(ctx)] == [["drive/Storyboards/Film/02.png"]] * 2
    listed = (await call(ctx, "list_storyboard_cells", storyboard="Film"))["cells"]
    filed = [f for f in os.listdir(ctx.files.roots["clips"]) if " - Film 02" in f]   # c1573bb: flat names
    newest = max(filed, key=lambda f: (f[:17], int((re.search(r"-(\d+)\.mp4$", f) or [0, 1])[1])))
    assert len(filed) == 2 and [c["clip"] for c in listed] == [None, f"clips/{newest}", None]


async def test_the_identity_model_sends_the_cast_and_not_the_cell_picture(ctx) -> None:
    await call(ctx, "set_storyboard_settings", model=OMNI)
    await call(ctx, "render_storyboard", storyboard="Film", cells=[1])
    (params,) = submitted(ctx)
    assert params["references"] == ["chars/Character 11.png", "chars/Character 4.png"] and params["mode"] == "refs"


async def test_a_failed_cell_stops_the_drip_and_names_the_cell(ctx) -> None:
    await call(ctx, "render_storyboard", storyboard="Film")
    await rendering.on_finished(ctx, finished("j_1", outputs=[clip(ctx, "120001-000")]))
    ctx.jobs.jobs["j_2"][0].error = "Out of memory"
    await rendering.on_finished(ctx, finished("j_2", state="failed"))
    assert len(ctx.jobs.jobs) == 2 and cells.DRIP == {}
    assert (await call(ctx, "list_storyboard_cells", storyboard="Film"))["stopped"] == "Cell 2: Out of memory"
    await call(ctx, "render_storyboard", storyboard="Film", cells=[3])
    assert "stopped" not in await call(ctx, "list_storyboard_cells", storyboard="Film")


async def test_a_later_cell_the_builder_refuses_stops_the_drip_with_its_number(ctx) -> None:
    await call(ctx, "render_storyboard", storyboard="Film")
    await call(ctx, "put_cell", storyboard="Film", cell=2, text="seconds: 5\n\n")
    await rendering.on_finished(ctx, finished("j_1", outputs=[clip(ctx, "120001-000")]))
    assert len(ctx.jobs.jobs) == 1 and cells.DRIP == {}
    assert cells.ERRORS == {"Film": "Cell 2: the cell has no clip text"}


async def test_one_render_at_a_time_and_its_settings_first(ctx) -> None:
    await call(ctx, "render_storyboard", storyboard="Film")
    with pytest.raises(Invalid, match="Film is rendering now, cell 1"):
        await call(ctx, "render_storyboard", storyboard="Film", cells=[3])
    ctx.jobs.jobs["j_1"][0].state = "cancelled"            # taken off the queue: no job.finished comes
    await call(ctx, "render_storyboard", storyboard="Film", cells=[3])
    assert submitted(ctx)[-1]["prompt"] == "Shot 3: the lamp turns."
    clear()
    with pytest.raises(Invalid, match="Film has cells 1 to 3"):
        await call(ctx, "render_storyboard", storyboard="Film", cells=[4])
    ctx.doc("settings", {}).patch({"model": None})
    with pytest.raises(Invalid, match="Choose the clip model in the storyboard settings"):
        await call(ctx, "render_storyboard", storyboard="Film")


async def test_with_generate_image_off_the_render_says_unknown_job_kind(ctx) -> None:
    def off(kind: str, params: dict):
        raise Refused("not_found", "Unknown job kind")

    ctx.jobs.submit = off
    with pytest.raises(Refused) as e:
        await call(ctx, "render_storyboard", storyboard="Film")
    assert e.value.text == "Unknown job kind" and cells.DRIP == {}


async def test_a_drawn_picture_becomes_its_cell_with_its_text(ctx) -> None:
    await call(ctx, "set_storyboard_settings", picture_model=IMAGE)
    drawn = await call(ctx, "draw_cell", storyboard="Film", cell=4, prompt="The keeper climbs.", cast=["Character 11"])
    assert drawn == {"storyboard": "Film", "cell": 4, "job": "j_1", "state": "queued"}
    (params,) = submitted(ctx)
    assert (params["model"], params["mode"], params["references"], params["images"]) == \
        (IMAGE, "refs", ["chars/Character 11.png"], 1)
    assert params["width"] > params["height"], "the clips' shape"
    waiting = await call(ctx, "put_cell", storyboard="Film", cell=4, text="seconds: 5\n\nShot 4: the character climbs.")
    assert waiting == {"storyboard": "Film", "cell": 4, "waiting": True}
    landed = temp_picture(ctx, "130000-000", (9, 9, 9))
    await rendering.on_finished(ctx, finished("j_1", outputs=[landed]))
    cell = (await call(ctx, "list_storyboard_cells", storyboard="Film"))["cells"][3]
    assert (cell["id"], cell["text"]) == ("drive/Storyboards/Film/04.png", "Shot 4: the character climbs.")
    assert pixels(ctx, cell["id"]) == pixels(ctx, landed)
    await call(ctx, "draw_cell", storyboard="Film", cell=2, prompt="Again.")
    again = temp_picture(ctx, "131000-000", (8, 8, 8))
    await rendering.on_finished(ctx, finished("j_2", outputs=[again]))
    cell = (await call(ctx, "list_storyboard_cells", storyboard="Film"))["cells"][1]
    assert pixels(ctx, cell["id"]) == pixels(ctx, again) and cell["text"] == "Shot 2: the lamp turns."
