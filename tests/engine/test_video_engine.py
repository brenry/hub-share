"""Native video models on the engine side: the catalog lists clip models with their facts, read from the
definitions alone (an Omni-like one with its reference cap; a legacy-like one stays out by its own fields), and the
worker sends a clip task with the video values forced, and the lane frees the GPU as soon as a clip ends, made or
failed, its peak reported as for a picture. The fake engine's H3-like definitions stand in for the real ones."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from hub.core.engine import EngineFailed
from hub.modules.generate_image import build, models
from hub.worker import adapters, catalogvideo
from hub.worker.adapters import fork, upstream
from hub.worker.adapters.fork import FAMILIES as KEYS
from tests.engine.helpers import (
    ENGINE_PYTHON,
    FAKE_ENGINE,
    WORKER,
    FakeCtx,
    FakeEngine,
    Worker,
    engine_task,
    make_engine_root,
    task,
)
from tests.engine.helpers import clip_task as clip_request
from tests.engine.test_engine_lane import Events, job
from tests.engine.test_memory_profile import lines, readable_clips, recorded_lane

HUB = Path(__file__).resolve().parents[2] / "hub"
SIZES_540 = {"21:9": [1280, 544], "16:9": [960, 544], "9:16": [544, 960], "1:1": [736, 736], "4:3": [736, 544],
             "3:4": [544, 736], "3:2": [896, 576], "2:3": [576, 896]}
CLIP = {"model_type": "minimax_h3", "prompt": "a lighthouse at dusk", "resolution": "960x544", "seed": 7,
        "image_mode": 0, "video_length": 141, "sliding_window_size": 141, "minimax_h3_multi_window": False,
        "num_inference_steps": 3, "batch_size": 1, "multi_prompts_gen_type": "FG", "image_prompt_type": "",
        "video_prompt_type": "", "minimax_h3_text_encoder": "nvfp4_awq", "audio_prompt_type": "A"}
# The same clip as the module sends it: the engine task above is what the adapter makes of it (test_video_screen).
CLIP_REQUEST = clip_request("minimax_h3", prompt="a lighthouse at dusk", frames=141, steps=3, encoder="nvfp4_awq")
CLIP_PEAK_MB = 400 + 20_000          # the fake engine's GPU (fake_gpu): the CUDA context and a clip model


@pytest.fixture(params=("legacy", "upstream"))
def worker(request, tmp_path):
    root = make_engine_root(tmp_path, request.param)
    w = Worker(root, tmp_path / "state")
    w.root, w.state, w.flavour = root, tmp_path / "state", request.param
    assert w.until(lambda m: m["ev"] in ("ready", "fatal"))[-1]["ev"] == "ready"
    yield w
    w.close()


def query(w: Worker) -> dict:
    w.send({"op": "query", "id": "q", "what": "catalog"})
    return w.until(lambda m: m["ev"] == "reply")[-1]["data"]


def test_catalog_lists_text_to_clip_models_with_their_facts(worker):
    (worker.root / "ckpts" / "minimax_h3").mkdir(parents=True)               # the definition's text_encoder_folder
    (worker.root / "ckpts" / "minimax_h3" / "qwen3vl-32B-Q2_K.gguf").write_bytes(b"x")
    data = query(worker)
    kinds = {m["id"]: m["kind"] for m in data["models"]}
    assert {k for k, v in kinds.items() if v == "video"} == {"minimax_h3", "minimax_h3_fused_turbo",
                                                              "minimax_h3_ref2va"}
    assert "minimax_h3_legacy" not in kinds, "legacy-like: flagged as a sidecar runtime"
    assert "t2v" not in kinds, "a video definition that publishes no lattice or tiers is not offered"
    models = {m["id"]: m for m in data["models"]}
    assert all(m["video"] is None for m in data["models"] if m["kind"] == "image")
    pruned, fused = models["minimax_h3"], models["minimax_h3_fused_turbo"]
    assert pruned["video"]["fps"] == 24 and pruned["video"]["steps"] == 20
    assert pruned["video"]["frames"] == {"min": 124, "step": 17, "max": 345, "default": 124}
    assert [t["name"] for t in pruned["video"]["tiers"]] == ["480p", "540p", "720p", "1080p"], "the engine's order"
    assert pruned["video"]["tiers"][1]["sizes"] == SIZES_540, "named aspects as given, 3:2 and 2:3 by the budget"
    assert pruned["video"]["tiers"][2]["sizes"]["3:2"] == [1152, 768]
    assert all(v % 32 == 0 for m in (pruned, fused) for t in m["video"]["tiers"] for s in t["sizes"].values()
               for v in s), "multiples of the model's block"
    assert pruned["video_task"] == {"minimax_h3_text_encoder": "nvfp4_awq"}, "the key the definition names"
    variants = json.loads((worker.root / "fake_engine.json").read_text())["architectures"]["minimax_h3"]
    assert pruned["video"]["text_encoders"] == list(variants["minimax_h3_text_encoder_variants"]), "its order"
    assert pruned["video"]["text_encoder_default"] == "nvfp4_awq"
    assert pruned["video"]["text_encoder_names"]["gguf_q2_k"] == "GGUF Q2_K (Lowest RAM)"
    assert pruned["video"]["text_encoders_found"] == ["gguf_q2_k"], "the one whose file is in a model folder"
    assert pruned["guidance_key"] is None and pruned["block"] == 32 and pruned["loras"] is True
    assert {m["video"]["one_pass"]["minimax_h3_multi_window"] for m in models.values() if m["kind"] == "video"} == {
        False}, "the engine's own *_multi_window switch, sent False"
    assert fused["video"]["steps"] == 4 and fused["video"]["frames"]["default"] == 243
    assert fused["steps_range"] == [4, 8] and fused["loras"] is False, "the fused model takes no LoRA"
    assert pruned["steps_range"] == [1, 50] and fused["status"] == "available"
    assert "minimax_h3" not in data["weights"]["models"], "the Image models panel stays pictures only"


def test_video_facts_need_every_field(tmp_path):
    spec = json.loads((make_engine_root(tmp_path) / "fake_engine.json").read_text())
    base = {**spec["architectures"]["minimax_h3"], "family": "x"}
    factory = {"video_length": 130, "num_inference_steps": 20}
    assert catalogvideo.video_facts(base, factory, keys=KEYS)["frames"]["default"] == 141, \
        "a factory length snaps up the lattice"
    assert catalogvideo.video_facts(base, {}, keys=KEYS)["frames"]["default"] == 124
    for change in ({"image_outputs": True}, {"t2v_class": False}, {"image_prompt_types_allowed": "S"},
                   {"omni_reference": True, "omni_reference_limits": {"image": 9}}, {"other_sidecar": True},
                   {"fps": None}, {"frames_steps": 0},
                   {"resolution_presets": {}}, {"frames_maximum": 100}, {"audio_only": True}):
        assert catalogvideo.video_facts({**base, **change}, factory, keys=KEYS) is None, change
    assert catalogvideo.video_task({"x_text_encoder_default": "b", "x_text_encoder_variants": {"a": {}}},
                                   keys=KEYS) == {}
    assert catalogvideo.video_facts(base, factory, keys=KEYS)["text_encoders_found"] is None, "no way to look: not said"
    none = catalogvideo.encoder_facts({}, keys=KEYS)
    assert none == {"text_encoders": [], "text_encoder_default": None, "text_encoder_names": {},
                    "text_encoders_found": None}
    spec = {"x_text_encoder_default": "a", "x_text_encoder_variants": {"a": {"URLs": ["http://h/f/a.gguf"]}, "b": {}},
            "text_encoder_folder": "sub"}
    seen: list[str] = []
    facts = catalogvideo.encoder_facts(spec, lambda n: seen.append(n) or n == "sub/a.gguf", keys=KEYS)
    assert facts["text_encoders_found"] == ["a"] and seen == ["a.gguf", "sub/a.gguf"], "by base name, then the folder"
    assert facts["text_encoder_names"] == {"a": "a", "b": "b"}, "no name: the id"
    assert catalogvideo.steps_range({"inference_steps_min": 8, "inference_steps_max": 4}) is None


def test_a_clip_task_reaches_the_engine_with_the_video_values_forced(worker):
    worker.send({"op": "run", "job": "c1", "task": 1, "request": CLIP_REQUEST})
    got = worker.until(lambda m: m["ev"] == "task_done")
    [out] = [m["file"] for m in got if m["ev"] == "output"]
    assert got[-1]["ok"] and out.endswith(".mp4") and Path(out).read_bytes()[4:8] == b"ftyp"
    steps = [m["step"] for m in got if m["ev"] == "progress" and m["phase"] == "inference"]
    assert steps == [1, 2, 3], "progress relayed as for a picture"
    sent = json.loads((worker.state / "settings" / "last_task.json").read_text())
    forced = (fork if worker.flavour == "legacy" else upstream).FORCED_VIDEO
    assert sent["image_mode"] == 0 and {k: sent[k] for k in forced} == forced
    assert worker.flavour == "legacy" or "MMAudio_setting" not in sent, "upstream: the deprecated key is never sent"
    assert (sent["video_length"], sent["sliding_window_size"], sent["minimax_h3_multi_window"]) == (141, 141, False)
    assert sent["minimax_h3_text_encoder"] == "nvfp4_awq" and sent["prompt_enhancer"] == ""
    config = json.loads((worker.state / "config" / "wgp_config.json").read_text())
    assert config["video_container"] == "mp4" and config["enhancer_enabled"] == 0


@pytest.fixture
def accept_all(monkeypatch):
    """Upstream's accepted-settings check opened to these tasks' keys (its own tests: test_upstream_rules.py)."""
    keys = {*CLIP, *PICTURES, *upstream.FORCED_TASK, *upstream.FORCED_VIDEO}
    monkeypatch.setattr(upstream, "accepted_names", lambda: frozenset(keys))


@pytest.mark.parametrize("api", ["legacy", "upstream"])
def test_translate_forces_video_values_only_for_a_clip(api, accept_all):
    translate = adapters.by_flavour(api).translate
    clip = translate(CLIP, {"sliding_window_size": 345, "audio_prompt_type": "A"})
    assert fork.FORCED_VIDEO == {"audio_prompt_type": "", "MMAudio_setting": 0}
    assert upstream.FORCED_VIDEO == {"audio_prompt_type": "", "postprocess_audio": ""}, "R16 §3.4: the model's sound"
    line = fork if api == "legacy" else upstream
    assert {k: clip[k] for k in line.FORCED_VIDEO} == line.FORCED_VIDEO
    assert clip["sliding_window_size"] == 141 and clip["minimax_h3_multi_window"] is False, "window keys pass"
    assert clip["prompt_enhancer"] == "" and clip["output_filename"] == "{date}-{seed}"
    image = translate({**CLIP, "image_mode": 1, "audio_prompt_type": "A"}, {})
    assert not set(line.FORCED_VIDEO) - {"audio_prompt_type"} & set(image) and image["audio_prompt_type"] == "A", \
        "a picture is sent as before"


def test_core_and_worker_name_no_model():
    """Everything about a video model comes from its definition: no model name in hub/core, nor anywhere in
    hub/worker but an adapter's facts file (the engine key families have their own guard: test_rules.py)."""
    worker = [p for p in (HUB / "worker").rglob("*") if p.is_file() and "__pycache__" not in p.parts
              and not p.name.endswith(".facts.json")]
    assert any(p.parent.name == "adapters" for p in worker), "the adapters are walked"
    for path in [*(HUB / "core").glob("*.py"), *worker]:
        assert not re.search(r"minimax|h3", path.read_text()), path


