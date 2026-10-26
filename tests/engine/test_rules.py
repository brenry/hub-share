"""House rules for the image-engine code: no content filters, no logging, stdlib-only worker, no engine key family
outside the adapters, and (Stage 9 step 4) no engine task key or prompt letter on the Hub's side of the seam."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from hub.worker.adapters import ADAPTERS

HUB = Path(__file__).resolve().parents[2] / "hub"
ADAPTER_DIR = HUB / "worker" / "adapters"
# The key families R9 §3 names as the fork's conventions: guarded even if a facts file stopped listing one.
FLOOR = ("omni_reference", "_references", "_reference_detail", "_multi_window", "_sidecar", "_text_encoder")
OURS = [*(HUB / "worker").rglob("*.py"), HUB / "core" / "engine.py", HUB / "core" / "supervisor.py",
        HUB / "core" / "autoreg.py",
        *(HUB / "modules" / "generate_image").glob("*.py"), *(HUB / "modules" / "loras").glob("*.py"),
        *(HUB / "modules" / "media").glob("*.py")]


def imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_no_content_filters_and_no_logging():
    for path in OURS:
        text = path.read_text().lower()
        assert not re.search(r"nsfw|safety|censor|content_filter|moderat", text), path
        assert "logging" not in imports(path) and "print(" not in text.replace("print(one_line", ""), path


def test_worker_is_stdlib_only():
    import sys
    allowed = set(sys.stdlib_module_names) | {"protocol", "netguard", "wan2gp", "catalog", "catalogvideo", "probe",
                                                     "definitions", "faults", "wgpconfig", "enginedump", "engineapi",
                                                     "enginewire", "adapters", "join", "joincmd", "mixcmd", "probejoin",
                                                     "keep", "enginerequests", "catalogspeech", "frames"}
    walked = [p for p in (HUB / "worker").rglob("*.py") if "__pycache__" not in p.parts]
    assert ADAPTER_DIR / "fork.py" in walked
    for path in walked:
        assert imports(path) <= allowed, path


def families() -> set[str]:
    """Every engine key family the adapters' facts files name (prefix fields, suffixes, the encoder's parts joined),
    plus the floor."""
    out = set(FLOOR)
    for adapter in ADAPTERS:
        keys = adapter.families
        out |= {*keys.fields(), *keys.suffixes().values(), *([keys.encoder] if keys.encoder else [])}
    return out


def test_no_engine_key_family_outside_the_adapters():
    """How an engine names a key per model family (`omni_reference`, `<family>_references`, `_multi_window`...)
    is the adapter's alone: no other file under hub/ names one, in code, data or a docstring."""
    names = families()
    assert {"_multi_window", "_references", "omni_reference_limits", "_text_encoder_default"} <= names
    pattern = re.compile("|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)))
    files = [p for p in HUB.rglob("*") if p.suffix in (".py", ".json") and "__pycache__" not in p.parts]
    outside = [p for p in files if ADAPTER_DIR not in p.parents]
    assert len(outside) > 50 and any(ADAPTER_DIR in p.parents for p in files)
    found = [f"{p.relative_to(HUB)}: {m.group(0)}" for p in outside if (m := pattern.search(p.read_text()))]
    assert found == []


def test_modules_reach_core_only_through_the_api():
    for path in OURS:
        if "modules" in path.parts:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").startswith("hub."):
                    assert node.module == "hub.core.api", (path, node.module)


# Stage 9 step 4: modules and the core build requests in the Hub's words (`engineapi`); the keys an engine task is made
# of, and the prompt letters some of them hold, are the adapters' (`adapters/tasks.py`). Checked in every string the
# Hub's side holds (code, data, docstrings), by whole word, and in every keyword argument's name (`dict(key=...)`).
# The scope and what it leaves out: `test_no_engine_task_key_on_the_hubs_side`.
ENGINE_KEYS = ("model_type", "image_mode", "image_prompt_type", "video_prompt_type", "sliding_window_size",
               "sliding_window_overlap", "activated_loras", "loras_multipliers", "num_inference_steps",
               "guidance_scale", "embedded_guidance_scale", "image_refs", "image_start", "image_end", "image_fit_mode",
               "video_source", "video_length", "keep_frames_video_source", "remove_background_images_ref",
               "remove_background", "multi_prompts_gen_type", "image_intent", "character_name", "MMAudio_setting",
               "audio_prompt_type", "postprocess_audio", "prompt_enhancer", "negative_prompt", "alt_prompt",
               "output_filename", "image_refs_relative_size")
# The reference, picture-type and prompt letters a task holds ("T" text, "S" start, "E" end, "V" continue, "L" last
# video, "I" references, "K"/"F" their modes, "FG" one prompt).
LETTERS = frozenset({"T", "S", "E", "L", "V", "I", "SE", "TSEV", "TSEVL", "KI", "FI", "FG"})
WORKER_SIDE = ("engineapi.py", "enginewire.py", "protocol.py", "main.py", "wan2gp.py", "join.py", "joincmd.py",
               "mixcmd.py", "probejoin.py", "probe.py", "netguard.py", "faults.py")
# Files on the Hub's side that still name engine keys, each with why (a debt, said where it is kept). None since
# Stage 10: the registry's pointer form is the adapter's (`adapters/pointers.py`).
KNOWN: dict[Path, str] = {}


def hub_side() -> list[Path]:
    files = [*(HUB / "core").glob("*.py"), *(HUB / "modules").rglob("*.py"), *(HUB / "worker" / n for n in WORKER_SIDE)]
    return [p for p in files if "__pycache__" not in p.parts and p not in KNOWN]


def strings(path: Path) -> list[str]:
    """Every string the file holds: its constants and the names of its keyword arguments (`dict(model_type=...)`)."""
    tree = ast.parse(path.read_text())
    return [*(n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)),
            *(n.arg for n in ast.walk(tree) if isinstance(n, ast.keyword) and n.arg)]


