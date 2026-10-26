"""`install/install-engine.sh` and `uninstall.sh --engine`, on a sandbox with no GPU and no network: a fake
old engine folder with weights, a shared model folder, a fake upstream checkout (a git repo whose commit stands in for
the pin) and a real venv beside the Hub's prefix; `systemctl` is a stub. The switch changes the Hub's engine only: the
model and LoRA folders (in Settings) are never touched; a failure undoes the run."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.engine.helpers import make_engine_root

REPO = Path(__file__).resolve().parents[2]
INSTALL = REPO / "install"
UPSTREAM = "https://github.com/deepbeepmeep/Wan2GP"
CLI_ARGS = '''import argparse


def parse_wgp_args(config_filename, argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--attention", default="")
    parser.add_argument("--profile", default="-1")
    return parser.parse_args(argv)
'''
SYSTEMCTL = ('#!/bin/sh\necho "$@" >> "$(dirname "$0")/systemctl.log"\n'
             'case "$*" in *is-active*) exit 3 ;; esac\nexit 0\n')


def git(app: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(app), *args], check=True, capture_output=True, text=True,
                          env=env).stdout.strip()


@pytest.fixture
def box(tmp_path: Path) -> dict[str, Any]:
    """The old engine folder, the Hub's prefix with its data and an engine made by step 1 (app and env)."""
    old = make_engine_root(tmp_path / "o", "upstream").rename(tmp_path / "old")
    (old / "models").mkdir()
    (old / "models" / "_settings.json").write_text("{}")
    shutil.rmtree(old / "loras")
    for name, data in (("ckpts/main.safetensors", b"m"), ("ckpts/Qwen3-VL/config.json", b"c"),
                       ("loras/wan/style.safetensors", b"l")):
        (old / name).parent.mkdir(parents=True, exist_ok=True)
        (old / name).write_bytes(data)
    (old / "wgp_config.json").write_text(json.dumps({"services": {"api_key": "SECRET"}, "save_path": str(old / "out"),
                                                     "checkpoints_paths": [str(old / "ckpts")], "profile": 4,
                                                     "compile": "transformer"}))
    (old / "finetunes").mkdir()
    (old / "finetunes" / "mine.json").write_text('{"model": {}}')
    (old / "finetunes" / "pointer.json").write_text('{"model": {"hub_auto": true}}')
    prefix = tmp_path / "hub"
    (prefix / "engine").mkdir(parents=True)
    app = make_engine_root(tmp_path / "a", "upstream").rename(prefix / "engine" / "app")
    (app / "wgp_config.json").unlink()                    # a fresh checkout: no config, no LoRA or settings folder
    shutil.rmtree(app / "loras")
    shutil.rmtree(app / "settings")
    (app / "shared" / "cli_args.py").write_text(CLI_ARGS)
    future = "from __future__ import annotations\n"
    planted = future + ("import os as _os\nif _os.path.exists('FAIL_IMPORT'):\n"
                        "    _there = open('FAIL_IMPORT').read().strip()\n"
                        "    if _there:\n        _os.makedirs(_there)\n"
                        "    raise SystemExit('planted')\n")
    (app / "wgp.py").write_text((app / "wgp.py").read_text().replace(future, planted, 1))
    git(app, "init", "-q")
    git(app, "remote", "add", "origin", UPSTREAM)
    git(app, "add", "-A")
    git(app, "commit", "-qm", "upstream")
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(prefix / "engine" / "env")], check=True)
    (prefix / "venv" / "bin").mkdir(parents=True)
    (prefix / "venv" / "bin" / "python").write_text(
        f'#!/bin/bash\nargs=(); for a in "$@"; do [ "$a" = -I ] || args+=("$a"); done\n'
        f'PYTHONPATH={REPO} exec {sys.executable} "${{args[@]}}"\n')
    (prefix / "venv" / "bin" / "python").chmod(0o755)
    (prefix / "hub").symlink_to(REPO / "hub")
    shared = tmp_path / "shared"
    for name in ("diffusion_models/krea2/k.safetensors", "text_encoders/t.safetensors"):
        (shared / name).parent.mkdir(parents=True, exist_ok=True)
        (shared / name).write_bytes(b"s")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "systemctl").write_text(SYSTEMCTL)
    (tools / "systemctl").chmod(0o755)
    data = prefix / "data"
    run([sys.executable, "-m", "hub", "init", "--data", str(data), "--bind", "127.0.0.1", "--engine-root", str(old),
         "--engine-python", str(old / "env" / "bin" / "python"), "--lora-folder", str(old / "loras")], tools)
    s = json.loads((data / "settings.json").read_text())
    s["engine"]["args"] = ["--attention", "sage2", "--lora-dir-wan", "/x"]
    s["engine"]["model_folders"] += [str(shared / "diffusion_models"), str(shared / "text_encoders")]
    (data / "settings.json").write_text(json.dumps(s))
    return {"old": old, "prefix": prefix, "app": app, "data": data, "tools": tools, "shared": shared,
            "pin": git(app, "rev-parse", "--short=7", "HEAD")}


