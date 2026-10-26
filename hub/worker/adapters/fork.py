"""The fork's adapter: the older Wan2GP line HocusPocus carries (the worker's "legacy" flavour).

What is the fork's own and nowhere else: its key families (`fork.facts.json`), how it fills a task (generic defaults
underneath, "one prompt" as 2, LoRAs by base name in a flat folder), its factory settings (built from
`primary_settings` and the handler, as its UI does), its LoRA root and its read-only linked LoRA folders.
Probe order puts it after `upstream`: a Wan2GP root (or opened session) upstream declines is the fork's.
Stdlib only; run by the engine's Python like the rest of the worker.
"""
from __future__ import annotations

import copy
import glob
import os
import posixpath
import shutil
from typing import Any

from . import joins, modelfiles, plan, pointers, soundtail, tasks

try:
    from ..engineapi import KeyFamilies, read_facts
    from ..faults import Unready
except ImportError:  # run as a script by the engine's Python
    from engineapi import KeyFamilies, read_facts
    from faults import Unready

FACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fork.facts.json")
FAMILIES = KeyFamilies(**read_facts(FACTS)["families"])
NO_FFMPEG = "ffmpeg is not installed on the server"
# Per task: the Hub's promise (the task's prompt reaches the model unchanged), plus a file name that says nothing.
FORCED_TASK: dict[str, Any] = {"prompt_enhancer": "", "negative_prompt": "", "alt_prompt": "",
                               "output_filename": "{date}-{seed}"}
# A clip (image_mode 0) keeps the sound its model makes: never driven by a soundtrack, never a second audio model.
FORCED_VIDEO: dict[str, Any] = {"audio_prompt_type": "", "MMAudio_setting": 0}
# What this module reads from the engine, each tagged with the line that publishes it (R9 §3; the contract test).
READS: dict[str, dict[str, str]] = {
    "wgp": {"get_model_def": "both", "get_base_model_type": "both", "primary_settings": "legacy",
            "settings_version": "both", "get_model_handler": "both", "args": "both", "server_config": "both",
            "DEFAULT_LORA_ROOT": "legacy", "get_lora_search_dirs": "legacy", "fl": "legacy",
            "get_model_recursive_prop": "both", "resolve_lora_path": "legacy",
            **dict.fromkeys(read_facts(FACTS)["companions"]["calls"].values(), "legacy")},
    "api": {},
    "definition": {"i2v_class": "legacy", "settings": "both", "source": "legacy", "VAE_URLs": "legacy",
                   "wangp_1272": "legacy", **dict.fromkeys(FAMILIES.fields(), "legacy")},
    "settings": {},
    "generate_video": {},
    "suffixes": dict.fromkeys(FAMILIES.suffixes().values(), "legacy"),
}


def wan2gp_root(root: str) -> bool:
    return os.path.isfile(os.path.join(root, "wgp.py")) and os.path.isfile(os.path.join(root, "shared", "api.py"))


def translate(task: dict, factory: dict) -> dict:
    """The Hub's task as the fork takes it, forced values on top. The fork starts every task from generic defaults
    (30 steps, 832x480...), so the model's own defaults go underneath; it reads "one prompt" as 2, not "FG"; and it
    finds LoRAs by file name in a flat folder."""
    extra = FORCED_VIDEO if task.get("image_mode") == 0 else {}
    out = {**copy.deepcopy(factory), **copy.deepcopy(task), **FORCED_TASK, **extra}
    if out.get("multi_prompts_gen_type") == "FG":
        out["multi_prompts_gen_type"] = 2
    out["activated_loras"] = [posixpath.basename(n) for n in out.get("activated_loras") or []]
    return out


def factory_settings(w: Any, model_type: str) -> dict:
    """The model's pristine defaults, never written to disk: the fork fills every task from `primary_settings`, so
    those sit underneath, with the handler's and the model's own values on top (as the fork's UI builds them)."""
    model_def = w.get_model_def(model_type)
    base = w.get_base_model_type(model_type)
    i2v = model_def.get("i2v_class", False)
    ui = copy.deepcopy(w.primary_settings)
    ui |= {
        "settings_version": w.settings_version,
        "resolution": "1280x720" if "720" in base else "832x480",
        "flow_shift": 7.0 if "720" not in base and i2v else 5.0,
    }
    w.get_model_handler(model_type).update_default_settings(base, model_def, ui)
    ui.update(copy.deepcopy(model_def.get("settings") or {}))
    return ui


