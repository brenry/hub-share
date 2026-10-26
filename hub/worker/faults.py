"""One plain line for an engine failure: the first error's message and, when the error carries a traceback (live
or as text), the frame it came from. Stdlib only.
"""
from __future__ import annotations

import os
import traceback
import types
from typing import Any

try:
    from .engineapi import STAGES
except ImportError:  # run as a script by the engine's Python
    from engineapi import STAGES


class Refused(ValueError):
    """The adapter cannot turn a request into its engine's task (a picture the model takes no role for, a mixed
    cut-out on a line with one switch, a window above the line's largest): the text is the one line shown, with no
    frame (it is the Hub's own refusal, not an engine fault)."""


class Unready(RuntimeError):
    """What the engine would fetch (the worker is offline) is not on the server: the text is the one line shown.
    An adapter raises it from `prepare(root)`, before the engine opens; `lacking(w, model)` lists the files it
    would fetch before that model loads (None: those every model needs) and the worker refuses the task instead."""


def where(error: Any) -> str:
    """The engine frame that raised (file:line in function), from a live traceback or the engine's text of one."""
    tb = getattr(error, "__traceback__", None) or getattr(error, "traceback", None) or getattr(error, "tb", None)
    if isinstance(tb, types.TracebackType):
        frames = traceback.extract_tb(tb)
        if not frames:
            return ""
        last = frames[-1]
        return f" (at {os.path.basename(last.filename)}:{last.lineno} in {last.name})"
    if not isinstance(tb, str):
        tb = str(getattr(error, "message", error))        # some engine errors carry the traceback in their text
    lines = [ln.strip() for ln in tb.splitlines() if ln.strip().startswith("File ")]
    return f" ({' <- '.join(ln.replace('File ', '') for ln in lines[-2:])})" if lines else ""


def failure(errors: list[Any], cancelled: bool) -> dict[str, str]:
    """One plain line for the first engine error, with the frame it came from (none for the adapter's own refusal,
    `Refused`); its stage in the Hub's words
    (`engineapi.STAGES`): an engine's own stage word (`validation`...) reads `generation`."""
    stages = [str(getattr(e, "stage", "") or "") for e in errors]
    if cancelled or "cancelled" in stages:
        return {"stage": "cancelled", "text": "Cancelled"}
    first = next((e for e in errors if str(getattr(e, "message", e)).strip()), None)
    message = str(getattr(first, "message", first)) if first is not None else ""
    if "out of memory" in message.lower():
        return {"stage": "oom", "text": "Out of GPU memory"}
    line = message.strip().splitlines()[0][:600] if message.strip() else "The engine could not make the image"
    stage = next((s for s in stages if s), "generation")
    return {"stage": stage if stage in STAGES else "generation",
            "text": line + ("" if isinstance(first, Refused) else where(first))}


