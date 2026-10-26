"""Shared setup for the continue tests (Stage 6): the real worker's catalog for the fake engine's H3-like definitions,
a module context over the real `Files` (clips root included) and clips written into it."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from hub.core.files import Files
from hub.modules.generate_image import build, models
from tests.engine.helpers import ENGINE_PYTHON, WORKER, FakeCtx, FakeEngine, load_catalog, make_engine_root
from tests.fakes.mp4 import tiny_mp4

PRUNED, FUSED, OMNI, IMAGE = "minimax_h3", "minimax_h3_fused_turbo", "minimax_h3_ref2va", "flux2_klein_9b"
LABEL, OMNI_LABEL = "H3 First / Last — Pruned", "H3 Omni — Pruned"
DAY, STEM = "2026-10-14", "101500-123"
LOOSE = f"clips/{DAY}/{STEM}.mp4"
PROMPT = "integrated_multimodal_description: [Shot 1] The rain gets louder."


def dump_catalog(base: Path) -> list[dict]:
    """The clip models as the real worker reports them for the fake engine."""
    root = make_engine_root(base, "legacy")
    out = base / "catalog.json"
    subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--dump-catalog", str(out)],
                   check=True, capture_output=True, timeout=60)
    return [m for m in json.loads(out.read_text())["models"] if m["kind"] == "video"]


class Bus:
    """Records what is published; a Generate window is open."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict]] = []

    def publish(self, lane: str, type: str, data: dict, key: str | None = None) -> None:
        self.sent.append((lane, type, data))

    def presence(self) -> dict:
        return {"screens": {"workspace": 1}}


async def make_ctx(tmp_path: Path, clip_models: list[dict], only: tuple[str, ...] | None = None) -> FakeCtx:
    """A module context whose catalog is the image fixture plus the clip models (`only`: those ids alone)."""
    cat = load_catalog("catalog_upstream.json", tmp_path / "loras")
    cat["models"] += clip_models
    if only is not None:
        cat["models"] = [m for m in cat["models"] if m["id"] in only]
    c = FakeCtx("generate-image", tmp_path / "data", FakeEngine(cat), {"image": build.image_job})
    c.bus = Bus()
    c.files = Files(tmp_path / "data")
    await models.catalog(c)
    return c


def put_clip(ctx: Any, item: str = LOOSE, data: bytes | None = None, **facts: Any) -> str:
    """A clip in the clips root at `item` (`tiny_mp4` with `facts`: 960x544, 124 frames, sound by default)."""
    path = ctx.files.roots["clips"] / item.split("/", 1)[1]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if data is not None else tiny_mp4(**{"w": 960, "h": 544, "frames": 124, "audio": True,
                                                               **facts}))
    return item


def press(model: str = PRUNED, refs: list | None = None, **extra: Any) -> dict:
    """The Generate press a window sends with a clip in box 1."""
    return {"model": model, "mode": "refs", "prompt": PROMPT, "references": [LOOSE] if refs is None else refs,
            "width": 960, "height": 544, "frames": 124, "steps": None, "loras": [],
            "seed": {"mode": "fixed", "value": 7}, **extra}


def real(ctx: Any, item: str) -> str:
    return str(Path(ctx.files.resolve(item)).resolve())
