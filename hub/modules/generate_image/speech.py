"""One Generate press on a speech model -> a JobPlan of one spoken line (`SpeechRequest`).

Who speaks is the one character whose picture is in the box: its name is the picture's name in the Characters folder.
Its voice is its sample when it has one (`<Name>.wav` beside its picture, kept from Sounds), else the words for it
(its `Voice`), else the engine invents one for this line alone. The line's length cap is the model's most (its
catalog `speech` facts): the line takes its natural length. Size, count, steps and guidance are not sent; LoRAs are
refused, and so is a line the engine cannot speak. Each refusal is one line. A line the engine plans longer
than `modules.generate-image.speech_turn_seconds` (4 to 45 s, default 5) goes as turns of whole sentences.
"""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from hub.core.api import Ctx, Invalid, JobPlan, SpeechRequest, request_wire, spoken_line

from . import pace

NO_SPEAKER = "Drop one character's picture"
ONE_SPEAKER = "One character speaks at a time"
NO_LORAS = "{} takes no LoRAs"


def _loras(p: dict) -> bool:
    """Whether the press sends a LoRA at a strength above 0."""
    value = p.get("loras") or []
    return isinstance(value, list) and any(isinstance(e, dict) and e.get("strength") not in (0, None) for e in value)


def speaker(ctx: Ctx, p: dict) -> dict[str, Any]:
    """The character in the box ({name, id, voice, sample}), or one line: none, more than one, not a character."""
    refs = p.get("references") if isinstance(p.get("references"), list) else []
    if len(refs) > 1:
        raise Invalid("references", ONE_SPEAKER)
    item = refs[0] if refs else None
    if not isinstance(item, str) or not item.startswith("chars/") or "/" in item[6:]:
        raise Invalid("references", NO_SPEAKER)
    name = PurePosixPath(item).stem
    found = next((c for c in ctx.files.characters() if c["id"] == item), None)
    if found is None or ctx.files.character(name) != item:
        raise Invalid("references", NO_SPEAKER)
    return found


def speech_job(p: dict, ctx: Ctx, model: dict, ui: dict, prompt: str, seeds: list[int]) -> JobPlan:
    """The line `prompt` in the voice of the character in the box: one engine task per seed, judged by its words
    when the judge is on (`speech_judge`); its takes are `presstakes`'."""
    try:
        spoken_line(prompt)
    except ValueError as err:
        raise Invalid("prompt", str(err)) from None
    if _loras(p):
        raise Invalid("loras", NO_LORAS.format(ui["label"]))
    who = speaker(ctx, p)
    sample = ctx.files.character_sample(who["name"])
    voice = str(who.get("voice") or "").strip() or None
    seconds = int(((ui.get("speech") or {}).get("seconds") or {}).get("max") or 0)
    if seconds <= 0:
        raise Invalid("model", f"{ui['label']} says no length for a line")
    tasks = tuple(request_wire(SpeechRequest(
        model["id"], prompt, seed, seconds, sample=str(sample) if sample else None,
        direction=None if sample else voice,
        turn_seconds=float(ctx.settings.get("speech_turn_seconds") or 0) or None, pace=pace.current(ctx),
        join_seconds=float(ctx.settings.get("speech_join_seconds") or 0) or None,
        judge=bool(ctx.settings.get("speech_judge", True)))) for seed in seeds)
    summary = {
        "prompt": prompt, "model": ui["label"], "model_id": model["id"], "mode": "refs", "kind": "sound",
        "width": None, "height": None, "count": len(seeds), "steps": None, "guidance": None, "seeds": list(seeds),
        "loras": [],
        "references": [who["name"]], "voice": "sample" if sample else "words" if voice else "new",
    }
    return JobPlan("image", model["id"], tasks, summary)
