"""A native clip model's catalog facts, read from its definition, its factory settings and the engine's own
`generate_video` signature alone: no model is named here (the catalog, `catalog.py`, calls in). How the engine names
a key per model family (the reference list, the one-pass switch, the text encoder...) is the adapter's (`keys`, from
its facts file): no key family is named here either."""
from __future__ import annotations

import inspect
import math
import os
from collections.abc import Callable
from typing import Any

try:
    from .engineapi import KeyFamilies
except ImportError:  # run as a script by the engine's Python
    from engineapi import KeyFamilies

RATIOS = {"1:1": 1.0, "4:3": 4 / 3, "3:4": 3 / 4, "3:2": 3 / 2, "2:3": 2 / 3, "16:9": 16 / 9, "9:16": 9 / 16}
# What this module reads from the engine (R9 §3; the contract test), each tagged with the line that publishes it.
READS: dict[str, dict[str, str]] = {
    "wgp": {"generate_video": "both"},
    "api": {},
    "definition": {"image_outputs": "both", "audio_only": "both", "t2v_class": "both", "settings": "both",
                   "image_prompt_types_allowed": "both", "fps": "both", "frames_minimum": "both",
                   "frames_steps": "both", "frames_maximum": "both", "vae_block_size": "both", "block_size": "both",
                   "resolution_presets": "legacy", "resolution_preset_order": "legacy",
                   "auto_resolution_budgets": "legacy", "text_encoder_folder": "both",
                   "sliding_window_defaults": "both", "inference_steps_min": "legacy",
                   "inference_steps_max": "legacy", "reference_video_max_frames": "upstream"},
    "settings": {"video_length": "both", "num_inference_steps": "both", "sliding_window_overlap": "both"},
    "generate_video": {},
    "suffixes": {},
}


def _ends(name: str, suffix: str | None) -> bool:
    """`name` ends with the family suffix (never, when the engine has no such family)."""
    return bool(suffix) and name.endswith(str(suffix))


