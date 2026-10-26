"""The Generate screen's settings, as the tool server reads and sets them, and their one declaration.

The assistant's draft prompt is the session's: held in memory (`routes.session_part`), shown beside the chat of
every window, never on disk; setting it here redraws that panel at once. The rest is the draft on disk
(`routes.DRAFT`): model, aspect, megapixels, count, the LoRA stack per model, and per model its steps, guidance and
seed. A change made here is saved and told to every open Generate window, which redraws its bar from it. The
prompt box is no setting: nothing here or in any tool reads or writes it. The model is the pulldown's
alone; a shot's named characters go into empty boxes (`voiced`), never into or over the filled ones, so a
job runs on the pulldown and boxes as set or is refused in one line. The selection is never touched from here. The
bounds below are the only place each one is written: `SETTINGS` (what the tool server publishes), `apply` and the job
builder (`build.py`) all read them.
"""
from __future__ import annotations

import math
from typing import Any

from hub.core.api import Ctx, Invalid, Setting, seed_value, whole

from . import cast, chain, models, pace, routes, shotcheck, voiced

ASPECTS = {"1:1": 1.0, "4:3": 4 / 3, "3:4": 3 / 4, "3:2": 3 / 2, "2:3": 2 / 3, "16:9": 16 / 9, "9:16": 9 / 16}
AUTO_RATIO = (0.4, 2.5)
MEGAPIXELS = (1, 1.5, 2, 4)
STEPS, GUIDANCE, COUNT, STRENGTH = (1, 100), (0, 50), (1, 6), (0, 2)
SEED_MAX = 999_999_999
SETTINGS = (
    Setting("draft", "text", text="The assistant's draft prompt, shown beside the chat"),
    Setting("shot", "object", schema=shotcheck.SCHEMA,
            text="A clip as who, where, camera, action and lines; the hub writes its prompt into the draft"),
    Setting("steps", "integer", lo=STEPS[0], hi=STEPS[1], text="Steps the model runs"),
    Setting("guidance", "number", lo=GUIDANCE[0], hi=GUIDANCE[1], text="Guidance scale, for a model that has one"),
    Setting("megapixels", "number", choices=MEGAPIXELS, text="Megapixels of the picture"),
    Setting("aspect", "choice", choices=("auto", *ASPECTS),
            text="Shape of the picture; auto is reference 1's shape, else 1:1"),
    Setting("count", "integer", lo=COUNT[0], hi=COUNT[1], text="Number of pictures made"),
    Setting("seed", "seed", lo=0, hi=SEED_MAX, text="Seed of the first picture"),
    Setting("loras", "loras", lo=STRENGTH[0], hi=STRENGTH[1],
            text="Active LoRAs of the model: id (as list_loras lists it) and strength"),
)
ADVANCED = ("steps", "guidance", "seed")                      # kept per model, as the web screen's Advanced
# The card alone keeps a clip's length, text encoder and detail per model (`frames`, `text_encoder`, `detail`):
# the tools neither read nor set them, so the six tools and their schema stay as they were.
SESSION = {"draft", "shot"}                                   # the session's, never on disk
SAVED = {s.name for s in SETTINGS if s.name not in SESSION}   # the settings in the draft on disk


def _round16(x: float) -> int:
    return int(math.floor(x / 16 + 0.5)) * 16                # the screen's Math.round(x / 16) * 16


def auto_ratio(references: list) -> float:
    """Auto: reference 1's shape, kept within AUTO_RATIO; 1:1 with no reference (the web screen's autoRatio)."""
    first = references[0] if references else None
    w = first.get("w") if isinstance(first, dict) else None
    h = first.get("h") if isinstance(first, dict) else None
    if isinstance(w, (int, float)) and isinstance(h, (int, float)) and w > 0 and h > 0:
        return min(AUTO_RATIO[1], max(AUTO_RATIO[0], w / h))
    return 1.0


