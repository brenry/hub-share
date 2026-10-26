"""Rebuild the fake engine from a capture: `python rebuild.py <dump.json> [--check] [--into DIR]`.

Rewrites `fake_engine.json` and `defaults/*.json` in DIR (default: this folder) from a dump the worker wrote
(`main.py --dump-engine`) plus one hand-kept file, `overlay.json` in DIR: `keep` (dump model type -> fake file name),
`edits` (per fake model, test-only `model` and `settings` changes, each with a `why`; null removes a field),
`available`, `flavour` and `primary_settings` (used only when the dump has none). Neither output is edited by hand:
`--check` writes nothing and exits 1 with the files that would change. Bad input stops it with one line (exit 2).

From the dump: `version`, `settings_version`, `families`, `primary_settings`, `generate_video`. Per architecture of a
kept model: `architectures` holds the definition fields equal across every dumped model of it (less `name`,
`description`, `URLs`, `settings`), `handler_defaults` the factory values common to them that differ from
`primary_settings` and are in no model's own settings, `lora_keys` the models' LoRA folder. Per kept model:
`defaults/<id>.json` = {"model": the rest of its definition, **its settings, plus the factory values the handler set
for it alone}, URLs pointing at a fake host, then the overlay's edits. The output is sorted: a rerun on the same
dump changes no byte.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FAKE_URL = "https://huggingface.co/fake/resolve/main/"
URL_KEYS = ("URLs", "preload_URLs", "loras")
NOT_SHARED = ("name", "description", "URLs", "settings", "path")


class Stop(Exception):
    """Bad input: the one line shown."""


def text(value: Any) -> str:
    return json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def fake_urls(value: Any, url: bool = False) -> Any:
    """Every file listed under a URL key, as a link to the fake host. A plain string there (`"URLs": "<type>"`)
    names another model, which the engine follows, so it stays."""
    if isinstance(value, dict):
        return {k: v if isinstance(v, str) else fake_urls(v, url or k in URL_KEYS or k.endswith("_URLs"))
                for k, v in value.items()}
    if isinstance(value, list):
        return [FAKE_URL + v.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] if url and isinstance(v, str)
                else fake_urls(v, url) for v in value]
    return value


def check_overlay(dump: dict, overlay: dict) -> None:
    if dump.get("format") != 1:
        raise Stop("the dump is not a format 1 engine dump")
    keep = overlay.get("keep") or {}
    for model_type in keep:
        if model_type not in dump["models"]:
            raise Stop(f"overlay keep names {model_type}, which the dump does not hold")
    for model_id, edit in (overlay.get("edits") or {}).items():
        if model_id not in keep.values():
            raise Stop(f"overlay edits name {model_id}, which keep does not make")
        if not isinstance(edit, dict) or not str(edit.get("why") or "").strip():
            raise Stop(f"overlay edit for {model_id} has no why")


def shared_fields(defs: list[dict]) -> dict[str, Any]:
    first, rest = defs[0], defs[1:]
    return {k: v for k, v in first.items() if k not in NOT_SHARED and all(k in d and d[k] == v for d in rest)}


def handler_set(factory: dict, settings: dict, primary: dict) -> dict[str, Any]:
    """The factory values neither the model's own settings nor `primary_settings` explain."""
    return {k: v for k, v in factory.items() if k not in settings and (k not in primary or primary[k] != v)}


def build(dump: dict, overlay: dict) -> dict[str, str]:
    """{relative path: file text} for the whole fake."""
    check_overlay(dump, overlay)
    models, keep = dump["models"], overlay["keep"]
    primary = dump.get("primary_settings")
    primary = primary if isinstance(primary, dict) else overlay.get("primary_settings") or {}
    by_arch: dict[str, list[dict]] = {}
    for facts in models.values():
        by_arch.setdefault(str(facts["architecture"]), []).append(facts)
    archs = sorted({str(models[t]["architecture"]) for t in keep})
    architectures, handler_defaults, lora_keys = {}, {}, {}
    for arch in archs:
        group = by_arch[arch]
        entry = shared_fields([m["definition"] for m in group])
        if "family" not in entry and len({str(m["family"]) for m in group}) == 1:
            entry["family"] = group[0]["family"]
        architectures[arch] = entry
        sets = [handler_set(m["factory"], m["settings"], primary) for m in group]
        handler_defaults[arch] = {k: v for k, v in sets[0].items() if all(k in s and s[k] == v for s in sets[1:])}
        found = [models[t]["lora_key"] for t in sorted(keep) if models[t]["architecture"] == arch]
        if found and found[0] is not None:
            lora_keys[arch] = found[0]
    files: dict[str, str] = {}
    edits = overlay.get("edits") or {}
    for model_type, model_id in sorted(keep.items()):
        facts = models[model_type]
        arch = str(facts["architecture"])
        definition = facts["definition"]
        model = {k: v for k, v in definition.items()
                 if k in ("name", "description", "architecture", "URLs") or (k not in architectures[arch]
                                                                              and k not in ("settings", "path"))}
        if isinstance(model.get("URLs"), str):
            model["URLs"] = keep.get(model["URLs"], model["URLs"])
        own = handler_set(facts["factory"], facts["settings"], primary)
        settings = {**facts["settings"], **{k: v for k, v in own.items() if k not in handler_defaults[arch]}}
        edit = edits.get(model_id) or {}
        for target, changes in ((model, edit.get("model") or {}), (settings, edit.get("settings") or {})):
            for k, v in changes.items():
                if v is None:
                    target.pop(k, None)
                else:
                    target[k] = v
        files[f"defaults/{model_id}.json"] = text({"model": fake_urls(model), **settings})
    files["fake_engine.json"] = text({
        "flavour": overlay.get("flavour") or "upstream",
        "version": dump["engine"]["version"], "settings_version": dump["engine"]["settings_version"],
        "primary_settings": primary, "families": dump["families"], "generate_video": dump["generate_video"],
        "architectures": fake_urls(architectures), "handler_defaults": handler_defaults, "lora_keys": lora_keys,
        "available": sorted(overlay.get("available") or []),
    })
    return files


def changes(into: Path, files: dict[str, str]) -> list[str]:
    """The files that differ from `files` (or are not part of it) in `into`, sorted."""
    stale = [f"defaults/{p.name}" for p in (into / "defaults").glob("*.json") if f"defaults/{p.name}" not in files]
    differ = [rel for rel, body in files.items()
              if not (into / rel).is_file() or (into / rel).read_text(encoding="utf-8") != body]
    return sorted(stale + differ)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="rebuild.py")
    p.add_argument("dump")
    p.add_argument("--check", action="store_true")
    p.add_argument("--into", default=str(HERE))
    opts = p.parse_args(argv)
    into = Path(opts.into)
    try:
        dump = json.loads(Path(opts.dump).read_text(encoding="utf-8"))
        overlay = json.loads((into / "overlay.json").read_text(encoding="utf-8"))
        files = build(dump, overlay)
    except Stop as exc:
        print(f"rebuild: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"rebuild: cannot read the dump or the overlay ({type(exc).__name__}: {exc})", file=sys.stderr)
        return 2
    changed = changes(into, files)
    if opts.check:
        for rel in changed:
            print(rel)
        return 1 if changed else 0
    for rel in changed:
        path = into / rel
        if rel in files:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(files[rel], encoding="utf-8")
        else:
            path.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
