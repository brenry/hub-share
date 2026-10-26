"""The model folder is the truth: weight files no definition names become models through small pointer files in the
engine's own `finetunes` folder (hub_auto), which the engine reads when it starts like any finetune. The real worker
runs on the fake engine, whose loader and family handlers work like the real ones (wgp.py: `finetunes/*.json`,
`init_model_def`; `get_model_name` needs a description; a main file named without a URL must be found where it is).
No weight file is read past its header, written, moved or deleted, and only hub_auto files are ever touched."""
from __future__ import annotations

import asyncio
import builtins
import json
import os
import re
import struct
from pathlib import Path

import pytest

from hub.core import autoreg, engine, fingerprints
from hub.worker import definitions
from hub.worker.adapters import pointers
from tests.engine.helpers import ENGINE_PYTHON, make_engine_root, snapshot, task
from tests.engine.test_engine_lane import Events, Probes, job

BLOCKS = [f"blocks.{i}.{part}.weight" for i in range(40) for part in ("attn.qkv", "attn.proj", "mlp.0", "mlp.2")]
PULLS = ("URLs2", "preload_URLs", "modules", "loras", "source", "path", "settings", "visible")
MINIMAL = {"name", "description", "architecture", "URLs", "hub_auto", "hub_file", "hub_base"}


def weight(path: Path, names: list[str], payload: int) -> Path:
    raw = json.dumps({"__metadata__": {"format": "pt"},
                      **{n: {"dtype": "BF16", "shape": [1], "data_offsets": [0, 2]} for n in names}}).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"\1" * payload)
    return path


def header_end(path: Path) -> int:
    return 8 + struct.unpack("<Q", path.read_bytes()[:8])[0]


@pytest.fixture
def spy(monkeypatch):
    """The furthest byte the hub read in each file it opened."""
    seen: dict[str, int] = {}

    class Spy:
        def __init__(self, path, *args, **kwargs) -> None:
            self.path, self.f = str(path), builtins.open(path, *args, **kwargs)

        def read(self, *args):
            data = self.f.read(*args)
            seen[self.path] = max(seen.get(self.path, 0), self.f.tell())
            return data

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> None:
            self.f.close()

    monkeypatch.setattr(fingerprints, "open", Spy, raising=False)
    return seen


@pytest.fixture(params=("legacy", "upstream"))
async def rig(request, tmp_path):
    root = make_engine_root(tmp_path, request.param)
    folder = tmp_path / "shared"
    known = weight(folder / "flux2" / "flux-2-klein-9b.safetensors", BLOCKS, 60_000)
    settings = {"engine": {"python": ENGINE_PYTHON, "root": str(root), "args": [], "model_folders": [str(folder)]},
                "gpus": [{"id": "gpu0", "index": 0, "uuid": "GPU-a", "engine": True}], "diagnostics": False}
    lane, _ = engine.create(settings, tmp_path / "data", Probes(None))
    lane.lora_roots = [str(folder / "loras")]
    lane.defs = root / "finetunes"            # where the pointers go (the engine reads definitions there)
    yield lane, folder, known, tmp_path / "data" / "engine"
    await lane.stop()


async def ids(lane, **args) -> set[str]:
    return {m["id"] for m in (await lane.query("models", **args))["models"]}


async def generate(lane, model: str, **extra) -> dict:
    events = Events()
    await lane.run(job(task(model=model, steps=2, **extra)), events)
    return events.of("task_done")[-1]


def finetune(lane, name: str, model: dict, **settings) -> Path:
    """A finetune not written by the Hub."""
    path = lane.defs / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": model, **settings}))
    return path


