"""The join through the real worker process (Stage 11 §1, §5.1): a join request (`kind` "join") runs the
join, not the engine, and keeps the resident model in `task_done`; `op: cancel` stops it; `--probe-join` prints one
JSON line, with its argument rules."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from hub.worker import main
from tests.engine import fake_ffmpeg
from tests.engine.helpers import ENGINE_PYTHON, WORKER, Worker, make_engine_root, snapshot, task
from tests.fakes.mp4 import tiny_mp4


def clips(folder: Path, *frames: int, sound: bool = False) -> list[Path]:
    """Clips of these frames; the first has sound (`sound`: every one)."""
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for k, n in enumerate(frames):
        path = folder / f"10150{k}-12{k}.mp4"
        path.write_bytes(tiny_mp4(frames=n, audio=sound or k == 0))
        out.append(path)
    return out


def request(paths: list[Path], *frames: int) -> dict:
    items = [{"path": str(p), "in": 0, "out": n, "fps": 24.0, "w": 960, "h": 544, "frames": n, "audio": k == 0}
             for k, (p, n) in enumerate(zip(paths, frames, strict=True))]
    return {"items": items, "canvas": {"w": 960, "h": 544, "fps": 24.0}, "audio": [], "crf": 18, "preset": "medium"}


@pytest.fixture
def served(tmp_path, monkeypatch):
    for name, value in fake_ffmpeg.install(tmp_path / "bin").items():
        monkeypatch.setenv(name, value)
    w = Worker(make_engine_root(tmp_path, "legacy"), tmp_path / "state")
    w.bin, w.state = tmp_path / "bin", tmp_path / "state"
    assert w.until(lambda m: m["ev"] in ("ready", "fatal"))[-1]["ev"] == "ready"
    yield w
    w.close()


def test_a_join_task_runs_ffmpeg_and_keeps_the_resident_model(served, tmp_path):
    served.send({"op": "run", "job": "p1", "task": 1, "request": task()})
    assert served.until(lambda m: m["ev"] == "task_done")[-1]["model"] == "flux2_klein_9b"
    paths = clips(tmp_path / "clips", 124, 141)
    served.send({"op": "run", "job": "jn", "task": 1, "request": {"kind": "join", **request(paths, 124, 141)}})
    got = served.until(lambda m: m["ev"] == "task_done")
    done = got[-1]
    assert done["ok"] and done["model"] == "flux2_klein_9b" and done["job"] == "jn", done
    assert [m["ev"] for m in got if m["ev"] == "model"] == [], "no model loaded or freed"
    [out] = [m["file"] for m in got if m["ev"] == "output"]
    assert out == str(served.state / "outbox" / "join-jn.mp4") and os.path.isfile(out)
    assert [m["step"] for m in got if m["ev"] == "progress"] == [132, 265]
    assert len(fake_ffmpeg.calls(served.bin, "ffmpeg")) == 1


def test_op_cancel_stops_a_running_join(served, tmp_path):
    fake_ffmpeg.configure(served.bin, sleep=60)
    paths = clips(tmp_path / "clips", 124, 124)
    served.send({"op": "run", "job": "jc", "task": 1, "request": {"kind": "join", **request(paths, 124, 124)}})
    served.until(lambda m: m["ev"] == "progress")
    served.send({"op": "cancel", "job": "jc"})
    done = served.until(lambda m: m["ev"] == "task_done")[-1]
    assert done["error"] == {"stage": "cancelled", "text": "Cancelled"} and not done["ok"]
    served.send({"op": "run", "job": "p2", "task": 1, "request": task()})
    assert served.until(lambda m: m["ev"] == "task_done")[-1]["ok"], "the worker is free again"


def alive(pid: int) -> bool:
    """The process runs: it is there and not a zombie waiting to be reaped."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] not in ("Z", "X")


