"""The upstream adapter: current Wan2GP, whose session lists its model definitions (the worker's "upstream" flavour).

What is upstream's own (read from WanGP 18.05, af2ed29, and held against the capture of it,
tests/fixtures/contract/upstream-18.05; no task has run on it yet):
- a task sent as the Hub builds it (the engine merges the model's factory settings itself), its factory settings
  and LoRA root from its own functions, LoRA folders searched recursively;
- no per-task crop of a start picture: upstream fits pictures by its config (`fit_canvas` 2, exact size, centre
  crop; wgp.py:7492-7496) and refuses a key it does not know (`setting_names.py`), so the fork's crop key is never
  sent and the config is forced instead (`FORCED_CONFIG`);
- every task's keys among the settings it accepts (`shared/utils/setting_names.accepted_setting_names`: an unknown key
  is refused, wgp.py:1047-1049), checked before it is sent when the engine has that call;
- every API task's size within the model's resolution budget (`budget`: the definition's, else the default its facts
  file names; wgp.py:9246-9250); a model's fork ids (`was`, the facts file's `renamed`); a step lock its definition
  does not publish (`steps_lock`); a clip's sound as its model makes it (`postprocess_audio` empty, never the fork's
  deprecated `MMAudio_setting`);
- for the clip architectures its facts file lists (`native`): frames up to the one-window default its schema offers
  (`sliding_window_defaults.window_default`; a pass never under `window_min` nor, continuing, above `window_max`),
  the text encoder as the first slot of the `config` selection (`system_configs`, `shared/config_groups.py`),
  identities as reference pictures (`image_refs` with the letter "I": the chosen size is kept, api.py:94-99), with no
  name (upstream binds a name in the prompt alone) and one cut-out for every picture (`remove_background_images_ref`),
  the tiers mirrored in its facts file, the letters that keep a supplied sound as the clip's (`soundtrack`);
  for an H3 model it cannot drive, one line (`why_not`).
First in probe order: a Wan2GP root whose session has `list_model_defs` (or, before it is opened, whose
`shared/api.py` defines it) is upstream's. Stdlib only; run by the engine's Python.
"""
from __future__ import annotations

import copy
import functools
import importlib
import os
from typing import Any

from . import anywhere, joins, modelfiles, plan, pointers, soundtail, soundtask, tasks
from . import upstream_weights as weights

try:
    from .. import keep
    from ..engineapi import KeyFamilies, read_facts
    from ..faults import Refused, Unready
except ImportError:  # run as a script by the engine's Python
    import keep
    from engineapi import KeyFamilies, read_facts
    from faults import Refused, Unready

FACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upstream.facts.json")


@functools.cache
def facts_file() -> dict[str, Any]:
    """The facts file, read once per process (every reader here takes it from this; none changes it)."""
    return read_facts(FACTS)


FAMILIES = KeyFamilies(**facts_file()["families"])
FORCED_TASK: dict[str, Any] = {"prompt_enhancer": "", "negative_prompt": "", "alt_prompt": "",
                               "output_filename": "{date}-{seed}"}
FORCED_VIDEO: dict[str, Any] = {"audio_prompt_type": "", "postprocess_audio": ""}   # the model's own sound alone
FORCED_CONFIG: dict[str, Any] = {"fit_canvas": 2}
ACCEPTED = ("shared.utils.setting_names", "accepted_setting_names")   # the settings a task may hold
UNKNOWN = "The engine does not take the setting {}"
NO_SETTINGS = "This engine does not say which settings it accepts"
UNHELD = "This engine's start may remove weight files past the Hub's hold ({} in wgp.py)"
_accepted: list[frozenset[str]] = []          # the engine's list once read; a miss is never kept
LINE = tasks.Line(fit=None)
ENCODER_GROUP, ENCODER_KEY, IDENTITY_LETTERS = "Text Encoder", "config", "I"
LISTING = "list_model_defs"                  # the session call only upstream has (R9 §1.1)
READS: dict[str, dict[str, str]] = {
    "wgp": {"get_factory_settings": "upstream", "get_lora_root": "upstream", "get_base_model_type": "both",
            "server_config": "both"},
    "api": {LISTING: "upstream"},
    "definition": {**dict.fromkeys(FAMILIES.fields(), "upstream"), "sliding_window_defaults": "both",
                   "system_configs": "upstream", "text_encoder_variant": "upstream", "image_ref_choices": "both",
                   "resolution_budget": "upstream", "hub_files": "upstream", "audio_overlap_repair_ms": "upstream"},
    "settings": {},
    "generate_video": {},
    "suffixes": dict.fromkeys(FAMILIES.suffixes().values(), "upstream"),
}


def lists_models(root: str, session: Any = None) -> bool:
    """The opened session has the listing call; before opening, the root's `shared/api.py` defines it."""
    if session is not None:
        return hasattr(session, LISTING)
    try:
        with open(os.path.join(root, "shared", "api.py"), encoding="utf-8", errors="replace") as f:
            return f"def {LISTING}(" in f.read()
    except OSError:
        return False