PICTURES = {"image_prompt_type": "S", "image_start": "/abs/character 11.png", "image_fit_mode": "crop",
            "minimax_h3_references": [{"type": "image", "path": "/abs/character 11.png", "image_intent": "identity"}]}


@pytest.mark.parametrize("api", ["legacy", "upstream"])
def test_translate_passes_a_clips_pictures_as_they_are(api, accept_all):
    """The worker names no picture key: whatever the module put in the task reaches the engine unchanged (no
    `video_prompt_type` letter is needed for a start frame: "S" in `image_prompt_type` says it)."""
    sent = adapters.by_flavour(api).translate({**CLIP, **PICTURES},
                                              {"minimax_h3_references": [], "image_prompt_type": ""})
    assert {k: sent[k] for k in PICTURES} == PICTURES and sent["video_prompt_type"] == ""


def test_a_clips_pictures_reach_the_engine(worker):
    start = {**CLIP_REQUEST, "references": [{"path": "/abs/character 11.png", "role": "start", "name": None,
                                             "cutout": False}]}
    worker.send({"op": "run", "job": "c2", "task": 1, "request": start})
    assert worker.until(lambda m: m["ev"] == "task_done")[-1]["ok"]
    sent = json.loads((worker.state / "settings" / "last_task.json").read_text())
    assert (sent["image_prompt_type"], sent["image_start"]) == ("S", "/abs/character 11.png")
    if worker.flavour == "legacy":
        assert sent["image_fit_mode"] == "crop", "the fork crops per task"
    else:
        assert "image_fit_mode" not in sent, "upstream refuses the fork's key: it crops by its config (fit_canvas)"
        assert adapters.by_flavour("upstream").forced_config == {"fit_canvas": 2}