def test_ffmpeg_dies_with_the_worker(served, tmp_path):
    """`op: stop` is `os._exit(0)`: the running ffmpeg goes with the worker (PR_SET_PDEATHSIG), even one that ignores
    SIGTERM."""
    fake_ffmpeg.configure(served.bin, sleep=60, ignore_term=True)
    paths = clips(tmp_path / "clips", 124, 124)
    served.send({"op": "run", "job": "jd", "task": 1, "request": {"kind": "join", **request(paths, 124, 124)}})
    served.until(lambda m: m["ev"] == "progress")
    [ffmpeg] = fake_ffmpeg.calls(served.bin, "ffmpeg")
    assert alive(ffmpeg["pid"])
    served.send({"op": "stop"})
    served.proc.wait(10)
    end = time.monotonic() + 10
    while alive(ffmpeg["pid"]) and time.monotonic() < end:
        time.sleep(0.05)
    assert not alive(ffmpeg["pid"]), "ffmpeg outlived its worker"


def probe_join(root: Path, state: Path, *extra: str, env: dict | None = None):
    return subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--state", str(state),
                           "--probe-join", *extra], capture_output=True, text=True, timeout=60,
                          env={**os.environ, **(env or {})})


@pytest.mark.parametrize("flavour", ["legacy", "upstream"])
def test_the_probe_prints_one_line_whole_then_trimmed(tmp_path, flavour):
    root = make_engine_root(tmp_path, flavour)
    env = fake_ffmpeg.install(tmp_path / "bin")
    paths = clips(tmp_path / "data" / "clips" / "2026-10-14", 124, 141, sound=True)
    before_root, before_data = snapshot(root), snapshot(tmp_path / "data")
    whole = probe_join(root, tmp_path / "s1", *map(str, paths), env=env)
    assert whole.returncode == 0, whole.stderr
    [line] = [json.loads(x) for x in whole.stdout.splitlines()]
    assert list(line) == ["path", "inputs", "out", "expect_frames", "open_seconds", "join_seconds"]
    assert line["path"] == "copy" and line["out"]["frames"] == line["expect_frames"] == 265
    assert line["out"] == {"frames": 265, "w": 960, "h": 544, "fps": 24.0, "seconds": round(265 / 24, 3),
                           "audio": True}
    assert line["inputs"][0] == {"file": str(paths[0]), "v": {
        "codec": "h264", "profile": "High", "w": 960, "h": 544, "pix_fmt": "yuv420p", "fps": "24/1",
        "extradata_hash": "CRC32:6d1b2c3a"}, "a": {"codec": "aac", "rate": "48000", "channels": 2}}
    assert line["inputs"][1]["file"] == str(paths[1]) and line["open_seconds"] >= 0 and line["join_seconds"] >= 0
    trimmed = probe_join(root, tmp_path / "s2", *map(str, paths), "--trim", env=env)
    [cut] = [json.loads(x) for x in trimmed.stdout.splitlines()]
    assert cut["path"] == "encode" and cut["out"]["frames"] == cut["expect_frames"] == 100 + 117
    assert sorted(os.listdir(tmp_path / "s2")) == ["config", "joined.mp4", "outbox", "settings"]
    assert snapshot(root) == before_root and snapshot(tmp_path / "data") == before_data, "nothing written there"


def test_the_probe_says_why_a_join_failed(tmp_path):
    root = make_engine_root(tmp_path)
    env = fake_ffmpeg.install(tmp_path / "bin", exit=1, stderr=["Invalid data found when processing input"])
    paths = clips(tmp_path / "clips", 124, 124)
    done = probe_join(root, tmp_path / "s", *map(str, paths), env=env)
    assert done.returncode == 1 and done.stdout == ""
    assert done.stderr.strip() == "The engine probe stopped: The join failed: Invalid data found when processing input"


@pytest.mark.parametrize("argv, why", [
    (["--root", "r", "--state", "s", "--probe-join", "a.mp4"], "two clips or more"),
    (["--root", "r", "--probe-join", "a.mp4", "b.mp4"], "two clips or more"),
    (["--root", "r", "--check-weights", "--probe-join", "a.mp4", "b.mp4"], "--check-weights reads alone"),
])
def test_the_probe_arguments_are_refused_by_their_rules(argv, why, capsys):
    with pytest.raises(SystemExit) as stop:
        main.parse(argv)
    assert stop.value.code == 2 and why in capsys.readouterr().err


def test_the_probe_needs_no_socket():
    opts, engine_args = main.parse(["--root", "r", "--state", "s", "--probe-join", "a.mp4", "b.mp4", "--trim",
                                    "--", "--x"])
    assert opts.join == ["a.mp4", "b.mp4"] and opts.trim and opts.fd is None and engine_args == ["--x"]