def declares_settings(root: str) -> bool:
    """The root's `shared/utils/setting_names.py` defines the call that lists the settings a task may hold."""
    try:
        with open(os.path.join(root, *ACCEPTED[0].split(".")) + ".py", encoding="utf-8", errors="replace") as f:
            return f"def {ACCEPTED[1]}(" in f.read()
    except OSError:
        return False


def accepted_names() -> frozenset[str]:
    """The settings the engine accepts in a task (its `accepted_setting_names`), kept once read. An engine without
    the call is refused in one line each time it is asked, never remembered as "nothing to check" (`prepare` refuses
    such a root before it opens)."""
    if not _accepted:
        try:
            names = getattr(importlib.import_module(ACCEPTED[0]), ACCEPTED[1])()
        except (ImportError, AttributeError):
            raise Refused(NO_SETTINGS) from None
        _accepted.append(frozenset(str(n) for n in names))
    return _accepted[0]


def translate(task: dict, factory: dict) -> dict:
    """The Hub's task as upstream takes it: unchanged, forced values on top (`factory` is not used); a key upstream
    does not accept is refused here in one line, before the engine refuses the whole task. A clip that follows a
    sound (`audio_guide`) keeps its own sound letters."""
    extra = FORCED_VIDEO if task.get("image_mode") == 0 else {}
    if extra and task.get("audio_guide"):
        extra = {k: v for k, v in extra.items() if k != "audio_prompt_type"}
    out = {**copy.deepcopy(task), **FORCED_TASK, **extra}
    unknown = sorted(set(out) - accepted_names())
    if unknown:
        raise Refused(UNKNOWN.format(unknown[0]))
    return out


def factory_settings(w: Any, model_type: str) -> dict:
    return copy.deepcopy(w.get_factory_settings(model_type))


def lora_root(w: Any) -> str:
    return w.get_lora_root()


def lora_search(w: Any, model_type: str) -> list[str]:
    return []