ONE_PASS_KEY = "minimax_h3_multi_window"


@pytest.fixture(scope="module")
def dumps(tmp_path_factory) -> dict[str, dict]:
    """The real worker's catalog for the fake engine: as the fork is shaped ("engine": the switch only as a keyword
    of `generate_video`), with the switch also in the definitions' settings ("settings"), and with neither."""
    out = {}
    for name in ("engine", "settings", "neither"):
        base = tmp_path_factory.mktemp(name)
        root = make_engine_root(base, "legacy")
        for path in (root / "defaults").glob("minimax_h3*.json") if name == "settings" else ():
            path.write_text(json.dumps({**json.loads(path.read_text()), ONE_PASS_KEY: True}))
        if name == "neither":                       # the engine's generate_video, as fake_engine.json declares it
            spec = json.loads((root / "fake_engine.json").read_text())
            for param in spec["generate_video"]:
                param["name"] = "other_switch" if param["name"] == ONE_PASS_KEY else param["name"]
            (root / "fake_engine.json").write_text(json.dumps(spec))
        subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--dump-catalog", str(base / "c.json")],
                       check=True, capture_output=True, timeout=60)
        out[name] = {m["id"]: m for m in json.loads((base / "c.json").read_text())["models"]}
    return out


def clip_task(tmp_path: Path, model: dict) -> dict:
    """The engine task the fork's adapter makes of the module's clip request for `model`."""
    ctx = FakeCtx("generate-image", tmp_path / "data", FakeEngine(None))
    p = {"mode": "new", "prompt": "a lighthouse", "width": 960, "height": 544, "frames": 130, "steps": None,
         "loras": [], "seed": {"mode": "fixed", "value": 7}}
    request = build.clip_job(p, ctx, model, models.ui_model(model, models.ref_caps(ctx))).tasks[0]
    return engine_task(request, {"engine": {"api": "legacy"}, "models": [model]})


