"""Each model's own files, chosen in Settings: the Settings → Image models section's routes.

`GET /model-files`: every model with its parts that name a file (what the engine uses now and where it found
it), and the weight files in the engine's checkpoint folders and LoRA folders to choose from. `PUT /model-files
{model, part, path}`: that part of that model uses `path` (an existing file anywhere on this computer, never copied,
moved or renamed); `path` null puts the engine's own back. The engine line's adapter writes the choice where the
engine reads model definitions (`hub/worker/adapters/modelfiles.py`), and the engine reads them again.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from starlette.requests import Request

from hub.core.api import Ctx, Invalid

from . import models
from .routes import unavailable

FILE_EXT = (".safetensors", ".sft", ".gguf", ".pt", ".pth", ".bin", ".ckpt")   # the weight files offered and taken
NOT_A_FILE = "Not a weight file on this computer (an absolute path to a .safetensors, .gguf or like file)"


def weight_files(folders: list[str]) -> list[str]:
    """The weight files under `folders` (any depth; hidden folders and partial downloads left out), sorted, once; a
    folder inside another listed one is walked with it (the engine lists a folder and its first-level subfolders)."""
    seen: set[str] = set()
    out: list[str] = []
    real = [os.path.realpath(f) for f in folders]
    tops = [f for f, r in zip(folders, real, strict=True)
            if not any(r != o and r.startswith(o.rstrip(os.sep) + os.sep) for o in real)]
    for top in dict.fromkeys(tops):
        for here, dirs, files in os.walk(top):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for name in sorted(files):
                path = os.path.join(here, name)
                real = os.path.realpath(path)
                if name.lower().endswith(FILE_EXT) and not name.startswith(".") and real not in seen:
                    seen.add(real)
                    out.append(path)
    return out


async def _listing(ctx: Ctx, rescan: bool = False) -> Any:
    try:
        cat = await ctx.engine.query("models")
        files = await ctx.engine.query("files", rescan=rescan)
    except Exception as exc:
        return unavailable(exc)
    engine = cat.get("engine") or {}
    scratch = (engine.get("checkpoints") or [None])[0]                  # the Hub's own scratch folder: not offered
    weights = [p for p in engine.get("checkpoints") or [] if p != scratch and os.path.isdir(p)]
    loras = {d for m in cat["models"] for d in (*(m.get("lora_dirs") or []), *(m.get("lora_extra") or []))}
    listed = [{"id": m["id"], "name": m["name"], "kind": m.get("kind", "image"), "parts": files.get(m["id"]) or []}
              for m in cat["models"] if m["id"] in files
              and m.get("status") in ("available", "partial")]          # only what Generate shows
    files, lora_files = await asyncio.gather(
        asyncio.to_thread(weight_files, weights), asyncio.to_thread(weight_files, sorted(d for d in loras
                                                                                        if os.path.isdir(d))))
    return {"models": [m for m in listed if m["parts"]], "files": files, "loras": lora_files}


async def get_model_files(ctx: Ctx, request: Request) -> Any:
    """`?fresh=1`: the engine looks for each part's file again (a file just added to a folder)."""
    return await _listing(ctx, request.query_params.get("fresh") == "1")


async def choose_model_file(ctx: Ctx, request: Request) -> Any:
    """{model, part, path}: path an existing absolute weight file, or null for the engine's own."""
    body: Any = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("model"), str) or not isinstance(body.get("part"), str):
        raise Invalid("model", "Send the model, the part and the file")
    path = body.get("path")
    if path is not None and (not isinstance(path, str) or not os.path.isabs(path) or not os.path.isfile(path)
                             or not path.lower().endswith(FILE_EXT)):
        raise Invalid("path", NOT_A_FILE)
    try:
        await ctx.engine.query("files", choose=(body["model"], body["part"], path))
        await models.catalog(ctx)                                   # the job builder's copy follows
    except ValueError as exc:
        raise Invalid("part", str(exc)) from None
    except Exception as exc:
        return unavailable(exc)
    return await _listing(ctx)
