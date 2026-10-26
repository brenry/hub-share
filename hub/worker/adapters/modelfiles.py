"""Each model's own files, chosen from the model folders: no file is renamed, copied, linked or
forced.

The engine already lets a model definition name its files, and takes a local absolute path where it is
(`shared/utils/files_locator.py`: `extract_alternate_path` returns a local path unchanged, `locate_file` an existing
absolute file): the main weights (`URLs`, `URLs2`), the text encoder (`text_encoder_URLs`), the files a family lists
as its own (`finetune_custom_urls`: a video VAE and an audio VAE, say), the extra files it loads (`preload_URLs`,
with a family's `vision_encoder_filename` naming the same file) and its own LoRAs (`loras`). A finetune
file with the model's own id is merged into its default definition at start (wgp.py `refresh_model_defs`: defaults
then finetunes, `existing_model_def.update`), so the Hub writes `finetunes/<model id>.json` holding only the parts
chosen on the Model files screen, and under `hub_files` what each part was before, to put it back. The engine reads it
at its next start.

Worker side: `parts(w, model_type)`, what each part is now and where it was found. Controller side, as a library
with no worker running: `choose(root, model_type, record, path)`. Files the family's code names itself (a VAE
upscaler, tokenizer folders) cannot be redirected by a definition; the weight check lists them. Stdlib only.
"""
from __future__ import annotations

import contextlib
import json
import os
import tempfile
from typing import Any

from .upstream_weights import runtime_def

FOLDER = "finetunes"
MARK = "hub_files"           # in the override's model part: {key: the engine's own value before the choice}
WHOLE = {"URLs": "Main weights", "URLs2": "Second main weights", "text_encoder_URLs": "Text encoder"}
ENTRIES = {"preload_URLs": "Extra file", "loras": "Model LoRA"}
CUSTOM, TWIN = "finetune_custom_urls", "vision_encoder_filename"
LABELS = {"video_vae_file": "Video VAE", "audio_vae_file": "Audio VAE"}
FILE_EXT = (".safetensors", ".sft", ".gguf", ".pt", ".pth", ".bin", ".ckpt")
YOURS = "finetunes/{}.json is your own definition: change its files there"
SAME_NAME = "The engine looks for this file by its name: choose a file named {}"
POINTER = "hub_auto"         # a pointer the Hub wrote for a weight file (`pointers.py`): its main file is that file
# What this module reads from the engine (R9 §3; the contract test), each tagged with the line that publishes it.
READS: dict[str, dict[str, str]] = {
    "wgp": dict.fromkeys(("_get_dropdown_deps", "model_dropdowns", "get_model_def"), "upstream"),
    "api": {}, "definition": dict.fromkeys(("hub_files", "finetune_custom_urls", "vision_encoder_filename",
                                            "text_encoder_URLs"), "upstream"),
    "settings": {}, "generate_video": {}, "suffixes": {},
}


def _name(value: Any) -> str:
    """A file's own name: a URL's last part, a "file|folder" entry's file."""
    return os.path.basename(str(value).split("|", 1)[0]) if value else ""


def _where(found: Any) -> str | None:
    return os.path.abspath(found) if isinstance(found, str) and found and os.path.isfile(found) else None


def parts(w: Any, model_type: str) -> list[dict[str, Any]]:
    """Each part of `model_type` that names a file: {part, label, name, path (None: not found), chosen, values}.
    `name` is the file the engine picks now (for the main weights and the text encoder: the one its quantization
    picks, upstream's own status call); `values` what the definition holds, for `choose`. A model the engine cannot
    answer for has none (never the whole list)."""
    try:
        return _parts(w, model_type)
    except Exception:
        return []


