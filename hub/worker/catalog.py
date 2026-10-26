"""The engine catalog: image, native video and speech models, their defaults and LoRA folders, read without side
effects. A model whose output is a 3D asset (`mesh_outputs`; upstream's media type "3d", wgp.py:8841), though the
engine also marks it as making images (its preview), is not a picture model: the catalog leaves it out.

Shared by the Wan2GP adapters (`adapters/`): what differs between the engine lines (factory settings, the LoRA root
and linked folders, how keys are named per model family) is asked of the adapter, never named here. Everything here
only reads `wgp` globals. The engine's own `get_lora_dir` creates missing folders; the worker replaces it with
`lora_dir` below, which only computes the path.
"""
from __future__ import annotations

import inspect
import os
from typing import Any

try:
    from .catalogspeech import speech_facts
    from .catalogvideo import engine_switches, steps_range, video_facts, video_task
except ImportError:  # run as a script by the engine's Python
    from catalogspeech import speech_facts
    from catalogvideo import engine_switches, steps_range, video_facts, video_task

DEFAULT_KEYS = ("num_inference_steps", "guidance_scale", "embedded_guidance_scale", "resolution")
STATUS = {0: "missing", 1: "partial", 2: "available"}
SHAPE = 13                    # the entry shape (`kind`, `video`, `speech`, `budget`, `sounds`, `cues`): cache key
# What this module reads from the engine (R9 §3; the contract test), each tagged with the line that publishes it.
READS: dict[str, dict[str, str]] = {
    "wgp": {"models_def": "both", "get_model_def": "both", "get_model_family": "both", "families_infos": "both",
            "model_dropdowns": "both", "get_model_download_status": "both", "get_model_recursive_prop": "both",
            "get_local_model_filename": "both", "_get_dropdown_deps": "both", "get_base_model_type": "both",
            "get_model_handler": "both", "args": "both", "server_config": "both", "WanGP_version": "both",
            "settings_version": "both"},
    "api": {},
    "definition": {"visible": "both", "image_outputs": "both", "mesh_outputs": "both", "name": "both",
                   "embedded_guidance": "both", "guidance_max_phases": "both", "image_ref_choices": "both",
                   "vae_block_size": "both", "lock_inference_steps": "both", "no_lora": "upstream", "hub_auto": "both",
                   "hub_base": "both", "loras_disabled": "legacy", "URLs": "both"},
    "settings": dict.fromkeys(DEFAULT_KEYS, "both"),
    "generate_video": {},
    "suffixes": {},
}


def guidance_key(model_def: dict) -> str | None:
    """The guidance control the engine's own UI shows for a model (or None)."""
    if model_def.get("embedded_guidance"):
        return "embedded_guidance_scale"
    if (model_def.get("guidance_max_phases") or 0) >= 1:
        return "guidance_scale"
    return None


def ref_choices(model_def: dict) -> list[str]:
    """The `video_prompt_type` values the model accepts for reference images ("" = none)."""
    spec = model_def.get("image_ref_choices")
    if not isinstance(spec, dict):
        return []
    values = []
    for choice in spec.get("choices") or ():
        value = choice[1] if isinstance(choice, (list, tuple)) and len(choice) > 1 else choice
        values.append(str(value or ""))
    return values


def modes(choices: list[str]) -> list[str]:
    """The Hub's words for a model's reference choices: "new" when it runs with no picture, "refs" when a choice
    takes pictures (its letters hold "I")."""
    return [m for m, ok in (("new", not choices or "" in choices), ("refs", any("I" in c for c in choices))) if ok]


def size(text: Any) -> list[int] | None:
    try:
        w, h = (int(v) for v in str(text).lower().split("x"))
    except ValueError:
        return None
    return [w, h] if w > 0 and h > 0 else None


