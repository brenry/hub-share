"""`install/helpers.py` (config, base-python) and `install/engineargs.py`, in-process or as the installer runs
them."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

INSTALL = Path(__file__).resolve().parents[2] / "install"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"install_{name}", INSTALL / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helpers = load("helpers")


def test_config_drops_secrets_and_old_paths_and_never_names_the_owners_folders(tmp_path):
    old = tmp_path / "old"
    (old / "x").mkdir(parents=True)
    src = old / "wgp_config.json"
    src.write_text(json.dumps({"services": {"k": "S"}, "notification_sound": 1, "enabled_plugins": ["p"],
                               "save_path": str(old / "outputs"), "lora_dir": str(old / "x"), "profile": 3,
                               "attention_mode": "sage2", "loras_root": "loras",
                               "checkpoints_paths": ["ckpts", str(old / "ckpts"), "/shared/diffusion_models"]}))
    out = tmp_path / "cfg.json"
    helpers.config(str(src), str(out), str(old), "/app/outputs")
    assert json.loads(out.read_text()) == {"profile": 3, "attention_mode": "sage2", "enhancer_enabled": 0,
                                           "checkpoints_paths": ["ckpts"],
                                           **dict.fromkeys(helpers.SAVE_KEYS, "/app/outputs")}
    src.write_text(json.dumps({"compile": "transformer", "attention_mode": "sage2"}))
    helpers.config(str(src), str(out), str(old), "/o", other_engine=True)
    assert "compile" not in json.loads(out.read_text()), "another engine's compile choice is left out"
    helpers.config(str(src), str(out), str(old), "/o")
    assert json.loads(out.read_text())["compile"] == "transformer", "the app's own config keeps it"
    assert subprocess.run([sys.executable, "-I", str(INSTALL / "helpers.py"), "config", "-", str(out), "--source",
                           str(old), "--outputs", "/o"]).returncode == 0
    cfg = json.loads(out.read_text())
    assert cfg["transformer_quantization"] == "int8" and cfg["checkpoints_paths"] == ["ckpts"]


def fake_venv(tmp_path: Path) -> tuple[Path, Path]:
    """A venv whose base Python lives outside /usr, like uv's: `base` holds bin/ (a link to this Python) and the
    headers; the venv's `python` links into it."""
    base = tmp_path / "uv" / "cpython-3.x"
    (base / "bin").mkdir(parents=True)
    (base / "include" / "python3.x").mkdir(parents=True)
    (base / "include" / "python3.x" / "Python.h").write_text("")
    real = os.path.realpath(sys.executable)
    (base / "bin" / "python3.x").symlink_to(real)
    env = tmp_path / "env"
    subprocess.run([real, "-m", "venv", "--without-pip", str(env)], check=True)
    for name in os.listdir(env / "bin"):
        if name.startswith("python"):
            (env / "bin" / name).unlink()
            (env / "bin" / name).symlink_to(base / "bin" / "python3.x")
    cfg = (env / "pyvenv.cfg").read_text().splitlines()
    (env / "pyvenv.cfg").write_text("\n".join(f"home = {base / 'bin'}" if c.startswith("home") else c
                                              for c in cfg) + "\n")
    return env, base


def test_base_python_copies_and_repoints_then_undoes(tmp_path):
    env, base = fake_venv(tmp_path)
    links = {n: os.readlink(env / "bin" / n) for n in os.listdir(env / "bin") if n.startswith("python")}
    dest, undo = tmp_path / "engine" / "python", tmp_path / "undo.json"
    said = helpers.base_python(str(env), str(dest), str(undo))
    assert said.startswith("The engine's Python ") and str(dest) in said
    assert all(os.readlink(env / "bin" / n) == str(dest / "bin" / "python3.x") for n in links)
    assert f"home = {dest / 'bin'}" in (env / "pyvenv.cfg").read_text()
    assert "already its own" in helpers.base_python(str(env), str(dest), str(tmp_path / "u2.json"))
    helpers.base_python_undo(str(undo))
    assert {n: os.readlink(env / "bin" / n) for n in links} == links and not dest.exists()
    assert f"home = {base / 'bin'}" in (env / "pyvenv.cfg").read_text()


def test_base_python_leaves_a_system_python_alone(tmp_path):
    env = tmp_path / "env"
    subprocess.run(["/usr/bin/python3", "-m", "venv", "--without-pip", str(env)], check=True)
    assert "left as it is" in helpers.base_python(str(env), str(tmp_path / "p"), str(tmp_path / "u.json"))
    assert not (tmp_path / "p").exists() and not (tmp_path / "u.json").exists()


def test_engineargs_keeps_what_upstreams_parser_takes(tmp_path):
    app = tmp_path / "app"
    (app / "shared").mkdir(parents=True)
    (app / "shared" / "cli_args.py").write_text(
        "import argparse\n\n\ndef parse_wgp_args(config_filename, argv=None):\n    p = argparse.ArgumentParser()\n"
        "    p.add_argument('--attention', default='')\n    p.add_argument('--compile', action='store_true')\n"
        "    return p.parse_args(argv)\n")
    done = subprocess.run([sys.executable, "-I", "-B", str(INSTALL / "engineargs.py"), str(app), "--attention",
                           "sage2", "--lora-dir-hunyuan", "/x", "--compile", "--attention", "nope"],
                          capture_output=True, text=True, cwd=app, check=True)
    assert json.loads(done.stdout) == ["--attention", "sage2", "--compile"]
    assert done.stderr.splitlines() == [
        "Left out of the engine's arguments: --lora-dir-hunyuan /x (upstream does not take it)",
        "Left out of the engine's arguments: --attention nope (upstream does not take it)"]
