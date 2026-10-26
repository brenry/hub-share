"""What the engine before the switch knew of the model files, so the models set up there are set up again.

Switching the engine (Stage 10, `install/install-engine.sh`) kept the old engine's settings beside the new one
(`<engine folder>/.settings-before.json`, its `engine.root`) and left the old engine untouched. Two things there say
what each model file is: the pointers the Hub wrote into the old engine's `finetunes` (`hub_auto`: the file
and the model it was set up like, `hub_file`/`hub_base`), and the old engine's own definitions (`defaults`,
`finetunes`), whose `URLs` name the files they load. Both become choices.json entries for the new engine
(`autoreg.sync`), under the new engine's ids (the facts file's `renamed`), only for a model the new engine has; a
choice made in Settings wins. Nothing is written here and nothing of the old engine is changed. Stdlib only.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

BEFORE = ".settings-before.json"


def _read(path: Path) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def previous_root(root: str) -> str | None:
    """The engine folder the Hub ran before the switch, when it is still there."""
    saved = _read(Path(root).parent / BEFORE)
    old = ((saved or {}).get("engine") or {}).get("root") if isinstance(saved, dict) else None
    if not isinstance(old, str) or not old or not os.path.isdir(old):
        return None
    return None if os.path.realpath(old) == os.path.realpath(root) else old


def _model(path: Path) -> dict[str, Any] | None:
    doc = _read(path)
    part = doc.get("model") if isinstance(doc, dict) else None
    return part if isinstance(part, dict) else None


def _kind(part: dict[str, Any], stem: str, renamed: dict[str, str], kinds: set[str]) -> str | None:
    """The new engine's model a definition stands for: its own id (renamed), the model a Hub pointer was set up
    like, else the architecture it declares (an owner's finetune of that kind), the first the new engine has."""
    for name in (part.get("hub_base") if part.get("hub_auto") else stem, part.get("architecture")):
        if isinstance(name, str) and name:
            for kind in (renamed.get(name, name), name):
                if kind in kinds:
                    return kind
    return None


def _paths(part: dict[str, Any]) -> list[str]:
    """The files a definition loads: a Hub pointer's own file, and every `URLs` entry."""
    urls = part.get("URLs")
    found = [part.get("hub_file")] if part.get("hub_auto") else []
    found += urls if isinstance(urls, list) else []
    return [str(u).split("|", 1)[0] for u in found if isinstance(u, str) and u]


def known_before(old: str, renamed: dict[str, str], kinds: set[str]) -> tuple[dict[str, str], dict[str, str]]:
    """({file path: model}, {file name: model}) for every file the old engine's definitions and the Hub's old
    pointers there load, under the new engine's ids and only for a model it has. A pointer or an owner's finetune
    wins over the engine's own default for the same file name."""
    by_path: dict[str, str] = {}
    by_name: dict[str, str] = {}
    for folder in ("defaults", "finetunes"):                         # finetunes last: they win
        for file in sorted(Path(old, folder).glob("*.json")):
            part = _model(file)
            kind = _kind(part, file.stem, renamed, kinds) if part is not None else None
            if part is None or kind is None:
                continue
            for path in _paths(part):
                if os.path.isabs(path):
                    by_path[path] = kind
                by_name[os.path.basename(path)] = kind
    return by_path, by_name


def choices(root: str, files: list[str], kinds: set[str], renamed: dict[str, str]) -> dict[str, str]:
    """{weight file: model} for the files in the model folders (`files`) the old engine knew: by the path it
    recorded, else by the file name (the same file seen through another folder), each a model the new engine has."""
    old = previous_root(root)
    if old is None:
        return {}
    by_path, by_name = known_before(old, renamed, kinds)
    out = {}
    for path in files:
        kind = by_path.get(path) or by_path.get(os.path.realpath(path)) or by_name.get(os.path.basename(path))
        if kind:
            out[path] = kind
    return out


def words(text: str) -> set[str]:
    """The words and numbers in a name, camelCase split (as `autoreg.words`)."""
    return {w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", text)}


def _letters(text: str) -> set[str]:
    return {w for w in words(text) if w.isalpha() and len(w) >= 3}


def by_name(path: str, kinds: dict[str, Any], form: Any) -> Any:
    """The engine's image model a file is named for: the most words of three letters or more shared by the
    file's name and the model's id and name, then the fewest of the model's words left over; two shared at least,
    and only when one model alone is best (else none: the file waits)."""
    mine = _letters(Path(path).stem)
    scored = []
    for k in kinds.values():
        have = _letters(k.model_type) | _letters(form.title(k.definition, k.model_type))
        scored.append(((len(mine & have), -len(have - mine)), k))
    scored.sort(key=lambda s: s[0], reverse=True)
    if scored and scored[0][0][0] >= 2 and (len(scored) == 1 or scored[1][0] < scored[0][0]):
        return scored[0][1]
    return None
