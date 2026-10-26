"""The Wan2GP task a Hub request becomes: the keys, prompt letters, references and window, from the request and the
model's catalog entry. The fork's conventions are the default; a line's own differences are its `Line`. Stdlib only.

Pictures: one task per picture, references sent as the model's reference letters ("I" when it offers them, else its
first choice that takes pictures). Clips: one pass (the window is the clip, never under the line's smallest window; the
model's one-pass switch, when the catalog found one, sent off); a `start` (and `end`) picture fitted by crop or by the
line's config; `identity` pictures as the reference list the entry names (`key`: each with the engine's identity intent,
its name and its cut-out) or as reference pictures under the entry's letters (`letters`: one cut-out for all, so mixed
boxes are refused); a `source` clip continued in one window of `frames + overlap - 1`, `frames` new, never above the
line's largest window, with the identity pictures of a model that takes them. A picture whose role the model
does not take is refused in one line (`Refused`), never dropped. A spoken line (`speech`): one speaker's turn, the voice
the speaker's sample when there is one, else the words for it as the turn's direction; a line longer than the request's
`turn_seconds` goes as one turn per group of whole sentences; the line takes its own length, capped at the
model's most. A line the engine cannot speak is refused in one line. A clip following a sound takes its
length and the soundtrack letters (`_sound`); voice samples go as audio references (`voiceref`), never beside
a sound. A sound from a prompt: `soundtask`."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Any

from . import lipsync, refvideo, turns, voiceref
from .soundtask import seeded, sound  # (a sound from a prompt alone)

try:
    from ..faults import Refused
except ImportError:  # run as a script by the engine's Python
    from faults import Refused

IDENTITY = "identity"          # the manifest's intent for a character's picture (the fork's `reference_manifest.py`)
WINDOW = "sliding_window_size"
# The one-line refusals of a request the model cannot take (`{}`: the model's name).
NO_ROLE = "{} takes no {}"
WORDS = {"reference": "reference picture", "identity": "identity picture", "start": "start frame", "end": "last frame"}
LAST_ALONE = "A last frame needs a start frame"
ONE_EACH = "{} takes one start frame and one last frame"
TOO_MANY = "Too many identities for {} ({} of {})"
SOURCE_ALONE = "A continued clip takes no other picture"
NO_CONTINUE = "{} cannot continue a clip"
STEP_MAX = "{} continues at most {} frames at a time"
MIXED_CUTOUT = "Cut-out is on or off for every box on {}"
NO_CUTOUT = "{} cuts out no backgrounds"
NO_NAMES = "{} takes no names with its pictures"
NO_DETAIL = "{} has no detail setting"
NO_SOUND = "{} cannot follow a sound"
SOUND_MAX = "{} follows at most {} s of sound in one clip"
SOUND_MIN = "{} follows at least {} s of sound"
SOUND_CONTINUE = "A continued clip takes no sound"
SPEAKER = "Speaker 1:"         # the engine's dialogue script: one turn, one speaker (upstream dialogue.py:27-45)
HEADER_IN_LINE = "A line is the spoken words only, no Speaker header"
NO_WORDS = "A line needs words outside [ ]"
# The engine's turn header and `[...]` direction (upstream dialogue.py:44-45); quotes round a turn are not words (:130).
_HEADER = re.compile(r"^\s*Speaker\s*(\d+)\s*(?:\{([^{}\n]*)\})?\s*:\s*", re.IGNORECASE | re.MULTILINE)
_DIRECTION = re.compile(r"\[([^\[\]\n]+)\]")
_QUOTES = "\"'\u201c\u201d\u2018\u2019 "


@dataclass(frozen=True)
class Line:
    """What a Wan2GP line does differently: `fit` is its per-task crop of a start picture (None: the line fits by
    its config instead); `keep_frames` whether a continue names the source frames it keeps."""
    fit: dict[str, Any] | None = None
    keep_frames: bool = True


FORK = Line(fit={"image_fit_mode": "crop"})


def _size(request: Any) -> str:
    return f"{request.size[0]}x{request.size[1]}"


def _loras(request: Any) -> dict[str, Any]:
    return {"activated_loras": [n for n, _ in request.loras],
            "loras_multipliers": " ".join(f"{s:g}" for _, s in request.loras)}


def ref_letters(entry: dict) -> str | None:
    """The reference letters a picture model offers: "I" when it has it, else its first choice that takes pictures
    (such as "KI": the first picture is the subject); None when it takes none."""
    choices = entry.get("ref_choices") or []
    return "I" if "I" in choices else next((c for c in choices if "I" in c), None)


def picture(request: Any, entry: dict) -> dict[str, Any]:
    paths = [r.path for r in request.references if r.role == "reference"]
    letters, name = ref_letters(entry), entry.get("name") or request.model
    if len(paths) < len(request.references) or (paths and letters is None):
        raise Refused(NO_ROLE.format(name, WORDS["reference"]))
    if any(r.cutout for r in request.references):
        raise Refused(NO_CUTOUT.format(name))
    if any(r.name is not None for r in request.references):
        raise Refused(NO_NAMES.format(name))
    task: dict[str, Any] = {
        "model_type": request.model, "prompt": request.prompt, "resolution": _size(request), "batch_size": 1,
        "image_mode": 1, "multi_prompts_gen_type": "FG", "video_prompt_type": letters if paths else "",
        "remove_background_images_ref": 0, **_loras(request)}
    if request.steps is not None:
        task["num_inference_steps"] = request.steps
    key = entry.get("guidance_key")
    if key and request.guidance is not None:
        task[key] = request.guidance
    if paths:
        task["image_refs"] = paths
    return {**task, **seeded(request)}


def _identity(ref: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"type": "image", "path": ref.path, "image_intent": IDENTITY}
    if ref.name is not None:
        item["character_name"] = ref.name
    if ref.cutout:
        item["remove_background"] = True
    return item


def _roles(request: Any, entry: dict) -> dict[str, list[Any]]:
    """A clip's pictures by role, each role one the model takes (the catalog's `video.references` and `continues`),
    else one line (`Refused`): nothing is dropped."""
    video, name = entry.get("video") or {}, entry.get("name") or request.model
    refs = video.get("references") or {}
    by = {role: [r for r in request.references if r.role == role] for role in ("start", "end", "source", "identity")}
    if by["source"]:              # beside a continued clip: identities alone, on a model that takes them
        if len(by["source"]) > 1 or by["start"] or by["end"] or (by["identity"] and refs.get("role") != "identity"):
            raise Refused(SOURCE_ALONE)
        if not video.get("continues") or not video.get("overlap"):
            raise Refused(NO_CONTINUE.format(name))
    for role, takes in (("identity", refs.get("role") == "identity"), ("start", refs.get("role") == "start"),
                        ("end", refs.get("role") == "start" and bool(refs.get("end")))):
        if by[role] and not takes:
            raise Refused(NO_ROLE.format(name, WORDS[role]))
    if by["end"] and not by["start"]:
        raise Refused(LAST_ALONE)
    if len(by["start"]) > 1 or len(by["end"]) > 1:
        raise Refused(ONE_EACH.format(name))
    cap = int(refs.get("max") or 0)
    if len(by["identity"]) > cap:
        raise Refused(TOO_MANY.format(name, len(by["identity"]), cap))
    frames = [*by["start"], *by["end"]]
    if any(r.cutout for r in frames):
        raise Refused(NO_CUTOUT.format(name))
    if any(r.name is not None for r in frames) or (not refs.get("names") and any(r.name for r in by["identity"])):
        raise Refused(NO_NAMES.format(name))
    if request.detail is not None and not (refs.get("detail") or {}).get("key"):
        raise Refused(NO_DETAIL.format(name))
    return by


def _identities(request: Any, entry: dict, by: dict[str, list[Any]]) -> dict[str, Any]:
    """The task keys for a clip's identity pictures ({} when it has none): the entry's reference list (`key`) or
    its letters with the pictures and one cut-out switch."""
    refs = (entry.get("video") or {}).get("references") or {}
    if not by["identity"]:
        return {}
    if refs.get("key"):
        return {refs["key"]: [_identity(r) for r in by["identity"]]}
    cut = {bool(r.cutout) for r in by["identity"]}
    if len(cut) > 1:                              # the line has one switch for every picture
        raise Refused(MIXED_CUTOUT.format(entry.get("name") or request.model))
    return {"video_prompt_type": refs["letters"], "image_refs": [r.path for r in by["identity"]],
            "remove_background_images_ref": int(cut == {True})}


def pictures(request: Any, entry: dict, line: Line) -> dict[str, Any]:
    """The task keys for a clip's pictures, by role (`_roles`)."""
    by = _roles(request, entry)
    if by["identity"]:
        return {"image_prompt_type": "", **_identities(request, entry, by)}
    if not by["start"]:
        return {}
    start = {"image_prompt_type": "S", **(line.fit or {})}
    if by["end"]:
        return {**start, "image_prompt_type": "SE", "image_start": by["start"][0].path,
                "image_end": by["end"][0].path}
    return {**start, "image_start": by["start"][0].path}


