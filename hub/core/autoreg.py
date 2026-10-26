"""The model folder is the truth: weight files no engine definition names become usable models.

Each weight file (EXT) under the model folders (any depth) that no definition names is compared with the image
models whose main weight file is present, by the tensor names in its header (8-byte little-endian length + JSON;
nothing past the header is read). A Jaccard overlap of at least MATCH, and a size between LOW and HIGH times that
model's file (fp8 is about half of bf16, int4 about a quarter), means the same architecture in another finetune or
precision. The hub then writes a pointer definition in the folder the engine reads finetune definitions from, in
their form: the file's full path and the matched model's architecture, plus the few defaults its file sets. The
engine reads it when it starts, like any finetune there; a full path is found where it is. The pointer's form, its
folder and the reading of a definition file are the engine line's: the root's adapter answers them
(`Adapter.pointers`, `hub/worker/adapters/pointers.py`), called here as a library: no worker runs for it, since the
form is read from no engine. Only the Hub's own pointers are
ever written or removed: one whose file left the folders, or that a definition not the Hub's now names, is deleted,
and one written in another form (an older hub's) is written again in this one, set up like the same model. Weight
files are never copied, moved, linked or deleted.
"""
from __future__ import annotations

import contextlib
import os
import re
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

from hub.core import inherit
from hub.core.fingerprints import Fingerprints, read_json, write_json
from hub.worker import adapters
from hub.worker.adapters import pointers as wan2gp_form

MATCH, LOW, HIGH = 0.9, 0.25, 1.3
EXT = (".safetensors", ".sft", ".gguf")   # the weight file names the engine takes (definitions.WEIGHT_EXT)
ONE_AT_A_TIME = threading.Lock()      # two registry passes, or a pass and a choice, never write at once


@dataclass
class Found:
    changed: bool = False                                    # a pointer was written or removed
    files: list[dict[str, Any]] = field(default_factory=list)   # one record per weight file, for the panel
    bases: list[str] = field(default_factory=list)          # the models a file can be set up like (no pointers)


class Known(NamedTuple):
    """A model to match against: one present main file and the definition file that names it."""
    names: frozenset[str]
    size: int
    file: str
    model_type: str
    architecture: str
    definition: dict[str, Any]                               # the definition file, in the engine line's form
    owners: bool                                             # a finetune definition not written by the Hub


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a or b else 0.0


def _inside(path: str, roots: Iterable[str]) -> str | None:
    real = os.path.realpath(path)
    for root in roots:
        top = os.path.realpath(root)
        if real == top or real.startswith(top.rstrip(os.sep) + os.sep):
            return root
    return None


def weight_files(folders: list[str], skip: list[str]) -> list[str]:
    """The absolute path of every weight file (EXT), any depth, each once; LoRA folders skipped."""
    out: dict[str, str] = {}
    for folder in folders:
        for top, dirs, files in os.walk(folder):
            dirs[:] = sorted(d for d in dirs if not _inside(os.path.join(top, d), skip))
            for name in sorted(files):
                path = os.path.join(top, name)
                if name.lower().endswith(EXT) and os.path.isfile(path):
                    out.setdefault(os.path.realpath(path), os.path.abspath(path))
    return list(out.values())


def form_of(root: str) -> Any:
    """The pointer form of the engine line that drives `root` (`Adapter.pointers`); Wan2GP's when none does yet."""
    try:
        return adapters.select(root).pointers
    except adapters.NoAdapter:
        return wan2gp_form


def pointers(folder: Path, form: Any = wan2gp_form) -> dict[Path, dict[str, Any]]:
    """The hub's pointer files in `folder`, each with its whole definition."""
    out = {}
    for file in sorted(folder.glob("*.json")):
        definition = read_json(file) if file.is_file() else None
        if form.ours(definition):
            out[file] = definition
    return out