def canvas(aspect: str, mp: float, references: list, model: dict | None = None) -> tuple[int, int]:
    """Width and height from the aspect and megapixels, in multiples of 16 (the web screen's canvasOf), shrunk to the
    largest canvas of that shape within the model's budget when it is above it (`models.budget`); for a video
    model, the size of the tier the megapixels pick (models.tier_size), auto at the tier's shape nearest the start
    frame's (square when box 1 is no start frame)."""
    p = mp * 1048576
    clip = models.video(model) if model else None
    if clip:
        start = (models.picture_refs(model) or {}).get("role") == "start"
        return models.tier_size(clip, aspect, ASPECTS.get(aspect) or auto_ratio(references if start else []), mp)
    ratio = ASPECTS.get(aspect) or auto_ratio(references)
    return models.within(model, _round16(math.sqrt(p * ratio)), _round16(math.sqrt(p / ratio)), ratio)


def clip_frames(screen: dict, model: dict) -> int | None:
    """A video model's clip length: its Advanced `frames` on the lattice, else its default; None for an image model."""
    clip = models.video(model)
    return models.frames(clip, (screen["advanced"].get(model["id"]) or {}).get("frames")) if clip else None


def clip_encoder(screen: dict, model: dict) -> str | None:
    """A video model's text encoder: its Advanced `text_encoder` when the model lists it, else None (its default)."""
    return models.encoder(model, (screen["advanced"].get(model["id"]) or {}).get("text_encoder"))


def clip_detail(screen: dict, model: dict) -> str | None:
    """A manifest model's reference detail: its Advanced `detail` when announced, else None (the factory default)."""
    return models.detail(model, (screen["advanced"].get(model["id"]) or {}).get("detail"))


def draft(ctx: Ctx) -> str:
    """The assistant's draft prompt: the session's, "" when nothing is there."""
    text = routes.session_part(ctx).get("draft")
    return text if isinstance(text, str) else ""


def references(ctx: Ctx) -> list[dict]:
    """The reference boxes of the session: [{id, w, h}] as the Generate window filled them."""
    refs = routes.session_part(ctx).get("references")
    return [r for r in refs if isinstance(r, dict) and isinstance(r.get("id"), str)] if isinstance(refs, list) else []


def read(ctx: Ctx) -> dict[str, Any]:
    """The saved settings as plain values."""
    d = ctx.doc(routes.DRAFT, {}).get()
    aspect = d.get("aspect") if d.get("aspect") == "auto" or d.get("aspect") in ASPECTS else "auto"
    size = d.get("size") if d.get("size") in MEGAPIXELS else 1
    images = d.get("images") if isinstance(d.get("images"), int) and COUNT[0] <= d["images"] <= COUNT[1] else 1
    return {"model": d.get("model"), "loras": d.get("lorasByModel") or {}, "advanced": d.get("advancedByModel") or {},
            "aspect": aspect, "size": size, "images": images}


def stack(screen: dict, model_id: str) -> list[dict]:
    """The active LoRAs for this model, above 0, in order."""
    out = []
    for e in screen["loras"].get(model_id) or []:
        if isinstance(e, dict) and isinstance(e.get("id"), str) and isinstance(e.get("strength"), (int, float)):
            if round(float(e["strength"]), 2) > 0:
                out.append({"id": e["id"], "strength": round(float(e["strength"]), 2)})
    return out


NOT_PICKED = "The model picked on the Generate screen cannot run; pick one there"


def pick_model(cat: dict, screen: dict) -> dict:
    """The model picked on the screen, as it is; refused in one line when it is not listed or its files are gone:
    no other model is ever chosen."""
    model = models.find(cat, screen["model"])                 # a saved id the engine renamed: its new id
    if model is None or model not in models.present(cat):
        raise Invalid("model", NOT_PICKED)
    return model


_whole = whole                                             # the core's plain-value check (`api.whole`)


def _seed(value: Any) -> dict:
    """"random", or a whole number 0-SEED_MAX given as a number or as text (`api.seed_value`)."""
    first = seed_value(value, SEED_MAX)
    return {"mode": "random"} if first is None else {"mode": "fixed", "value": first}


def _loras(model: dict, value: Any) -> list[dict]:
    if not isinstance(value, list):
        raise Invalid("loras", "loras must be a list of {id, strength}")
    out: list[dict] = []
    for e in value:
        if not isinstance(e, dict) or not isinstance(e.get("id"), str) or isinstance(e.get("strength"), bool) \
                or not isinstance(e.get("strength"), (int, float)) or not STRENGTH[0] <= e["strength"] <= STRENGTH[1]:
            raise Invalid("loras", f"each LoRA needs an id from list_loras and a strength from {STRENGTH[0]} to "
                                   f"{STRENGTH[1]}")
        if models.lora_name(model, e["id"]) is None:
            raise Invalid("loras", f'No LoRA "{e["id"]}" in this model\'s folder')
        if any(x["id"] == e["id"] for x in out):
            raise Invalid("loras", f'A LoRA is listed twice: "{e["id"]}"')
        out.append({"id": e["id"], "strength": round(float(e["strength"]), 2)})
    return out


