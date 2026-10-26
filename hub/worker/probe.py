"""Measure a continue before its scene cap is set (Stage 6, step 0), run by hand on the engine host:

    python -B main.py --root ROOT --state DIR --probe-continue CLIP [--chain K] [--model ID] [--frames N]
                      [--models DIR]... [--profile N] -- ENGINE ARGS

The engine is opened as for `--dump-catalog`. The first catalog model whose facts say `continues` (or `--model`) runs
K continue steps: step 1 continues CLIP, step k the file step k-1 made. Each step sends the Hub's continue request
(`continue_request`, the same as `hub/modules/generate_image/chain.py` builds) with seed 1, the model's default steps
and `PROMPT`; its output is moved from `<state>/outbox` to `<state>/step<k>.mp4`. One JSON line per step goes to stdout,
with the window the engine task was sent (`adapter.window`), never one worked out again here.
The clips' facts come from the Hub's own MP4 reader (`hub/core/clip.py`, stdlib only), loaded by its path (as the
serving worker's `adapters/soundtail.py` does). `expect`: the frames a step adds, less those it left off the
source's end (`adapter.dropped`). Nothing is written in the engine root or the Hub's data.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from types import ModuleType
from typing import Any

try:
    from . import wan2gp
    from .engineapi import ClipRequest, Reference
except ImportError:  # run as a script by the engine's Python
    import wan2gp
    from engineapi import ClipRequest, Reference

PROMPT = "The same shot continues."
SEED = 1
CLIP_READER = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "core", "clip.py")


def clip_reader() -> ModuleType:
    """`hub/core/clip.py`, loaded from its file (it imports the stdlib alone)."""
    spec = importlib.util.spec_from_file_location("hub_probe_clip", CLIP_READER)
    if spec is None or spec.loader is None:
        raise RuntimeError("The Hub's clip reader is not beside the worker")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pick(models: list[dict], wanted: str | None) -> dict:
    """`wanted`, or the first model whose files are there and whose facts say it continues a clip."""
    for m in models:
        facts = m.get("video") or {}
        if (m.get("id") == wanted) if wanted else (facts.get("continues") and m.get("status") != "missing"):
            if not facts.get("continues"):
                raise RuntimeError(f"{m.get('name') or wanted} cannot continue a clip")
            return m
    raise RuntimeError(f"No model {wanted!r} in the catalog" if wanted else "No model here can continue a clip")


def frames(model: dict, asked: int | None) -> int:
    """`asked`, else the model's default length capped at the longest step (the largest window, else the frame
    maximum, less `overlap - 1`; on the lattice)."""
    if asked:
        return asked
    v = model["video"]
    top = v.get("window_max") or v["frames"]["max"]
    lo, step, hi = v["frames"]["min"], v["frames"]["step"], min(v["frames"]["max"], top - (v["overlap"] - 1))
    return min(v["frames"]["default"], lo + max(0, (hi - lo) // step) * step)


def continue_request(model: dict, source: str, w: int, h: int, n: int, steps: Any, seed: int,
                     prompt: str) -> ClipRequest:
    """The one request of a continue: the clip (an absolute real path) as the `source`, the new part `n` frames at
    the source's size, in one pass (the adapter's window: `n + overlap - 1`)."""
    return ClipRequest(model["id"], prompt, (w, h), seed, n, steps=steps, references=[Reference(source, "source")])


def step(engine: wan2gp.Engine, reader: ModuleType, model: dict, k: int, source: str, n: int) -> dict[str, Any]:
    """One continue of `source`: the task run, its file moved to `<state>/step<k>.mp4`, the line about it."""
    src = reader.facts(source)
    request = continue_request(model, source, src["w"], src["h"], n, model["video"]["steps"], SEED, PROMPT)
    made: list[str] = []
    done = engine.run(f"probe-{k}", 1, request,
                      lambda m: made.append(str(m["file"])) if m.get("ev") == "output" else None)
    if not done.get("ok") or not made:
        raise RuntimeError(f"Step {k} failed: {(done.get('error') or {}).get('text') or 'no file'}")
    dest = os.path.join(engine.state, f"step{k}.mp4")
    os.replace(made[-1], dest)
    out = reader.facts(dest)
    return {"step": k, "model": model["id"], "window": engine.adapter.window(engine.sent), "files": engine.made,
            "source": {key: src[key] for key in ("frames", "w", "h", "seconds")},
            "out": {key: out[key] for key in ("frames", "w", "h", "seconds", "audio")},
            "grew": out["frames"] - src["frames"], "expect": n - 1 - engine.adapter.dropped(engine.sent),
            "dropped": engine.adapter.dropped(engine.sent), "peak_vram_mb": done.get("peak_vram_mb"),
            "peak_rss_mb": done.get("peak_rss_mb"), "hwm_rss_mb": wan2gp.rss_mb("VmHWM:"),
            "seconds": done.get("seconds"), "path": dest}


def run(opts: argparse.Namespace, engine_args: list[str]) -> int:
    source = os.path.realpath(opts.probe)                  # before the engine moves the cwd to its root
    reader = clip_reader()
    engine = wan2gp.Engine(opts.root, os.path.abspath(opts.state), engine_args, opts.models, opts.profile)
    engine.open()
    model = pick(engine.catalog()["models"], opts.model)
    n = frames(model, opts.frames)
    for k in range(1, opts.chain + 1):
        line = step(engine, reader, model, k, source, n)
        source = line.pop("path")
        sys.stdout.write(json.dumps(line) + "\n")
        sys.stdout.flush()
    return 0