def describe(model_type: str, model_def: dict, factory: dict, *, family: str, status: int,
             lora_dirs: list[str], recursive: bool) -> dict[str, Any]:
    """One catalog entry. This is the shape the controller and the fixtures use. `base`: for a pointer the hub wrote
    (marked hub_auto), the model it is set up like; else None. `steps`, `size`, `guidance` and `modes` are the
    factory defaults and the reference choices in the Hub's words, which modules read; `defaults`, `guidance_key`
    and `ref_choices` are the engine's, which its adapter reads to build a task."""
    key = guidance_key(model_def)
    choices = ref_choices(model_def)
    steps = factory.get("num_inference_steps")
    return {
        "id": model_type,
        "name": str(model_def.get("name") or model_type),
        "family": family,
        "status": STATUS.get(status, "missing"),
        "defaults": {key: factory[key] for key in DEFAULT_KEYS if factory.get(key) is not None},
        "steps": steps if isinstance(steps, int) and not isinstance(steps, bool) else None,
        "size": size(factory.get("resolution")),
        "guidance": factory.get(key) if key and isinstance(factory.get(key), (int, float)) else None,
        "modes": modes(choices),
        "guidance_key": key,
        "ref_choices": choices,
        "block": int(model_def.get("vae_block_size") or 16),
        "lock_steps": bool(model_def.get("lock_inference_steps")),
        "loras": bool(lora_dirs) and not model_def.get("no_lora", False),
        "lora_dirs": lora_dirs,
        "lora_recursive": recursive,
        "base": (str(model_def.get("hub_base") or "") or None) if model_def.get("hub_auto") else None,
    }


def lora_dir(w: Any, root: str, model_type: str, adapter: Any) -> str:
    """Where the engine looks for this model's LoRAs (absolute). Creates nothing. A handler's `get_lora_dir` takes
    the base type alone (a folder key under the root, or the `lora_config` entry for it) or, in older handlers, the
    base type, the engine's arguments and the root (a path)."""
    base = w.get_base_model_type(model_type)
    get_dir = getattr(w.get_model_handler(model_type), "get_lora_dir", None)
    if base is None or get_dir is None:
        raise LookupError(f"no LoRA folder for {model_type}")
    try:
        inspect.signature(get_dir).bind(base)
    except TypeError:
        path = get_dir(base, w.args, adapter.lora_root(w))
    else:
        key = get_dir(base)
        path = (getattr(w.args, "lora_config", None) or {}).get(key) or os.path.join(adapter.lora_root(w), key)
    if path is None:
        raise LookupError(f"no LoRA folder for {model_type}")
    return os.path.normpath(os.path.join(root, path))


def lora_dirs(w: Any, root: str, model_type: str, adapter: Any) -> list[str]:
    """Primary folder first, then the read-only linked folders the adapter knows of.
    The worker's cwd is the engine root, as the engine expects."""
    primary = lora_dir(w, root, model_type, adapter)
    found = [os.path.normpath(os.path.join(root, d)) for d in adapter.lora_search(w, model_type)]
    return [primary] + [d for d in found if d != primary]


def presence(w: Any, deps: Any, model_type: str) -> int:
    """0 missing, 1 partial, 2 available. The engine's own status demands every companion file under
    the configured quantization; here a model counts as present as soon as any variant of its main
    weight file is in a model folder (the way LoRAs are detected), and runs with the engine's fallbacks."""
    status = int(w.model_dropdowns.get_model_download_status(deps, model_type))
    if status != 0:
        return status
    urls = w.get_model_recursive_prop(model_type, "URLs", return_list=True) or []
    names = [os.path.basename(u) if u.startswith("http") else u   # a path (a hub_auto pointer) is used as it is
             for u in (urls if isinstance(urls, list) else [urls]) if isinstance(u, str) and u]
    return 1 if any(deps.get_local_model_filename(n) is not None for n in names) else 0


def line_facts(w: Any, adapter: Any, model_type: str, model_def: dict) -> dict[str, Any]:
    """What the adapter knows of the model that its definition does not say (`Adapter.line_facts`), each only when
    there is one, so a line with none leaves the entry as it was: `budget`, the pixels a task's size may hold; `was`,
    the ids the model had on the engine line the Hub ran before; `lock_steps` and `steps`, a step count it must run
    at."""
    facts = adapter.line_facts(w, model_type, model_def)
    out: dict[str, Any] = {}
    if isinstance(facts.get("budget"), int) and facts["budget"] > 0:
        out["budget"] = facts["budget"]
    if facts.get("was"):
        out["was"] = [str(v) for v in facts["was"]]
    if isinstance(facts.get("steps"), int) and facts.get("lock_steps"):
        out |= {"lock_steps": True, "steps": facts["steps"]}
    return out


