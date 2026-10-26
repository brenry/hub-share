"""The models set up on the engine before the switch come back on the new one, with no question:
the Hub's old pointers and the old engine's own definitions say what each model file is."""
from __future__ import annotations

import json
from pathlib import Path

from hub.core import inherit


def engines(tmp_path: Path) -> tuple[Path, Path]:
    old, new = tmp_path / "hocuspocus" / "app", tmp_path / "hub" / "engine" / "app"
    for d in (old / "defaults", old / "finetunes", new):
        d.mkdir(parents=True)
    (new.parent / inherit.BEFORE).write_text(json.dumps({"engine": {"root": str(old), "python": "/x/python"}}))
    return old, new


def test_old_pointers_and_old_definitions_name_the_owners_files(tmp_path):
    old, new = engines(tmp_path)
    comfy = tmp_path / "shared" / "diffusion_models"
    mine, fork_named, other = (str(comfy / n) for n in ("z_image_turbo_community.safetensors",
                                                        "qwen_image_2.1_bf16.safetensors", "t5xxl_fp16.safetensors"))
    (old / "finetunes" / "auto_z.json").write_text(json.dumps({"model": {
        "hub_auto": True, "hub_file": mine, "hub_base": "z_image", "URLs": [mine]}}))
    (old / "defaults" / "qwen_image_21.json").write_text(json.dumps({"model": {
        "URLs": ["https://hf.co/x/qwen_image_2.1_bf16.safetensors|qwen"]}}))
    (old / "finetunes" / "mine.json").write_text("not json")
    got = inherit.choices(str(new), [mine, fork_named, other], {"z_image", "qwen_image_21_7B"},
                          {"qwen_image_21": "qwen_image_21_7B"})
    assert got == {mine: "z_image", fork_named: "qwen_image_21_7B"}, "under the new engine's ids; t5 unknown"
    assert inherit.choices(str(new), [mine], {"flux2_klein_9b"}, {}) == {}, "a model the new engine lacks: none"


def test_no_switch_record_or_the_same_engine_gives_nothing(tmp_path):
    old, new = engines(tmp_path)
    assert inherit.choices(str(old), ["/a.safetensors"], {"z_image"}, {}) == {}
    (new.parent / inherit.BEFORE).write_text(json.dumps({"engine": {"root": str(new)}}))
    assert inherit.previous_root(str(new)) is None
    (new.parent / inherit.BEFORE).unlink()
    assert inherit.previous_root(str(new)) is None


def test_a_file_seen_through_another_folder_and_the_owners_finetune_of_a_kind(tmp_path):
    """The pointer recorded the file under one folder, the model folders now reach it under another: matched by
    name. A finetune not the Hub's in the old engine (`finetune_1`) stands for the kind it declares."""
    old, new = engines(tmp_path)
    (old / "finetunes" / "auto_krea2_turbo_bf16.json").write_text(json.dumps({"model": {
        "hub_auto": True, "hub_file": "/old/place/krea2_turbo_bf16.safetensors", "hub_base": "krea2_turbo",
        "URLs": ["krea2_turbo_bf16.safetensors"]}}))
    (old / "finetunes" / "finetune_1.json").write_text(json.dumps({"model": {
        "name": "Finetune 1", "architecture": "krea2_raw",
        "URLs": ["/var/models/krea2-raw-1-bf16.safetensors"]}}))
    files = ["/shared/diffusion_models/krea2_turbo_bf16.safetensors",
             "/shared/diffusion_models/krea2-raw-1-bf16.safetensors"]
    got = inherit.choices(str(new), files, {"krea2_turbo", "krea2_raw"}, {})
    assert got == {files[0]: "krea2_turbo", files[1]: "krea2_raw"}


def test_a_file_is_set_up_as_the_model_it_is_named_for_and_never_on_a_tie():
    """Words of three letters or more shared with the engine's model ids and names; the fewest left over wins;
    two models equally best: none."""
    from types import SimpleNamespace
    form = SimpleNamespace(title=lambda d, fb: d.get("name", fb))
    kinds = {i: SimpleNamespace(model_type=i, definition={"name": n}) for i, n in (
        ("krea2_turbo", "Krea 2 Turbo"), ("krea2_turbo_edit", "Krea 2 Turbo Identity Edit v1.2"),
        ("krea2_raw", "Krea 2 RAW"), ("z_image", "Z-Image Turbo 6B"), ("qwen_image_21_7B", "Qwen Image 2.1 7B"))}
    def pick(name):
        found = inherit.by_name(f"/m/{name}.safetensors", kinds, form)
        return found.model_type if found else None
    assert pick("krea2_turbo_bf16") == "krea2_turbo"
    assert pick("krea2-raw-1-bf16") == "krea2_raw"
    assert pick("z_image_turbo_community") == "z_image"
    assert pick("Qwen3-VL-4B-Instruct_vision_bf16") is None, "one shared word: not a model it is named for"
    assert pick("t5xxl_fp16") is None
