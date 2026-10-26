"""The context key's rename (`scriptshape.renamed`, `scripts._load`, `first_cut/script._renamed`): a version-2 file
saved before the rename, its cards under the old key, opens with the same cards and is never rewritten by a read; its
next write (a tool call or a card edit) saves `context` only. The old key is taken from the vocabulary scanner, so this
file carries no retired word. Neutral names only (CLAUDE.md): the cast is the shipped example's, read from the file."""
from __future__ import annotations

import json
from pathlib import Path

from hub.modules.director import owner, routes, scripts, tools
from hub.modules.first_cut import script as first_cut_script
from tests.engine.test_media_characters import png_bytes
from tests.engine.test_script_shape import FIXTURE
from tests.engine.test_script_tools import Ctx, call, ctx  # noqa: F401  (the fixture)
from tools import vocabulary

OLD = next(iter(vocabulary.RETIRED))
NAME = "Script 1"
SHIPPED = json.loads(FIXTURE.read_text(encoding="utf-8"))


def _old(value: dict) -> dict:
    """`value` with `context` named the old key, in its place."""
    return {(OLD if k == "context" else k): v for k, v in value.items()}


def _write(c: Ctx, name: str, value: dict) -> Path:
    path = routes.folder(c) / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def _problem(c: Ctx, name: str) -> str | None:
    rows = scripts.listing(routes.folder(c), routes.characters(c))
    return next(row["problem"] for row in rows if row["name"] == name)


def test_an_old_file_opens_with_the_same_cards(ctx: Ctx) -> None:  # noqa: F811
    old = _write(ctx, NAME, _old(SHIPPED))
    _write(ctx, "Script 2", SHIPPED)
    (ctx.data_dir.parents[1] / "Characters" / "Character 1.png").write_bytes(png_bytes())   # the fixture's cast
    before = old.read_bytes()
    chars = routes.characters(ctx)
    got, want = scripts.one(routes.folder(ctx), NAME, chars), scripts.one(routes.folder(ctx), "Script 2", chars)
    assert got["problem"] is None and list(got["script"]) == ["version", "context", "scenes"]
    for key in ("script", "pictures", "unpictured", "seconds"):
        assert got[key] == want[key], key
    assert got["pictures"], "the cards' pictures found"
    assert _problem(ctx, NAME) is None
    assert old.read_bytes() == before, "a read writes nothing"


async def test_the_next_write_saves_context_only(ctx: Ctx) -> None:  # noqa: F811
    path = _write(ctx, NAME, _old(SHIPPED))
    tools._pointer(ctx).replace({"name": NAME})
    await call(ctx, "context_set", {"style": "style 1"})
    held = json.loads(path.read_text(encoding="utf-8"))
    assert list(held) == ["version", "context", "scenes"] and held["version"] == 2 and OLD not in held
    assert held["context"]["style"] == "style 1"
    assert held["context"]["cast"] == SHIPPED["context"]["cast"]

    path = _write(ctx, "Script 2", _old(SHIPPED))
    member = SHIPPED["context"]["cast"][0]["name"]
    got = await owner.edit_op(ctx, {"name": "Script 2", "op": "member", "member": member, "field": "look",
                                    "value": "look 1"})
    assert "problem" not in got, got
    held = json.loads(path.read_text(encoding="utf-8"))
    assert list(held) == ["version", "context", "scenes"] and held["version"] == 2 and OLD not in held
    assert held["context"]["cast"][0]["look"] == "look 1"


def test_what_the_rename_leaves_alone(ctx: Ctx) -> None:  # noqa: F811
    both = {"version": 2, "context": SHIPPED["context"], OLD: SHIPPED["context"], "scenes": SHIPPED["scenes"]}
    _write(ctx, "Script 1", both)
    assert _problem(ctx, "Script 1") == f"The script has a key the format does not know: {OLD}"
    no_cast = {"version": 2, OLD: {"set": SHIPPED["context"]["set"]}, "scenes": SHIPPED["scenes"]}
    _write(ctx, "Script 2", no_cast)
    assert _problem(ctx, "Script 2") == "The script has no context"
    one = {"version": 1, "scenes": SHIPPED["scenes"]}
    _write(ctx, "Script 3", one)
    got = scripts.one(routes.folder(ctx), "Script 3", routes.characters(ctx))
    assert got["problem"] is None and got["script"] == one and got["pictures"] == {}


def test_the_first_cut_reads_an_old_file(ctx: Ctx) -> None:  # noqa: F811
    _write(ctx, NAME, _old(SHIPPED))
    got = first_cut_script.load(ctx, NAME)
    assert isinstance(got, dict) and OLD not in got and list(got)[:3] == ["version", "context", "scenes"]
    assert got["context"]["set"] == SHIPPED["context"]["set"] and got["context"]["style"] == SHIPPED["context"]["style"]
