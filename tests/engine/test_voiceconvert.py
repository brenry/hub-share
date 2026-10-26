"""The voice step's worker side (`adapters/voiceconvert.py`): the engine's own remux task, SeedVC's
on/off and what it lacks read as the engine reads them, a held model released first, and the component's fetch
guarded. The engine's modules are stood in for by stubs whose code is upstream `af2ed29`'s where the result matters
(`build_audio_remux_settings`, `shared/api.py:1562-1583`, copied without its overrides hook)."""
from __future__ import annotations

import json
import os
import sys
import threading
import types
from typing import Any

import pytest

from hub.worker import engineapi
from hub.worker.adapters import upstream_weights, voiceconvert
from hub.worker.faults import Refused

ROOT = "/engine/app"
COMPONENT = f"{ROOT}/postprocessing/seedvc"
SPEECH_FILES = ["seed-vc/DiT.pth", "seed-vc/config.yml", "seed-vc/campplus.bin", "bigvgan/config.json",
                "bigvgan/generator.pt", *(f"whisper-small/f{i}" for i in range(11))]


def build_audio_remux_settings(video_source, *, postprocess_audio, audio_source=None, postprocess_audio_prompt="",
                               postprocess_audio_neg_prompt="", seed=-1, repeat_generation=1,
                               replace_voice_sample=None, replace_voice_sample2=None, api_options=None,
                               return_media=False, **settings_overrides):
    """Upstream `af2ed29` `shared/api.py:1562-1583`, as captured."""
    return {"mode": "edit_remux", "prompt": "Audio remuxing", "image_mode": 0, "video_source": os.fspath(video_source),
            "postprocess_audio": postprocess_audio or "", "postprocess_audio_prompt": postprocess_audio_prompt or "",
            "postprocess_audio_neg_prompt": postprocess_audio_neg_prompt or "", "seed": int(seed),
            "repeat_generation": int(repeat_generation),
            "audio_source": None if audio_source is None else os.fspath(audio_source),
            "replace_voice_sample": None if replace_voice_sample is None else os.fspath(replace_voice_sample),
            "replace_voice_sample2": None if replace_voice_sample2 is None else os.fspath(replace_voice_sample2),
            "temporal_upsampling": "", "spatial_upsampling": "", "film_grain_intensity": 0,
            "film_grain_saturation": 0.5, "batch_size": 1}


class SeedVCProcessor:
    """Upstream `af2ed29` `postprocessing/seedvc_processor/audio_processor.py:59-70`, its bridge's modes inlined
    (`bridge.py:239-251`)."""

    @classmethod
    def normalize_config_section(cls, config):
        mode = config.get("mode", 0)
        try:
            mode = int(mode)
        except (TypeError, ValueError):
            mode = 0
        if mode not in (1, 2, 3) and mode != 0:
            mode = 0
        return {"mode": mode}


@pytest.fixture
def engine_modules(monkeypatch):
    """The engine's modules the step reads, with `here` the files found and `installed` the component's state."""
    state: dict[str, Any] = {"here": set(SPEECH_FILES) | {"roformer/a.ckpt", "roformer/a.yaml"}, "installed": True,
                             "versions": []}
    assets = types.ModuleType("postprocessing.seedvc_processor.assets")

    def required(mode=1, root="seed-vc"):
        state["versions"].append(mode)
        return list(SPEECH_FILES)
    assets.query_required_files = required
    component = types.ModuleType("postprocessing.seedvc_processor.component")
    component.installed = lambda: state["installed"]
    component.SEEDVC_COMPONENT_DIR = COMPONENT
    locator = types.ModuleType("shared.utils.files_locator")
    locator.locate_file = lambda name, error_if_none=True: f"/models/{name}" if name in state["here"] else None
    download = types.ModuleType("shared.utils.download")
    download.query_audio_background_replacement_download_def = lambda: [
        {"sourceFolderList": ["roformer"], "fileList": [["a.ckpt", "a.yaml"]]}]
    download.download_def_missing_files = lambda d: [f"{f}/{n}" for one in d for f, names in
                                                     zip(one["sourceFolderList"], one["fileList"], strict=True)
                                                     for n in names if f"{f}/{n}" not in state["here"]]
    api = types.ModuleType("shared.api")
    api.build_audio_remux_settings = build_audio_remux_settings
    processor = types.ModuleType("postprocessing.seedvc_processor.audio_processor")
    processor.SeedVCProcessor = SeedVCProcessor
    migration = types.ModuleType("shared.utils.wgp_config_migration")
    migration.SEEDVC_MODE_CHOICES = [("v1.0 Speech", 1), ("v1.0 Singing / F0 44k", 2), ("v2 Speech", 3)]  # `:17`
    for module in (assets, component, locator, download, api, processor, migration):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    return state


def w(mode: Any = 1) -> types.SimpleNamespace:
    config = {"audio_processors": {"seedvc": {"mode": mode}}} if mode is not None else {}
    released: list[int] = []
    return types.SimpleNamespace(server_config=config, release_model=lambda: released.append(1), released=released)


