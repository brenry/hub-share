"""`main.py --dump-engine`: the engine's own facts in one file, read-only and sterile. The fake root sits under a
folder with a marker word, its config holds a secret, notification keys and save paths, and `finetunes/` holds an
owner definition and a Hub pointer: none of it may reach the file."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.engine.helpers import ENGINE_PYTHON, WORKER, make_engine_root, snapshot

MARKER = "zebrawombat"
SECRET = "hushhush-4471"
URL_KEYS = ("URLs", "preload_URLs", "loras")


def owner_root(tmp_path: Path, flavour: str) -> Path:
    base = tmp_path / f"home-of-{MARKER}"
    base.mkdir()
    root = make_engine_root(base, flavour)
    (root / "wgp_config.json").write_text(json.dumps({
        "services": {"api_key": SECRET}, "notification_sound_enabled": 1, "notification_url": f"https://{MARKER}.lan",
        "save_path": str(base / f"{MARKER}-videos"), "image_save_path": str(base / f"{MARKER}-images"),
        "checkpoints_paths": ["ckpts", str(base / f"{MARKER}-models")], "last_model_type": "z_image"}))
    (root / "finetunes").mkdir()
    (root / "finetunes" / f"{MARKER}_mix.json").write_text(json.dumps({"model": {
        "name": f"{MARKER} mix", "description": "not the Hub's", "architecture": "z_image",
        "URLs": [str(base / f"{MARKER}-models" / f"{MARKER}.safetensors")]}, "num_inference_steps": 9}))
    (root / "finetunes" / "auto_pointer.json").write_text(json.dumps({"model": {
        "name": "Pointer", "description": "the Hub's", "architecture": "z_image", "hub_auto": True,
        "hub_base": "z_image", "URLs": [str(base / f"{MARKER}-models" / "pointer.safetensors")]}}))
    return root


def dump(root: Path, out: Path, *extra: str, tmp: Path | None = None, argv: list[str] | None = None,
         ) -> subprocess.CompletedProcess:
    env = {**os.environ, "TMPDIR": str(tmp)} if tmp else None
    return subprocess.run([*(argv or [ENGINE_PYTHON, "-B", str(WORKER)]), "--root", str(root), "--dump-engine",
                           str(out), *extra], capture_output=True, text=True, timeout=60, env=env)


@pytest.fixture(scope="module", params=("legacy", "upstream"))
def done(request, tmp_path_factory) -> dict:
    tmp_path = tmp_path_factory.mktemp(request.param)
    root, tmp = owner_root(tmp_path, request.param), tmp_path / "tmp"
    tmp.mkdir()
    before = snapshot(root)
    out = tmp_path / "out" / "engine.json"
    out.parent.mkdir()
    result = dump(root, out, tmp=tmp)
    return {"flavour": request.param, "root": root, "tmp": tmp, "before": before, "after": snapshot(root),
            "result": result, "out": out, "text": out.read_text() if out.is_file() else "", "base": tmp_path}


def test_the_dump_writes_one_json_file_and_nothing_else(done):
    result = done["result"]
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert done["after"] == done["before"], "the engine root is untouched"
    assert list(done["tmp"].iterdir()) == [], "the temp state folder is gone"
    assert sorted(p.name for p in done["out"].parent.iterdir()) == ["engine.json"]
    data = json.loads(done["text"])
    assert data["format"] == 1 and data["engine"]["flavour"] == done["flavour"]
    assert done["text"] == json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n", "sorted, indent 1"


def test_the_dump_is_sterile(done):
    text, data = done["text"], json.loads(done["text"])
    for word in (MARKER, SECRET, str(done["base"]), os.path.realpath(done["base"]), "/tmp/", "hub-engine-"):
        assert word.lower() not in text.lower(), word
    assert data["left_out"] == {"finetunes": 1, "hub_auto": 1, "unreadable": []}
    assert "auto_pointer" not in text and "Pointer" not in text
    assert "services" in data["config_keys"]["file"] and "notification_url" in data["config_keys"]["file"]
    assert "save_path" in data["config_keys"]["memory"], "names only"
    shipped = {p.stem for p in (Path(done["root"]) / "defaults").glob("*.json")}
    assert set(data["models"]) == shipped == {m["id"] for m in data["catalog"]["models"]} | {"krea2_hidden", "t2v",
                                                                                               "minimax_h3_legacy"}


def urls(value, under: bool = False):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from urls(v, under or k in URL_KEYS or k.endswith("_URLs"))
    elif isinstance(value, list):
        for v in value:
            yield from urls(v, under)
    elif isinstance(value, str) and under:
        yield value


def test_the_dump_has_the_shape_the_rebuild_reads(done):
    data = json.loads(done["text"])
    upstream = done["flavour"] == "upstream"
    definitions = [m["definition"] for m in data["models"].values()]
    assert all("path" not in d for d in definitions)
    names = list(urls(definitions))
    assert names and all("/" not in n and "\\" not in n and ":" not in n for n in names), "base names only"
    assert "flux-2-klein-9b.safetensors" in names
    switch = [p for p in data["generate_video"] if p["name"].endswith("_multi_window")]
    assert [(p["kind"], p["default"]) for p in switch] == [("POSITIONAL_OR_KEYWORD", True)]
    assert data["generate_video"][0] == {"name": "task", "kind": "POSITIONAL_OR_KEYWORD", "default": "<required>"}
    probe = data["names"]["probe"]
    assert (probe["get_factory_settings"], probe["get_lora_search_dirs"]) == (upstream, not upstream)
    assert probe["list_model_defs"] is upstream and probe["wan_model"] and probe["_get_dropdown_deps"]
    assert "submit_task" in data["names"]["session"] and "get_local_model_filename" in data["names"]["dropdown_deps"]
    assert data["classes"]["ProgressUpdate"]["fields"] == ["phase", "status", "progress", "current_step",
                                                           "total_steps"]
    assert data["families"]["flux2"] == [10, "Flux 2"] and data["primary_settings"]["num_inference_steps"] == 30
    assert {"model_type", "prompt", "postprocess_audio"} <= set(data["accepted_settings"]), "what a task may hold"
    klein = data["models"]["flux2_klein_9b"]
    assert (klein["architecture"], klein["family"], klein["lora_key"]) == ("flux2_klein_9b", "flux2", "flux2_klein_9b")
    assert klein["settings"]["num_inference_steps"] == 4 and klein["factory"]["num_inference_steps"] == 4
    assert data["models"]["qwen_image_21_7B"]["lora_key"] == "qwen21"
    assert data["handlers"]["flux2_klein_9b"]["get_lora_dir"] == (
        ["base_model_type"] if upstream else ["base_model_type", "args", "lora_root"])
    cat = data["catalog"]
    assert set(cat) == {"engine", "models"} and set(cat["engine"]) == {"api", "version", "settings_version"}
    for entry in cat["models"]:
        assert not {"status", "lora_dirs"} & set(entry) and "text_encoders_found" not in (entry["video"] or {})
    clips = {m["id"]: m["video"]["one_pass"] for m in cat["models"] if m["kind"] == "video"}
    assert clips and all(v == {switch[0]["name"]: False} for v in clips.values()), "the one-pass answer"


LEAKY = """import sys
sys.path.insert(0, sys.argv[1])
import enginedump, main
real = enginedump.redact
def leaky(doc, root):
    out = real(doc, root)
    out["models"]["z_image"]["definition"]["extra"] = doc["models"]["z_image"]["definition"]["extra"]
    return out
