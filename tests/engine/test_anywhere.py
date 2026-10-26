"""A file the engine looks for only in a folder named after the model is found by its name anywhere in the
model folders (sorted by kind, not by model); nothing on disk changes."""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

from hub.worker.adapters import anywhere


def engine_locate(roots: list[str]):
    """Upstream's search: `<root>/<file>` for each checkpoint path, `folder/file` kept as it is."""
    def locate_file(file_name, create_path_if_none=False, error_if_none=True, extra_paths=None):
        name = os.path.basename(file_name) if file_name.startswith("http") else file_name
        for root in roots:
            if os.path.isfile(os.path.join(root, name)):
                return os.path.join(root, name)
        if error_if_none:
            raise Exception(f"Unable to locate file '{name}'")
        return None
    return locate_file


def test_a_file_under_another_folder_is_found_by_its_name_and_only_one_of_a_name(tmp_path):
    enc = tmp_path / "shared" / "text_encoders"
    enc.mkdir(parents=True)
    vision = enc / "Qwen3-VL-4B-Instruct_vision_bf16.safetensors"
    vision.write_bytes(b"x")
    roots = [str(tmp_path / "shared")]
    locate = anywhere.wrap(engine_locate(roots), lambda: roots)
    assert locate("Qwen3-VL-4B-Instruct/Qwen3-VL-4B-Instruct_vision_bf16.safetensors") == str(vision.resolve())
    assert locate("https://hf.co/x/Qwen3-VL-4B-Instruct_vision_bf16.safetensors") == str(vision.resolve())
    assert locate("missing.safetensors", error_if_none=False) is None
    (tmp_path / "shared" / "a").mkdir()
    (tmp_path / "shared" / "b").mkdir()
    (tmp_path / "shared" / "a" / "model.safetensors").write_bytes(b"1")
    (tmp_path / "shared" / "b" / "model.safetensors").write_bytes(b"2")
    locate = anywhere.wrap(engine_locate(roots), lambda: roots)
    assert locate("model.safetensors", error_if_none=False) is None, "two files of that name: never a guess"
    assert sorted(os.listdir(enc)) == ["Qwen3-VL-4B-Instruct_vision_bf16.safetensors"], "nothing moved or linked"


def test_install_wraps_the_open_engines_locator_once(tmp_path, monkeypatch):
    fl = types.ModuleType("shared.utils.files_locator")
    fl._checkpoints_paths = [str(tmp_path)]
    fl.locate_file = engine_locate([str(tmp_path)])
    monkeypatch.setitem(sys.modules, "shared.utils.files_locator", fl)
    assert anywhere.install() and anywhere.install()
    assert fl.locate_file.hub_anywhere
    (tmp_path / "deep").mkdir()
    (tmp_path / "deep" / "vae.safetensors").write_bytes(b"v")
    assert fl.locate_file("vae_folder/vae.safetensors") == str((tmp_path / "deep" / "vae.safetensors").resolve())
    assert Path(tmp_path / "deep" / "vae.safetensors").read_bytes() == b"v"


def test_a_models_own_lora_outside_its_lora_folder_is_found_by_name(tmp_path, monkeypatch):
    """Krea 2 Identity Edit's own LoRA sits in a LoRA folder in Settings, not in loras/krea2: found, nothing moved."""
    fl = types.ModuleType("shared.utils.files_locator")
    fl._checkpoints_paths = [str(tmp_path / "models")]
    fl.locate_file = engine_locate([str(tmp_path / "models")])
    monkeypatch.setitem(sys.modules, "shared.utils.files_locator", fl)
    mine = tmp_path / "shared" / "loras" / "krea2_identity_edit_v1_2.safetensors"
    mine.parent.mkdir(parents=True)
    mine.write_bytes(b"l")
    def engine_lora(d, lora):
        return lora if d is None else os.path.join(d, os.path.basename(lora))
    w = types.SimpleNamespace(get_lora_root=lambda: str(tmp_path / "shared" / "loras"), get_lora_local_path=engine_lora)
    assert anywhere.install(w)
    url = "https://huggingface.co/DeepBeepMeep/krea-2/resolve/main/krea2_identity_edit_v1_2.safetensors"
    assert w.get_lora_local_path(str(tmp_path / "shared" / "loras" / "krea2"), url) == str(mine.resolve())
    assert w.get_lora_local_path(None, "x.safetensors") == "x.safetensors"
    assert anywhere.install(w) and w.get_lora_local_path.hub_anywhere