async def test_a_finetune_is_registered_used_and_removed_without_touching_weights(rig, spy):
    lane, folder, known, data = rig
    copy = weight(folder / "deep" / "more" / "My Klein-finetune_fp8.safetensors", BLOCKS[:-4] + ["extra.w"], 52_000)
    other = weight(folder / "other.safetensors", [f"layers.{i}.w" for i in range(160)], 40_000)
    weight(folder / "loras" / "style.safetensors", ["a.lora_down.weight"], 100)
    before, engine_root = snapshot(folder), snapshot(Path(lane.engine["root"]))
    cat = await lane.query("models", rescan=True)
    models = {m["id"]: m for m in cat["models"]}
    auto, base = models["auto_my_klein_finetune_fp8"], models["flux2_klein_9b"]
    assert auto["status"] in ("available", "partial") and auto["name"] == "My Klein-finetune_fp8"
    assert (auto["defaults"], auto["ref_choices"], auto["lora_dirs"], auto["family"]) == (
        base["defaults"], base["ref_choices"], base["lora_dirs"], base["family"]), "the engine fills in the rest"
    assert (auto["base"], base["base"]) == ("flux2_klein_9b", None), "the catalog names a pointer's base"
    assert not any("other" in i or "style" in i for i in models), "a file not recognised is not a model"
    files = {f["name"]: f for f in (await lane.query("weights"))["files"]}
    assert (files["other.safetensors"]["status"], files["other.safetensors"]["candidates"]) == ("unknown", [])
    assert "style.safetensors" not in files, "LoRA folders are not model folders"
    pointer = json.loads((lane.defs / "auto_my_klein_finetune_fp8.json").read_text())
    assert set(pointer["model"]) == MINIMAL
    assert pointer["model"]["URLs"] == [str(copy)] and pointer["model"]["hub_file"] == str(copy)
    assert pointer["model"]["architecture"] == "flux2_klein_9b" and pointer["model"]["hub_auto"] is True
    assert str(copy) in pointer["model"]["description"] and "Flux 2 Klein 9B" in pointer["model"]["description"]
    assert {k: v for k, v in pointer.items() if k != "model"} == {"num_inference_steps": 4, "guidance_scale": 1,
                                                                  "resolution": "1024x1024"}
    prints = json.loads((data / "fingerprints.json").read_text())
    for path in (known, copy, other):
        st = path.stat()
        assert prints[str(path)]["size"] == st.st_size and prints[str(path)]["mtime_ns"] == st.st_mtime_ns
        assert spy[str(path)] == header_end(path), "only the header is read"
    assert lane.sup.pid is None, "the worker that read the new pointer was stopped again"
    spy.clear()
    assert await ids(lane, rescan=True) == set(models) and spy == {}, "unchanged files come from fingerprints.json"

    done = await generate(lane, "auto_my_klein_finetune_fp8")
    assert done["model"] == "auto_my_klein_finetune_fp8"
    assert (await generate(lane, "flux2_klein_9b"))["model"] == "flux2_klein_9b", "the engine's own models still run"
    await lane.stop()

    os.unlink(copy)            # the file removed
    assert "auto_my_klein_finetune_fp8" not in await ids(lane, rescan=True)
    assert not (lane.defs / "auto_my_klein_finetune_fp8.json").exists()
    files = {k: v for k, v in snapshot(folder).items() if not v[0]}
    assert files == {k: v for k, v in before.items() if not v[0] and "My Klein" not in k}, "no weight file touched"
    assert str(copy) not in json.loads((data / "fingerprints.json").read_text())
    skip = lambda k: "auto_" in k or k == "finetunes"      # noqa: E731  the pointer files and their folder
    own = {k: v for k, v in snapshot(Path(lane.engine["root"])).items() if not skip(k)}
    assert own == {k: v for k, v in engine_root.items() if not skip(k)}, "the engine's own files are never written"