def request() -> engineapi.VoiceRequest:
    return engineapi.VoiceRequest("/data/clips/2026-10-18/a.mp4", "/chars/Character 7.wav", 7)


def test_the_task_is_the_engines_own_remux_with_one_speaker(engine_modules):
    assert voiceconvert.task(request()) == build_audio_remux_settings(
        "/data/clips/2026-10-18/a.mp4", postprocess_audio="seedvc_one_speaker",
        replace_voice_sample="/chars/Character 7.wav", seed=7)
    assert voiceconvert.task(request())["mode"] == "edit_remux"


def test_no_seed_passes_no_seed_argument(engine_modules):
    """R55 §3: a voice with no seed leaves `seed` out, so the remux takes its own -1; `seed=None` would
    raise in `int(seed)`."""
    none = engineapi.VoiceRequest("/data/clips/Clip 1.mp4", "/chars/Speaker 1.wav", None)
    assert voiceconvert.task(none) == build_audio_remux_settings(
        "/data/clips/Clip 1.mp4", postprocess_audio="seedvc_one_speaker", replace_voice_sample="/chars/Speaker 1.wav")
    assert voiceconvert.task(none)["seed"] == -1


def test_off_is_the_off_line(engine_modules):
    for mode in (None, 0, "0", "x"):
        assert voiceconvert.state(w(mode), ROOT) == {"on": False, "lacking": [], "line": voiceconvert.OFF}
    assert voiceconvert.OFF == "Voice conversion is off in the engine's config (audio_processors.seedvc.mode)"


def test_everything_here_refuses_nothing(engine_modules):
    assert voiceconvert.state(w(1), ROOT) == {"on": True, "lacking": [], "line": ""}
    assert engine_modules["versions"] == [1], "the files of the mode the config names"


def test_lacking_files_are_grouped_by_folder(engine_modules):
    engine_modules["here"] -= {"seed-vc/DiT.pth", "seed-vc/campplus.bin", *(f"whisper-small/f{i}" for i in range(11)),
                               "roformer/a.yaml"}
    got = voiceconvert.state(w(1), ROOT)
    assert got["lacking"] == ["seed-vc (2 files)", "whisper-small (11 files)", "roformer (1 file)"]
    assert got["line"] == ("Voice conversion lacks, in your model folders: seed-vc (2 files), whisper-small "
                           "(11 files), roformer (1 file)")


def test_the_component_lacking_is_named(engine_modules):
    engine_modules["installed"] = False
    got = voiceconvert.state(w(1), ROOT)
    assert got["lacking"] == ["the SeedVC component (engine postprocessing/seedvc)"]
    assert got["line"].endswith("the SeedVC component (engine postprocessing/seedvc)")


class Job:
    def __init__(self, files: list[str]) -> None:
        progress = types.SimpleNamespace(phase="inference", current_step=None, total_steps=None, progress=40,
                                         status="Applying Audio Remuxing - Replace Voice")
        self.events = types.SimpleNamespace(iter=lambda timeout: iter([types.SimpleNamespace(kind="progress",
                                                                                             data=progress)]))
        self.files, self.cancel_requested = files, False

    def result(self) -> types.SimpleNamespace:
        return types.SimpleNamespace(generated_files=self.files, errors=[])


class Engine:
    def __init__(self, mode: Any, files: list[str]) -> None:
        self.w, self.root, self.held = w(mode), ROOT, "minimax_h3_ref2va"
        self.w.release_model = self.release
        self._lock, self._cancel_pending, self._job, self._job_id = threading.Lock(), None, None, None
        self.submitted: list[dict] = []
        self.session = types.SimpleNamespace(submit_task=lambda p: self.submitted.append(p) or Job(files))
        self.order: list[str] = []

    def loaded(self) -> str | None:
        return self.held

    def release(self) -> None:
        self.order.append("released")
        self.held = None


def test_a_held_model_is_released_first_then_the_converted_clip_lands(engine_modules):
    engine = Engine(1, ["/state/outbox/converted.mp4"])
    sent: list[dict] = []
    done = voiceconvert.run(engine, "j_1", 2, request(), sent.append)
    assert engine.order == ["released"] and engine.submitted == [voiceconvert.task(request())]
    assert [e["ev"] for e in sent] == ["progress", "output"]
    assert sent[0]["text"] == "Applying Audio Remuxing - Replace Voice", "the engine's own status"
    assert sent[1] == {"job": "j_1", "task": 2, "ev": "output", "file": "/state/outbox/converted.mp4"}
    assert done["ok"] is True and done["model"] is None and "error" not in done


def test_off_or_lacking_refuses_before_anything_runs(engine_modules):
    engine = Engine(0, ["/x.mp4"])
    done = voiceconvert.run(engine, "j_1", 2, request(), lambda e: None)
    assert done["ok"] is False and done["error"] == {"stage": "generation", "text": voiceconvert.OFF}
    assert engine.order == [] and engine.submitted == [], "no model released, nothing submitted"
    engine_modules["installed"] = False
    done = voiceconvert.run(Engine(1, ["/x.mp4"]), "j_1", 2, request(), lambda e: None)
    assert done["error"]["text"].startswith("Voice conversion lacks, in your model folders:")


