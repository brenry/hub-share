"""Shared setup for the storyboard tests: a Storyboard context and a Generate Image context over one real `Files`
(Temp, clips, a Drive with the storyboards folder set, a Characters folder), Generate's real job builder behind the
storyboard's `ctx.jobs.submit`, and helpers that land a picture or a clip as the engine would."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from hub.core.files import Files
from hub.modules.generate_image import build, models
from hub.modules.storyboard import cells
from tests.engine.continue_kit import Bus
from tests.engine.helpers import FakeCtx, FakeEngine, load_catalog

KIND = "generate-image.image"
DAY = "2026-10-14"
CAST = {"Character 11": (64, 64, (200, 10, 10)), "Character 4": (64, 96, (10, 200, 10))}


def clear() -> None:
    cells.DRAWS.clear()
    cells.DRIP.clear()
    cells.ERRORS.clear()


async def make(tmp_path: Path, clip_models: list[dict] | None = None, boards: str | None = "Storyboards") -> FakeCtx:
    """The storyboard's context; `ctx.gi` is Generate Image's, whose builder checks every submitted job."""
    cat = load_catalog("catalog_upstream.json", tmp_path / "loras")
    cat["models"] += clip_models or []
    data, drive, chars = tmp_path / "data", tmp_path / "Drive", tmp_path / "Characters"
    drive.mkdir()
    chars.mkdir()
    for name, (w, h, rgb) in CAST.items():
        Image.new("RGB", (w, h), rgb).save(chars / f"{name}.png")
    files = Files(data, drive, chars)
    files.set_storyboards(boards)
    gi = FakeCtx("generate-image", data, FakeEngine(cat))
    gi.bus, gi.files = Bus(), files
    await models.catalog(gi)
    ctx = FakeCtx("storyboard", data, FakeEngine(cat), {KIND: lambda p, _c: build.image_job(p, gi)})
    ctx.files, ctx.gi = files, gi       # type: ignore[attr-defined]
    return ctx


def temp_picture(ctx: Any, stem: str, rgb: tuple[int, int, int], group: str = "") -> str:
    """A picture in Temp as the engine lands one: `out/<day>/[<group>/]<time>.png`."""
    rel = f"{DAY}/{group + '/' if group else ''}{stem}.png"
    path = ctx.files.roots["out"] / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (80, 48), rgb).save(path)
    return f"out/{rel}"


def clip(ctx: Any, stem: str) -> str:
    """A clip in the clips root as the engine lands one: `clips/<day>/<time>.mp4`."""
    path = ctx.files.roots["clips"] / DAY / f"{stem}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0\0\0\x08free")
    return f"clips/{DAY}/{stem}.mp4"


def pixels(ctx: Any, item: str) -> bytes:
    with Image.open(ctx.files.resolve(item)) as im:
        return im.convert("RGB").tobytes()


def finished(job: str, state: str = "done", outputs: list[str] | None = None) -> dict:
    return {"job": job, "kind": KIND, "tool": "generate-image", "state": state, "outputs": outputs or []}


def submitted(ctx: Any) -> list[dict]:
    """The params of every job the storyboard submitted, in order."""
    return [params for _job, params in ctx.jobs.jobs.values()]