def view(ctx: Ctx, cat: dict, model: dict) -> dict[str, Any]:
    """The settings as the tool server reports them: the assistant's draft, then plain values, the seed as text
    ("random" or the number) and the seeds the last render used (`last_seeds`; setting `seed` to one of them keeps
    that picture's start); width and height as a press of Generate would render them (a clip in box 1: its size,
    and `seconds` the step it adds); `last_clip`, the newest clip this screen made ("" when none). `model` and
    `references` are the screen's pick and boxes: reported, never set here."""
    screen = read(ctx)
    ui = models.ui_model(model, models.ref_caps(ctx))
    adv = screen["advanced"].get(model["id"]) or {}
    width, height = canvas(screen["aspect"], screen["size"], references(ctx), model)
    seed = adv.get("seed") if isinstance(adv.get("seed"), dict) and adv["seed"].get("mode") == "fixed" else None
    guidance = adv.get("guidance") if isinstance(adv.get("guidance"), (int, float)) else ui["defaults"]["guidance"]
    out = {"draft": draft(ctx), "shot": routes.session_part(ctx).get("shot"), "model": model["id"],
           "model_name": ui["label"],
           "loras": [{"id": e["id"], "file": e["id"].split("/", 1)[1], "strength": e["strength"]}
                     for e in stack(screen, model["id"])],
           "steps": (None if ui["lockSteps"] else adv.get("steps")) or ui["defaults"]["steps"],
           "guidance": guidance if ui["guidanceKey"] else None,
           "aspect": screen["aspect"], "megapixels": screen["size"], "width": width, "height": height,
           "count": 1 if ui["video"] else screen["images"],
           "seed": str(seed["value"]) if seed and "value" in seed else "random", "last_seeds": last_seeds(ctx, model),
           "references": cast.labels(ctx), "last_clip": chain.last_clip(ctx)}
    if ui["kind"] == "speech":                                # the voice's measured pace, the last take
        measured = pace.read(ctx)
        out["speech_pace"], out["speech_pace_runs"] = measured["pace"], measured["runs"]
        out["last_take"] = routes.session_part(ctx).get("last_take") or None     # its words verdict
    if ui["video"]:                                           # a clip: its length too; a continue: the step, its size
        held = chain.held(ctx)
        out["frames"] = clip_frames(screen, model)
        shown = routes.session_part(ctx).get("video") if ui["video"].get("reference_video") else None
        out["video"] = shown["id"].rsplit("/", 1)[-1].rsplit(".", 1)[0] if isinstance(shown, dict) else ""
        out["seconds"] = round((out["frames"] - (1 if held else 0)) / ui["video"]["fps"], 2)
        if held:
            out["width"], out["height"] = held.get("w"), held.get("h")
    return out


def last_seeds(ctx: Ctx, model: dict) -> list[int]:
    """The seeds the last render of this model used, picture by picture (memory only; [] when none this session)."""
    last = routes.session_part(ctx).get("last_seeds")
    return list(last["seeds"]) if isinstance(last, dict) and last.get("model") == model["id"] else []


def _advanced(draft: dict, model: dict, ui: dict, changes: dict) -> dict:
    """The model's Advanced entry with the change applied: steps, guidance, seed, a video model's text encoder; the
    model's defaults where nothing was set before, as the web screen writes it."""
    adv = dict((draft.get("advancedByModel") or {}).get(model["id"]) or {})
    adv.setdefault("steps", ui["defaults"]["steps"])
    adv.setdefault("guidance", ui["defaults"]["guidance"])
    adv.setdefault("seed", {"mode": "random"})
    if ui["video"]:                                           # the card's clip length, kept on the lattice
        adv["frames"] = models.frames(ui["video"], adv.get("frames"))
    models.drop_stale(model, adv)                             # a text encoder or detail no longer listed: its default
    if "steps" in changes:
        models.check_steps(model, ui["label"], changes["steps"])
        adv["steps"] = _whole(changes["steps"], "steps", *(model.get("steps_range") or STEPS))
    if "guidance" in changes:
        if not ui["guidanceKey"]:
            raise Invalid("guidance", f"{ui['label']} has no guidance setting")
        g = changes["guidance"]
        if isinstance(g, bool) or not isinstance(g, (int, float)) or not GUIDANCE[0] <= g <= GUIDANCE[1]:
            raise Invalid("guidance", f"guidance must be a number from {GUIDANCE[0]} to {GUIDANCE[1]}")
        adv["guidance"] = round(float(g), 1)
    if "seed" in changes:
        adv["seed"] = _seed(changes["seed"])
    if "frames" in changes and ui["video"]:                   # a shot's length from its lines
        adv["frames"] = models.frames(ui["video"], changes["frames"])
    return adv