async def test_the_pointer_copies_the_plainest_fitting_definition_and_nothing_that_pulls_files(rig):
    lane, folder, known, _ = rig
    finetune(lane, "klein_ref_variant", {"name": "Klein refs", "description": "Borrows the base file, adds a LoRA.",
                                         "architecture": "flux2_klein_9b", "URLs": "flux2_klein_9b",
                                         "loras": ["https://example.invalid/refs.safetensors"],
                                         "preload_URLs": ["https://example.invalid/extra.safetensors"]},
             video_prompt_type="KI", num_inference_steps=12)
    copy = weight(folder / "flux-2-klein-9b-ref-tuned.safetensors", BLOCKS, 40_000)
    assert "auto_flux_2_klein_9b_ref_tuned" in await ids(lane, rescan=True)
    pointer = json.loads((lane.defs / "auto_flux_2_klein_9b_ref_tuned.json").read_text())
    assert "Flux 2 Klein 9B" in pointer["model"]["description"], "a definition naming the file itself wins"
    assert not set(PULLS) & set(pointer["model"]) and "video_prompt_type" not in pointer
    assert pointer["model"]["URLs"] == [str(copy)] and pointer["num_inference_steps"] == 4
    assert (await generate(lane, "auto_flux_2_klein_9b_ref_tuned"))["model"] == "auto_flux_2_klein_9b_ref_tuned"


async def test_the_owners_own_finetune_and_the_file_name_choose_between_equal_matches(rig):
    lane, folder, known, _ = rig
    weight(folder / "flux2" / "flux-2-klein-base-9b.safetensors", BLOCKS, 40_000)      # the base model is present too
    mine = weight(folder / "mine" / "studio-v3.safetensors", BLOCKS, 40_000)
    finetune(lane, "studio_v3", {"name": "Studio v3", "description": "Not the Hub's.",
                                 "architecture": "flux2_klein_9b", "guidance_max_phases": 1, "URLs": [str(mine)]},
             num_inference_steps=25, guidance_scale=3)
    weight(folder / "new" / "studio-v4.safetensors", BLOCKS, 40_000)
    weight(folder / "new" / "klein-base-finetune.safetensors", BLOCKS, 40_000)
    models = {m["id"]: m for m in (await lane.query("models", rescan=True))["models"]}
    assert {"studio_v3", "auto_studio_v4", "auto_klein_base_finetune"} <= set(models)
    v4 = json.loads((lane.defs / "auto_studio_v4.json").read_text())
    assert (v4["num_inference_steps"], v4["guidance_scale"]) == (25, 3)
    assert set(v4["model"]) == MINIMAL, "only the architecture: copied model fields make the engine want helper files"
    base = json.loads((lane.defs / "auto_klein_base_finetune.json").read_text())
    assert "Flux 2 Klein Base 9B" in base["model"]["description"] and base["num_inference_steps"] == 30
    assert models["auto_klein_base_finetune"]["defaults"] == models["flux2_klein_base_9b"]["defaults"]
    assert (await generate(lane, "auto_studio_v4"))["model"] == "auto_studio_v4"


async def test_a_pointer_deleted_by_hand_comes_back_under_the_same_id(rig):
    """The engine that answers may still hold the pointer it read at start; it must not count as naming the file."""
    lane, folder, _, _ = rig
    weight(folder / "deep" / "tuned.safetensors", BLOCKS, 40_000)
    assert "auto_tuned" in await ids(lane, rescan=True)
    await generate(lane, "auto_tuned")                  # the worker stays up holding the model and the pointer
    (lane.defs / "auto_tuned.json").unlink()
    assert "auto_tuned" in await ids(lane, rescan=True) and (lane.defs / "auto_tuned.json").is_file()
    assert sorted(p.name for p in lane.defs.glob("*.json")) == ["auto_tuned.json"]
    assert (await generate(lane, "auto_tuned"))["model"] == "auto_tuned"


async def test_an_sft_file_is_a_weight_file_as_the_engine_takes_it(rig):
    lane, folder, _, _ = rig
    weight(folder / "deep" / "tuned.sft", BLOCKS, 40_000)
    assert autoreg.EXT == definitions.WEIGHT_EXT
    assert "auto_tuned" in await ids(lane, rescan=True)
    assert (await generate(lane, "auto_tuned"))["model"] == "auto_tuned"