def test_the_fake_engine_publishes_the_one_pass_switch_as_the_fork_does():
    spec = json.loads((FAKE_ENGINE / "fake_engine.json").read_text())   # the signature the fake's wgp.py takes
    assert {"name": ONE_PASS_KEY, "kind": "POSITIONAL_OR_KEYWORD", "default": True} in spec["generate_video"], \
        "a keyword of generate_video, never a setting"
    for path in (FAKE_ENGINE / "defaults").glob("*.json"):
        assert "_multi_window" not in path.read_text(), path


def test_one_pass_is_read_from_the_settings_first(tmp_path):
    spec = json.loads((make_engine_root(tmp_path) / "fake_engine.json").read_text())
    base = {**spec["architectures"]["minimax_h3"], "family": "x"}
    assert catalogvideo.video_facts(base, {}, keys=KEYS)["one_pass"] is None, "no setting and no engine switch: none"
    own = {**base, "settings": {"x_multi_window": True, "x_window": 3}}
    assert catalogvideo.video_facts(own, {}, keys=KEYS)["one_pass"] == {"x_multi_window": False}, \
        "the definition's settings"
    assert catalogvideo.video_facts(base, {"y_multi_window": True}, keys=KEYS)["one_pass"] == {"y_multi_window": False}
    switches = {ONE_PASS_KEY: True}
    assert catalogvideo.video_facts(own, {}, switches=switches, keys=KEYS)["one_pass"] == {"x_multi_window": False}


