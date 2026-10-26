"""Upstream's weight files found before it would fetch one (`adapters/upstream_weights.py`, Stage 10; architect note
§6): the files a model lacks by upstream's own presence calls and the facts file's companions, `--check-weights` on the
fake's upstream 18.05 root, and the guard that turns any fetch into one line."""
from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pytest

from hub.worker.adapters import upstream, upstream_weights
from hub.worker.faults import Refused
from tests.engine.helpers import ENGINE_PYTHON, WORKER, make_engine_root, snapshot

SPEECH, PRUNED = "minimax_h3_tts_ref2va_pruned", "minimax_h3_fl2va_pruned"


def check(root: Path, *extra: str) -> list[str]:
    done = subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--check-weights", *extra],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and done.stderr == "", done.stderr
    return done.stdout.splitlines()


def test_check_weights_names_what_upstream_would_fetch(tmp_path):
    root = make_engine_root(tmp_path, "upstream", h3=True)
    before = snapshot(root)
    whisper = upstream.facts_file()["companions"]["models"][SPEECH]
    assert whisper == ["whisper_medium/config.json", "whisper_medium/model.safetensors"]
    assert check(root, "--model", SPEECH) == [f"{p} ({SPEECH})" for p in whisper]
    assert check(root, "--model", PRUNED) == []
    assert check(root, "--model", "minimax_h3_fl2va_pdd") == ["minimax_h3_fl2va_pdd_8step_lora_bf16.safetensors "
                                                              "(minimax_h3_fl2va_pdd)"], "a model's own LoRA"
    assert check(root, "--model", "krea2_turbo_edit") == ["krea2_turbo_edit_bf16.safetensors (krea2_turbo_edit)"]
    assert snapshot(root) == before, "reads only"
    for path in whisper:
        (root / "ckpts" / path).parent.mkdir(parents=True, exist_ok=True)
        (root / "ckpts" / path).write_bytes(b"w")
    assert check(root, "--model", SPEECH) == []
    assert not (root / "network").exists()


class Deps:
    def __init__(self, here: set[str]) -> None:
        self.here = here

    def get_lora_dir(self, model_type: str) -> str:
        return "/loras/m"

    def get_local_model_filename(self, name: str, lora_dir: str | None = None) -> str | None:
        return name if name in self.here else None


def stub_engine(monkeypatch, here: set[str], bundles: list[dict]) -> types.SimpleNamespace:
    menus = types.SimpleNamespace(
        get_missing_core_file_entries_for_status=lambda deps, m: [{"filename": "https://h/x/main.safetensors"}],
        get_expected_secondary_file_entries_for_status=lambda deps, m: [
            {"filename": "vae.safetensors"}, {"filename": "pre.safetensors"}, {"path": "/loras/m/turbo.safetensors"}])
    handler = types.SimpleNamespace(query_model_files=lambda compute, base, model_def: bundles)
    download = types.ModuleType("shared.utils.download")
    download.download_def_missing_files = lambda defs: [p for d in defs for f in d["fileList"][0]
                                                        if (p := f"{d['sourceFolderList'][0]}/{f}") not in here]
    locator = types.ModuleType("shared.utils.files_locator")
    locator.locate_file = lambda path, error_if_none=True: path if path in here else None
    monkeypatch.setitem(sys.modules, "shared.utils.download", download)
    monkeypatch.setitem(sys.modules, "shared.utils.files_locator", locator)
    return types.SimpleNamespace(_get_dropdown_deps=lambda: Deps(here), model_dropdowns=menus,
                                 get_model_def=lambda m: {}, get_base_model_type=lambda m: "arch",
                                 get_model_handler=lambda m: handler)