def lora_root(w: Any) -> str:
    """The LoRA root as the fork resolves it: `--loras`, else the config's `loras_root`, else its default."""
    cli = getattr(w.args, "loras", "")
    cli = cli.strip() if isinstance(cli, str) else ""
    return cli or w.server_config.get("loras_root", w.DEFAULT_LORA_ROOT) or w.DEFAULT_LORA_ROOT


def lora_search(w: Any, model_type: str) -> list[str]:
    """The fork's read-only "linked" LoRA folders for the model (relative to the root, as it gives them)."""
    search = getattr(w, "get_lora_search_dirs", None)
    return list(search(model_type)) if search else []


def prepare(root: str) -> None:
    """Before the engine opens. Its `download_ffmpeg` (run at session start) returns at once, never fetching, when
    `_resolve_path` finds each program (`<root>/ffmpeg_bins`, `<root>`, then `shutil.which` on PATH; a `<root>/ffmpeg`
    is quarantined first) and `_libs_present()` holds (ffmpeg outside ffmpeg_bins, or a libavdevice there). It never
    reads FFMPEG_BINARY. So: resolve them the same way; found, name them as its `_set_env_vars` does; else one line."""
    spec = read_facts(FACTS)["ffmpeg"]
    if not os.path.isfile(os.path.join(root, spec["fetcher"])):
        return                                   # an engine that fetches no ffmpeg
    bins, found = os.path.join(root, spec["folder"]), {}
    for name, env in spec["programs"].items():
        here = [p for p in (os.path.join(bins, name), *([os.path.join(root, name)] if name != "ffmpeg" else []))
                if os.path.exists(p)]
        path = here[0] if here else shutil.which(name)
        if path is None:
            raise Unready(NO_FFMPEG)
        found[env] = os.path.abspath(path)
    first = next(iter(found.values()))
    if os.path.dirname(first) == bins and not glob.glob(os.path.join(bins, spec["libs"])):
        raise Unready(NO_FFMPEG)
    os.environ.update(found)


def _key(*parts: str) -> str:
    return os.path.join(*[p for p in parts if p])


def wanted(fl: Any, defs: list[dict]) -> list[str]:
    """What the engine's `process_files_def` (wgp.py:3696-3780) would fetch for these definitions, by its rules: a
    folder set is whole in one checkpoint folder and not partial in its write target; other files anywhere."""
    out: list[str] = []
    for d in defs:
        sources = d.get("sourceFolderList") or []
        for target, source, files in zip(d.get("targetFolderList") or [None] * len(sources), sources,
                                         d.get("fileList") or [], strict=False):
            parts = [p for p in (target, source) if p]
            keys = [_key(*parts, f) for f in files]
            if not files:
                out += [_key(*parts)] if parts and fl.locate_folder(_key(*parts), error_if_none=False) is None else []
                continue
            nowhere = [k for k in keys if fl.locate_file(k, error_if_none=False) is None]
            if d.get("independent_files") or not parts:
                out += nowhere
                continue
            top = fl.get_smart_download_root(target or source)
            short = [k for k in keys if not os.path.isfile(os.path.join(top, k))]
            whole = any(all(os.path.isfile(os.path.join(r, k)) for k in keys) for r in fl.get_checkpoints_paths())
            if not whole or (short and os.path.isdir(os.path.join(top, *parts))):
                out += nowhere or short
    return out


def _every_model(w: Any) -> list[dict]:
    """`download_models`' fetches for any model: its shared list, the mask tool's and the audio set when the config
    enables it. The prompt enhancer's are left out: the worker forces it off (`FORCED_CONFIG`)."""
    spec = read_facts(FACTS)["companions"]
    config, pick = copy.deepcopy(w.server_config), spec["by_config"]   # the engine's helpers rewrite their config
    groups = [*spec["shared"], ["", [pick["when_default"] if config.get(pick["key"], pick["default"]) ==
                                     pick["default"] else pick["otherwise"]]]]
    audio = getattr(w, spec["calls"]["audio"], None)
    if audio is not None and audio(config)[0]:
        (folder, files), *rest = spec["audio"]
        groups += [[folder, [*files, os.path.basename(audio(config)[4])]], *rest]
    defs = [{"sourceFolderList": [g[0] for g in groups], "fileList": [g[1] for g in groups]}]
    mask = getattr(w, spec["calls"]["mask"], None)
    return defs + ([mask(config)] if mask is not None else [])