def _draft(ctx: Ctx, value: Any) -> str:
    """The draft text, checked; refused with no Generate window connected: the panel shows it, and
    nothing written now may turn up in a later session."""
    if not isinstance(value, str):
        raise Invalid("draft", "draft must be text")
    if not (ctx.bus.presence().get("screens") or {}).get("workspace"):
        raise Invalid("draft", "No Generate window is open")
    return value


def apply(ctx: Ctx, cat: dict, changes: dict) -> dict:
    """Set the given settings on the screen and return the settings after: the draft into the session's panel, the
    rest saved (the draft on disk is rebuilt only when a saved setting is in `changes`); open windows redraw both.
    The tool server has already refused a setting that is not in SETTINGS: the model and the boxes are not."""
    shot = changes.get("shot")
    changes = {k: v for k, v in changes.items() if k != "draft"} if shot is not None else changes   # shot wins
    text = _draft(ctx, changes["draft"]) if "draft" in changes else None
    model = pick_model(cat, read(ctx))
    if models.video(model):
        _clip_refusals(model, changes)
    if shot is not None:                                      # the hub writes the prompt, the length too
        _draft(ctx, "")
        now = (clip_frames(read(ctx), model) or 0) / ((models.video(model) or {}).get("fps") or 1)
        voiced.cast_named(ctx, shot, model)                  # the shot's named characters into empty boxes
        text, frames = shotcheck.prepare(ctx, model, shot, now)
        changes = {**changes, **({"frames": frames} if frames else {})}
    if set(changes) & (SAVED | {"frames"}):
        _save(ctx, model, changes)
    if text is not None:
        routes.session_part(ctx).update(draft=text, shot=shot)
    ctx.bus.publish("changed", "draft", {})
    return view(ctx, cat, model)


def _clip_refusals(model: dict, changes: dict) -> None:   # what a video model cannot take (its pictures: `cast`)
    if "count" in changes and changes["count"] != 1:
        raise Invalid("count", f"{model['name']} makes one clip at a time")


def _save(ctx: Ctx, model: dict, changes: dict) -> None:
    """The saved part of the draft with the changes applied, as the web screen writes it: the model is never
    touched, the rest kept; nothing is written until every value has passed."""
    ui = models.ui_model(model, models.ref_caps(ctx))
    doc = ctx.doc(routes.DRAFT, {})
    draft = {k: v for k, v in doc.get().items() if k in routes.SAVED_FIELDS}
    if "aspect" in changes:
        if changes["aspect"] != "auto" and changes["aspect"] not in ASPECTS:
            raise Invalid("aspect", f"aspect must be auto or one of {', '.join(ASPECTS)}")
        draft["aspect"] = changes["aspect"]
    if "megapixels" in changes:
        if changes["megapixels"] not in MEGAPIXELS:
            raise Invalid("megapixels", f"megapixels must be one of {', '.join(map(str, MEGAPIXELS))}")
        draft["size"] = changes["megapixels"]
    if "count" in changes and not ui["video"]:              # a clip is always one: the pictures' count stays
        draft["images"] = _whole(changes["count"], "count", *COUNT)
    if set(changes) & {*ADVANCED, "frames"}:
        draft["advancedByModel"] = {**(draft.get("advancedByModel") or {}),
                                    model["id"]: _advanced(draft, model, ui, changes)}
    if "loras" in changes:
        loras = dict(draft.get("lorasByModel") or {})
        loras[model["id"]] = _loras(model, changes["loras"])
        draft["lorasByModel"] = loras
    doc.replace(draft)