def entry(w: Any, root: str, adapter: Any, model_type: str, deps: Any = None,
          switches: dict[str, bool] | None = None) -> dict[str, Any] | None:
    """One model's catalog entry, or None when the catalog leaves it out (hidden, a 3D model, neither a picture, a
    clip nor a speech model the shared rules read, or its facts unreadable). A speech model (`catalogspeech`, and a
    script its adapter's line facts name): kind "speech", its `speech` facts, no LoRAs; one with no script but cue
    ranks: kind "sound", its `cues`, `why_not` when the adapter says it is `blocked`. `deps` and
    `switches`: the engine's, read once per catalog."""
    keys = adapter.families
    deps = w._get_dropdown_deps() if deps is None else deps
    switches = engine_switches(w, keys=keys) if switches is None else switches
    model_def = w.get_model_def(model_type)
    if not isinstance(model_def, dict) or not model_def.get("visible", True) or model_def.get("mesh_outputs"):
        return None
    image = bool(model_def.get("image_outputs"))
    speech = None if image else speech_facts(model_def)
    said = adapter.line_facts(w, model_type, model_def) if speech else {}
    script = said.get("script")
    cues = said.get("cues") if speech and not script else None   # a cue's sound model
    if speech and not script and not cues:
        return None                               # a speech model whose script the adapter does not know
    native = None if image or speech else adapter.native(w, model_type, model_def)
    why_not = (native or {}).get("why_not")
    clip = not image and not speech and not why_not
    if clip and video_facts(model_def, {"video_length": 0}, keys=keys, native=native) is None:
        return None
    try:
        dirs = lora_dirs(w, root, model_type, adapter)
    except Exception:
        dirs = []
    try:
        family = w.get_model_family(model_type, for_ui=True)
        factory = adapter.factory_settings(w, model_type)
        out = describe(
            model_type, model_def, factory,
            family=str(w.families_infos.get(family, (0, family))[1]),
            status=presence(w, deps, model_type),
            lora_dirs=dirs, recursive=adapter.lora_recursive)
    except Exception:
        return None
    out |= {"kind": "image", "video": None}
    if out["status"] == "partial":                # some file not where the engine looks: is any still missing?
        try:
            out["lacks"] = list(adapter.lacking(w, model_type))[:1]
        except Exception:
            out["lacks"] = []
    if cues:                                      # never in the pulldown (`models.present`); picked by kind
        return out | {"kind": "sound", "speech": speech, "loras": False, "cues": dict(cues),
                      **({"why_not": str(said["blocked"])} if said.get("blocked") else {})}
    if speech:
        return out | {"kind": "speech", "speech": speech, "loras": False, "script": script,
                      **({"sounds": True} if said.get("sounds") else {})}         # a sound from a prompt
    if why_not:                                   # the engine has it; the adapter cannot drive it: one line
        return out | {"kind": "video", "why_not": str(why_not)}
    extra = line_facts(w, adapter, model_type, model_def)
    if not image:
        found = lambda name: deps.get_local_model_filename(name) is not None  # noqa: E731
        out |= {"kind": "video", "video": video_facts(model_def, factory, found, switches, keys=keys, native=native),
                "video_task": video_task(model_def, keys=keys), "steps_range": steps_range(model_def)}
        out["loras"] = out["loras"] and not model_def.get("loras_disabled", False)
        if out["video"] and "steps" in extra:
            out["video"]["steps"] = extra["steps"]
    return out | extra


def build(w: Any, root: str, adapter: Any) -> dict[str, Any]:
    """The full catalog of image, native video and speech models, available or not (`kind` says which). `adapter`: the
    engine line's (`adapters/`), for its factory settings, LoRA folders and key families."""
    deps = w._get_dropdown_deps()
    switches = engine_switches(w, keys=adapter.families)
    models = [e for t in sorted(w.models_def) if (e := entry(w, root, adapter, t, deps, switches)) is not None]
    paths = w.server_config.get("checkpoints_paths") or []
    return {
        "engine": {"api": adapter.flavour, "version": str(w.WanGP_version), "settings_version": w.settings_version,
                   "root": root, "loras_root": os.path.normpath(os.path.join(root, adapter.lora_root(w))),
                   "checkpoints": [os.path.normpath(os.path.join(root, p)) for p in paths]},
        "models": models,
    }
