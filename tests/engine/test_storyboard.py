"""The Storyboard module's declarations: the registry takes them, the core generates eight tools with
their labels, every tool refuses while no storyboards folder is set, and the cells are numbered pictures in a Drive
folder whose text lives in the picture's one text field."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from hub.core import schema
from hub.core.api import Invalid
from hub.core.features import tools_of
from hub.core.registry import discover, validate
from hub.modules.storyboard import cells, manifest, screen
from hub.settings import validate as validate_settings
from tests.engine.storyboard_kit import clear, make, pixels, temp_picture

TOOLS = [
    ("get_storyboard_settings",
     "Settings of the Clip Cells screen: storyboard, model, picture_model, tier, aspect, steps, seed."),
    ("set_storyboard_settings", "Set settings of the Clip Cells screen: storyboard, model, picture_model, tier, "
                                "aspect, steps, seed. Returns the settings after."),
    ("list_storyboards", "Storyboards in the storyboards folder, by name, with the number of cells in each."),
    ("list_storyboard_cells", "Cells of one storyboard in order: number, seconds, camera, cast, clip text, and the "
                              "cell's newest clip when there is one."),
    ("put_cell", "Makes or replaces cell N of a storyboard: its picture from a character name or the newest Temp "
                 "picture, its text, or both. A first cell makes the storyboard."),
    ("move_cell", "Moves cell N of a storyboard to place M; the cells are renumbered 01 onward."),
    ("draw_cell", "Queues one picture from a picture prompt with the picture model and the cast's character pictures "
                  "as references; it becomes cell N when it lands, its text kept."),
    ("render_storyboard", "Queues one clip per cell of a storyboard, every cell or the listed ones, one after another "
                          "in cell order."),
]
TEXT = "seconds: 5\ncamera: slow push-in\ncast: Character 11, Character 4\n\nA lighthouse at dusk; the lamp turns."
TOOL = {t.name: t for t in tools_of(manifest.MODULE)}


@pytest.fixture(autouse=True)
def _fresh():
    clear()
    yield
    clear()


@pytest.fixture
async def ctx(tmp_path: Path):
    return await make(tmp_path)


async def call(ctx, name: str, **args):
    return await TOOL[name].fn(ctx, args)


async def refused(ctx, name: str, **args) -> str:
    with pytest.raises(Invalid) as e:
        await call(ctx, name, **args)
    return e.value.text


def test_the_registry_takes_the_declarations_and_the_shipped_modules_load() -> None:
    validate([manifest.MODULE])
    mods, errors = discover()
    assert "storyboard" in {m.id for m in mods} and errors == []
    m = manifest.MODULE
    assert (m.tab, m.jobs, m.routes, list(m.listens)) == (None, {}, (), ["job.finished"])
    others = {n for o in mods if o.id != m.id for n in (o.title, o.tab.label if o.tab else None) if n}
    assert m.title == "Clip Cells" and m.title not in others, "turned on, never a second Storyboard"


def test_eight_tools_with_their_labels() -> None:
    assert [(t.name, t.description) for t in tools_of(manifest.MODULE)] == TOOLS
    for _name, text in TOOLS:
        assert len(text) <= 200 and text.endswith(".")
        assert not re.search(r"\b(always|never|must)\b", text, re.I)


async def test_every_tool_refuses_in_one_line_without_a_storyboards_folder(tmp_path: Path) -> None:
    ctx = await make(tmp_path, boards=None)
    args = {"get_storyboard_settings": {}, "set_storyboard_settings": {"steps": 5}, "list_storyboards": {},
            "list_storyboard_cells": {"storyboard": "Film"},
            "put_cell": {"storyboard": "Film", "cell": 1, "picture": "Character 11"},
            "move_cell": {"storyboard": "Film", "from": 1, "to": 2},
            "draw_cell": {"storyboard": "Film", "cell": 1, "prompt": "a lighthouse"},
            "render_storyboard": {"storyboard": "Film"}}
    assert list(args) == [name for name, _ in TOOLS]
    for name, a in args.items():
        assert await refused(ctx, name, **a) == "No storyboards folder is set", name
    assert ctx.jobs.jobs == {}


async def test_a_first_cell_from_a_character_makes_the_storyboard_and_its_text_round_trips(ctx) -> None:
    made = await call(ctx, "put_cell", storyboard="Film", cell=1, picture="Character 11", text=TEXT)
    assert made == {"storyboard": "Film", "cell": 1, "id": "drive/Storyboards/Film/01.png"}
    assert pixels(ctx, made["id"]) == pixels(ctx, "chars/Character 11.png")
    assert ctx.files.picture_text(made["id"]) == TEXT
    assert await call(ctx, "list_storyboards") == {"folder": "Storyboards",
                                                   "storyboards": [{"name": "Film", "cells": 1}]}
    listed = await call(ctx, "list_storyboard_cells", storyboard="Film")
    assert listed == {"storyboard": "Film", "cells": [
        {"cell": 1, "id": made["id"], "seconds": 5, "camera": "slow push-in", "cast": ["Character 11", "Character 4"],
         "text": "A lighthouse at dusk; the lamp turns.", "clip": None}]}


async def test_a_cell_from_the_newest_temp_picture(ctx) -> None:
    temp_picture(ctx, "090000-000", (1, 2, 3))
    newest = temp_picture(ctx, "101500-000", (4, 5, 6))
    temp_picture(ctx, "100000-000", (7, 8, 9), group="Favorites")
    made = await call(ctx, "put_cell", storyboard="Film", cell=1, picture="newest")
    assert pixels(ctx, made["id"]) == pixels(ctx, newest)
    assert await refused(ctx, "put_cell", storyboard="Film", cell=2,
                         picture="Character 22") == "No character is called Character 22"


async def test_no_temp_picture_no_picture_yet_and_nothing_given_are_refused(ctx) -> None:
    assert await refused(ctx, "put_cell", storyboard="Film", cell=1, picture="newest") == "Temp holds no picture"
    assert await refused(ctx, "put_cell", storyboard="Film", cell=1, text=TEXT) == \
        "Cell 1 has no picture yet; give one"
    assert await refused(ctx, "put_cell", storyboard="Film", cell=1) == "Give the cell a picture, a text or both"


async def test_any_text_and_any_count_of_cells_are_kept(ctx) -> None:
    ctx.settings = {"cell_text_max": 50, "max_cells": 3}           # retired, read by nothing
    await call(ctx, "put_cell", storyboard="Film", cell=1, picture="Character 11", text="x" * 5000)
    [cell] = (await call(ctx, "list_storyboard_cells", storyboard="Film"))["cells"]
    assert cell["text"] == "x" * 5000
    assert await refused(ctx, "put_cell", storyboard="Film", cell=3, picture="Character 4") == "The next cell is 2"
    for n in range(2, 26):
        await call(ctx, "put_cell", storyboard="Film", cell=n, picture="Character 4")
    assert await refused(ctx, "put_cell", storyboard="Film", cell=27, picture="Character 4") == "The next cell is 26"


@pytest.mark.parametrize("text, why", [
    ("seconds: 5\nmood: grim\n\nA lighthouse.", "Unknown header line \"mood: grim\""),
    ("camera: pan\ncamera: tilt\n\nA lighthouse.", "The camera line is there twice"),
    ("seconds: soon\n\nA lighthouse.", "seconds is a number above 0"),
    ("seconds: 0\n\nA lighthouse.", "seconds is a number above 0"),
])
async def test_an_unknown_or_bad_header_is_refused(ctx, text: str, why: str) -> None:
    assert (await refused(ctx, "put_cell", storyboard="Film", cell=1, picture="Character 11",
                          text=text)).startswith(why)
    assert await call(ctx, "list_storyboards") == {"folder": "Storyboards", "storyboards": []}


def test_the_cell_text_format() -> None:
    assert cells.parse(TEXT) == {"seconds": 5, "camera": "slow push-in", "cast": ["Character 11", "Character 4"],
                                 "text": "A lighthouse at dusk; the lamp turns."}
    assert cells.write(cells.parse(TEXT)) == TEXT
    plain = "integrated_multimodal_description: [Shot 1] A lighthouse.\n\nThe lamp turns."
    assert cells.parse(plain) == {"seconds": None, "camera": "", "cast": [], "text": plain}, "no header: all clip"
    assert cells.write(cells.parse("seconds: 2.5\r\n\r\nGo.")) == "seconds: 2.5\n\nGo."


async def test_text_alone_keeps_the_picture_and_a_new_picture_keeps_the_text(ctx) -> None:
    first = (await call(ctx, "put_cell", storyboard="Film", cell=1, picture="Character 11", text=TEXT))["id"]
    again = (await call(ctx, "put_cell", storyboard="Film", cell=1, text="seconds: 3\n\nCloser."))["id"]
    assert again == first and pixels(ctx, again) == pixels(ctx, "chars/Character 11.png")
    swapped = (await call(ctx, "put_cell", storyboard="Film", cell=1, picture="Character 4"))["id"]
    assert pixels(ctx, swapped) == pixels(ctx, "chars/Character 4.png")
    assert ctx.files.picture_text(swapped) == "seconds: 3\n\nCloser."


async def test_cell_100_is_taken_and_written_as_100(ctx) -> None:
    for n in range(1, 101):                                         # no most of the Hub's on a cell
        schema.check(TOOL["put_cell"].input_schema, {"storyboard": "Film", "cell": n, "picture": "Character 11"})
        await call(ctx, "put_cell", storyboard="Film", cell=n, picture="Character 11")
    assert (ctx.files.roots["drive"] / "Storyboards" / "Film" / "100.png").is_file()
    assert (await call(ctx, "list_storyboard_cells", storyboard="Film"))["cells"][-1]["cell"] == 100
    moved = await call(ctx, "move_cell", storyboard="Film", **{"from": 100, "to": 1})
    assert moved["cells"][0] == "drive/Storyboards/Film/01.png" and moved["cells"][-1].endswith("/100.png")


async def test_numbering_after_a_move_keeps_each_cells_text(ctx) -> None:
    for n, who in enumerate(("Character 11", "Character 4", "Character 11"), 1):
        await call(ctx, "put_cell", storyboard="Film", cell=n, picture=who, text=f"Shot {n}.")
    moved = await call(ctx, "move_cell", storyboard="Film", **{"from": 3, "to": 1})
    assert moved["cells"] == [f"drive/Storyboards/Film/0{k}.png" for k in (1, 2, 3)]
    listed = (await call(ctx, "list_storyboard_cells", storyboard="Film"))["cells"]
    assert [c["text"] for c in listed] == ["Shot 3.", "Shot 1.", "Shot 2."]
    assert sorted(p.name for p in (ctx.files.roots["drive"] / "Storyboards" / "Film").iterdir()) == \
        ["01.png", "02.png", "03.png"]
    assert await refused(ctx, "move_cell", storyboard="Film", **{"from": 1, "to": 4}) == "Film has cells 1 to 3"


async def test_a_picture_dropped_in_by_hand_is_a_cell_and_the_next_cell_renumbers(ctx) -> None:
    await call(ctx, "put_cell", storyboard="Film", cell=1, picture="Character 11", text="Shot 1.")
    folder = ctx.files.roots["drive"] / "Storyboards" / "Film"
    shutil.copy(ctx.files.roots["chars"] / "Character 4.png", folder / "zz extra.png")
    listed = (await call(ctx, "list_storyboard_cells", storyboard="Film"))["cells"]
    assert [(c["cell"], c["id"], c["text"]) for c in listed] == [
        (1, "drive/Storyboards/Film/01.png", "Shot 1."), (2, "drive/Storyboards/Film/zz extra.png", "")]
    await call(ctx, "put_cell", storyboard="Film", cell=3, picture="Character 11", text="Shot 3.")
    assert sorted(p.name for p in folder.iterdir()) == ["01.png", "02.png", "03.png"]
    assert pixels(ctx, "drive/Storyboards/Film/02.png") == pixels(ctx, "chars/Character 4.png")


@pytest.mark.parametrize("name", ["../Elsewhere", "a/b", ".hidden", " ", "x" * 256])
async def test_a_storyboard_name_that_leaves_the_folder_is_refused(ctx, name: str) -> None:
    assert await refused(ctx, "put_cell", storyboard=name, cell=1, picture="Character 11") == cells.BAD_NAME
    assert not (ctx.files.roots["drive"] / "Elsewhere").exists()


async def test_an_unknown_storyboard_is_named(ctx) -> None:
    assert await refused(ctx, "list_storyboard_cells", storyboard="Nope") == "No storyboard is called Nope"
    assert await refused(ctx, "set_storyboard_settings", storyboard="Nope") == "No storyboard is called Nope"


async def test_the_settings_are_checked_against_live_lists(ctx) -> None:
    await call(ctx, "put_cell", storyboard="Film", cell=1, picture="Character 11")
    assert await call(ctx, "get_storyboard_settings") == {**screen.DEFAULTS, "seed": "random"}
    after = await call(ctx, "set_storyboard_settings", storyboard="film", picture_model="flux2_klein_9b", steps=8,
                       seed="41")
    assert after == {**screen.DEFAULTS, "storyboard": "Film", "picture_model": "flux2_klein_9b", "steps": 8,
                     "seed": "41"}
    assert await refused(ctx, "set_storyboard_settings", model="flux2_klein_9b") == \
        "No clip model with the id flux2_klein_9b can run"
    assert await refused(ctx, "set_storyboard_settings", tier="540p") == "Choose the clip model first"
    assert await refused(ctx, "set_storyboard_settings", aspect="wide") == \
        "Give the shape as width:height, such as 16:9"
    assert await refused(ctx, "set_storyboard_settings", seed="-1") == \
        "seed must be random or a whole number from 0 to 999999999"


def test_the_storyboards_retired_settings_are_dropped_when_read() -> None:
    assert validate_settings({})["modules"]["storyboard"] == {}
    assert validate_settings({"modules": {"storyboard": {"max_cells": 100, "cell_text_max": 0}}})["modules"][
        "storyboard"] == {}, "max_cells and cell_text_max retired, dropped when read"