def remove(file: Path) -> bool:
    try:
        file.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def words(text: str) -> set[str]:
    """The words and numbers in a name, camelCase split: 'BigModel2Base_bf16' -> {big, model, 2, base, bf, 16}."""
    return {w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", text)}


def rank(path: str, names: frozenset[str], size: int, k: Known, form: Any = wan2gp_form) -> tuple:
    """Best match first: tensor-name overlap; then a definition naming the file itself (not one borrowing another
    model's file to add a LoRA or a module); then the most words shared by the file's name and the model's (its id
    and its file: a base and a distilled model share their tensors); then a finetune not the Hub's (proven in the
    engine); then the closest size; then the plainest definition (fewest entries a pointer leaves behind)."""
    return (jaccard(names, k.names), form.names_its_file(k.definition),
            len(words(Path(path).stem) & (words(k.model_type) | words(Path(k.file).stem))), k.owners,
            -abs(size - k.size), -form.extras(k.definition))


def model_kinds(models: dict[str, Any], defs: Path, form: Any = wan2gp_form) -> dict[str, Known]:
    """Every image model a file can be set up like, by id: `choose` says what the file is, whatever its name and
    whether or not the engine's own file of that kind is here (no tensor names to match then: `names` empty)."""
    out = {}
    for model_type, info in models.items():
        definition = read_json(info.get("source") or "")
        if form.model(definition) is not None:
            out[model_type] = Known(frozenset(), 0, "", model_type, str(info["architecture"]), definition,
                                    _inside(info["source"], [str(defs)]) is not None)
    return out


def known_models(models: dict[str, Any], fps: Fingerprints, defs: Path, form: Any = wan2gp_form) -> list[Known]:
    """The engine's image models with a present main file, each with the definition file to take values from."""
    out = []
    for model_type, info in models.items():
        definition = read_json(info.get("source") or "")
        if form.model(definition) is None:
            continue
        owners = _inside(info["source"], [str(defs)]) is not None
        for path in info.get("files") or ():
            names, size = fps.get(path)
            if names:
                out.append(Known(names, size, path, model_type, str(info["architecture"]), definition, owners))
    return out


def slug(stem: str) -> str:
    return "auto_" + (re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_") or "model")


def register(path: str, k: Known, defs: Path, taken: set[str], form: Any = wan2gp_form) -> bool:
    """Write the pointer definition for `path`, set up like the definition of `k`."""
    stem = Path(path).stem
    model_type, n = slug(stem), 2
    while model_type in taken:
        model_type, n = f"{slug(stem)}_{n}", n + 1
    try:
        write_json(defs / f"{model_type}.json", form.document(path, stem, k.model_type, k.architecture, k.definition))
    except OSError:
        return False
    taken.add(model_type)
    return True


def sync(weights: dict[str, Any], folders: list[str], skip: list[str], defs: Path, cache: Path,
         choices: dict[str, str] | None = None, form: Any = wan2gp_form) -> Found:
    """Bring the pointer definitions in `defs` in line with the model folders and choices.json
    (`choices`: weight path -> base model id, "" = leave the file alone); returns what changed, the models a file
    can be set up like, and one record per weight file for the Image models panel. `form`: the engine line's pointer
    form (`Adapter.pointers`)."""
    found, fps, choices = Found(), Fingerprints(cache), dict(choices or {})
    named = set(weights.get("named") or ())
    owned = {os.path.realpath(f): m for m, info in (weights.get("models") or {}).items()
             for f in info.get("files") or () if os.path.basename(f) in named}
    owned.update(weights.get("claimed") or {})                # files chosen for a model's parts
    have: dict[str, tuple[Path, str]] = {}                    # weight file -> (pointer file, base)
    redo: dict[str, str] = {}                                 # weight file -> the base of its stale pointer
    for file, definition in pointers(defs, form).items():
        path, base = form.points_at(definition)
        real = os.path.realpath(path) if path else ""
        if path and os.path.isfile(path) and _inside(path, folders) and not _inside(path, skip) \
                and os.path.basename(path) not in named and real not in owned and real not in have \
                and choices.get(path) != "":
            if not form.stale(definition):
                have[real] = (file, base)
            elif remove(file):        # written again below, set up like the same model
                found.changed, redo[real] = True, base
        elif remove(file):            # the file left the folders, a definition not the Hub's names it now, a
            found.changed = True      # second pointer names it, or its choice is "" (not a model)
    known = known_models(weights.get("models") or {}, fps, defs, form)
    kinds = model_kinds(weights.get("models") or {}, defs, form)       # every kind, its official file here or not
    found.bases = list(kinds)
    taken = set(weights.get("types") or ()) | {f.stem for f in defs.glob("*.json")}
    for path in weight_files(folders, skip):
        real = os.path.realpath(path)
        record = {"path": path, "name": os.path.basename(path), "folder": _inside(path, folders),
                  "size_mb": os.path.getsize(path) >> 20, "status": "unknown", "model": None, "base": None,
                  "suggested": None, "candidates": [], "chosen": choices.get(path)}
        found.files.append(record)
        if os.path.basename(path) in named or real in owned:
            record.update(status="known", model=owned.get(real))
            continue
        names, size = fps.get(path)
        fits = sorted((k for k in known if names and jaccard(names, k.names) >= MATCH
                       and LOW * k.size <= size <= HIGH * k.size), key=lambda k: rank(path, names, size, k, form),
                      reverse=True)
        record["candidates"] = list(dict.fromkeys(k.model_type for k in fits))
        record["suggested"] = fits[0].model_type if fits else None
        wanted = choices.get(path)
        pick = kinds.get(wanted or redo.get(real) or "")
        if wanted is None and pick is None:       # no choice, or a stale pointer's base that is gone: the best fit
            pick = fits[0] if fits else inherit.by_name(path, kinds, form)   # else the model it is named for
        if real in have and (wanted is None or have[real][1] == wanted) and (wanted or have[real][1]):
            record.update(status="pointer", model=have[real][0].stem, base=have[real][1])
            continue
        if real in have:              # another base chosen: the old pointer goes first
            remove(have[real][0])
            taken.discard(have[real][0].stem)
            found.changed = True
        if pick is not None and wanted != "" and register(path, pick, defs, taken, form):
            found.changed = True
            record.update(status="pointer", model=slug_for(path, defs, form), base=pick.model_type)
    fps.save()
    return found


def slug_for(path: str, defs: Path, form: Any = wan2gp_form) -> str | None:
    """The model id of the pointer that names `path` (just written)."""
    return next((f.stem for f, definition in pointers(defs, form).items() if form.points_at(definition)[0] == path),
                None)


def refresh(catalog: dict[str, Any] | None, engine: dict[str, Any] | None, lora_roots: list[str], data: Path) -> Found:
    """`sync` for one engine lane: its model folders, the LoRA folders skipped, the pointers in the folder the
    engine line reads finetunes from (where finetunes not the Hub's sit too); fingerprints in <data>/engine. Pointers an
    earlier hub version kept in <data>/engine/definitions are deleted (the hub's own, nothing else)."""
    old = data / "definitions"
    for file in pointers(old):
        remove(file)
    with contextlib.suppress(OSError):
        old.rmdir()                   # only when that left it empty
    root = str((engine or {}).get("root") or "")
    if catalog is None or not root or not isinstance(catalog.get("weights"), dict):
        return Found()
    skip = [str(p) for p in (*lora_roots, (catalog.get("engine") or {}).get("loras_root")) if p]
    form, folders = form_of(root), [str(f) for f in (engine or {}).get("model_folders", [])]
    try:
        renamed = dict(adapters.select(root).facts().get("renamed", {}).get("ids", {}))
    except Exception:
        renamed = {}
    with ONE_AT_A_TIME:
        before = inherit.choices(root, weight_files(folders, skip), set(catalog["weights"].get("models") or {}),
                                 renamed)                 # what the engine before the switch knew
        return sync(catalog["weights"], folders, skip, Path(form.folder(root)), data / "fingerprints.json",
                    {**before, **choices(data)}, form)


CHOICES = "choices.json"


def choices(data: Path) -> dict[str, str]:
    """The base choices (<data>/engine/choices.json: weight path -> model id, "" = not a model); entries
    for files that are gone are dropped."""
    saved = read_json(data / CHOICES)
    kept = {k: v for k, v in (saved or {}).items() if isinstance(k, str) and isinstance(v, str) and os.path.isfile(k)} \
        if isinstance(saved, dict) else {}
    if kept != saved:
        write_json(data / CHOICES, kept)
    return kept


def choose(data: Path, path: str, base: str) -> None:
    """Save the base chosen for a weight file ("" = not a model); the next rescan applies it."""
    with ONE_AT_A_TIME:
        write_json(data / CHOICES, {**choices(data), path: base})


def panel(catalog: dict[str, Any], found: Found | None) -> dict[str, Any]:
    """The Image models panel: every image model a file can be set up like (the engine's own and finetune
    definitions, never a pointer; its official file here or not), one record per file."""
    can = set(found.bases) if found else set()
    bases = [{"id": m["id"], "name": m["name"]} for m in catalog["models"] if m["id"] in can]
    return {"bases": bases, "files": list(found.files) if found else []}
