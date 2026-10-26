"""The voice step of a converted clip: upstream WanGP's SeedVC turns the speech of the clip the render
made into the speaker's voice from the speaker's `<Name>.wav`, the room kept, the picture muxed as it is (upstream
`af2ed29`: `shared/api.py:1562-1583`, `wgp.py:6191`, `:6282`, `:6353-6372`;
`postprocessing/seedvc_processor/bridge.py:356-384`).

`task(request)` is the engine's own remux task (`build_audio_remux_settings`, one speaker), submitted as it is: the
engine built it, so it is not `translate`d. `state(w, root)` says whether SeedVC is on in the engine's config
(`audio_processors.seedvc.mode`, off by default, `audio_processors.py:673-679`) and what it lacks: each file of its
mode not found where the engine looks (`assets.query_required_files`, `files_locator.locate_file`), the separator's
(`download_def_missing_files`), each counted under its folder, and the component (`component.installed()`). The engine
fetches what lacks (`bridge.py:302-325`); the Hub never does (CLAUDE.md), so `run` refuses in that one line first, and
the guard (`upstream_weights.GUARDED`, `download_url`) refuses a fetch that slips past. A model the worker holds is
released first (`wgp.py:270-282`): the step loads SeedVC alone. Stdlib only; nothing on stdout.

`keep_root(w, root)` puts the root config's `audio_processors.seedvc` section into the
engine's live config, in memory: the engine's migration sets mode 2 in the worker's copy at each start when the root is
unmigrated (`wgp.py:2789`; `shared/utils/wgp_config_migration.py:258-261`, `:159-162`), and SeedVC reads that live
config at each call (`audio_processors.py:216-225`, `seedvc_processor/audio_processor.py:72-82`). No file is written. A
mode but 1 is refused by its name (`SEEDVC_MODE_CHOICES`, `wgp_config_migration.py:17`).
"""
from __future__ import annotations

import importlib
import json
import os
import time
from typing import Any

try:
    from .. import faults
except ImportError:  # run as a script by the engine's Python
    import faults

METHOD = "seedvc_one_speaker"            # `postprocessing/audio_processors.py:57`: every voice to the one sample
CONFIG = ("audio_processors", "seedvc", "mode")    # `audio_processors.py:44`, `audio_processor.py:45`, `:53-57`
OFF = "Voice conversion is off in the engine's config (audio_processors.seedvc.mode)"
MODE = ("Voice conversion is set to mode {} in the engine's config; speech is mode 1 (audio_processors.seedvc.mode in "
        "the engine's wgp_config.json)")
LACKS = "Voice conversion lacks, in your model folders: {}"
COMPONENT = "the SeedVC component (engine {})"
# What this module reads from the engine (R9 §3; the contract test), each tagged with the line that publishes it.
READS: dict[str, dict[str, str]] = {
    "wgp": {"server_config": "upstream", "release_model": "upstream"},
    "api": {}, "definition": {}, "settings": {}, "generate_video": {}, "suffixes": {},
}


def mode(w: Any) -> int:
    """SeedVC's mode in the engine's config: 0 off (its default), else the version it runs."""
    value: Any = getattr(w, "server_config", None) or {}
    for key in CONFIG:
        value = value.get(key) if isinstance(value, dict) else None
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def keep_root(w: Any, root: str) -> None:
    """The root's SeedVC section, normalized as the engine normalizes it, over the engine's live one; a root without
    it (or unreadable) leaves the engine's value."""
    try:
        with open(os.path.join(root, "wgp_config.json"), encoding="utf-8") as f:
            section = json.load(f).get(CONFIG[0], {}).get(CONFIG[1])
    except (OSError, ValueError, AttributeError):
        return
    config = getattr(w, "server_config", None)
    if not isinstance(section, dict) or not isinstance(config, dict):
        return
    processor = importlib.import_module("postprocessing.seedvc_processor.audio_processor").SeedVCProcessor
    sections = config.get(CONFIG[0])
    if not isinstance(sections, dict):
        sections = config[CONFIG[0]] = {}
    live = sections.get(CONFIG[1])
    sections[CONFIG[1]] = {**(live if isinstance(live, dict) else {}), **processor.normalize_config_section(section)}