def _parts(w: Any, model_type: str) -> list[dict[str, Any]]:
    deps, menus = w._get_dropdown_deps(), w.model_dropdowns
    model_def = w.get_model_def(model_type) or {}
    resolved = runtime_def(w, model_type, model_def)                 # an "Auto" choice as the load resolves it
    chosen = model_def.get(MARK) if isinstance(model_def.get(MARK), dict) else {}
    core = list(menus.get_expected_core_file_entries_for_status(deps, model_type))
    out: list[dict[str, Any]] = []

    def add(part: str, label: str, name: Any, found: Any, key: str, values: Any, mine: bool | None = None,
            **more: Any) -> None:
        out.append({"part": part, "label": label, "name": _name(name), "path": _where(found),
                    "chosen": key in chosen if mine is None else mine, "values": values, **more})

    mains = [] if model_def.get(POINTER) else [k for k in ("URLs", "URLs2") if isinstance(model_def.get(k), list)
                                               and model_def.get(k)]
    for key, entry in zip(mains, core, strict=False):
        add(key, WHOLE[key], entry.get("filename"), deps.get_local_model_filename(entry.get("filename")), key,
            list(model_def[key]))
    encoder = model_def.get("text_encoder_URLs")
    if isinstance(encoder, list) and encoder and len(core) > len(mains):
        entry = core[-1]
        add("text_encoder_URLs", WHOLE["text_encoder_URLs"], entry.get("filename"),
            deps.get_local_model_filename(entry.get("filename"), extra_paths=entry.get("extra_paths")),
            "text_encoder_URLs", list(encoder))
    for key in model_def.get(CUSTOM) or []:                       # unnamed: the family's code picks its own
        value = resolved.get(key)
        if isinstance(key, str) and key:
            named = isinstance(value, str) and bool(value)
            found = deps.get_local_model_filename(value) if named else None
            if named and not _where(found):                       # a family's own LoRA, in its LoRA folder
                found = deps.get_lora_local_path(deps.get_lora_dir(model_type), value)
            add(key, LABELS.get(key) or key.replace("_", " ").capitalize(), value if named else "", found, key,
                value if named else None)
    twin = model_def.get(TWIN) if isinstance(model_def.get(TWIN), str) else ""
    for key, label in ENTRIES.items():
        listed = model_def.get(key)
        if not isinstance(listed, list):
            continue
        lora_dir = deps.get_lora_dir(model_type) if key == "loras" else ""
        for i, value in enumerate(listed):
            if not isinstance(value, str) or not value or "|%" in value:  # "file|%lora_dir": the family's code
                continue                                                    # finds it by that form (ltx2.py:1304)
            found = (deps.get_lora_local_path(lora_dir, value) if key == "loras"
                     else deps.get_local_model_filename(value))
            same = key == "preload_URLs" and twin and _name(twin) == _name(value)
            more = {"twin": TWIN, "twin_value": twin} if same else {}
            was = chosen.get(key) if isinstance(chosen.get(key), list) else None
            mine = was is not None and (i >= len(was) or was[i] != value)          # this entry, not its list
            add(f"{key}:{i}", f"{label}: {_name(value)}", value, found, key, list(listed), mine, **more)
    return out


def ours(definition: Any) -> bool:
    part = definition.get("model") if isinstance(definition, dict) else None
    return isinstance(part, dict) and (isinstance(part.get(MARK), dict) or bool(part.get(POINTER)))


def choose(root: str, model_type: str, record: dict[str, Any], path: str | None) -> None:
    """Point the part `record` (one of `parts`) of `model_type` at `path` (an existing absolute file), or put the
    engine's own back (`path` None). Writes or deletes `finetunes/<model_type>.json`, or changes the Hub's pointer
    of that id in place; refuses a definition the Hub did not write, and a list entry the family's code finds by name
    unless the file keeps that name."""
    if not root:
        raise ValueError("The engine's folder is not set")
    file = os.path.join(root, FOLDER, f"{model_type}.json")
    doc: Any = None
    with contextlib.suppress(OSError, ValueError):
        with open(file, encoding="utf-8") as f:
            doc = json.load(f)
    if os.path.exists(file) and not ours(doc):
        raise ValueError(YOURS.format(model_type))
    doc = doc if ours(doc) else {"model": {MARK: {}}}
    model = doc["model"]
    before = model.setdefault(MARK, {})
    key, _, at = str(record["part"]).partition(":")
    if key in ENTRIES:
        if path and not record.get("twin") and os.path.basename(path) != record["name"]:
            raise ValueError(SAME_NAME.format(record["name"]))
        base = list(before.get(key, record["values"]))
        now = list(model.get(key, record["values"]))
        now[int(at)] = path or base[int(at)]
        _keep(model, before, key, now, base, now != base)
        if record.get("twin"):
            twin_before = before.get(record["twin"], record.get("twin_value"))
            _keep(model, before, record["twin"], path or twin_before, twin_before, bool(path))
    else:
        _keep(model, before, key, [path] if key in WHOLE else path, before.get(key, record["values"]), bool(path))
    if not before:
        model.pop(MARK, None)
        if not model.get(POINTER):                        # the choices only: nothing left to hold
            with contextlib.suppress(FileNotFoundError):
                os.remove(file)
            return
    _write(file, doc)


def _write(file: str, doc: Any) -> None:
    """`doc` as `file`, whole or not at all: a partial write leaves no file behind."""
    os.makedirs(os.path.dirname(file), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(file), prefix=".hub-files-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1)
        os.replace(tmp, file)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _keep(model: dict[str, Any], before: dict[str, Any], key: str, value: Any, original: Any, changed: bool) -> None:
    """The key set to `value` with its original remembered, or dropped (the engine's own back) when unchanged. A
    pointer never holds these keys itself (`pointers.POINTER_KEYS`), so dropping one puts the engine's own back too."""
    if changed:
        before.setdefault(key, original)
        model[key] = value
    else:
        model.pop(key, None)
        before.pop(key, None)