def _extra(request: Any, entry: dict) -> dict[str, Any]:
    """The text encoder, the identity detail and the LoRAs the request names, under the entry's keys."""
    out: dict[str, Any] = {}
    task = entry.get("video_task") or {}
    key = next(iter(task)) if len(task) == 1 else (entry.get("video") or {}).get("encoder_key")
    if request.encoder and key:
        out[key] = request.encoder
    detail = ((entry.get("video") or {}).get("references") or {}).get("detail") or {}
    if request.detail is not None and detail.get("key"):
        out[detail["key"]] = request.detail
    return {**out, **(_loras(request) if request.loras else {})}


def _sound(request: Any, entry: dict, by: dict[str, list[Any]]) -> dict[str, Any]:
    """A clip that follows a sound: the model's soundtrack letters, the sound, and the whole frames of its
    lattice the sound covers (the engine floors a length to it, frame_scheduler.py:23-30, wgp.py:7370; never more,
    so the sound covers the clip and is kept whole), in one window; the prompt asks for lip movement (`lipsync`)."""
    video, name = entry.get("video") or {}, entry.get("name") or request.model
    if by["source"]:
        raise Refused(SOUND_CONTINUE)
    if not video.get("soundtrack"):
        raise Refused(NO_SOUND.format(name))
    fps, lattice = int(video["fps"]), video.get("frames") or {}
    lo, step = int(lattice.get("min") or 1), int(lattice.get("step") or 1)
    top = int(video.get("window_max") or lattice.get("max") or 0)
    covered = math.floor(float(request.sound_seconds or 0) * fps + 1e-9)
    if covered > top:
        raise Refused(SOUND_MAX.format(name, top // fps))
    if covered < lo:                              # the shortest clip would outrun the sound
        raise Refused(SOUND_MIN.format(name, math.ceil(lo / fps * 10) / 10))
    frames = lo + (covered - lo) // step * step
    who = next((r.name for r in by["identity"] if r.name), None)
    return {"video_length": frames, WINDOW: max(frames, int(video.get("window_min") or 0)),
            "audio_prompt_type": str(video["soundtrack"]), "audio_guide": request.sound,
            "prompt": lipsync.ask(request.prompt, who)}


def clip(request: Any, entry: dict, line: Line = FORK) -> dict[str, Any]:
    video = entry.get("video") or {}
    one_pass = (video.get("one_pass") or {}) if request.one_pass else {}
    least = int(video.get("window_min") or 0)
    by = _roles(request, entry)
    if getattr(request, "voices", None):          # voice references: the clip's task, then their keys
        return voiceref.merge(clip(replace(request, voices=[]), entry, line), request, entry, by)
    if getattr(request, "video", None):           # a reference video: the clip's task, then its keys
        return refvideo.merge(clip(replace(request, video=None), entry, line), request, entry, by)
    if getattr(request, "sound", None):
        return {**clip(replace(request, sound=None), entry, line), **_sound(request, entry, by)}
    if by["source"]:
        overlap = int(video["overlap"])
        window, top = max(request.frames + overlap - 1, least), video.get("window_max")
        if top and window > top:                  # the line's largest window: one pass of a continue stays in it
            raise Refused(STEP_MAX.format(entry.get("name") or request.model, int(top) - overlap + 1))
        return {
            "model_type": request.model, "image_mode": 0, "prompt": request.prompt, "resolution": _size(request),
            "video_length": request.frames, WINDOW: window,
            "sliding_window_overlap": overlap, **one_pass, "num_inference_steps": request.steps,
            **seeded(request), "batch_size": 1, "multi_prompts_gen_type": "FG", "image_prompt_type": "V",
            "video_source": by["source"][0].path, **({"keep_frames_video_source": ""} if line.keep_frames else {}),
            "video_prompt_type": "", **(entry.get("video_task") or {}), **_extra(request, entry),
            **_identities(request, entry, by)}
    return {
        "model_type": request.model, "image_mode": 0, "prompt": request.prompt, "resolution": _size(request),
        "video_length": request.frames, WINDOW: max(request.frames, least), **one_pass,
        "num_inference_steps": request.steps, **seeded(request), "batch_size": 1, "multi_prompts_gen_type": "FG",
        "image_prompt_type": "", "video_prompt_type": "", **(entry.get("video_task") or {}),
        **pictures(request, entry, line), **_extra(request, entry)}


def window(task: dict) -> int | None:
    """The frames one pass of an engine task holds, as sent (None: no window in it)."""
    value = task.get(WINDOW)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def spoken_line(text: str) -> None:
    """Refuse a line the engine's parser would fail once `Speaker 1:` is put before it, in one line."""
    if _HEADER.search(text or ""):
        raise Refused(HEADER_IN_LINE)
    if not " ".join(_DIRECTION.sub(" ", text or "").split()).strip(_QUOTES):
        raise Refused(NO_WORDS)


def speech(request: Any, entry: dict) -> dict[str, Any]:
    """One spoken line: the script `Speaker 1:` then the line, its voice the speaker's sample (prompt
    letter "A" and the sample's path) or, without one, the words for the voice as the turn's `[…]` direction. A line
    the engine plans above `turn_seconds` goes as one turn per group of whole sentences, each turn opening with the
    voice words and the text's leading `[…]` (`turns`). The length cap is the model's most (the line
    takes its natural length). No `image_mode`: the model's factory value
    stands, and the line's sound choice is never the clip's forced one (`upstream.translate`)."""
    spoken_line(request.prompt)
    direction = (request.direction or "").strip() if not request.sample else ""
    voice = f"[{direction}] " if direction else ""
    target = request.turn_seconds
    pace = getattr(request, "pace", None)
    long = bool(target) and turns.planned(request.prompt, pace) > target
    lead, groups = turns.blocks(request.prompt, target, pace) if long else ("", [])
    if len(groups) > 1:            # one turn per group, each with the line's direction
        script = "\n".join(f"{SPEAKER}\n{voice}{lead}{group}" for group in groups)
    else:
        script = f"{SPEAKER}\n{voice}{request.prompt}"
    task: dict[str, Any] = {
        "model_type": request.model, "prompt": script, **seeded(request), "batch_size": 1,
        "multi_prompts_gen_type": "FG", "duration_seconds": request.seconds,
        "audio_prompt_type": "A" if request.sample else ""}
    if request.sample:
        task["audio_guide"] = request.sample
    return task


def task(request: Any, entry: dict, line: Line = FORK) -> dict[str, Any]:
    """The engine task of a picture, clip, line or sound request (`kind` "image", "video", "speech" or "sound")."""
    if request.kind == "image":
        return picture(request, entry)
    if request.kind == "sound":
        return sound(request, entry)
    if request.kind == "video":
        return clip(request, entry, line)
    if request.kind == "speech":
        return speech(request, entry)
    raise ValueError(f"No engine task for a {request.kind} request")