def named(version: int) -> str:
    """The mode with the engine's own label for it, as `2 (v1.0 Singing / F0 44k)`."""
    choices = importlib.import_module("shared.utils.wgp_config_migration").SEEDVC_MODE_CHOICES
    label = next((name for name, value in choices if value == version), "")
    return f"{version} ({label})" if label else str(version)


def lacking(root: str, version: int) -> list[str]:
    """What SeedVC of this version lacks, as the engine looks for it: each folder with its count of files not found
    ("seed-vc (2 files)"), then the component when it is not installed."""
    assets = importlib.import_module("postprocessing.seedvc_processor.assets")
    component = importlib.import_module("postprocessing.seedvc_processor.component")
    locate = importlib.import_module("shared.utils.files_locator").locate_file
    download = importlib.import_module("shared.utils.download")
    missing = [p for p in assets.query_required_files(version) if locate(p, error_if_none=False) is None]
    missing += download.download_def_missing_files(download.query_audio_background_replacement_download_def())
    folders: dict[str, int] = {}
    for path in missing:
        folder = str(path).replace("\\", "/").split("/", 1)[0]
        folders[folder] = folders.get(folder, 0) + 1
    out = [f"{name} ({n} {'file' if n == 1 else 'files'})" for name, n in folders.items()]
    if not component.installed():
        out.append(COMPONENT.format(os.path.relpath(component.SEEDVC_COMPONENT_DIR, root).replace("\\", "/")))
    return out


def state(w: Any, root: str) -> dict[str, Any]:
    """{on, lacking, line}: the line is the refusal ("" when the step can run). The root section first."""
    keep_root(w, root)
    version = mode(w)
    if not version:
        return {"on": False, "lacking": [], "line": OFF}
    if version != 1:
        return {"on": True, "lacking": [], "line": MODE.format(named(version))}
    lacks = lacking(root, version)
    return {"on": True, "lacking": lacks, "line": LACKS.format(", ".join(lacks)) if lacks else ""}


def task(request: Any) -> dict[str, Any]:
    """The engine's own remux task for the request: the clip, its voice turned into the sample's, one speaker."""
    build = importlib.import_module("shared.api").build_audio_remux_settings
    seed = {} if request.seed is None else {"seed": request.seed}    # `seed=None` raises there (R55 §3)
    return build(request.clip, postprocess_audio=METHOD, replace_voice_sample=request.sample, **seed)


def run(engine: Any, job_id: str, k: int, request: Any, emit: Any) -> dict[str, Any]:
    """The voice step to its end, as `Engine.run` reports a task: progress (the engine's own status, "Replace
    Voice"), the converted clip as `output`, then `task_done`."""
    started, base = time.monotonic(), {"job": job_id, "task": k}
    errors: list[Any] = []
    result, cancelled = None, False
    try:
        line = state(engine.w, engine.root)["line"]
        if line:
            errors.append(faults.Refused(line))
        else:
            if engine.loaded() is not None:
                engine.w.release_model()
            params = task(request)
            with engine._lock:
                cancelled = engine._cancel_pending == job_id
                engine._cancel_pending = None
                job = None if cancelled else engine.session.submit_task(params)
                engine._job, engine._job_id = job, job_id
            if job is not None:
                for event in job.events.iter(timeout=0.5):
                    if event.kind == "error":
                        errors.append(event.data)
                    elif event.kind == "progress":
                        p = event.data
                        emit({**base, "ev": "progress", "phase": p.phase, "step": p.current_step,
                              "steps": p.total_steps, "pct": p.progress, "text": p.status})
                result = job.result()
                cancelled = bool(job.cancel_requested)
                runner = getattr(job, "_thread", None)
                if runner is not None:
                    runner.join(30)
    except Exception as exc:
        errors.append(exc)
    finally:
        with engine._lock:
            engine._job, engine._job_id = None, None
    files = list(getattr(result, "generated_files", None) or [])[-1:]
    for path in files:
        emit({**base, "ev": "output", "file": os.path.abspath(path)})
    errors.extend(getattr(result, "errors", None) or [])
    ok = bool(files) and not errors and not cancelled
    done = {**base, "ev": "task_done", "ok": ok, "seconds": round(time.monotonic() - started, 2),
            "model": engine.loaded(), "peak_vram_mb": None, "peak_rss_mb": None}
    if not ok:
        done["error"] = faults.failure(errors, cancelled)
    return done