def test_the_guard_sees_keyword_arguments(tmp_path):
    path = tmp_path / "x.py"
    path.write_text("task = dict(model_type='m', seed=1)\n")
    assert "model_type" in strings(path) and "seed" in strings(path)


def test_no_engine_task_key_on_the_hubs_side():
    """No engine task key (ENGINE_KEYS) in any string or keyword argument on the Hub's side. The scope (`hub_side`) and
    what it leaves out, each on purpose:
    - in: hub/core/*.py, hub/modules/**/*.py, and the worker's Hub-side files (WORKER_SIDE: the seam's types and wire,
      the session loop, the join, the probes, the fault lines), which speak to the adapter and never build a task;
    - out: hub/worker/adapters/ (the one place engine keys live); the worker's shared helpers (catalog.py,
      catalogvideo.py, definitions.py, wgpconfig.py, enginedump.py), which read the engine's own definitions and
      config under the engine's field names (the key families have their own guard, above); the KNOWN debts, each
      with its why; tests, docs and the web client (it sends the Hub's settings, never a task);
    - the list holds task keys alone, never a definition field or a config key: those are the helpers' to read."""
    pattern = re.compile(r"\b(" + "|".join(ENGINE_KEYS) + r")\b")
    files = hub_side()
    assert len(files) > 60 and HUB / "modules" / "generate_image" / "build.py" in files
    found = sorted({f"{p.relative_to(HUB)}: {m.group(1)}" for p in files for text in strings(p)
                    if (m := pattern.search(text))})
    assert found == []
    assert all(pattern.search(text) for p in KNOWN for text in [p.read_text()]), "a known debt that is paid: drop it"


def test_no_prompt_letter_where_tasks_were_built():
    """The modules and the core's engine lane hold no reference or prompt letter as a value (the core's picture code
    names image modes such as "I" for Pillow, which are not the engine's letters)."""
    lane = [HUB / "core" / n for n in ("api.py", "engine.py", "enginecat.py", "enginelane.py", "enginequery.py",
                                        "plan.py", "clipplan.py")]
    files = [*(p for p in (HUB / "modules").rglob("*.py") if "__pycache__" not in p.parts), *lane]
    found = sorted({f"{p.relative_to(HUB)}: {v!r}" for p in files for v in strings(p) if v in LETTERS})
    assert found == []