async def test_a_file_added_during_a_job_never_stops_the_job(rig):
    lane, folder, _, _ = rig
    await ids(lane, rescan=True)
    running = asyncio.create_task(generate(lane, "flux2_klein_9b", prompt="SLOW a cat"))
    await asyncio.sleep(0.3)
    weight(folder / "late.safetensors", BLOCKS, 40_000)
    listed = await ids(lane, rescan=True)              # waits for the job before the engine reads the new pointer
    assert running.done() and (await running)["model"] == "flux2_klein_9b"
    assert "auto_late" in listed and (await generate(lane, "auto_late"))["model"] == "auto_late"


async def test_a_different_size_or_shape_is_not_registered(rig):
    lane, folder, _, _ = rig
    weight(folder / "half.safetensors", BLOCKS, 0)                           # same names, a tenth of the size
    weight(folder / "mixed.safetensors", BLOCKS[:120] + [f"x.{i}" for i in range(40)], 40_000)   # overlap 0.6
    found = await ids(lane)
    files = {f["name"]: f["status"] for f in (await lane.query("weights"))["files"]}
    assert (files["half.safetensors"], files["mixed.safetensors"]) == ("unknown", "unknown")
    assert not any(i.startswith("auto_") for i in found) and not list(lane.defs.glob("auto_*.json"))


async def test_owner_definitions_are_never_touched_and_win_over_a_pointer(rig):
    lane, folder, _, _ = rig
    mine = finetune(lane, "auto_mine", {"name": "Mine", "description": "x", "architecture": "z_image",
                                        "URLs": ["/gone.safetensors"]})
    tuned = weight(folder / "deep" / "tuned.safetensors", BLOCKS, 40_000)
    assert "auto_tuned" in await ids(lane, rescan=True)
    own = finetune(lane, "my_tuned", {"name": "My tuned", "description": "x", "architecture": "flux2_klein_9b",
                                      "URLs": [str(tuned)]})
    before = snapshot(lane.defs)
    found = await ids(lane, rescan=True)
    assert "my_tuned" in found and "auto_tuned" not in found, "a definition not the Hub's replaces the pointer"
    assert not (lane.defs / "auto_tuned.json").exists()
    assert snapshot(lane.defs) == {k: v for k, v in before.items() if k != "auto_tuned.json"}
    assert mine.is_file() and own.is_file(), "only hub_auto files are removed"


async def test_pointers_an_earlier_version_kept_in_hub_data_are_deleted(rig):
    lane, _, _, data = rig
    old = data / "definitions"
    old.mkdir(parents=True)
    (old / "auto_old.json").write_text(json.dumps({"model": {"name": "Old", "hub_auto": 2, "URLs": ["/x"]}}))
    (old / "notes.json").write_text(json.dumps({"model": {"name": "Not the hub's"}}))
    await lane.query("models", rescan=True)
    assert sorted(p.name for p in old.iterdir()) == ["notes.json"], "nothing but hub_auto files is deleted"
    (old / "notes.json").unlink()
    (old / "auto_old.json").write_text(json.dumps({"model": {"hub_auto": True}}))
    await lane.query("models", rescan=True)
    assert not old.exists(), "the folder goes once only the hub's files were in it"


def test_the_new_code_names_no_model():
    names = {p.stem for p in (Path(__file__).parent / "fake_engine" / "defaults").glob("*.json")}
    words = names | {"flux", "klein", "qwen", "wan", "krea", "hunyuan", "ltx", "chroma", "sdxl", "z-image"}
    for module in (autoreg, definitions):
        text = Path(module.__file__).read_text().lower()
        assert not [w for w in words if re.search(rf"\b{re.escape(w)}\b", text)], module.__file__


