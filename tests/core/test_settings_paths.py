"""Folders edited in Settings: each path rule, with the one line the screen shows."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PIL import Image

from hub import pathrules
from hub import settings as cfg
from hub.core.api import Invalid
from hub.settings_edit import ui_patch
from tests.core.harness import start_hub

TEMP = "That is the Hub's own folder; pick your own folder"


@pytest.fixture
def disk(tmp_path: Path) -> dict[str, Path]:
    engine = tmp_path / "Wan2GP"
    engine.mkdir()
    (engine / "wgp.py").write_text("")
    python = tmp_path / "env" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n")
    python.chmod(0o755)
    for name in ("out", "in", "models", "loras"):
        (tmp_path / name).mkdir()
    (tmp_path / "file.txt").write_text("x")
    folders = {n: tmp_path / n for n in ("out", "in", "models", "loras")}
    return {"base": tmp_path, "engine": engine, "python": python, **folders}


def base(disk: dict[str, Path]) -> dict:
    s = cfg.validate({"engine": {"root": str(disk["engine"]), "python": str(disk["python"]), "args": [],
                                 "model_folders": [str(disk["models"])]},
                      "modules": {"loras": {"folders": [str(disk["loras"])]}}})
    return s


def roots(disk: dict[str, Path]) -> dict[str, str]:
    return {"temp": str(disk["out"]), "inputs": str(disk["in"])}


def refused(disk: dict[str, Path], changes: dict) -> tuple[str, str]:
    with pytest.raises(cfg.SettingsError) as e:
        ui_patch(base(disk), changes, roots(disk))
    return e.value.field, e.value.text


def test_good_edits_apply_and_are_normalised(disk: dict[str, Path]) -> None:
    other = disk["base"] / "elsewhere"
    other.mkdir()
    s = ui_patch(base(disk), {"paths": {"drive": str(other) + "/"}, "engine": {"model_folders": []},
                                  "modules": {"loras": {"folders": [str(disk["loras"]), str(disk["models"])]}}},
                     roots(disk))
    assert s["paths"] == {"drive": str(other), "characters": ""}
    assert s["engine"]["model_folders"] == [], "an empty model folder list is allowed"
    assert s["modules"]["loras"]["folders"] == [str(disk["loras"]), str(disk["models"])]
    s = ui_patch(base(disk), {"engine": {"root": str(disk["engine"]), "python": str(disk["python"])}}, roots(disk))
    assert s["engine"]["root"] == str(disk["engine"])


def test_the_drive_folder(disk: dict[str, Path]) -> None:
    key, field = "drive", "paths.drive"
    assert refused(disk, {"paths": {key: "relative/out"}}) == (field, "Use a full path, starting with /")
    assert refused(disk, {"paths": {key: "~/out"}}) == (field, "Use a full path, starting with /")
    assert refused(disk, {"paths": {key: str(disk["out"]) + "\0x"}}) == (field, "Not a valid path")
    assert refused(disk, {"paths": {key: ""}}) == (field, "Enter a full path")
    assert refused(disk, {"paths": {key: 7}}) == (field, "Enter a full path")
    assert refused(disk, {"paths": {key: str(disk["base"] / "nope")}}) == (field, "Folder not found")
    assert refused(disk, {"paths": {key: str(disk["base"] / "file.txt")}}) == (field, "Not a folder")
    assert refused(disk, {"paths": {key: str(disk["models"] / ".")}}) == (field, "Inside a model folder")
    inner = disk["loras"] / "flux"
    inner.mkdir()
    assert refused(disk, {"paths": {key: str(inner)}}) == (field, "Inside a LoRA folder")
    assert refused(disk, {"paths": {key: str(disk["engine"])}}) == (field, "Inside the engine folder")
    assert refused(disk, {"paths": {key: str(disk["base"])}})[1] == TEMP, "a folder holding the Temp is refused"
    assert refused(disk, {"paths": {key: str(disk["out"] / ".")}})[1] == TEMP
    for old in ("outputs", "inputs", "archive"):
        assert refused(disk, {"paths": {old: str(disk["base"])}})[0] == "paths", "Temp and inputs are not settings"
    assert not (disk["base"] / "nope").exists(), "folders are never created"


def test_the_drive_must_be_writable(disk: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    ro = disk["base"] / "ro"
    ro.mkdir()
    real = os.access
    monkeypatch.setattr(pathrules.os, "access", lambda p, mode: real(p, mode) and not (str(p) == str(ro)
                                                                                      and mode & os.W_OK))
    assert refused(disk, {"paths": {"drive": str(ro)}}) == ("paths.drive", "Not writable")
    assert ui_patch(base(disk), {"modules": {"loras": {"folders": [str(ro)]}}}, roots(disk)), "read is enough"


def test_engine_root_and_python(disk: dict[str, Path]) -> None:
    assert refused(disk, {"engine": {"root": str(disk["models"])}}) == ("engine.root", "No wgp.py in this folder")
    assert refused(disk, {"engine": {"root": "Wan2GP"}}) == ("engine.root", "Use a full path, starting with /")
    assert refused(disk, {"engine": {"root": str(disk["base"] / "gone")}}) == ("engine.root", "Folder not found")
    assert refused(disk, {"engine": {"python": str(disk["base"] / "gone")}}) == ("engine.python", "File not found")
    assert refused(disk, {"engine": {"python": str(disk["base"] / "file.txt")}}) == ("engine.python", "Not a Python")
    assert refused(disk, {"engine": {"python": str(disk["models"])}}) == ("engine.python", "Not a Python")
    assert refused(disk, {"engine": {"python": "python3"}}) == ("engine.python", "Use a full path, starting with /")
    assert refused(disk, {"engine": {"python": "/usr/bin/\0python"}}) == ("engine.python", "Not a valid path")
    assert refused(disk, {"engine": {"args": ["--x"]}})[0] == "engine"


@pytest.mark.parametrize("field, wrap", [
    ("engine.model_folders", lambda v: {"engine": {"model_folders": v}}),
    ("modules.loras.folders", lambda v: {"modules": {"loras": {"folders": v}}}),
])
def test_folder_lists(disk: dict[str, Path], field: str, wrap, monkeypatch: pytest.MonkeyPatch) -> None:
    good = str(disk["models"])
    assert refused(disk, wrap("x")) == (field, "Up to 32 folders")
    assert refused(disk, wrap([good] * 33)) == (field, "Up to 32 folders")
    assert refused(disk, wrap([good, "rel/x"])) == (f"{field}[1]", "Use a full path, starting with /")
    assert refused(disk, wrap([good, str(disk["base"] / "gone")])) == (f"{field}[1]", "Folder not found")
    assert refused(disk, wrap([str(disk["base"] / "file.txt")])) == (f"{field}[0]", "Not a folder")
    assert refused(disk, wrap([good, good + "/"])) == (f"{field}[1]", "Already listed")
    assert refused(disk, wrap(["/a\0b"])) == (f"{field}[0]", "Not a valid path")
    assert refused(disk, wrap([str(disk["out"])])) == (f"{field}[0]", "Overlaps the Temp folder")
    assert refused(disk, wrap([str(disk["base"])])) == (f"{field}[0]", "Overlaps the Temp folder")
    real = os.access
    monkeypatch.setattr(pathrules.os, "access", lambda p, mode: real(p, mode) and str(p) != good)
    assert refused(disk, wrap([good])) == (f"{field}[0]", "Not readable")


def test_only_folders_lists_change_under_modules(disk: dict[str, Path]) -> None:
    assert refused(disk, {"modules": {"loras": {"folders": [], "x": 1}}})[0] == "modules.loras"
    assert refused(disk, {"modules": {"loras": []}})[0] == "modules.loras"
    assert refused(disk, {"modules": {"assistant": {}}})[0] == "modules"


def test_paths_in_settings_json_are_checked_for_type_only() -> None:
    assert cfg.validate({})["paths"] == {"drive": "", "characters": ""}
    with pytest.raises(cfg.SettingsError) as e:
        cfg.validate({"paths": {"drive": 3}})
    assert e.value.field == "paths.drive"
    with pytest.raises(cfg.SettingsError) as e:
        cfg.validate({"paths": {"characters": ["/x"]}})
    assert e.value.field == "paths.characters"
    assert cfg.characters_root(cfg.validate({})) is None
    assert cfg.characters_root(cfg.validate({"paths": {"characters": "/srv/Cast"}})) == Path("/srv/Cast")
    assert cfg.drive_root(cfg.validate({})) is None
    assert cfg.drive_root(cfg.validate({"paths": {"drive": "/srv/Drive"}})) == Path("/srv/Drive")
    old = cfg.validate({"paths": {"outputs": "/x", "inputs": "/y", "archive": "/z"}})
    assert old["paths"] == {"drive": "", "characters": ""}, \
        "the old Temp, inputs and archive settings are dropped when read"


def test_the_characters_folder(disk: dict[str, Path]) -> None:
    """The same rules as the Drive (writable, not the Hub's own, outside the engine, model and LoRA folders), but
    "" sets it back to none."""
    field = "paths.characters"
    cast = disk["base"] / "Characters"
    cast.mkdir()
    s = ui_patch(base(disk), {"paths": {"characters": str(cast) + "/"}}, roots(disk))
    assert s["paths"] == {"drive": "", "characters": str(cast)}
    assert cfg.characters_root(s) == cast
    cleared = ui_patch(s, {"paths": {"characters": ""}}, roots(disk))
    assert cleared["paths"]["characters"] == "" and cfg.characters_root(cleared) is None
    assert refused(disk, {"paths": {"characters": "relative/x"}}) == (field, "Use a full path, starting with /")
    assert refused(disk, {"paths": {"characters": 7}}) == (field, "Enter a full path")
    assert refused(disk, {"paths": {"characters": str(disk["base"] / "nope")}}) == (field, "Folder not found")
    assert refused(disk, {"paths": {"characters": str(disk["out"])}}) == (field, TEMP)
    assert refused(disk, {"paths": {"characters": str(disk["base"])}}) == (field, TEMP), "a folder holding the Temp"
    inner = disk["loras"] / "people"
    inner.mkdir()
    assert refused(disk, {"paths": {"characters": str(inner)}}) == (field, "Inside a LoRA folder")
    assert refused(disk, {"paths": {"characters": str(disk["models"])}}) == (field, "Inside a model folder")
    assert refused(disk, {"paths": {"characters": str(disk["engine"])}}) == (field, "Inside the engine folder")


def test_the_characters_folder_must_be_writable(disk: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    ro = disk["base"] / "ro"
    ro.mkdir()
    real = os.access
    monkeypatch.setattr(pathrules.os, "access", lambda p, mode: real(p, mode) and not (str(p) == str(ro)
                                                                                      and mode & os.W_OK))
    assert refused(disk, {"paths": {"characters": str(ro)}}) == ("paths.characters", "Not writable")


def test_a_folder_list_may_not_overlap_the_characters_folder(disk: dict[str, Path]) -> None:
    cast = disk["base"] / "Characters"
    (cast / "loras").mkdir(parents=True)
    with pytest.raises(cfg.SettingsError) as e:
        ui_patch(base(disk), {"modules": {"loras": {"folders": [str(cast / "loras")]}}},
                     {**roots(disk), "characters": str(cast)})
    assert (e.value.field, e.value.text) == ("modules.loras.folders[0]", "Overlaps the Characters folder")
    with pytest.raises(cfg.SettingsError) as e:
        ui_patch(base(disk), {"paths": {"characters": str(cast)},
                                  "engine": {"model_folders": [str(cast / "loras")]}}, roots(disk))
    assert (e.value.field, e.value.text) == ("paths.characters", "Inside a model folder"), \
        "the model folders set in the same edit count"
    assert ui_patch(base(disk), {"modules": {"loras": {"folders": [str(disk["loras"])]}}},
                        {**roots(disk), "characters": ""}), "no Characters folder: nothing to overlap"


async def test_the_characters_folder_applies_live(tmp_path: Path) -> None:
    """Core.update_settings: Files follows at once (listing, ids), the settings view names the folder, the Hub's own
    data folder and a LoRA folder are refused with nothing changed, and "" sets it back to none."""
    loras = tmp_path / "loras"
    (loras / "people").mkdir(parents=True)
    cast = tmp_path / "Characters"
    cast.mkdir()
    Image.new("RGB", (4, 4)).save(cast / "Character 42.png")
    hub = await start_hub(tmp_path / "data", settings={"modules": {"loras": {"folders": [str(loras)]}}})
    core = hub.core
    try:
        assert "chars" not in core.files.roots and core.settings_view()["characters"] == ""
        await core.update_settings({"paths": {"characters": str(cast)}})
        assert core.files.roots["chars"] == cast and core.settings["paths"]["characters"] == str(cast)
        assert core.settings_view()["characters"] == str(cast)
        assert core.files.characters() == [{"name": "Character 42", "id": "chars/Character 42.png", "notes": "",
                                              "voice": "", "sample": False, "views": []}]
        assert core.files.existing_image("chars/Character 42.png") == cast / "Character 42.png"
        assert json.loads((tmp_path / "data" / "settings.json").read_text())["paths"]["characters"] == str(cast)
        inside = tmp_path / "data" / "mine"
        inside.mkdir()
        for bad, text in ((inside, TEMP), (tmp_path / "data", TEMP), (loras / "people", "Inside a LoRA folder")):
            with pytest.raises(Invalid) as e:
                await core.update_settings({"paths": {"characters": str(bad)}})
            assert (e.value.field, e.value.text) == ("paths.characters", text), bad
            assert core.files.roots["chars"] == cast, "a refused edit changes nothing"
        await core.update_settings({"paths": {"characters": ""}})
        assert "chars" not in core.files.roots and core.settings_view()["characters"] == ""
        assert core.files.characters() == [] and core.settings["paths"]["characters"] == ""
    finally:
        await hub.close()
