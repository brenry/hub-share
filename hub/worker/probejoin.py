"""Measure a join before its defaults are final (Stage 11, step 0), run by hand on the engine host:

    python -B main.py --root ROOT --state DIR --probe-join CLIP CLIP [CLIP]... [--trim] [--models DIR]...
                      [--profile N] -- ENGINE ARGS

The engine is opened as for `--probe-continue` (so the adapter's `prepare` names ffmpeg and ffprobe), then the
worker's own join (`join.run`) joins the clips in order, whole (the copy path when the inputs allow it) or, with
`--trim`, each kept from frame 12 to its frames - 12 (the encode path), at the sequence defaults (crf 18, preset
medium). Its file is moved from `<state>/outbox` to `<state>/joined.mp4`. One JSON line goes to stdout:

    {"path", "inputs": [{"file", "v", "a"}], "out": {frames, w, h, fps, seconds, audio}, "expect_frames",
     "open_seconds", "join_seconds"}

The clips' facts come from the Hub's own MP4 reader (`hub/core/clip.py`, loaded by its path). Nothing is written in
the engine root or the Hub's data.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

try:
    from . import join, probe, wan2gp
except ImportError:  # run as a script by the engine's Python
    import join
    import probe
    import wan2gp

CUT = 12                  # --trim: frames dropped at each end of every clip
CRF, PRESET = 18, "medium"


def request(reader: Any, clips: list[str], trim: bool) -> dict[str, Any]:
    """The sequence module's request for these clips (whole, or trimmed by `CUT` at each end)."""
    items = []
    for path in clips:
        f = reader.facts(path)
        if trim and f["frames"] <= 2 * CUT:
            raise RuntimeError(f"{os.path.basename(path)} has {f['frames']} frames, too few to trim")
        items.append({"path": path, "in": CUT if trim else 0, "out": f["frames"] - CUT if trim else f["frames"],
                      "fps": f["fps"], "w": f["w"], "h": f["h"], "frames": f["frames"], "audio": f["audio"]})
    first = items[0]
    return {"items": items, "canvas": {"w": first["w"], "h": first["h"], "fps": first["fps"]}, "audio": [],
            "crf": CRF, "preset": PRESET}


def run(opts: argparse.Namespace, engine_args: list[str]) -> int:
    clips = [os.path.realpath(c) for c in opts.join]       # before the engine moves the cwd to its root
    reader = probe.clip_reader()
    asked = request(reader, clips, opts.trim)
    engine = wan2gp.Engine(opts.root, os.path.abspath(opts.state), engine_args, opts.models, opts.profile)
    started = time.monotonic()
    engine.open()
    opened = round(time.monotonic() - started, 2)
    seen: list[Any] = []
    made: list[str] = []
    started = time.monotonic()
    done = join.run("probe", 1, asked, lambda m: made.append(str(m["file"])) if m.get("ev") == "output" else None,
                    engine.loaded(), engine.state, told=lambda cmd, probed: seen.append((cmd, probed)))
    took = round(time.monotonic() - started, 2)
    if not done.get("ok") or not made or not seen:
        raise RuntimeError(f"The join failed: {(done.get('error') or {}).get('text') or 'no file'}")
    dest = os.path.join(engine.state, "joined.mp4")
    os.replace(made[-1], dest)
    out = reader.facts(dest)
    cmd, probed = seen[-1]
    line = {"path": cmd.path, "inputs": [{"file": c, **p} for c, p in zip(clips, probed, strict=True)],
            "out": {key: out[key] for key in ("frames", "w", "h", "fps", "seconds", "audio")},
            "expect_frames": cmd.expect, "open_seconds": opened, "join_seconds": took}
    sys.stdout.write(json.dumps(line) + "\n")
    sys.stdout.flush()
    return 0
