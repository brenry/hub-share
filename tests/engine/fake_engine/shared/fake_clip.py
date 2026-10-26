"""The fake engine's clips: a small MP4 (`tests/fakes/mp4.tiny_mp4`) whose boxes say what the real engine's file
would hold. A plain clip is `video_length` frames at `resolution`. A "V" task (`video_source`) follows the real
engine (R7 §2.1): the canvas is the source's, the frames to make are `video_length + overlap - 1`, split into
windows by the engine's own count (`1 + ceil((total - window) / (window - reuse))`, reuse = min(window - step,
overlap)), each window writing a file of the source plus the new frames so far; the last holds the source plus
`video_length - 1` frames. Paths of the reader and the writer come from `fake_engine.json` (`hub_clip`, `fakes`)."""
from __future__ import annotations

import functools
import importlib.util
import json
import math
import os
import sys
from typing import Any


@functools.cache
def _tools() -> tuple[Any, Any]:
    """The writer (`tiny_mp4`) and the Hub's reader (`clip.facts`), loaded at the first clip: their paths are the test
    rig's (`make_engine_root`), so a fake rebuilt from its capture alone still starts."""
    with open("fake_engine.json", encoding="utf-8") as f:
        spec = json.load(f)
    sys.path.insert(0, spec["fakes"])
    from mp4 import tiny_mp4

    reader = importlib.util.spec_from_file_location("fake_engine_clip", spec["hub_clip"])
    clip = importlib.util.module_from_spec(reader)
    reader.loader.exec_module(clip)
    return tiny_mp4, clip.facts


def windows(total: int, window: int, reuse: int) -> int:
    return 1 if total <= window else 1 + math.ceil((total - window) / (window - reuse))


def write(path: str, inputs: dict[str, Any], model_def: dict[str, Any]) -> list[str]:
    """The files a clip task makes, in order; the last is the whole clip."""
    tiny_mp4, facts = _tools()
    n = int(inputs["video_length"])
    sound = bool(model_def.get("returns_audio"))
    if "V" not in str(inputs.get("image_prompt_type") or "") or not inputs.get("video_source"):
        w, h = (int(v) for v in str(inputs["resolution"]).split("x"))
        with open(path, "wb") as f:
            f.write(tiny_mp4(w=w, h=h, frames=n, audio=sound))
        return [path]
    src = facts(inputs["video_source"])
    overlap = int(inputs.get("sliding_window_overlap") or 1)
    window = int(inputs.get("sliding_window_size") or n)
    count = windows(n + overlap - 1, window, min(window - int(model_def["frames_steps"]), overlap))
    made = []
    for k in range(1, count + 1):
        name = path if k == count else f"{os.path.splitext(path)[0]}_{k}.mp4"
        with open(name, "wb") as f:
            f.write(tiny_mp4(w=src["w"], h=src["h"], frames=src["frames"] + (n - 1) * k // count, audio=sound))
        made.append(name)
    return made