def test_the_components_fetch_is_guarded(monkeypatch):
    download = types.ModuleType("shared.utils.download")
    download.download_url = lambda url, filename, gen=None: "fetched"
    monkeypatch.setitem(sys.modules, "shared.utils.download", download)
    assert "shared.utils.download.download_url" in upstream_weights.guard()
    with pytest.raises(Refused) as err:
        sys.modules["shared.utils.download"].download_url(
            "https://codeload.github.com/deepbeepmeep/WanGP-SeedVC/zip/f59018fd", "/engine/_seedvc_x/WanGP-SeedVC.zip")
    assert str(err.value) == "Not in the engine's weights: WanGP-SeedVC.zip"


def rooted(tmp_path, config: dict) -> tuple[str, bytes]:
    """An engine root holding its own `wgp_config.json`; its bytes, to show they are not touched."""
    path = tmp_path / "wgp_config.json"
    path.write_text(json.dumps(config, indent=1), encoding="utf-8")
    return str(tmp_path), path.read_bytes()


def test_the_owners_root_mode_wins_over_the_engines_migration_in_memory_only(engine_modules, tmp_path):
    root, before = rooted(tmp_path, {"audio_processors": {"seedvc": {"mode": 1}}})
    engine = w(2)                         # the worker's copy after the engine's migration
    engine.server_config["audio_processors"]["mmaudio"] = {"mode": 1}
    live = engine.server_config["audio_processors"]
    assert voiceconvert.state(engine, root) == {"on": True, "lacking": [], "line": ""}
    assert engine_modules["versions"] == [1], "speech's files, not singing's"
    assert engine.server_config["audio_processors"] is live, "the engine's own dict, which SeedVC reads at each call"
    assert live == {"seedvc": {"mode": 1}, "mmaudio": {"mode": 1}}
    assert (tmp_path / "wgp_config.json").read_bytes() == before and os.listdir(tmp_path) == ["wgp_config.json"]


def test_the_owners_root_mode_is_normalized_as_the_engine_does(engine_modules, tmp_path):
    for given, kept in (("1", 1), ("x", 0), (9, 0)):
        root, _ = rooted(tmp_path, {"audio_processors": {"seedvc": {"mode": given}}})
        engine = w(2)
        voiceconvert.keep_root(engine, root)
        assert engine.server_config["audio_processors"]["seedvc"] == {"mode": kept}


def test_a_root_without_the_section_leaves_the_engines_value(engine_modules, tmp_path):
    for config in ({}, {"audio_processors": {}}, {"audio_processors": {"seedvc": 1}}, {"audio_processors": []}):
        root, _ = rooted(tmp_path, config)
        engine = w(2)
        voiceconvert.keep_root(engine, root)
        assert engine.server_config == {"audio_processors": {"seedvc": {"mode": 2}}}
    engine = w(1)
    voiceconvert.keep_root(engine, str(tmp_path / "no-such-root"))
    assert engine.server_config == {"audio_processors": {"seedvc": {"mode": 1}}}
    (tmp_path / "wgp_config.json").write_text("{not json", encoding="utf-8")
    voiceconvert.keep_root(engine, str(tmp_path))
    assert engine.server_config == {"audio_processors": {"seedvc": {"mode": 1}}}


def test_a_mode_but_speech_is_refused_by_its_name(engine_modules):
    lines = {n: voiceconvert.state(w(n), ROOT) for n in (2, 3)}
    assert lines[2] == {"on": True, "lacking": [], "line": (
        "Voice conversion is set to mode 2 (v1.0 Singing / F0 44k) in the engine's config; speech is mode 1 "
        "(audio_processors.seedvc.mode in the engine's wgp_config.json)")}
    assert lines[3]["line"] == ("Voice conversion is set to mode 3 (v2 Speech) in the engine's config; speech is "
                                "mode 1 (audio_processors.seedvc.mode in the engine's wgp_config.json)")
    assert engine_modules["versions"] == [], "no file listed before the mode is named"
    assert voiceconvert.state(w(0), ROOT)["line"] == voiceconvert.OFF


def test_the_owners_root_off_is_the_off_line(engine_modules, tmp_path):
    root, _ = rooted(tmp_path, {"audio_processors": {"seedvc": {"mode": 0}}})
    assert voiceconvert.state(w(2), root) == {"on": False, "lacking": [], "line": voiceconvert.OFF}


def test_run_reads_the_owners_root_before_it_refuses_or_submits(engine_modules, tmp_path):
    root, _ = rooted(tmp_path, {"audio_processors": {"seedvc": {"mode": 1}}})
    engine = Engine(2, ["/state/outbox/converted.mp4"])
    engine.root = root
    done = voiceconvert.run(engine, "j_1", 2, request(), lambda e: None)
    assert done["ok"] is True and engine.submitted == [voiceconvert.task(request())]
    refused = Engine(2, ["/x.mp4"])
    done = voiceconvert.run(refused, "j_1", 2, request(), lambda e: None)
    assert done["error"]["text"].startswith("Voice conversion is set to mode 2 (v1.0 Singing / F0 44k)")
    assert refused.submitted == [] and refused.order == []