def lacking(w: Any, model_type: str | None) -> list[str]:
    """What `download_models(file_type=0)` would fetch before `model_type` loads (wgp.py:3912-4012), as paths under
    the checkpoint folders: every model's, then the model's own (its main file in any variant, `preload_URLs`,
    `VAE_URLs`, LoRAs, its handler's `query_model_files`). None: every model's alone. No file locator: nothing."""
    fl = getattr(w, "fl", None)
    if fl is None:
        return []
    out = wanted(fl, _every_model(w))
    if model_type is None:
        return out
    model_def = w.get_model_def(model_type) or {}

    def listed(prop: str) -> list[str]:
        value = w.get_model_recursive_prop(model_type, prop, return_list=True) or []
        return [u for u in (value if isinstance(value, list) else [value]) if isinstance(u, str) and u]

    def found(url: str) -> bool:
        return fl.locate_file(os.path.basename(url) if url.startswith("http") else url, error_if_none=False) is not None

    main = listed("URLs")
    out += [os.path.basename(main[0])] if main and "source" not in model_def and not any(map(found, main)) else []
    vae = model_def.get("VAE_URLs") or []
    for url in [*listed("preload_URLs"), *([vae] if isinstance(vae, str) else vae)]:
        if not found(url) and not (model_def.get("wangp_1272") and "/loras/" in url):
            out.append(os.path.basename(url))
    resolve = getattr(w, "resolve_lora_path", None)
    out += [os.path.basename(u) for u in (listed("loras") if resolve else [])
            if not os.path.isfile(resolve(model_type, os.path.basename(u)))]
    query = getattr(w.get_model_handler(model_type), "query_model_files", None)
    if query is not None:
        files = query(lambda f: [] if f is None else [f[f.rfind("/") + 1:]], w.get_base_model_type(model_type),
                      model_def)
        out += wanted(fl, files if isinstance(files, list) else [files])
    return list(dict.fromkeys(out))


class Fork:
    name = "fork"
    flavour = "legacy"
    families = FAMILIES
    factory_underneath = True
    lora_recursive = False
    forced_config: dict[str, Any] = {}        # its crop is per task (`tasks.FORK`)
    READS = READS
    pointers = pointers                       # a Hub pointer as this line keeps it (a Wan2GP finetune file)
    modelfiles = modelfiles                   # each model's own files, as chosen

    def probe(self, root: str, session: Any = None) -> bool:
        """After `upstream` declined: an opened Wan2GP session, or (before opening) a Wan2GP root."""
        return session is not None or wan2gp_root(root)

    def facts(self) -> dict[str, Any]:
        return read_facts(FACTS)

    def task(self, request: Any, entry: dict) -> dict:
        return tasks.task(request, entry, tasks.FORK)

    translate = staticmethod(translate)
    factory_settings = staticmethod(factory_settings)
    lora_root = staticmethod(lora_root)
    lora_search = staticmethod(lora_search)
    prepare = staticmethod(prepare)
    lacking = staticmethod(lacking)

    @staticmethod
    def opened(w: Any) -> None:
        """Nothing to set once open: the pre-check (`lacking`) finds what the fork would fetch."""

    window = staticmethod(tasks.window)
    dropped = staticmethod(soundtail.dropped)
    finish = staticmethod(joins.finish)

    @staticmethod
    def plan(session: Any, task: dict) -> dict[str, Any]:
        """The fork has no preflight the worker reads: one line, no windows."""
        return {"valid": False, "windows": [], "warnings": [], "errors": [plan.NO_PREFLIGHT], "notes": []}

    @staticmethod
    def native(w: Any, model_type: str, model_def: dict) -> dict[str, Any] | None:
        """The fork publishes its clip facts in its definitions (`catalogvideo`): nothing of its own to add."""
        return None

    @staticmethod
    def line_facts(w: Any, model_type: str, model_def: dict) -> dict[str, Any]:
        """Nothing the definitions do not say: the fork checks no size against a budget, its ids are the ones the Hub
        saved first, and its definitions publish their step locks."""
        return {}
