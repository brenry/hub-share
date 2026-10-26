"""A reference video beside a clip's pictures: a Clips item the screen sends with a clip, for the
camera and the set. Read where it is: nothing is copied, cut or converted; the engine keeps its first 15 s.

A model whose catalog entry has no `reference_video`, a continued clip, an item that is not a clip the Hub can read
and a clip under 2 s are each refused in one line (as the worker's, `refvideo`).
"""
from __future__ import annotations

import os
import posixpath

from hub.core.api import Ctx, Invalid

from . import chain

UNREAD = "The Hub cannot read this clip"
NO_VIDEO = "{} takes no reference video"              # as the worker's (`refvideo.NO_VIDEO`)
VIDEO_CONTINUE = "A continued clip takes no reference video"   # as the worker's (`refvideo.VIDEO_CONTINUE`)
VIDEO_SHORT = "A reference video is at least 2 s"     # as the worker's (`refvideo.VIDEO_SHORT`)
NOT_A_CLIP = "The Video box takes a clip from Media, Clips"
SHORTEST = 2.0


def video(ctx: Ctx, p: dict, ui: dict, held: bool) -> tuple[str, float, str] | None:
    """(the clip's real path, its seconds, its name) when the press sends one (`p["video"]`, a Clips item id), else
    None."""
    item = p.get("video")
    if item in (None, ""):
        return None
    if not (ui.get("video") or {}).get("reference_video"):
        raise Invalid("video", NO_VIDEO.format(ui["label"]))
    if held:
        raise Invalid("video", VIDEO_CONTINUE)
    if not isinstance(item, str) or not chain.is_clip(ctx, item):
        raise Invalid("video", NOT_A_CLIP)
    try:
        real = os.path.realpath(ctx.files.existing_media(item))
    except Invalid:
        raise Invalid("video", UNREAD) from None
    seen = ctx.files.clip_facts(item)
    if not seen:
        raise Invalid("video", UNREAD)
    if float(seen["seconds"]) < SHORTEST:
        raise Invalid("video", VIDEO_SHORT)
    return real, float(seen["seconds"]), posixpath.splitext(posixpath.basename(item))[0]