async def test_the_owner_picks_the_base_and_the_choice_sticks(rig):
    """Two present models with the same tensor names (a distilled model and its base): the hub suggests one;
    choosing the other or "not a model" survives rescans and goes with the file."""
    lane, folder, _, data = rig
    weight(folder / "flux-2-klein-base-9b.safetensors", BLOCKS, 60_000)
    copy = weight(folder / "mine.safetensors", BLOCKS, 58_000)
    panel = await lane.query("weights")
    assert set(panel) == {"bases", "files"}
    assert {"flux2_klein_9b", "flux2_klein_base_9b"} <= {b["id"] for b in panel["bases"]}
    assert not any(b["id"].startswith("auto_") for b in panel["bases"]), "a pointer is never a base"
    mine = next(f for f in panel["files"] if f["path"] == str(copy))
    assert mine["status"] == "pointer" and mine["model"] == "auto_mine" and mine["chosen"] is None
    assert set(mine["candidates"]) == {"flux2_klein_9b", "flux2_klein_base_9b"} and mine["base"] == mine["suggested"]
    other = next(b for b in mine["candidates"] if b != mine["base"])
    known = next(f for f in panel["files"] if f["name"] == "flux-2-klein-9b.safetensors")
    assert (known["status"], known["model"], known["candidates"]) == ("known", "flux2_klein_9b", [])

    panel = await lane.query("weights", choose=(str(copy), other))
    mine = next(f for f in panel["files"] if f["path"] == str(copy))
    assert (mine["status"], mine["base"], mine["chosen"]) == ("pointer", other, other)
    pointer = json.loads((lane.defs / "auto_mine.json").read_text())
    base_def = json.loads((Path(lane.engine["root"]) / "defaults" / f"{other}.json").read_text())
    assert pointer["model"]["hub_base"] == other and pointer["num_inference_steps"] == base_def["num_inference_steps"]
    assert json.loads((data / "choices.json").read_text()) == {str(copy): other}
    assert (await generate(lane, "auto_mine", prompt="a cat"))["model"] == "auto_mine"
    await lane.stop()
    mine = next(f for f in (await lane.query("weights", choose=None))["files"] if f["path"] == str(copy))
    assert mine["base"] == other, "a rescan keeps the choice"

    panel = await lane.query("weights", choose=(str(copy), ""))
    mine = next(f for f in panel["files"] if f["path"] == str(copy))
    assert (mine["status"], mine["model"], mine["chosen"]) == ("unknown", None, "")
    assert not (lane.defs / "auto_mine.json").exists()
    assert "auto_mine" not in await ids(lane, rescan=True)
    os.unlink(copy)
    await lane.query("weights", choose=None)
    assert json.loads((data / "choices.json").read_text()) == {}, "a choice for a file that is gone is dropped"


async def test_a_pointer_an_older_hub_wrote_is_written_again_set_up_like_the_same_model(rig):
    """An earlier hub copied model fields (image_ref_choices) and settings (video_prompt_type) into its pointers: such
    a pointer is rewritten in the plain form, keeping the base it had even where another model fits better."""
    lane, folder, _, _ = rig
    weight(folder / "flux-2-klein-base-9b.safetensors", BLOCKS, 60_000)
    mine = weight(folder / "mine.safetensors", BLOCKS, 58_000)
    record = next(f for f in (await lane.query("weights"))["files"] if f["path"] == str(mine))
    other = next(b for b in record["candidates"] if b != record["suggested"])
    old = {"model": {"name": "mine", "description": "x", "architecture": "flux2_klein_9b",
                     "image_ref_choices": {"choices": [["None", ""], ["Refs", "KI"]]}, "URLs": [str(mine)],
                     "hub_auto": True, "hub_file": str(mine), "hub_base": other},
           "num_inference_steps": 30, "video_prompt_type": "KI"}
    (lane.defs / "auto_mine.json").write_text(json.dumps(old))
    panel = await lane.query("weights", rescan=True)
    pointer = json.loads((lane.defs / "auto_mine.json").read_text())
    assert set(pointer["model"]) == MINIMAL and set(pointer) <= {"model", *pointers.SETTINGS_KEYS}
    assert pointer["model"]["hub_base"] == other and "video_prompt_type" not in pointer
    record = next(f for f in panel["files"] if f["path"] == str(mine))
    assert (record["status"], record["model"], record["base"]) == ("pointer", "auto_mine", other)
    assert record["chosen"] is None, "kept, not chosen: no choice made here"
    assert (await generate(lane, "auto_mine"))["model"] == "auto_mine"


