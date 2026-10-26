"""Image models as the UI and MCP see them, derived from the engine catalog.

Model ids, defaults, guidance key and LoRA folders all come from the engine. The only fact the engine does not
publish is how many reference images a model takes: the table in settings.json
(`modules.generate-image.ref_caps`, model id prefix -> 1..6; the engine's validation stays the final word).
A video model (`kind` "video") makes one clip, with no guidance; its frame lattice, steps, tiers, text encoder
variants and the pictures it takes (`references`: a start frame, or identities) come from the catalog (`video`), of
which the size menu offers those set in `modules.generate-image.video_tiers` (tier names, or how many of the catalog's
first ones; names the catalog does not report are ignored). Its reference cap is the engine's, not `ref_caps`, and
no more than the bar's boxes (`cast.BOXES`). A speech model (`kind` "speech") speaks one typed line in
one character's voice: one box, nothing else (`speech_model`).
What the engine line's adapter adds to an entry is read here too: `budget` (the most pixels a task's size may hold),
`lock_steps` (the steps are the model's, not a setting), `was` (the ids it had on the line the Hub ran before, so a
saved id still finds it: `find`) and `why_not` (the engine has it, the Hub cannot drive it: never `present`).
"""
from __future__ import annotations

import math
import os
from collections.abc import Mapping
from typing import Any

from hub.core.api import Ctx, Invalid, clip_facts, snap_frames
from hub.core.api import tier_size as tier_canvas

from . import cast

DEFAULT_REF_CAP = 3                       # a model the table does not name
# What the engine does not publish about an identity picture (R6 §4.3): it cuts a name at NAME_MAX characters and
# refuses a picture whose long side is more than SHAPE_MAX times its short side. Every box of an identity model is
# sent as an identity; scene, style and composition wait for a control of their own (R6 row 4).
NAME_MAX = 120
SHAPE_MAX = 4
MAX_TIERS = 3                            # the size menu's places (1 MP, 1.5/2 MP, 4 MP)
NO_LIST = "The engine did not list its models"
READY = "sketch.ready"                    # the core event: a sketch may be drawn now (the Director listens)

_last: dict[str, Any] | None = None
_ctx: Ctx | None = None                   # the module's, for its settings where a model's facts are read (`video`)


async def catalog(ctx: Ctx, rescan: bool = False) -> dict[str, Any]:
    """The engine catalog ({engine, models, resident}); remembered for the job builder.
    `rescan` makes the engine look at the model folders again instead of using what it remembered."""
    global _last, _ctx
    _ctx = ctx
    _last = await ctx.engine.query("models", rescan=rescan)
    from . import rename  # late: it reads this module

    rename.adopt(ctx, _last)                  # saved ids follow an engine line that renames models
    ctx.emit(READY, {})                       # the engine answered: the Director's sketches may go on
    return _last


def cached() -> dict[str, Any] | None:
    return _last


def reason(exc: BaseException) -> str:
    """Why the engine could not answer: its own one plain line."""
    return (str(exc).strip().splitlines() or [NO_LIST])[0]


def ref_caps(ctx: Ctx) -> Mapping[str, Any]:
    return ctx.settings.get("ref_caps") or {}


def offered_tiers(cat: dict[str, Any] | None, setting: Any) -> list[str] | None:
    """The tier names the size menu offers: the first `setting` (a count) the catalog reports, or the names in
    `setting` it reports; None when the setting is neither (every tier the model has)."""
    names = list(dict.fromkeys(t["name"] for m in (cat or {}).get("models", []) if m.get("kind") == "video"
                               for t in (m.get("video") or {}).get("tiers") or []))
    if isinstance(setting, int) and not isinstance(setting, bool):
        return names[:setting]
    return [n for n in names if n in setting] if isinstance(setting, list) else None


def renamed(cat: dict[str, Any] | None) -> dict[str, str]:
    """{old id: id} for the catalog's models that had another id on the engine line the Hub ran before (`was`)."""
    return {str(old): m["id"] for m in (cat or {}).get("models", []) for old in m.get("was") or ()}


def find(cat: dict[str, Any] | None, model_id: Any) -> dict[str, Any] | None:
    """The catalog's model with this id, else the one that had it before (`was`: a saved id from the line before)."""
    models = (cat or {}).get("models", [])
    found = next((m for m in models if m["id"] == model_id), None)
    if found is None and isinstance(model_id, str) and (new := renamed(cat).get(model_id)) is not None:
        found = next((m for m in models if m["id"] == new), None)
    return found