def test_one_pass_falls_back_to_generate_video_minimax_h3_multi_window_of_hocuspocus_wgp_py_7450(tmp_path):
    spec = json.loads((make_engine_root(tmp_path) / "fake_engine.json").read_text())
    base = {**spec["architectures"]["minimax_h3"], "family": "x"}

    def generate_video(task, send_cmd, x_multi_window=True, odd_multi_window="no", minimax_h3_multi_window=True):
        pass

    switches = catalogvideo.engine_switches(SimpleNamespace(generate_video=generate_video), keys=KEYS)
    assert switches == {"x_multi_window": True, ONE_PASS_KEY: True}, "yes/no keywords ending _multi_window"
    assert catalogvideo.video_facts(base, {}, switches=switches, keys=KEYS)["one_pass"] == {ONE_PASS_KEY: False}, \
        "the switch whose prefix starts the definition's own keys (its text encoder), sent False"
    assert catalogvideo.video_facts(base, {}, switches={"x_multi_window": True}, keys=KEYS)["one_pass"] is None, \
        "another's"
    assert catalogvideo.engine_switches(SimpleNamespace(), keys=KEYS) == {}, "an engine without generate_video: none"
    plain = {k: v for k, v in base.items() if not k.startswith("minimax_h3_")}
    assert catalogvideo.video_facts(plain, {}, switches=switches, keys=KEYS)["one_pass"] is None, \
        "no key of that family"


def test_a_clip_task_carries_the_one_pass_key_from_the_engine_or_the_settings(tmp_path, dumps):
    for name in ("engine", "settings"):
        model = dumps[name]["minimax_h3"]
        assert {m["video"]["one_pass"][ONE_PASS_KEY] for m in dumps[name].values() if m["kind"] == "video"} == {
            False}, name
        task = clip_task(tmp_path / name, model)
        assert task[ONE_PASS_KEY] is False and task["sliding_window_size"] == task["video_length"] == 141, name
    neither = dumps["neither"]["minimax_h3"]
    assert neither["video"]["one_pass"] is None
    task = clip_task(tmp_path / "neither", neither)
    assert not [k for k in task if k.endswith("_multi_window")], "an engine without one: no such key sent"
    assert task["sliding_window_size"] == task["video_length"] == 141, "the window is still the whole clip"


def test_modules_hold_no_model_named_one_pass_key():
    """The module sends the catalog's fact: no `<model>_multi_window` literal in hub/modules."""
    for path in (HUB / "modules").rglob("*.py"):
        assert not re.search(r"\w_multi_window|minimax|h3", path.read_text()), path


async def clip_lane(tmp_path: Path, monkeypatch):
    """A lane whose catalog says which models are clips, holding a picture model; the record starts empty."""
    readable_clips(monkeypatch)
    lane, record = recorded_lane(tmp_path)
    assert {m["id"]: m["kind"] for m in (await lane.query("models"))["models"]}["minimax_h3"] == "video"
    await lane.run(job(task(), job_id="j_0"), Events())
    record.write_text("")
    return lane, record


async def test_a_clip_frees_the_gpu_when_it_ends_and_reports_its_peak(tmp_path, monkeypatch):
    lane, record = await clip_lane(tmp_path, monkeypatch)
    try:
        ev = Events()
        await lane.run(job(CLIP_REQUEST, job_id="c_1"), ev)
        assert ev[0] == ("model", {"state": "released", "model": "flux2_klein_9b"}), "the picture model first"
        [done] = ev.of("task_done")
        assert done["model"] == "minimax_h3" and done["peak_vram_mb"] == CLIP_PEAK_MB, "the need is learned from it"
        assert ev[-1] == ("model", {"state": "released", "model": "minimax_h3"}), "then the clip's, at once"
        assert lane.sup.pid is None and lane.held() is None and lane.residency() == [] and not lane.busy()
        assert lines(record) == ["start", "load minimax_h3"]
    finally:
        await lane.stop()


async def test_a_failed_clip_frees_the_gpu_too(tmp_path, monkeypatch):
    lane, record = await clip_lane(tmp_path, monkeypatch)
    try:
        ev = Events()
        with pytest.raises(EngineFailed) as err:
            await lane.run(job({**CLIP_REQUEST, "prompt": "OOM"}, job_id="c_1"), ev)
        assert err.value.stage == "oom" and ev[-1] == ("model", {"state": "released", "model": "minimax_h3"})
        assert lane.sup.pid is None and lane.held() is None
        await lane.run(job(task(), job_id="j_1"), Events())
        assert lines(record) == ["start", "start", "load flux2_klein_9b"], "the picture model in a fresh worker"
    finally:
        await lane.stop()