def _whole(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def pixels(value: Any) -> int | None:
    """A resolution budget's pixels: "WxH" (its area) or a whole number of pixels; None when neither."""
    if _whole(value):
        return int(value)
    try:
        w, h = (int(v) for v in str(value).lower().split("x"))
    except ValueError:
        return None
    return w * h if w > 0 and h > 0 else None


def budget(w: Any, model_def: dict) -> int | None:
    """The pixels an API task's size may hold: the definition's `resolution_budget`, else upstream's default."""
    return pixels(model_def.get("resolution_budget")) or pixels(facts_file()["budget"]["default"])


def was(model_type: str) -> list[str]:
    """The fork's ids of this model (the facts file's `renamed`), in the file's order."""
    return [old for old, new in facts_file()["renamed"]["ids"].items() if new == model_type]


def steps_lock(model_type: str) -> int | None:
    """The step count the model must run at though its definition publishes no lock (the facts file's `steps`)."""
    return _whole(facts_file()["steps"]["locked"].get(model_type))


def script(model_type: str) -> str | None:
    """The dialogue script a speech model's prompt is (the facts file's `speech`), else None."""
    return str(value) if (value := facts_file().get("speech", {}).get("script", {}).get(model_type)) else None


def line_facts(w: Any, model_type: str, model_def: dict) -> dict[str, Any]:
    """What the definition does not say (`catalog.line_facts`): the budget, the fork's ids, a step lock, a speech
    model's script and whether it makes a sound from a prompt alone (`sounds`), a cue model's ranks."""
    out: dict[str, Any] = {"budget": budget(w, model_def)}
    if speaks := script(model_type):
        out["script"] = speaks
        out |= {"sounds": True} if facts_file()["speech"].get("sounds", {}).get(model_type) else {}
    out |= soundtask.cue_facts(facts_file(), model_type)            # `cues`, and `blocked` for Medium
    if old := was(model_type):
        out["was"] = old
    out |= {"lock_steps": True, "steps": steps} if (steps := steps_lock(model_type)) else {}
    return out


def encoders(w: Any, model_def: dict) -> tuple[str, str | None, dict[str, Any]] | None:
    """The text encoder a task picks: (`config`, the default, {id: {name, URLs}}) from the definition's
    "Text Encoder" config group; the default is the definition's `text_encoder_variant`, else the config's text
    encoder quantization (the files an empty selection loads, wgp.py:3084-3114)."""
    group = model_def.get("system_configs")
    if not isinstance(group, dict) or group.get("_name") != ENCODER_GROUP:
        return None
    if "text_encoder_URLs" in (model_def.get(modelfiles.MARK) or {}):   # a chosen file: no choice
        return None                                                     # would override it (wgp.py config groups)
    variants = {str(k): {"name": str(v.get("name") or k), "URLs": list(v.get("text_encoder_URLs") or [])}
                for k, v in group.items() if not str(k).startswith("_") and isinstance(v, dict)}
    own = model_def.get("text_encoder_variant") or (getattr(w, "server_config", None) or {}).get(
        "text_encoder_quantization")
    return ENCODER_KEY, own if own in variants else None, variants


def identities(model_def: dict, cap: int) -> dict[str, Any] | None:
    """Identity pictures, when the definition offers reference pictures ("I" in a reference choice): none needed
    when it also runs without ("" is a choice)."""
    spec = model_def.get("image_ref_choices")
    choices = [str((c[1] if isinstance(c, (list, tuple)) and len(c) > 1 else c) or "")
               for c in ((spec or {}).get("choices") or [])] if isinstance(spec, dict) else []
    if not any(IDENTITY_LETTERS in c for c in choices):
        return None
    return {"role": "identity", "min": 0 if "" in choices else 1, "max": cap, "letters": IDENTITY_LETTERS,
            "names": False, "cutout": "all"}


def native(w: Any, model_type: str, model_def: dict) -> dict[str, Any] | None:
    """What this adapter reads for a clip architecture its facts file lists (`catalogvideo.video_facts` takes it):
    None for any other model, {"why_not": line} for one it cannot drive."""
    facts = facts_file()
    spec = facts["models"].get(str(w.get_base_model_type(model_type)))
    if spec is None:
        return None
    if spec.get("why_not"):
        return {"why_not": str(spec["why_not"])}
    window = model_def.get("sliding_window_defaults")
    window = window if isinstance(window, dict) else {}
    out: dict[str, Any] = {"clip": True, "frames_max": _whole(window.get("window_default")),
                           "window_min": _whole(window.get("window_min")),
                           "window_max": _whole(window.get("window_max")),
                           "tiers": copy.deepcopy(facts["tiers"][spec["tiers"]]["tiers"]),
                           "encoders": encoders(w, model_def)}
    if spec.get("sound_join"):                          # the sound a continue's join makes again (`soundtail`)
        out["sound_join"] = {"frames": int(spec["sound_join"]),
                             "repair_ms": float(model_def.get("audio_overlap_repair_ms") or 0)}
    for key in ("soundtrack", "reference_video", "voice_reference"):   # the letters of each choice
        if spec.get(key):
            out[key] = str(spec[key])
    refs = identities(model_def, int(spec["identities"])) if spec.get("identities") else None
    return {**out, "references": refs} if refs else out


class Upstream:
    name = "upstream"
    flavour = "upstream"
    families = FAMILIES
    factory_underneath = False
    lora_recursive = True
    forced_config = FORCED_CONFIG
    READS = READS
    pointers = pointers                       # a Hub pointer as this line keeps it (a Wan2GP finetune file)
    modelfiles = modelfiles                   # each model's own files, as chosen

    def probe(self, root: str, session: Any = None) -> bool:
        """An opened session with the listing call, or (before opening) a Wan2GP root whose api defines it."""
        if session is not None:
            return lists_models(root, session)
        return (os.path.isfile(os.path.join(root, "wgp.py")) and os.path.isfile(os.path.join(root, "shared", "api.py"))
                and lists_models(root))

    def facts(self) -> dict[str, Any]:
        return copy.deepcopy(facts_file())

    def task(self, request: Any, entry: dict) -> dict:
        """The task; a continue keeps only the source frames its sound covers (`soundtail`)."""
        return soundtail.cover(tasks.task(request, entry, LINE), entry.get("video") or {})

    def prepare(self, root: str) -> None:
        """Before the engine opens, each refused in one line: a root that does not say which settings a task may hold
        (every task is checked against that list, `translate`), or whose `wgp.py` could remove a file at import past
        the hold the worker puts on the weights (`keep.removals`)."""
        if not declares_settings(root):
            raise Unready(NO_SETTINGS)
        try:
            with open(os.path.join(root, "wgp.py"), encoding="utf-8", errors="replace") as f:
                found = keep.removals(f.read())
        except (OSError, SyntaxError, ValueError):
            found = []
        if found:
            raise Unready(UNHELD.format(found[0]))

    def lacking(self, w: Any, model_type: str | None) -> list[str]:
        """What upstream would fetch before the model loads, by its own presence calls (`upstream_weights`)."""
        return weights.lacking(w, model_type, facts_file()["companions"]["models"])

    def opened(self, w: Any) -> None:
        """Every fetch the open engine could make refuses in one line naming the file (`upstream_weights.guard`)."""
        weights.guard()
        anywhere.install(w)                    # a file found by its name in any of the model folders

    translate = staticmethod(translate)
    factory_settings = staticmethod(factory_settings)
    lora_root = staticmethod(lora_root)
    lora_search = staticmethod(lora_search)
    native = staticmethod(native)
    line_facts = staticmethod(line_facts)
    window = staticmethod(tasks.window)
    dropped = staticmethod(soundtail.dropped)
    finish = staticmethod(joins.finish)
    plan = staticmethod(plan.plan)                # the engine's own preflight
