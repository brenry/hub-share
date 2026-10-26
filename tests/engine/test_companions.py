"""What the fork's engine would fetch (the worker is offline) is found before it tries: ffmpeg before the engine
opens, a model's companion files before a task loads it, and `--check-weights` lists what is missing."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from hub.worker import adapters
from hub.worker.adapters import fork
from hub.worker.faults import Unready
from tests.engine.helpers import ENGINE_PYTHON, WORKER, Worker, make_engine_root, snapshot, task

MAIN = "flux-2-klein-9b.safetensors"          # flux2_klein_9b's main file, by its URL's base name


def fork_root(tmp_path: Path, fetcher: bool = False, locator: bool = False) -> Path:
    """A fake fork root; `fetcher`: it has the engine's ffmpeg fetcher; `locator`: it publishes a file locator."""
    root = make_engine_root(tmp_path, "legacy")
    if fetcher:
        (root / "shared" / "ffmpeg_setup.py").write_text("")
    spec = json.loads((root / "fake_engine.json").read_text())
    (root / "fake_engine.json").write_text(json.dumps({**spec, "locator": locator}))
    return root


def programs(folder: Path, *names: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_text("#!/bin/sh\n")
        (folder / name).chmod(0o755)
    return folder


def companions(root: Path, *skip: str) -> None:
    """Every file the fork wants for any model, under the root's checkpoint folder, but `skip`."""
    spec = json.loads(Path(fork.FACTS).read_text())["companions"]
    for folder, files in [*spec["shared"], ["", [spec["by_config"]["when_default"]]]]:
        for name in files:
            if os.path.join(folder, name) not in skip:
                (root / "ckpts" / folder).mkdir(parents=True, exist_ok=True)
                (root / "ckpts" / folder / name).write_bytes(b"x")


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("FFMPEG_BINARY", "FFPROBE_BINARY"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_ffmpeg_on_path_is_named_before_the_engine_opens(tmp_path, clean_env):
    root = fork_root(tmp_path, fetcher=True)
    bin_dir = programs(tmp_path / "bin", "ffmpeg", "ffprobe")
    clean_env.setenv("PATH", str(bin_dir))
    adapters.prepare(str(root))
    assert os.environ["FFMPEG_BINARY"] == str(bin_dir / "ffmpeg")
    assert os.environ["FFPROBE_BINARY"] == str(bin_dir / "ffprobe")


def test_a_copy_in_ffmpeg_bins_wins_only_with_its_libraries(tmp_path, clean_env):
    root = fork_root(tmp_path, fetcher=True)
    bins = programs(root / "ffmpeg_bins", "ffmpeg", "ffprobe")
    clean_env.setenv("PATH", str(tmp_path))
    with pytest.raises(Unready, match="^ffmpeg is not installed on the server$"):
        adapters.prepare(str(root))
    (bins / "libavdevice.so.61").write_bytes(b"x")
    adapters.prepare(str(root))
    assert os.environ["FFMPEG_BINARY"] == str(bins / "ffmpeg")


def test_an_engine_without_the_fetcher_needs_nothing(tmp_path, clean_env):
    clean_env.setenv("PATH", str(tmp_path))
    adapters.prepare(str(fork_root(tmp_path)))
    assert "FFMPEG_BINARY" not in os.environ


def test_no_ffmpeg_is_one_fatal_line(tmp_path, monkeypatch):
    root = fork_root(tmp_path, fetcher=True)
    monkeypatch.setenv("PATH", str(programs(tmp_path / "bin", "ffprobe")))
    w = Worker(root, tmp_path / "state")
    try:
        msg = w.until(lambda m: m["ev"] in ("ready", "fatal"))[-1]
        assert msg == {"ev": "fatal", "text": "ffmpeg is not installed on the server"}
        assert w.proc.wait(5) == 1
    finally:
        w.close()


def test_a_missing_companion_refuses_the_task_before_the_engine_runs(tmp_path):
    root = fork_root(tmp_path, locator=True)
    companions(root, os.path.join("pose", "yolox_l.onnx"))
    (root / "ckpts" / MAIN).write_bytes(b"x")
    state = tmp_path / "state"
    w = Worker(root, state)
    try:
        assert w.until(lambda m: m["ev"] in ("ready", "fatal"))[-1]["ev"] == "ready"
        w.send({"op": "run", "job": "j1", "task": 1, "request": task()})
        got = w.until(lambda m: m["ev"] == "task_done")
        assert [m["ev"] for m in got] == ["task_done"], "no loading, no progress: the engine never ran"
        assert got[-1]["ok"] is False and got[-1]["error"] == {
            "stage": "runtime", "text": "The engine lacks a companion file: yolox_l.onnx"}
        assert not (state / "settings" / "last_task.json").exists()
        (root / "ckpts" / "pose" / "yolox_l.onnx").write_bytes(b"x")
        w.send({"op": "run", "job": "j2", "task": 1, "request": task()})
        assert w.until(lambda m: m["ev"] == "task_done")[-1]["ok"]
    finally:
        w.close()


def test_check_weights_prints_one_line_per_missing_file_and_writes_nothing(tmp_path):
    root = fork_root(tmp_path, locator=True)
    companions(root, os.path.join("pose", "yolox_l.onnx"), os.path.join("depth", "depth_anything_v2_vitb.pth"))
    before = snapshot(root)

    def check(*extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--check-weights", *extra],
                              capture_output=True, text=True, timeout=60)

    out = check("--model", "flux2_klein_9b")
    assert out.returncode == 0 and out.stderr == ""
    assert out.stdout.splitlines() == ["pose/yolox_l.onnx (every model)",
                                       "depth/depth_anything_v2_vitb.pth (every model)", f"{MAIN} (flux2_klein_9b)"]
    assert snapshot(root) == before, "reads only"
    (root / "ckpts" / MAIN).write_bytes(b"x")
    assert check("--model", "flux2_klein_9b").stdout.splitlines()[2:] == []
