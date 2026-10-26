"""A reference video beside a clip's pictures: the engine's one-reference-video choice. Stdlib only.

The model's catalog entry names the letters (`video.reference_video`, the facts file's: Ref2VA's "Use One Reference
Video", `V-U`); they join the task's `video_prompt_type` as upstream's own UI joins a guide choice to the reference
pictures' letters, each letter not yet there appended in order (`wgp.py:11152-11157` `add_to_sequence`, used by
`:11302-11303` for the pictures and `:11385-11386` for the guide: "I" then "V-U" is "IV-U"). The clip's real path is
`video_guide`. The engine keeps the first 15 s and refuses a video under 2 s (handler `:1000`, `:1004`);
the Hub sends the file as it is and refuses the short one first. A model without the choice, and a continue, are
refused in one line; nothing is dropped.
"""
from __future__ import annotations

from typing import Any

try:
    from ..faults import Refused
except ImportError:  # run as a script by the engine's Python
    from faults import Refused

NO_VIDEO = "{} takes no reference video"
VIDEO_CONTINUE = "A continued clip takes no reference video"
VIDEO_SHORT = "A reference video is at least 2 s"
SHORTEST = 2.0                 # the handler, :1000


def add_to_sequence(source: str, letters: str) -> str:
    """`source` with each letter of `letters` it lacks appended, in order (upstream `wgp.py:11152-11157`)."""
    out = source
    for letter in letters:
        if letter not in source:
            out += letter
    return out


def merge(task: dict[str, Any], request: Any, entry: dict, by: dict[str, list[Any]]) -> dict[str, Any]:
    """The clip's task with the reference video: its letters joined to `video_prompt_type`, its path `video_guide`."""
    letters = str((entry.get("video") or {}).get("reference_video") or "")
    if not letters:
        raise Refused(NO_VIDEO.format(entry.get("name") or request.model))
    if by["source"]:
        raise Refused(VIDEO_CONTINUE)
    if float(getattr(request, "video_seconds", None) or 0) < SHORTEST:
        raise Refused(VIDEO_SHORT)
    return {**task, "video_prompt_type": add_to_sequence(str(task.get("video_prompt_type") or ""), letters),
            "video_guide": request.video}