def run(argv: list[str], tools: Path, pin: str = "", check: bool = True) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": f"{tools}:{os.environ['PATH']}", "HUB_INSTALL_TEST": "1", "HUB_ENGINE_PIN": pin,
           "PYTHONPATH": str(REPO)}
    done = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=REPO, timeout=180)
    if check:
        assert done.returncode == 0, done.stdout + done.stderr
    return done


def install(box: dict[str, Any], *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["bash", str(INSTALL / "install-engine.sh"), "--prefix", str(box["prefix"]), *args], box["tools"],
               str(box["pin"]), check)


def uninstall(box: dict[str, Any], *args: str) -> subprocess.CompletedProcess:
    return run(["bash", str(INSTALL / "uninstall.sh"), "--engine", "--prefix", str(box["prefix"]), *args],
               box["tools"], str(box["pin"]))


def tree(root: Path) -> dict[str, tuple[int, int] | None]:
    """Every entry with a file's inode and mtime; the stub's log left out."""
    return {str(p.relative_to(root)): None if p.is_dir() else (p.lstat().st_ino, p.lstat().st_mtime_ns)
            for p in sorted(root.rglob("*")) if not {".git", "__pycache__", "tools"} & set(p.relative_to(root).parts)}


def settings(box: dict[str, Any]) -> dict[str, Any]:
    return json.loads((box["data"] / "settings.json").read_text())


def test_a_dry_run_changes_nothing_and_lists_the_owners_folders(box, tmp_path):
    before = tree(tmp_path)
    done = install(box, "--dry-run")
    assert tree(tmp_path) == before
    out = done.stdout
    assert f"The Hub's engine: {box['old']} -> {box['app']}" in out and "Dry run" in out
    for folder in (box["old"] / "ckpts", box["shared"] / "diffusion_models", box["old"] / "loras"):
        assert f"      {folder}\n" in out
    assert "Left out of the engine's arguments: --lora-dir-wan /x" in done.stderr


def test_the_install_switches_the_engine_and_leaves_every_model_folder(box):
    old, app, shared = box["old"], box["app"], box["shared"]
    (app / "loras").mkdir()                               # upstream made it at its first start (on the server)
    weights = {**tree(old), **{f"shared/{k}": v for k, v in tree(shared).items()}}
    settings_before = settings(box)
    install(box, "--yes")
    assert {**tree(old), **{f"shared/{k}": v for k, v in tree(shared).items()}} == weights
    assert not (app / "ckpts").is_symlink() and not (app / "loras").is_symlink() and (app / "loras").is_dir()
    cfg = json.loads((app / "wgp_config.json").read_text())
    assert "services" not in cfg and "loras_root" not in cfg and cfg["profile"] == 4
    assert "compile" not in cfg, "the old engine's compilation is not carried over"
    assert cfg["checkpoints_paths"] == ["ckpts"], "upstream run by hand never searches (or prunes) the model folders"
    assert cfg["save_path"] == cfg["image_save_path"] == cfg["audio_save_path"] == str(app / "outputs")
    s = settings(box)
    assert (s["engine"]["root"], s["engine"]["python"]) == (str(app), str(box["prefix"] / "engine/env/bin/python"))
    assert s["engine"]["args"] == ["--attention", "sage2"]
    assert s["engine"]["cc"].endswith("gcc") and s["engine"]["cxx"].endswith("g++")
    assert s["engine"]["model_folders"] == settings_before["engine"]["model_folders"]
    assert s["modules"]["loras"] == settings_before["modules"]["loras"]
    before_file = box["prefix"] / "engine" / ".settings-before.json"
    assert json.loads(before_file.read_text())["engine"]["root"] == str(old)
    assert git(app, "status", "--porcelain", "--untracked-files=no") == ""
    assert "Go ahead?" not in install(box).stdout          # a repair: no question, the first undo file kept
    assert json.loads(before_file.read_text())["engine"]["root"] == str(old)
    uninstall(box)
    assert settings(box) == settings_before and not before_file.exists()
    assert not (app / "wgp_config.json").exists() and (app / "loras").is_dir() and app.is_dir()
    assert {**tree(old), **{f"shared/{k}": v for k, v in tree(shared).items()}} == weights