def budget(model: dict[str, Any]) -> int | None:
    """The most pixels a task's size may hold on this model (the catalog's `budget`; None: no limit)."""
    value = model.get("budget")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def within(model: dict[str, Any] | None, width: int, height: int, ratio: float) -> tuple[int, int]:
    """A picture's canvas, or (when it holds more pixels than the model's `budget`) the largest canvas of that shape
    within it, each side a multiple of 16."""
    top = budget(model) if model else None
    if top is None or width * height <= top:
        return width, height
    return max(16, int(math.sqrt(top * ratio) // 16) * 16), max(16, int(math.sqrt(top / ratio) // 16) * 16)


def check_steps(model: dict[str, Any], label: str, value: Any) -> None:
    """A step count other than the one a locked model runs (`locked_steps`) is refused in one line."""
    locked = locked_steps(model)
    if locked is not None and value is not None and value != locked:
        raise Invalid("steps", f"{label} runs {locked} steps")


def locked_steps(model: dict[str, Any]) -> int | None:
    """The steps a model always runs (the catalog's `lock_steps`), None when `steps` is a setting."""
    clip = model.get("video") if model.get("kind") == "video" else None
    steps = clip.get("steps") if isinstance(clip, dict) else model.get("steps")
    return steps if model.get("lock_steps") and isinstance(steps, int) and not isinstance(steps, bool) else None


def ref_cap(model: dict[str, Any], caps: Mapping[str, Any]) -> int:
    """The cap of the longest prefix in `caps` that the model's id starts with. A model the hub set up from a weight
    file (`base` in its catalog entry) takes the cap of the model it is set up like."""
    model_id = str(model.get("base") or model["id"])
    prefix = max((p for p in caps if model_id.startswith(p)), key=len, default=None)
    return int(caps[prefix]) if prefix is not None else DEFAULT_REF_CAP


def modes(model: dict[str, Any]) -> list[str]:
    """A picture model's modes, from the catalog: "new" when it runs with no picture, "refs" when it takes some."""
    return [m for m in model.get("modes") or [] if m in ("new", "refs")]


def takes_refs(model: dict[str, Any]) -> bool:
    return "refs" in modes(model)


def picture_refs(model: dict[str, Any]) -> dict[str, Any] | None:
    """The pictures a video model takes ({role, min, max, ...} from the catalog), None when it takes none."""
    clip = video(model)
    return clip["references"] if clip and clip_facts(model)["refs"]["max"] else None


def identities(model: dict[str, Any]) -> bool:
    """Whether a model's boxes are identities (the catalog's role for its pictures)."""
    refs = picture_refs(model)
    return bool(refs and refs.get("role") == "identity")


def takes_names(model: dict[str, Any]) -> bool:
    """Whether an identity model takes each picture's character name (the catalog says `names`)."""
    refs = picture_refs(model)
    return bool(refs and refs.get("names"))


def in_shape(w: Any, h: Any) -> bool:
    """A picture the manifest takes: its long side no more than SHAPE_MAX times its short side (4:1 itself passes)."""
    ok = all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in (w, h))
    return ok and max(w, h) <= SHAPE_MAX * min(w, h)


def detail_facts(model: dict[str, Any]) -> dict[str, Any] | None:
    """The detail an identity model announces ({choices: [{value, label}], default}), else None."""
    refs = picture_refs(model)
    facts = refs.get("detail") if refs else None
    return facts if isinstance(facts, dict) and facts.get("choices") else None


def detail(model: dict[str, Any], value: Any) -> str | None:
    """A manifest model's reference detail: `value` when the model announces it, else None (its default)."""
    facts = detail_facts(model)
    return value if facts and isinstance(value, str) and value in [c["value"] for c in facts["choices"]] else None


def drop_stale(model: dict[str, Any], adv: dict[str, Any]) -> None:
    """A card's text encoder or detail the model no longer lists goes: its default applies."""
    if encoder(model, adv.get("text_encoder")) is None:
        adv.pop("text_encoder", None)
    if detail(model, adv.get("detail")) is None:
        adv.pop("detail", None)


def clip_modes(model: dict[str, Any]) -> list[str]:
    """A video model's modes, as an image model's: "new" when it runs with no picture, "refs" when it takes some."""
    refs = picture_refs(model)
    return [mode for mode, ok in (("new", not refs or not refs.get("min")), ("refs", refs is not None)) if ok]


def video(model: dict[str, Any]) -> dict[str, Any] | None:
    """A video model's facts with the tiers the size menu offers (the `video_tiers` the model has, else its
    first MAX_TIERS); None for an image model."""
    facts = model["video"] if clip_facts(model) else None
    if facts is None:
        return None
    names = offered_tiers(_last or {"models": [model]}, _ctx.settings.get("video_tiers") if _ctx else None)
    offered = [t for t in facts["tiers"] if t["name"] in (names or ())] or facts["tiers"]
    return {**facts, "tiers": offered[:MAX_TIERS]}


def frames(facts: dict[str, Any], value: Any) -> int:
    """A clip length on the model's lattice: snapped up to the next allowed count, kept within min..max; the
    model's default when not a whole number."""
    return snap_frames(facts, value)


def encoder(model: dict[str, Any], value: Any) -> str | None:
    """A video model's text encoder variant: `value` when the model lists it (`text_encoders`), else None (the
    definition's default)."""
    clip = model.get("video") if model.get("kind") == "video" else None
    return value if isinstance(clip, dict) and value in (clip.get("text_encoders") or []) else None


def tier_size(facts: dict[str, Any], aspect: str, ratio: float, mp: float) -> tuple[int, int]:
    """The canvas of a clip: the tier the megapixels pick (<=1 first, 1.5/2 second, 4 third, else the last
    offered), at the aspect when the tier has it, else at its size nearest the ratio."""
    tiers = facts["tiers"]
    return tier_canvas(facts, tiers[min(len(tiers) - 1, 0 if mp <= 1 else 1 if mp <= 2 else 2)]["name"], aspect, ratio)


def speech_model(model: dict[str, Any]) -> dict[str, Any]:
    """A speech model as the UI sees it: one character's picture in one box, a typed line; no size,
    steps, guidance or LoRAs; `speech` its catalog facts (the line's length cap)."""
    return {"id": model["id"], "label": model["name"], "family": model["family"], "kind": "speech", "video": None,
            "speech": model.get("speech"), "modes": ["refs"], "refCap": 1,
            "defaults": {"steps": None, "guidance": None}, "guidanceKey": None, "budget": None, "lockSteps": False}


def ui_model(model: dict[str, Any], caps: Mapping[str, Any]) -> dict[str, Any]:
    if model.get("kind") == "speech":
        return speech_model(model)
    clip = video(model)
    key = None if clip else model["guidance_key"]
    refs = picture_refs(model) if clip else None
    if refs:                                 # the engine's cap, no more than the bar draws boxes
        clip = {**clip, "references": {**refs, "max": min(refs["max"], cast.BOXES)}}
    cap = (clip["references"]["max"] if refs else 0) if clip else ref_cap(model, caps) if takes_refs(model) else 0
    return {
        "id": model["id"],
        "label": model["name"],
        "family": model["family"],
        "kind": "video" if clip else "image",
        "video": clip,
        "modes": clip_modes(model) if clip else modes(model),
        "refCap": cap,
        "defaults": {"steps": clip["steps"] if clip else model.get("steps"),
                     "guidance": model.get("guidance") if key else None},
        "guidanceKey": key,
        "budget": budget(model),
        "lockSteps": locked_steps(model) is not None,
    }


def there(model: dict[str, Any]) -> bool:
    """Its weight files are all in the model folders (the engine's check; one that would be refused is not)."""
    return model.get("status") == "available" or (model.get("status") == "partial" and not model.get("lacks"))


def present(cat: dict[str, Any]) -> list[dict[str, Any]]:
    """Models whose weight files are all in the model folders (the engine's own check), by family. A model the
    engine has but its adapter cannot drive (`why_not`) is never one, nor a cue's sound model (kind `sound`:
    picked by `cue_maker`, never in the pulldown)."""
    found = [m for m in cat.get("models", []) if not m.get("why_not") and m.get("kind") != "sound" and there(m)]
    return sorted(found, key=lambda m: (str(m["family"]).lower(), str(m["name"]).lower(), m["id"]))


def cue_models(cat: dict[str, Any] | None, kind: str) -> list[dict[str, Any]]:
    """The catalog's sound models for a cue kind (or "room"), best first (the facts file's order)."""
    found = [m for m in (cat or {}).get("models", []) if m.get("kind") == "sound" and kind in (m.get("cues") or {})]
    return sorted(found, key=lambda m: (int(m["cues"][kind]), m["id"]))


def cue_maker(cat: dict[str, Any] | None, kind: str) -> dict[str, Any] | None:
    """The best sound model for `kind` whose files are all there and that the engine can run (no `why_not`)."""
    return next((m for m in cue_models(cat, kind) if there(m) and not m.get("why_not")), None)


def lora_name(model: dict[str, Any], lora_id: str) -> str | None:
    """The engine's name for a LoRA (its path inside the family folder) if the file is there.

    Ids are `<family folder>/<path>`; nothing may climb out of the folder."""
    key, _, rel = str(lora_id).partition("/")
    dirs = model.get("lora_dirs") or []
    parts = rel.split("/")
    if not dirs or not model.get("loras") or key != os.path.basename(dirs[0]) or "\\" in rel or "\0" in rel:
        return None
    if any(p in ("", ".", "..") for p in parts) or not rel.lower().endswith((".safetensors", ".sft")):
        return None
    if len(parts) > 1 and not model.get("lora_recursive"):
        return None
    for folder in dirs:
        top = os.path.realpath(folder)
        real = os.path.realpath(os.path.join(top, *parts))
        if os.path.commonpath([top, real]) == top and os.path.isfile(real):
            return rel
    for folder in model.get("lora_extra") or []:   # the LoRA folders in Settings: the engine takes a full path
        top = os.path.realpath(folder)
        real = os.path.realpath(os.path.join(top, *parts))
        if os.path.commonpath([top, real]) == top and os.path.isfile(real):
            return real
    return None
