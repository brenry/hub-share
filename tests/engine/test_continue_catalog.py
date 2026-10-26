"""Continue a clip, the engine side (Stage 6): the catalog's `continues`/`overlap` from
the definition alone, the window arithmetic on the lattice, the fake engine's "V" task, the worker keeping only a
clip's last file, the scene cap setting, and the probe (`hub/worker/probe.py`)."""
from __future__ import annotations

import functools
import json
import math
import subprocess
from pathlib import Path

import pytest

from hub import settings as cfg
from hub.core import clip
from hub.worker import catalogvideo, probe
from hub.worker.adapters.fork import FAMILIES as KEYS
from hub.worker.engineapi import Reference
from tests.engine.continue_kit import PRUNED, dump_catalog
from tests.engine.helpers import ENGINE_PYTHON, HERE, WORKER, Worker, clip_task, make_engine_root, snapshot
from tests.fakes.mp4 import tiny_mp4


@pytest.fixture(scope="module")
def clip_models(tmp_path_factory) -> dict[str, dict]:
    return {m["id"]: m for m in dump_catalog(tmp_path_factory.mktemp("engine"))}


def spec(tmp_path: Path) -> dict:
    return json.loads((make_engine_root(tmp_path) / "fake_engine.json").read_text())["architectures"]


def test_a_tsev_definition_continues_with_its_overlap(tmp_path, clip_models):
    base = spec(tmp_path)["minimax_h3"]
    assert base["image_prompt_types_allowed"] == "TSEV"
    facts = catalogvideo.video_facts(base, {}, keys=KEYS)
    assert (facts["continues"], facts["overlap"]) == (True, 18)
    assert (clip_models[PRUNED]["video"]["continues"], clip_models[PRUNED]["video"]["overlap"]) == (True, 18)
    omni = clip_models["minimax_h3_ref2va"]["video"]
    assert (omni["continues"], omni["overlap"]) == (False, None), "an identity model never continues"


def test_continuation_reads_the_definition_alone(tmp_path):
    base = spec(tmp_path)["minimax_h3"]
    lattice = (17, 124, 345)
    overlap = functools.partial(catalogvideo.continuation, keys=KEYS)
    assert overlap(base, {}, *lattice) == 18
    assert overlap({**base, "omni_reference": True}, {}, *lattice) is None, "identity model"
    assert overlap({**base, "image_prompt_types_allowed": "TSE"}, {}, *lattice) is None, "no V"
    plain = {k: v for k, v in base.items() if k != "sliding_window_defaults"}
    assert overlap(plain, {}, *lattice) is None, "no overlap anywhere"
    assert overlap(plain, {"sliding_window_overlap": 35}, *lattice) == 35, "the settings' own"
    for bad in (20, 1, 0, True, "18", 18.0):
        off = {**base, "sliding_window_defaults": {"overlap_default": bad}}
        assert overlap(off, {}, *lattice) is None, bad
    assert overlap(base, {}, 17, 124, 140) is None, "no room for the shortest clip"
    assert overlap(base, {}, 17, 124, 141) == 18
    assert catalogvideo.video_facts(plain, {}, keys=KEYS)["continues"] is False


def test_every_step_on_the_lattice_is_one_window(clip_models):
    v = clip_models[PRUNED]["video"]
    lo, step, hi, overlap = v["frames"]["min"], v["frames"]["step"], v["frames"]["max"], v["overlap"]
    steps = [n for n in range(lo, hi + 1, step) if n + overlap - 1 <= hi]
    longest = {**clip_models[PRUNED], "video": {**v, "frames": {**v["frames"], "default": hi}}}
    assert steps[0] == lo and steps[-1] == hi - (overlap - 1) == probe.frames(longest, None) == 328
    for n in steps:
        total = window = n + overlap - 1
        assert (window - lo) % step == 0, n
        reuse = min(window - step, overlap)
        assert 1 + math.ceil((total - window + 0) / (window - 0 - reuse)) == 1, n
    assert probe.frames(clip_models[PRUNED], None) == v["frames"]["default"] == 124


@pytest.fixture(params=("legacy", "upstream"))
def worker(request, tmp_path):
    root = make_engine_root(tmp_path, request.param)
    w = Worker(root, tmp_path / "state")
    w.state = tmp_path / "state"
    assert w.until(lambda m: m["ev"] in ("ready", "fatal"))[-1]["ev"] == "ready"
    yield w
    w.close()


def v_request(source: Path, n: int) -> dict:
    """A continue of `source` by `n` frames, as the module sends it (the adapter's window: n + 17)."""
    return clip_task(PRUNED, prompt="on", size=(1280, 704), seed=1, frames=n, steps=2,
                     references=[Reference(str(source), "source")])


def v_task(source: Path, n: int, window: int) -> dict:
    """The engine task of a continue with any window (`crafted_task.py`): what no request makes."""
    return {"model_type": PRUNED, "prompt": "on", "resolution": "1280x704", "seed": 1, "image_mode": 0,
            "video_length": n, "sliding_window_size": window, "sliding_window_overlap": 18,
            "minimax_h3_multi_window": False, "num_inference_steps": 2, "batch_size": 1,
            "multi_prompts_gen_type": "FG", "image_prompt_type": "V", "video_source": str(source),
            "keep_frames_video_source": "", "video_prompt_type": ""}


def test_a_v_task_makes_the_source_plus_n_minus_1_frames_at_its_size(worker, tmp_path):
    source = tmp_path / "src.mp4"
    source.write_bytes(tiny_mp4(w=544, h=960, frames=141, audio=True))
    worker.send({"op": "run", "job": "v1", "task": 1, "request": v_request(source, 124)})
    got = worker.until(lambda m: m["ev"] == "task_done")
    [out] = [m["file"] for m in got if m["ev"] == "output"]
    seen = clip.facts(Path(out))
    assert got[-1]["ok"] and (seen["frames"], seen["w"], seen["h"], seen["audio"]) == (141 + 123, 544, 960, True)
    assert got[-1]["peak_rss_mb"] > 0, "a clip's peak: the worker's high-water mark"


