"""Each model's own files, chosen from the model folders. The real worker runs on the fake engine
(upstream 18.05's H3 line and Qwen Image 2.1 from the capture): the engine lists each model's parts that
name a file and where it found each; a choice is a small `finetunes/<model id>.json` the engine merges over its own
definition (wgp.py `refresh_model_defs`), holding only the chosen parts and, under `hub_files`, what each was. No
weight file is copied, moved, renamed or linked; putting every part back removes the file."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from hub.core import engine
from hub.core.api import Invalid
from hub.modules.generate_image import modelfiles as routes
from hub.worker import definitions
from hub.worker.adapters import modelfiles, pointers
from tests.engine.helpers import ENGINE_PYTHON, FakeCtx, FakeRequest, make_engine_root
from tests.engine.test_autoreg import generate
from tests.engine.test_engine_lane import Probes

H3 = "minimax_h3_fl2va"


@pytest.fixture
async def lane(tmp_path):
    root = make_engine_root(tmp_path, "upstream", h3=True)
    settings = {"engine": {"python": ENGINE_PYTHON, "root": str(root), "args": [], "model_folders": []},
                "gpus": [{"id": "gpu0", "index": 0, "uuid": "GPU-a", "engine": True}], "diagnostics": False}
    lane, _ = engine.create(settings, tmp_path / "data", Probes(None))
    yield lane
    await lane.stop()


def mine(tmp_path: Path, name: str) -> str:
    """A file in a model folder of its own (a ComfyUI one, say), under its own name."""
    path = tmp_path / "comfyui" / "models" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"weights")
    return str(path)


def part(files: dict[str, Any], model: str, name: str) -> dict[str, Any]:
    return next(p for p in files[model] if p["part"] == name)


def override(lane, model: str) -> Path:
    return Path(lane.engine["root"]) / "finetunes" / f"{model}.json"


async def test_every_model_lists_its_parts_and_where_each_was_found(lane):
    files = await lane.query("files")
    ids = {m["id"] for m in (await lane.query("models"))["models"]}
    assert set(files) == ids, "every model, a missing one too: its files may be there under other names"
    assert [p["part"] for p in files[H3]][:4] == ["URLs", "text_encoder_URLs", "video_vae_file", "audio_vae_file"]
    main = part(files, H3, "URLs")
    assert main["name"] == "MiniMax-H3-FL2VA_bf16.safetensors" and os.path.isfile(main["path"])
    assert part(files, H3, "video_vae_file")["label"] == "Video VAE"
    assert not any(p["chosen"] for ps in files.values() for p in ps)
    assert part(files, "z_image", "URLs")["path"] is None


async def test_a_part_points_at_the_owners_file_and_back(lane, tmp_path):
    vae = mine(tmp_path, "h3_video_vae_int8_comfy.safetensors")
    files = await lane.query("files", choose=(H3, "video_vae_file", vae))
    chosen = part(files, H3, "video_vae_file")
    assert (chosen["chosen"], chosen["name"], chosen["path"]) == (True, "h3_video_vae_int8_comfy.safetensors", vae)
    assert json.loads(override(lane, H3).read_text()) == {"model": {"hub_files": {"video_vae_file": None},
                                                                   "video_vae_file": vae}}
    model = next(m for m in (await lane.query("models"))["models"] if m["id"] == H3)
    assert model["name"] and model["status"] != "missing", "the engine's own definition, with one part changed"
    assert Path(vae).read_bytes() == b"weights" and os.listdir(Path(vae).parent) == [Path(vae).name]

    encoder = mine(tmp_path, "qwen3vl_32b_layer50_fp8.safetensors")
    own = part(files, H3, "text_encoder_URLs")["values"]
    files = await lane.query("files", choose=(H3, "text_encoder_URLs", encoder))
    assert part(files, H3, "text_encoder_URLs")["path"] == encoder
    model = next(m for m in (await lane.query("models"))["models"] if m["id"] == H3)
    assert not (model.get("video") or {}).get("text_encoders"), "no encoder choice overrides the chosen file"

    await lane.query("files", choose=(H3, "video_vae_file", None))
    assert json.loads(override(lane, H3).read_text()) == {
        "model": {"hub_files": {"text_encoder_URLs": own}, "text_encoder_URLs": [encoder]}}
    files = await lane.query("files", choose=(H3, "text_encoder_URLs", None))
    assert not override(lane, H3).exists(), "every part back: no file left"
    assert not any(p["chosen"] for p in files[H3])
    assert part(files, H3, "text_encoder_URLs")["name"] == "Qwen3-VL-32B-Instruct-layer50_bf16.safetensors"


async def test_a_missing_model_takes_the_owners_file_and_runs_from_it(lane, tmp_path):
    files = await lane.query("files")
    missing = next(m for m in (await lane.query("models"))["models"] if m["status"] == "missing")
    assert part(files, missing["id"],
                "URLs")["path"] is None, "listed: the chosen file may be there under another name"
    edit = mine(tmp_path, "krea2-turbo-edit-fp8_scaled.safetensors")
    files = await lane.query("files", choose=(missing["id"], "URLs", edit))
    assert part(files, missing["id"], "URLs")["path"] == edit
    main = mine(tmp_path, "z_image_turbo_comfy.safetensors")
    await lane.query("files", choose=("z_image", "URLs", main))
    done = await generate(lane, "z_image", prompt="a cat")
    assert done["model"] == "z_image" and not done.get("error"), done


async def test_the_owners_own_definition_and_an_unknown_part_are_refused(lane, tmp_path):
    path = override(lane, "z_image")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"model": {"name": "My Z"}}))
    with pytest.raises(ValueError, match="your own definition"):
        await lane.query("files", choose=("z_image", "URLs", mine(tmp_path, "z.safetensors")))
    assert json.loads(path.read_text()) == {"model": {"name": "My Z"}}, "never touched"
    with pytest.raises(ValueError, match="has no part"):
        await lane.query("files", choose=(H3, "nothing", None))


async def test_the_route_takes_an_existing_weight_file_only(lane, tmp_path):
    ctx = FakeCtx("generate-image", tmp_path / "hubdata", lane)
    body = {"model": H3, "part": "video_vae_file"}
    for bad in ("relative.safetensors", str(tmp_path / "gone.safetensors"), mine(tmp_path, "notes.txt")):
        with pytest.raises(Invalid):
            await routes.choose_model_file(ctx, FakeRequest(body=json.dumps({**body, "path": bad}).encode()))
    with pytest.raises(Invalid):
        await routes.choose_model_file(ctx, FakeRequest(body=json.dumps({**body, "part": "nothing", "path": None})
                                                        .encode()))
    vae = mine(tmp_path, "vae.safetensors")
    listing = await routes.choose_model_file(ctx, FakeRequest(body=json.dumps({**body, "path": vae}).encode()))
    h3 = next(m for m in listing["models"] if m["id"] == H3)
    assert part({H3: h3["parts"]}, H3, "video_vae_file")["path"] == vae
    assert vae not in listing["files"], \
        "the model folders are offered, not the file just picked from elsewhere"
    again = await routes.get_model_files(ctx, FakeRequest({"fresh": "1"}))
    assert [m["id"] for m in again["models"]] == [m["id"] for m in listing["models"]]


class Stub:
    """An engine whose one model loads extra files and its own LoRA (Krea 2 Turbo Edit's shape)."""

    def __init__(self, root: Path) -> None:
        self.root, self.model = root, {"URLs": ["https://hf.co/x/krea2_turbo_edit_bf16.safetensors"],
                                       "preload_URLs": ["https://hf.co/x/qwen_vision_bf16.safetensors|Qwen3-VL",
                                                        "https://hf.co/x/edit_proj.safetensors",
                                                        "https://hf.co/x/system_lora.safetensors|%lora_dir"],
                                       "vision_encoder_filename": "Qwen3-VL/qwen_vision_bf16.safetensors",
                                       "loras": ["https://hf.co/x/turbo_lora.safetensors"]}
        self.model_dropdowns = self

    def get_model_def(self, _):
        return self.model

    def _get_dropdown_deps(self):
        return self

    def get_expected_core_file_entries_for_status(self, _deps, _model):
        return [{"filename": "krea2_turbo_edit_bf16.safetensors"}]

    def get_local_model_filename(self, name, **_):
        name = str(name)
        return name if os.path.isabs(name) and os.path.isfile(name) else None

    def get_model_handler(self, _):
        return None

    def get_lora_dir(self, _):
        return str(self.root / "loras")

    def get_lora_local_path(self, folder, value):
        return None


def test_extra_files_and_the_vision_encoder_named_twice_move_together(tmp_path):
    w = Stub(tmp_path)
    parts = modelfiles.parts(w, "krea2_edit")
    assert [p["part"] for p in parts] == ["URLs", "preload_URLs:0", "preload_URLs:1", "loras:0"]
    vision = parts[1]
    assert vision["twin"] == "vision_encoder_filename" and "twin" not in parts[2]
    root = tmp_path / "engine"
    path = mine(tmp_path, "qwen_2.5_vl_7b_vision.safetensors")
    modelfiles.choose(str(root), "krea2_edit", vision, path)          # named twice: any name, both move
    model = json.loads((root / "finetunes" / "krea2_edit.json").read_text())["model"]
    assert model["preload_URLs"] == [path, *w.model["preload_URLs"][1:]] and model["vision_encoder_filename"] == path
    assert model["hub_files"] == {"preload_URLs": w.model["preload_URLs"], "vision_encoder_filename":
                                  "Qwen3-VL/qwen_vision_bf16.safetensors"}   # krea2's "file|folder" form
    w.model = {**w.model, **model}                                    # as the engine merges it
    lora = modelfiles.parts(w, "krea2_edit")[3]
    with pytest.raises(ValueError, match="choose a file named turbo_lora.safetensors"):
        modelfiles.choose(str(root), "krea2_edit", lora, mine(tmp_path, "my_turbo.safetensors"))
    renamed_folder = mine(tmp_path, "turbo_lora.safetensors")         # found by name in the family's code
    modelfiles.choose(str(root), "krea2_edit", lora, renamed_folder)
    w.model = {**w.model, **json.loads((root / "finetunes" / "krea2_edit.json").read_text())["model"]}
    again = modelfiles.parts(w, "krea2_edit")
    assert [p["chosen"] for p in again] == [False, True, False, True], "the entry chosen, not its whole list"
    modelfiles.choose(str(root), "krea2_edit", again[1], None)
    modelfiles.choose(str(root), "krea2_edit", again[3], None)
    assert not (root / "finetunes" / "krea2_edit.json").exists()
    assert not [f for f in os.listdir(root / "finetunes") if f.startswith(".")], "no temporary file left"


def test_a_pointer_keeps_its_own_file_and_holds_the_owners_other_choices(tmp_path):
    w = Stub(tmp_path)
    w.model = {"URLs": ["/models/mine.safetensors"], "hub_auto": True, "text_encoder_URLs": ["https://hf.co/te.sft"]}
    w.get_expected_core_file_entries_for_status = lambda _d, _m: [{"filename": "mine.safetensors"},
                                                                  {"filename": "te.sft"}]
    parts = modelfiles.parts(w, "auto_mine")
    assert [p["part"] for p in parts] == ["text_encoder_URLs"], "its main file is set in Image models"
    root = tmp_path / "engine"
    pointer = {"model": {"name": "mine", "architecture": "flux2_klein_9b", "URLs": ["/models/mine.safetensors"],
                         "hub_auto": True, "hub_file": "/models/mine.safetensors", "hub_base": "flux2_klein_9b"},
               "num_inference_steps": 4}
    (root / "finetunes").mkdir(parents=True)
    (root / "finetunes" / "auto_mine.json").write_text(json.dumps(pointer))
    te = mine(tmp_path, "t5_fp8.safetensors")
    modelfiles.choose(str(root), "auto_mine", parts[0], te)
    doc = json.loads((root / "finetunes" / "auto_mine.json").read_text())
    assert doc["model"] == {**pointer["model"], "text_encoder_URLs": [te],
                            "hub_files": {"text_encoder_URLs": ["https://hf.co/te.sft"]}}
    assert doc["num_inference_steps"] == 4 and not pointers.stale(doc), "the registry keeps it as it is"
    assert pointers.stale({"model": {**pointer["model"], "image_ref_choices": {}}}), "a copied field still is"
    modelfiles.choose(str(root), "auto_mine", parts[0], None)
    assert json.loads((root / "finetunes" / "auto_mine.json").read_text()) == pointer, "the pointer as it was"


def test_a_pointer_takes_its_values_from_the_engines_own_definition(tmp_path):
    (tmp_path / "defaults").mkdir()
    (tmp_path / "defaults" / "m.json").write_text("{}")
    chosen = {"path": "finetunes/m.json", "hub_files": {"URLs": ["x"]}}
    assert definitions._source(str(tmp_path), "m", chosen) == str(tmp_path / "defaults" / "m.json")
    assert definitions._source(str(tmp_path), "m", {"path": "finetunes/m.json"}) == str(tmp_path / "finetunes/m.json")
    assert definitions._source(str(tmp_path), "n", {"hub_files": {}}) is None


def test_krea2_turbo_edits_vision_encoder_as_the_owners_capture_holds_it(tmp_path):
    """18.05's krea2_turbo_edit (the capture): its main file is another model's ("URLs": "krea2_turbo"),
    its vision encoder a "file|folder" preload entry named again as `vision_encoder_filename`: offered, moved
    together."""
    capture = json.loads((Path(__file__).parents[1] / "fixtures" / "contract" / "upstream-18.05" / "engine.json")
                         .read_text())["models"]["krea2_turbo_edit"]["definition"]
    w = Stub(tmp_path)
    w.model = dict(capture)
    w.get_expected_core_file_entries_for_status = lambda _d, _m: [{"filename": "krea2_turbo_bf16.safetensors"},
                                                                  {"filename": capture["text_encoder_URLs"][0]}]
    parts = {p["part"]: p for p in modelfiles.parts(w, "krea2_turbo_edit")}
    assert "URLs" not in parts, "its main file is krea2_turbo's: changed there"
    vision = parts["preload_URLs:0"]
    assert vision["name"] == "Qwen3-VL-4B-Instruct_vision_bf16.safetensors"
    assert vision["twin"] == "vision_encoder_filename"
    assert "text_encoder_URLs" in parts
    root, path = tmp_path / "engine", mine(tmp_path, "maestro_qwen3vl_4b_vision.safetensors")
    modelfiles.choose(str(root), "krea2_turbo_edit", vision, path)
    model = json.loads((root / "finetunes" / "krea2_turbo_edit.json").read_text())["model"]
    assert model["preload_URLs"] == [path] and model["vision_encoder_filename"] == path
