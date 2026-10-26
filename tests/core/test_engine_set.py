"""`hub engine set|restore|clear` (`hub/engineset.py`, Stage 10): the engine installer's change of the settings. The
model and LoRA folders are the Settings screen's: a switch of engine never changes them."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from hub import engineset, pathrules, settings, settings_edit
from tests.core.test_cli import hub_cli


@pytest.fixture
def world(tmp_path: Path) -> dict[str, Path]:
    old, prefix = tmp_path / "old", tmp_path / "hub"
    for d in (old / "ckpts" / "wan", old / "loras", old / "env" / "bin", prefix / "engine" / "app",
              prefix / "engine" / "env" / "bin", tmp_path / "elsewhere"):
        d.mkdir(parents=True)
    for py in (old / "env" / "bin" / "python", prefix / "engine" / "env" / "bin" / "python", tmp_path / "cc"):
        py.write_text("#!/bin/sh\n")
        py.chmod(0o755)
    for root in (old, prefix / "engine" / "app"):
        (root / "wgp.py").write_text("")
    return {"old": old, "prefix": prefix, "app": prefix / "engine" / "app",
            "py": prefix / "engine" / "env" / "bin" / "python", "cc": tmp_path / "cc",
            "elsewhere": tmp_path / "elsewhere"}


def old_settings(w: dict[str, Path]) -> dict:
    s = settings.validate({})
    s["engine"].update(root=str(w["old"]), python=str(w["old"] / "env/bin/python"), args=["--attention", "sage"],
                       model_folders=[str(w["old"] / "ckpts"), str(w["old"] / "ckpts" / "wan"), str(w["elsewhere"])])
    s["modules"]["loras"] = {"folders": [str(w["old"] / "loras")]}
    return settings.validate(s)


def test_set_points_the_hub_at_the_new_engine_and_leaves_the_owners_folders(world):
    s = old_settings(world)
    new = engineset.engine_set(s, root=str(world["app"]), python=str(world["py"]), cc=str(world["cc"]),
                               cxx=str(world["cc"]), engine_args=["--attention", "sage2"])
    eng = new["engine"]
    assert (eng["root"], eng["python"], eng["cc"], eng["cxx"], eng["args"]) == (
        str(world["app"]), str(world["py"]), str(world["cc"]), str(world["cc"]), ["--attention", "sage2"])
    assert eng["model_folders"] == s["engine"]["model_folders"], "the saved folders, even in the old engine's folder"
    assert new["modules"]["loras"] == s["modules"]["loras"]
    assert engineset.engine_set(s, root=str(world["app"]), python=str(world["py"]))["engine"]["args"] == [
        "--attention", "sage"], "no --args: the saved ones stay"
    assert engineset.before(s)["engine"]["root"] == str(world["old"])
    new["engine"]["model_folders"] = [str(world["elsewhere"])]          # the folders edited meanwhile
    back = engineset.restore(new, engineset.before(s))
    assert {**back["engine"], "model_folders": s["engine"]["model_folders"]} == s["engine"]
    assert back["engine"]["model_folders"] == [str(world["elsewhere"])], "the folders as they are now"
    cleared = engineset.clear(new)
    assert (cleared["engine"]["root"], cleared["engine"]["python"], cleared["engine"]["cc"]) == ("", "", "")
    assert cleared["engine"]["model_folders"] == [str(world["elsewhere"])]


def test_set_refuses_a_compiler_that_is_not_a_full_path(world):
    s = old_settings(world)
    with pytest.raises(pathrules.Refused) as err:
        engineset.engine_set(s, root=str(world["app"]), python=str(world["py"]), cc="gcc")
    assert err.value.field == "engine.cc"
    with pytest.raises(settings.SettingsError):
        settings.validate({**s, "engine": {**s["engine"], "cxx": "g++"}})


def test_the_settings_screen_takes_folders_inside_the_old_engine(world):
    s = old_settings(world)
    s["engine"].update(root=str(world["app"]), model_folders=[], python=str(world["py"]))
    done = settings_edit.ui_patch(s, {"engine": {"model_folders": [str(world["old"] / "ckpts")]},
                                      "modules": {"loras": {"folders": [str(world["old"] / "loras")]}}})
    assert done


def test_the_cli_writes_the_before_file_and_puts_it_back(world, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    settings.save(data, old_settings(world))
    before = tmp_path / "before.json"
    r = hub_cli("engine", "set", "--data", str(data), "--root", str(world["app"]), "--python", str(world["py"]),
                "--before", str(before), "--args", '["--attention", "sage2"]')
    assert r.returncode == 0, r.stderr
    saved = settings.load(data)
    assert saved["engine"]["root"] == str(world["app"]) and saved["engine"]["args"] == ["--attention", "sage2"]
    assert json.loads(before.read_text())["engine"]["root"] == str(world["old"])
    assert oct(os.stat(before).st_mode & 0o777) == "0o600"
    assert saved["engine"]["model_folders"] == old_settings(world)["engine"]["model_folders"]
    r = hub_cli("engine", "set", "--data", str(data), "--root", str(world["elsewhere"]), "--python", str(world["py"]))
    assert r.returncode == 1 and r.stderr.startswith("hub: engine.root: ")
    assert hub_cli("engine", "restore", "--data", str(data), "--before", str(before)).returncode == 0
    assert settings.load(data)["engine"]["root"] == str(world["old"])
    assert hub_cli("engine", "clear", "--data", str(data)).returncode == 0
    assert settings.load(data)["engine"]["root"] == ""


def test_init_without_an_engine_and_with_a_linked_checkpoint_folder(tmp_path):
    data = tmp_path / "data"
    r = hub_cli("init", "--data", str(data), "--bind", "127.0.0.1")
    assert r.returncode == 0, r.stderr
    assert settings.load(data)["engine"]["root"] == ""
    app, weights = tmp_path / "engine" / "app", tmp_path / "shared" / "ckpts"
    app.mkdir(parents=True)
    weights.mkdir(parents=True)
    (app / "ckpts").symlink_to("../../shared/ckpts")
    r = hub_cli("init", "--data", str(tmp_path / "d2"), "--bind", "127.0.0.1", "--engine-root", str(app),
                "--engine-python", "/usr/bin/false")
    assert r.returncode == 0, r.stderr
    assert settings.load(tmp_path / "d2")["engine"]["model_folders"] == [str(weights)], "the folder, never the link"
    assert hub_cli("init", "--data", str(tmp_path / "d3"), "--bind", "127.0.0.1", "--engine-root",
                   str(app)).returncode != 0