@pytest.mark.parametrize("flavour", ["legacy", "upstream"])
def test_a_clip_task_that_returns_two_files_emits_only_the_last(tmp_path, flavour):
    root, state = make_engine_root(tmp_path, flavour), tmp_path / "state"
    source = tmp_path / "src.mp4"
    source.write_bytes(tiny_mp4(frames=124, audio=True))
    crafted, out = tmp_path / "task.json", tmp_path / "out.json"
    crafted.write_text(json.dumps(v_task(source, 124, 124)))             # the window the engine chains on
    subprocess.run([ENGINE_PYTHON, "-B", str(HERE / "crafted_task.py"), str(WORKER.parent), str(root), str(state),
                    str(crafted), str(out)], check=True, capture_output=True, timeout=60)
    got = json.loads(out.read_text())
    outputs = [m["file"] for m in got["events"] if m["ev"] == "output"]
    assert got["done"]["ok"] and len(outputs) == 1, "two windows: two growing files, one emitted"
    assert clip.facts(Path(outputs[0]))["frames"] == 124 + 123, "the last file is the whole clip"
    assert sorted(p.name for p in (state / "outbox").iterdir()) == [Path(outputs[0]).name], "the rest: gone"


def test_the_scene_cap_setting():
    assert cfg.validate({})["modules"]["generate-image"]["continue_max_seconds"] == 60
    assert cfg.validate({"modules": {"generate-image": {"continue_max_seconds": 600}}})["modules"][
        "generate-image"]["continue_max_seconds"] == 600
    for bad in (9, 601, 30.5, True, "60"):
        with pytest.raises(cfg.SettingsError) as err:
            cfg.validate({"modules": {"generate-image": {"continue_max_seconds": bad}}})
        assert str(err.value) == ("settings.json: modules.generate-image.continue_max_seconds: must be a whole number "
                                  "from 10 to 600"), bad
        assert "\n" not in str(err.value)


def run_probe(root: Path, state: Path, source: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--state", str(state),
                           "--probe-continue", str(source), *extra], capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("flavour", ["legacy", "upstream"])
def test_the_probe_prints_one_line_per_step_against_the_fake_engine(tmp_path, flavour):
    root = make_engine_root(tmp_path, flavour)
    data = tmp_path / "data" / "clips" / "2026-10-14"
    data.mkdir(parents=True)
    source = data / "101500-123.mp4"
    source.write_bytes(tiny_mp4(frames=124, audio=True))
    before_root, before_data = snapshot(root), snapshot(tmp_path / "data")
    done = run_probe(root, tmp_path / "state", source, "--chain", "1")
    assert done.returncode == 0, done.stderr
    [line] = [json.loads(x) for x in done.stdout.splitlines()]
    assert set(line) == {"step", "model", "window", "files", "source", "out", "grew", "expect", "dropped",
                         "peak_vram_mb", "peak_rss_mb", "hwm_rss_mb", "seconds"}
    assert line["dropped"] == 0, "the fake's clip has sound under every frame: nothing left off"
    assert (line["step"], line["model"], line["window"], line["files"]) == (1, PRUNED, 141, 1)
    assert line["grew"] == line["expect"] == 123
    assert (line["out"]["w"], line["out"]["h"], line["out"]["audio"]) == (960, 544, True)
    assert line["source"] == {"frames": 124, "w": 960, "h": 544, "seconds": round(124 / 24, 3)}
    assert line["hwm_rss_mb"] >= 1 and clip.facts(tmp_path / "state" / "step1.mp4")["frames"] == 247
    assert snapshot(root) == before_root and snapshot(tmp_path / "data") == before_data, "nothing written there"


def test_the_probe_reports_the_window_the_task_was_sent_with(tmp_path):
    """The line's window is the engine task's own (`sliding_window_size` as sent), on upstream's H3."""
    root = make_engine_root(tmp_path, "upstream", h3=True)
    source = tmp_path / "src.mp4"
    source.write_bytes(tiny_mp4(frames=124, audio=True))
    done = run_probe(root, tmp_path / "state", source, "--chain", "1", "--model", "minimax_h3_fl2va_pruned")
    assert done.returncode == 0, done.stderr
    [line] = [json.loads(x) for x in done.stdout.splitlines()]
    sent = json.loads((tmp_path / "state" / "settings" / "last_task.json").read_text())
    assert line["window"] == sent["sliding_window_size"] == sent["video_length"] + 17 == 141


def test_the_probe_chains_and_refuses_a_model_that_cannot_continue(tmp_path):
    root = make_engine_root(tmp_path)
    source = tmp_path / "src.mp4"
    source.write_bytes(tiny_mp4(frames=124, audio=True))
    done = run_probe(root, tmp_path / "state", source, "--chain", "2", "--frames", "141")
    lines = [json.loads(x) for x in done.stdout.splitlines()]
    assert [(x["step"], x["files"], x["grew"], x["expect"], x["window"]) for x in lines] == [(1, 1, 140, 140, 158),
                                                                                           (2, 1, 140, 140, 158)]
    assert lines[1]["source"]["frames"] == lines[0]["out"]["frames"] == 264, "step 2 continues step 1's file"
    omni = run_probe(root, tmp_path / "state2", source, "--model", "minimax_h3_ref2va")
    assert omni.returncode == 1 and omni.stdout == ""
    assert omni.stderr.strip() == "The engine probe stopped: H3 Omni — Pruned cannot continue a clip"