async def test_the_owner_says_what_a_community_file_is_though_no_official_file_is_here(rig):
    """A community release under its own name, whose kind's official file is not in the folders: nothing to
    match its tensors against, so the Hub cannot guess; every image model is offered, and the choice sets it
    up."""
    lane, folder, _, _ = rig
    mine = weight(folder / "zimage_turbo_community_v3_fp8.safetensors", [f"layers.{i}.w" for i in range(90)], 30_000)
    panel = await lane.query("weights")
    record = next(f for f in panel["files"] if f["path"] == str(mine))
    assert (record["status"], record["candidates"], record["chosen"]) == ("unknown", [], None)
    bases = {b["id"] for b in panel["bases"]}
    assert "z_image" in bases, "offered though its official file is not in the folders"
    assert not list(folder.rglob("ZImageTurbo*")), "the fake's z_image file is nowhere in the folders"
    assert not any(b.startswith("auto_") for b in bases)
    panel = await lane.query("weights", choose=(str(mine), "z_image"))
    record = next(f for f in panel["files"] if f["path"] == str(mine))
    assert (record["status"], record["base"]) == ("pointer", "z_image")
    pointer = json.loads((lane.defs / f"{record['model']}.json").read_text())["model"]
    assert pointer["URLs"] == [str(mine)] and pointer["hub_base"] == "z_image"
    assert record["model"] in await ids(lane), "it shows in Generate under its own name"
    assert mine.stat().st_size and mine.parent == folder, "never moved"


async def test_a_file_the_engine_before_the_switch_knew_is_set_up_again_with_no_question(rig):
    """The Hub's pointer in the old engine said what the file is; the new engine gets it at the next scan."""
    lane, folder, _, _ = rig
    mine = weight(folder / "my_community_zimage.safetensors", [f"layers.{i}.w" for i in range(90)], 30_000)
    root = Path(lane.engine["root"])
    old = root.parent / "old_engine"
    (old / "finetunes").mkdir(parents=True)
    (old / "finetunes" / "auto_my.json").write_text(json.dumps({"model": {
        "hub_auto": True, "hub_file": str(mine), "hub_base": "z_image", "URLs": [str(mine)]}}))
    (root.parent / ".settings-before.json").write_text(json.dumps({"engine": {"root": str(old)}}))
    panel = await lane.query("weights", rescan=True)
    record = next(f for f in panel["files"] if f["path"] == str(mine))
    assert (record["status"], record["base"]) == ("pointer", "z_image")
    assert record["model"] in await ids(lane)
    assert json.loads((old / "finetunes" / "auto_my.json").read_text())["model"]["hub_base"] == "z_image", \
        "the old engine is never changed"
    panel = await lane.query("weights", choose=(str(mine), ""))
    assert next(f for f in panel["files"] if f["path"] == str(mine))["status"] == "unknown", "the choice wins"


async def test_a_gguf_file_named_for_a_model_is_set_up_as_it(rig):
    """A quantized .gguf release in the model folders is a model file too; named for one model, it is set up."""
    lane, folder, _, _ = rig
    mine = folder / "z_image_turbo-variant-Q6_K.gguf"
    mine.write_bytes(b"GGUF\x03\x00\x00\x00" + b"\0" * 64)
    panel = await lane.query("weights", rescan=True)
    record = next(f for f in panel["files"] if f["path"] == str(mine))
    assert (record["status"], record["base"]) == ("pointer", "z_image")
    assert record["model"] in await ids(lane)