enginedump.redact = leaky
sys.exit(main.main(sys.argv[2:]))
"""


def test_the_belt_refuses_a_path_the_rules_miss(tmp_path):
    root = make_engine_root(tmp_path)
    path = root / "defaults" / "z_image.json"
    planted = str(root / "deep" / "inside.bin")
    spec = json.loads(path.read_text())
    spec["model"]["extra"] = {"nested": [{"file": planted}]}
    path.write_text(json.dumps(spec))
    out = tmp_path / "engine.json"
    result = dump(root, out, argv=[ENGINE_PYTHON, "-B", "-c", LEAKY, str(WORKER.parent)])
    assert result.returncode == 1 and result.stdout == ""
    assert result.stderr.splitlines() == ["The engine dump was not written: a folder or host name is left at "
                                          "/models/z_image/definition/extra/nested/0/file"]
    assert planted not in result.stderr and str(root) not in result.stderr, "the pointer, never the value"
    assert not out.exists() and not Path(f"{out}.tmp").exists()
    plain = dump(root, out)                                       # the rules alone take it out
    assert plain.returncode == 0 and planted not in out.read_text() and '"file": "<path>"' in out.read_text()


def test_owner_folders_are_refused_and_a_broken_engine_writes_nothing(tmp_path):
    root, out = make_engine_root(tmp_path), tmp_path / "engine.json"
    for extra in (["--models", str(tmp_path)], ["--profile", "4"], ["--dump-catalog", str(tmp_path / "c.json")]):
        result = dump(root, out, *extra)
        assert result.returncode == 2 and "--dump-engine" in result.stderr, extra
    (root / "fake_engine.json").unlink()
    result = dump(root, out)
    assert result.returncode == 1 and result.stdout == ""
    assert len(result.stderr.splitlines()) == 1 and result.stderr.startswith("The engine could not start:")
    assert not out.exists() and not Path(f"{out}.tmp").exists()