def _whole(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _size(text: Any, block: int) -> list[int] | None:
    try:
        w, h = (int(v) // block * block for v in str(text).lower().split("x"))
    except ValueError:
        return None
    return [w, h] if w > 0 and h > 0 else None


def tiers(model_def: dict, block: int) -> list[dict[str, Any]]:
    """The model's resolution tiers in its own order: each named aspect as the definition gives it, and every shape
    of RATIOS it does not name sized the way the engine sizes an "auto" canvas: the tier's pixel budget
    (`auto_resolution_budgets[values["auto"]]`) at that ratio, rounded to the block (wgp.py's auto resolution)."""
    presets = model_def.get("resolution_presets")
    if not isinstance(presets, dict):
        return []
    budgets = model_def.get("auto_resolution_budgets") or {}
    out = []
    for name in [*(model_def.get("resolution_preset_order") or []), *presets]:
        values = (presets.get(name) or {}).get("values") if isinstance(presets.get(name), dict) else None
        if not isinstance(values, dict) or any(t["name"] == name for t in out):
            continue
        sizes = {a: s for a, v in values.items() if a != "auto" and (s := _size(v, block))}
        budget = _whole(budgets.get(values.get("auto")))
        for aspect, r in RATIOS.items():
            if aspect not in sizes and budget:
                sizes[aspect] = [max(block, round(math.sqrt(budget * r) / block) * block),
                                 max(block, round(math.sqrt(budget / r) / block) * block)]
        if sizes:
            out.append({"name": str(name), "sizes": sizes})
    return out


def encoder_choice(model_def: dict, *, keys: KeyFamilies) -> tuple[str, str, dict[str, Any]] | None:
    """The text encoder a definition lets a task pick: (task key, default, {variant id: spec}) from the field it
    publishes as the task key (ending `keys.encoder`) plus `keys.encoder_default`, and the one plus
    `keys.encoder_variants`; None when it names none or a default outside them."""
    if not (keys.encoder and keys.encoder_default):
        return None
    for name, value in model_def.items():
        if _ends(name, keys.encoder + keys.encoder_default) and isinstance(value, str) and value:
            key = name[:-len(keys.encoder_default)]
            variants = model_def.get(key + keys.encoder_variants) if keys.encoder_variants else None
            variants = variants if isinstance(variants, dict) else {}
            if not variants or value in variants:
                return key, value, variants
    return None


def encoder_facts(model_def: dict, found: Callable[[str], bool] | None = None, *,
                  keys: KeyFamilies, own: tuple[str, str | None, dict[str, Any]] | None = None) -> dict[str, Any]:
    """The text encoder variants in the definition's order, each with its `name` (else its id), the default, and the
    variants whose every file (`URLs`, by base name, also inside `text_encoder_folder`) `found` finds; None when
    `found` cannot tell. `own`: the (key, default, variants) the adapter read where the definition names none."""
    choice = encoder_choice(model_def, keys=keys) or own
    variants = choice[2] if choice else {}
    specs = {str(k): v if isinstance(v, dict) else {} for k, v in variants.items()}
    default = choice[1] if specs and choice else None
    out: dict[str, Any] = {"text_encoders": list(specs), "text_encoder_default": default,
                           "text_encoder_names": {k: str(v.get("name") or k) for k, v in specs.items()},
                           "text_encoders_found": None}
    if found is not None:
        folder = model_def.get("text_encoder_folder")
        def present(url: Any) -> bool:
            name = os.path.basename(url) if url.startswith("http") else url
            return found(name) or (isinstance(folder, str) and bool(folder) and found(os.path.join(folder, name)))
        try:
            out["text_encoders_found"] = [k for k, v in specs.items() if isinstance(v.get("URLs"), list) and v["URLs"]
                                          and all(isinstance(u, str) and present(u) for u in v["URLs"])]
        except Exception:
            pass
    return out


def picture_refs(model_def: dict, settings: dict, *, keys: KeyFamilies) -> dict[str, Any] | None:
    """The pictures a clip model takes, from its definition, or None. A reference-manifest model (the field
    `keys.manifest`) takes identity pictures: at least one, at most `[keys.manifest_limits]["image"]`, as the list its
    defaults file names (the one setting ending `keys.references` that is a list: `key`, the task key), each with its
    character's name (`names`); without both it is not usable (None); with `detail` when it announces one
    (`reference_detail`). Else "S" in
    `image_prompt_types_allowed` is a start picture (`image_start`); with "E" (`end`) a second picture is the last
    frame (`image_end`), so it takes up to two."""
    allowed = str(model_def.get("image_prompt_types_allowed") or "")
    if model_def.get(keys.manifest):
        limits = model_def.get(keys.manifest_limits)
        cap = _whole(limits.get("image")) if isinstance(limits, dict) else None
        key = next((k for k, v in settings.items() if _ends(k, keys.references) and isinstance(v, list)), None)
        if not (cap and key):
            return None
        detail = reference_detail(model_def, settings, keys=keys)
        return {"role": "identity", "min": 1, "max": cap, "key": key, "names": True,
                **({"detail": detail} if detail else {})}
    end = "E" in allowed
    return {"role": "start", "min": 0, "max": 2 if end else 1, "end": end} if "S" in allowed else None


def reference_detail(model_def: dict, settings: dict, *, keys: KeyFamilies) -> dict[str, Any] | None:
    """The reference detail a manifest model announces: {key, choices: [{value, label}], default}, from its
    `keys.detail_choices` field ((label, value) pairs, as tuples or lists, in the engine's order), its
    `keys.detail_default` (one of the values) and the task key, the one setting ending `keys.detail`; None when any
    part is missing."""
    pairs, default = model_def.get(keys.detail_choices), model_def.get(keys.detail_default)
    key = next((k for k in settings if _ends(k, keys.detail)), None)
    choices = [{"value": p[1], "label": p[0] or p[1]} for p in pairs if isinstance(p, (list, tuple)) and len(p) == 2
               and all(isinstance(v, str) for v in p) and p[1]] if isinstance(pairs, (list, tuple)) else []
    if not (key and choices) or default not in [c["value"] for c in choices]:
        return None
    return {"key": key, "choices": choices, "default": default}


def continuation(model_def: dict, settings: dict, step: int, lo: int, hi: int, *, keys: KeyFamilies) -> int | None:
    """The overlap a model continues a clip with (the engine's "V": `video_source` is the clip), or None. Read:
    "V" in `image_prompt_types_allowed`, no `keys.manifest` (an identity model never continues), and the overlap
    (`sliding_window_defaults["overlap_default"]`, else the settings' `sliding_window_overlap`) usable: a whole number
    above 1 whose `overlap - 1` lies on the frame lattice, with room for the shortest clip (`lo + overlap - 1 <= hi`).
    One pass of a continue is `frames + overlap - 1` frames; the clip grows by `frames - 1`."""
    if "V" not in str(model_def.get("image_prompt_types_allowed") or "") or model_def.get(keys.manifest):
        return None
    window = model_def.get("sliding_window_defaults")
    own = window.get("overlap_default") if isinstance(window, dict) else None
    overlap = _whole(own if own is not None else settings.get("sliding_window_overlap"))
    if overlap is None or overlap <= 1 or (overlap - 1) % step or lo + overlap - 1 > hi:
        return None
    return overlap


def engine_switches(w: Any, *, keys: KeyFamilies) -> dict[str, bool]:
    """The engine's switches that chain passes, as its `generate_video` declares them: each keyword parameter whose
    name ends `keys.one_pass` with a yes/no default ({name: default}); {} when the engine has no such function."""
    try:
        params = inspect.signature(w.generate_video).parameters.values()
    except (AttributeError, TypeError, ValueError):
        return {}
    return {p.name: p.default for p in params if _ends(p.name, keys.one_pass) and isinstance(p.default, bool)}


def one_pass(model_def: dict, settings: dict, switches: dict[str, bool], *,
             keys: KeyFamilies) -> dict[str, bool] | None:
    """The task values that keep a clip in one pass: the model's switch (a name ending `keys.one_pass`), sent False.
    The switch is the one its settings name, else an engine switch (`engine_switches`) whose prefix starts another key
    of the model's definition or settings (the family's own keys); None when there is none."""
    window = keys.one_pass
    if not window:
        return None
    key = next((k for k in settings if k.endswith(window)), None)
    names = [str(n) for n in (*model_def, *settings)]
    for switch in switches if key is None else ():
        prefix = switch[:-len(window)] + "_"
        if len(prefix) > 1 and any(n.startswith(prefix) and n != switch for n in names):
            key = switch
            break
    return {key: False} if key else None


def video_facts(model_def: dict, factory: dict, found: Callable[[str], bool] | None = None,
                switches: dict[str, bool] | None = None, *, keys: KeyFamilies,
                native: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """A native clip model's facts, or None. Definition fields read: `image_outputs`/`audio_only` (not a video
    model), `t2v_class`, "T" in `image_prompt_types_allowed` (text alone is a valid input) unless the model takes a
    reference manifest (`picture_refs`: it needs references), any flag ending `keys.sidecar` (runs in another
    runtime: the engine's in-process load refuses it), `fps`, `frames_minimum`/`frames_steps`/`frames_maximum` (the
    frame lattice), `resolution_presets` (the tiers), the text encoder variants (`encoder_facts`); defaults from the
    factory settings (`video_length`, steps); `one_pass` from the settings or the engine's switches (`one_pass`);
    whether it `continues` a clip and with what `overlap` (`continuation`). `native`: what the adapter reads where the
    definition publishes none of that (`Adapter.native`: a clip model without `t2v_class`, its frame maximum, tiers,
    text encoders, identity pictures, its smallest and largest window, the sound a continue's join makes again and
    the letters that keep a supplied sound, `soundtrack`). An identity model continues when its definition takes "V"
    and no manifest (`continuation`; upstream's Ref2VA)."""
    native = native or {}
    if model_def.get("image_outputs") or model_def.get("audio_only") or not (model_def.get("t2v_class")
                                                                               or native.get("clip")):
        return None
    settings = {**(model_def.get("settings") or {}), **factory}
    refs = native.get("references") or picture_refs(model_def, settings, keys=keys)
    text = "T" in str(model_def.get("image_prompt_types_allowed") or "")
    if (refs is None) if model_def.get(keys.manifest) else not text:
        return None
    if any(_ends(k, keys.sidecar) and v for k, v in model_def.items()):
        return None
    fps, lo, step, hi = (_whole(model_def.get(k)) for k in ("fps", "frames_minimum", "frames_steps", "frames_maximum"))
    hi = hi or _whole(native.get("frames_max"))
    block = int(model_def.get("vae_block_size") or model_def.get("block_size") or 16)
    table = tiers(model_def, block) or native.get("tiers") or []
    if not (fps and lo and step and hi and hi >= lo and table):
        return None
    want = _whole(factory.get("video_length")) or lo
    default = min(hi, lo + max(0, math.ceil((want - lo) / step)) * step)
    overlap = continuation(model_def, settings, step, lo, hi, keys=keys)
    own = native.get("encoders")
    out = {"fps": fps, "frames": {"min": lo, "step": step, "max": hi, "default": default},
           "steps": _whole(factory.get("num_inference_steps")), "tiers": table, "references": refs,
           "one_pass": one_pass(model_def, settings, switches or {}, keys=keys), "continues": overlap is not None,
           "overlap": overlap, **encoder_facts(model_def, found, keys=keys, own=own)}
    kept = ("window_min", "window_max", "sound_join", "soundtrack", "reference_video", "voice_reference")
    held = _whole(model_def.get("reference_video_max_frames")) if native.get("reference_video") else None
    return {**out, **{k: native[k] for k in kept if native.get(k)},
            **({"reference_video_seconds": held / fps} if held else {}),          # the engine keeps that much
            **({"encoder_key": own[0]} if own and not encoder_choice(model_def, keys=keys) else {})}


def video_task(model_def: dict, *, keys: KeyFamilies) -> dict[str, Any]:
    """Task values the definition names for every clip: the text encoder it defaults to, under the task key it
    publishes with its default and variants (`encoder_choice`)."""
    choice = encoder_choice(model_def, keys=keys)
    return {choice[0]: choice[1]} if choice else {}


def steps_range(model_def: dict) -> list[int] | None:
    lo, hi = _whole(model_def.get("inference_steps_min")), _whole(model_def.get("inference_steps_max"))
    return [lo, hi] if lo and hi and lo <= hi else None