def test_lacking_lists_core_secondary_bundles_and_companions_once(monkeypatch):
    bundles = [{"repoId": "r", "sourceFolderList": ["minimax_h3"], "fileList": [["vae_int8.safetensors", "up.bin"]]}]
    w = stub_engine(monkeypatch, {"pre.safetensors", "minimax_h3/up.bin", "c/a"}, bundles)
    got = upstream_weights.lacking(w, "m", {"m": ["c/a", "c/b"], "arch": ["c/b", "c/c"]})
    assert got == ["main.safetensors", "vae.safetensors", "turbo.safetensors", "minimax_h3/vae_int8.safetensors",
                   "c/b", "c/c"]
    assert upstream_weights.lacking(w, None, {"m": ["c/b"]}) == [], "upstream has no list every model needs"


def test_the_guard_turns_every_fetch_into_one_line(monkeypatch):
    modules = {"shared.utils.download": ("_hf_download",), "huggingface_hub": ("hf_hub_download", "snapshot_download"),
               "huggingface_hub.file_download": ("http_get",)}
    for name, calls in modules.items():
        module = types.ModuleType(name)
        for call in calls:
            setattr(module, call, lambda *a, **k: "fetched")
        monkeypatch.setitem(sys.modules, name, module)
    assert len(upstream_weights.guard()) == 4
    cases = [(sys.modules["shared.utils.download"]._hf_download, (), {"repo_id": "r", "filename": "a/b.safetensors"},
              "b.safetensors"),
             (sys.modules["huggingface_hub"].snapshot_download, (), {"repo_id": "r", "allow_patterns": "whisper/*"},
              "whisper"),
             (sys.modules["huggingface_hub.file_download"].http_get, ("https://x/y.bin", None),
              {"displayed_filename": "y.bin"}, "y.bin"),
             (sys.modules["huggingface_hub"].hf_hub_download, ("repo",), {}, "repo")]
    for call, args, kwargs, name in cases:
        with pytest.raises(Refused) as err:
            call(*args, **kwargs)
        assert str(err.value) == upstream_weights.LACKS.format(name)


def test_the_fork_sets_nothing_once_open():
    from hub.worker.adapters import fork
    assert fork.Fork.opened(object()) is None


def test_lacking_queries_the_definition_the_load_resolves(monkeypatch):
    """Upstream resolves an "Auto" choice at load (H3's Video VAE: int8 when the transformer runs int8) and fetches
    the resolved definition's files; the check must name the same file (the first H3 clip on the engine)."""
    seen: list[tuple[dict, dict]] = []

    def resolve(model_def, context):
        seen.append((model_def, context))
        vae = "minimax_h3/vae_int8.safetensors" if context["transformer_quantization"] == "int8" else "vae_fp16.st"
        return {**model_def, "video_vae_file": vae}

    def query(compute, base, model_def):
        name = model_def.get("video_vae_file", "vae_fp16.st")
        folder, _, file = name.rpartition("/")
        return [{"repoId": "r", "sourceFolderList": [folder], "fileList": [[file]]}]

    w = stub_engine(monkeypatch, {"main.safetensors", "vae.safetensors", "pre.safetensors", "/vae_fp16.st"}, [])
    handler = types.SimpleNamespace(query_model_files=query, resolve_runtime_model_def=resolve)
    w.get_model_handler = lambda m: handler
    w.server_config = {"mixed_precision": "1", "profile": 4}
    w.transformer_quantization, w.text_encoder_quantization = "int8", "bf16"
    got = upstream_weights.lacking(w, "m", {})
    assert "minimax_h3/vae_int8.safetensors" in got
    assert seen[0][1] == {"mixed_precision": "1", "profile": 4, "transformer_quantization": "int8",
                          "text_encoder_quantization": "bf16", "vae_precision": "16"}
    w.transformer_quantization = "bf16"
    assert "minimax_h3/vae_int8.safetensors" not in upstream_weights.lacking(w, "m", {})
    del handler.resolve_runtime_model_def
    assert "minimax_h3/vae_int8.safetensors" not in upstream_weights.lacking(w, "m", {}), "no resolver: as defined"