def test_a_failure_undoes_the_run(box, tmp_path):
    app = box["app"]
    settings_before = settings(box)
    (app / "FAIL_IMPORT").write_text("")
    done = install(box, "--yes", check=False)
    assert done.returncode != 0 and "The engine did not start" in done.stderr and "Undone" in done.stdout
    assert not (app / "wgp_config.json").exists() and not (app / "outputs").exists()
    assert not (box["prefix"] / "engine" / ".settings-before.json").exists()
    assert settings(box) == settings_before


def test_a_failed_repair_puts_back_the_settings_it_found(box):
    install(box, "--yes")
    s = settings(box)
    s["engine"]["args"] = ["--attention", "sage"]
    (box["data"] / "settings.json").write_text(json.dumps(s))
    found = settings(box)
    (box["app"] / "FAIL_IMPORT").write_text("")
    assert install(box, check=False).returncode != 0
    assert settings(box) == found
    assert json.loads((box["prefix"] / "engine" / ".settings-before.json").read_text())["engine"]["root"] == str(
        box["old"])


def test_with_no_saved_engine_arguments(box):
    s = settings(box)
    (box["data"] / "settings.json").write_text(json.dumps({**s, "engine": {**s["engine"], "args": []}}))
    install(box, "--yes")
    assert settings(box)["engine"]["args"] == []


def test_the_checks_refuse_in_one_line(box):
    assert "not the tested" in run(["bash", str(INSTALL / "install-engine.sh"), "--prefix", str(box["prefix"])],
                                   box["tools"], "0000000", check=False).stderr
    (box["prefix"] / "engine" / "weights").mkdir()
    done = install(box, "--dry-run", check=False)
    assert done.returncode == 1 and "holds more than the engine: weights" in done.stderr


def test_a_config_it_did_not_make_comes_back_with_the_undo(box):
    app = box["app"]
    (app / "wgp_config.json").write_text('{"mine": 1}')
    install(box, "--yes")
    assert json.loads((app / "wgp_config.json").read_text())["checkpoints_paths"] == ["ckpts"]
    install(box)                                          # a repair keeps the first copy
    uninstall(box)
    assert (app / "wgp_config.json").read_text() == '{"mine": 1}'
    assert not (box["prefix"] / "engine" / ".app-config-before.json").exists()


def test_a_purge_refuses_while_a_settings_folder_is_inside_the_engine(box):
    install(box, "--yes")
    (box["app"] / "ckpts").mkdir()
    s = settings(box)
    s["engine"]["model_folders"].append(str(box["app"] / "ckpts"))
    (box["data"] / "settings.json").write_text(json.dumps(s))
    done = run(["bash", str(INSTALL / "uninstall.sh"), "--engine", "--purge", "--prefix", str(box["prefix"])],
               box["tools"], check=False)
    assert done.returncode == 1 and f"inside the engine: {box['app'] / 'ckpts'}" in done.stderr
    assert (box["app"] / "ckpts").is_dir() and settings(box) == s
