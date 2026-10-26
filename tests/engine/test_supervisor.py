"""The supervisor with the protocol fake: start, events, crash backoff, the 3-crash rule, stop escalation."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time

import pytest

from hub.core import supervisor
from hub.core.supervisor import EngineFailed, Spawn, Supervisor, kill_orphan, make_spawn, worker_env
from tests.engine.helpers import FAKE_WORKER


def spawn(tmp_path, *modes: str, env: dict | None = None) -> Spawn:
    args = ("--root", str(tmp_path), "--state", str(tmp_path / "state"), "--", *modes)
    return Spawn(python=sys.executable, args=args, env=env or worker_env(tmp_path / "home", "GPU-test"),
                 pidfile=tmp_path / "run" / "worker.pid", script=FAKE_WORKER)


class Recorder:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.arrived = asyncio.Event()

    def __call__(self, msg: dict) -> None:
        self.events.append(msg)
        self.arrived.set()

    async def wait_for(self, ev: str, timeout: float = 10) -> dict:
        end = time.monotonic() + timeout
        while True:
            found = next((m for m in self.events if m.get("ev") == ev), None)
            if found is not None:
                return found
            self.arrived.clear()
            await asyncio.wait_for(self.arrived.wait(), max(0.01, end - time.monotonic()))


@pytest.fixture(autouse=True)
def quick_backoff(monkeypatch):
    monkeypatch.setattr(supervisor, "BACKOFF_S", (0.05, 0.1, 0.2))


async def test_start_run_and_clean_stop(tmp_path):
    rec = Recorder()
    sup = Supervisor(spawn(tmp_path), rec)
    await sup.start()
    assert sup.state == "ready" and sup.pid and sup.engine["version"] == "fake"
    assert json.loads((tmp_path / "run" / "worker.pid").read_text())["pid"] == sup.pid
    await sup.send({"op": "run", "job": "j1", "task": 1, "request": {"model": "m"}})
    done = await rec.wait_for("task_done")
    assert done["ok"] and (await rec.wait_for("output"))["file"].endswith("j1_1.png")
    await sup.stop()
    assert sup.state == "none" and sup.pid is None and not (tmp_path / "run" / "worker.pid").exists()
    assert rec.events[-1] == {"ev": "exit", "text": "The engine was stopped", "crash": False}
    await sup.start()
    assert sup.state == "ready"
    await sup.stop()


async def test_concurrent_starts_share_one_process(tmp_path):
    sup = Supervisor(spawn(tmp_path), Recorder())
    await asyncio.gather(sup.start(), sup.start(), sup.start())
    assert sup.state == "ready"
    pid = sup.pid
    await sup.start()
    assert sup.pid == pid
    await sup.stop()


async def test_crash_restarts_with_backoff_then_down_after_three(tmp_path):
    rec = Recorder()
    sup = Supervisor(spawn(tmp_path, "crash-on-run"), rec)
    for n in range(1, 4):
        await sup.start()
        rec.events.clear()
        await sup.send({"op": "run", "job": f"j{n}", "task": 1, "request": {}})
        crash = await rec.wait_for("exit")
        assert crash == {"ev": "exit", "text": "Engine stopped unexpectedly (exit code 139)", "crash": True}
        assert sup.pid is None
    assert sup.state == "down" and "stopped after 3 crashes" in (sup.down_text or "")
    with pytest.raises(EngineFailed) as err:
        await sup.start()
    assert err.value.stage == "runtime" and "3 crashes" in err.value.text
    sup.reset()
    started = time.monotonic()
    await sup.start()
    assert sup.state == "ready" and time.monotonic() - started < 5
    await sup.stop()


async def test_backoff_waits_after_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor, "BACKOFF_S", (0.6, 0.6, 0.6))
    rec = Recorder()
    sup = Supervisor(spawn(tmp_path, "crash-on-run"), rec)
    await sup.start()
    await sup.send({"op": "run", "job": "j1", "task": 1, "request": {}})
    await rec.wait_for("exit")
    started = time.monotonic()
    await sup.start()
    assert time.monotonic() - started >= 0.5
    await sup.stop()


@pytest.mark.parametrize(("mode", "text"), [
    ("fatal", "The engine could not start: no GPU"),
    ("exit-on-start", "Engine stopped while starting (exit code 3)"),
    ("old-proto", "The engine's worker speaks protocol 1; the Hub speaks 2 (install the Hub again)"),
])
async def test_start_failure_is_down_at_once(tmp_path, mode, text):
    sup = Supervisor(spawn(tmp_path, mode), Recorder())
    with pytest.raises(EngineFailed) as err:
        await sup.start()
    assert err.value.text == text and sup.state == "down" and sup.down_text == text
    with pytest.raises(EngineFailed):
        await sup.start()


async def test_missing_python_is_one_line(tmp_path):
    sp = spawn(tmp_path)
    sup = Supervisor(Spawn(str(tmp_path / "nope" / "python"), sp.args, sp.env, sp.pidfile, FAKE_WORKER), Recorder())
    with pytest.raises(EngineFailed) as err:
        await sup.start()
    assert err.value.text.startswith("The engine's Python could not run") and sup.state == "down"


async def test_stop_escalates_to_sigterm_then_sigkill(tmp_path):
    sup = Supervisor(spawn(tmp_path, "ignore-stop"), Recorder(), stop_grace=0.3, term_grace=0.3)
    await sup.start()
    started = time.monotonic()
    await sup.stop()
    took = time.monotonic() - started
    assert sup.state == "none" and 0.5 <= took < 3


async def test_stop_while_starting_releases_waiters(tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor, "BACKOFF_S", (1.0, 1.0, 1.0))
    sup = Supervisor(spawn(tmp_path), Recorder())
    sup._crashes = [time.monotonic()]
    waiter = asyncio.create_task(sup.start())
    await asyncio.sleep(0.1)
    await sup.stop()
    with pytest.raises(EngineFailed):
        await waiter
    assert sup.state == "none" and sup.pid is None


async def test_slow_start_times_out(tmp_path):
    sup = Supervisor(spawn(tmp_path), Recorder(), ready_timeout=0.0)
    with pytest.raises(EngineFailed) as err:
        await sup.start()
    assert err.value.text == "The engine took too long to start" and sup.state == "down"


async def test_send_needs_a_running_worker(tmp_path):
    with pytest.raises(EngineFailed):
        await Supervisor(spawn(tmp_path), Recorder()).send({"op": "stop"})


async def test_child_sees_exactly_the_clean_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN", "do-not-pass")
    rec = Recorder()
    sup = Supervisor(spawn(tmp_path, "report-env", env=worker_env(tmp_path / "home", "GPU-1234")), rec)
    await sup.start()
    child = (await rec.wait_for("env"))["env"]
    await sup.stop()
    assert "SECRET_TOKEN" not in child
    assert child["CUDA_VISIBLE_DEVICES"] == "GPU-1234" and child["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"
    assert child["HOME"] == str(tmp_path / "home") and child["HF_HUB_OFFLINE"] == "1"
    assert child["PYTHONDONTWRITEBYTECODE"] == "1" and child["DO_NOT_TRACK"] == "1"
    assert set(child) - {"PATH", "LD_LIBRARY_PATH", "LC_CTYPE"} == {
        "HOME", "TMPDIR", "LANG", "CUDA_DEVICE_ORDER", "CUDA_VISIBLE_DEVICES", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE",
        "HF_HUB_DISABLE_TELEMETRY", "DO_NOT_TRACK", "GRADIO_ANALYTICS_ENABLED", "PYTHONDONTWRITEBYTECODE",
        "PYTHONNOUSERSITE", "PYTHONUNBUFFERED"}


def test_make_spawn_passes_paths_and_engine_args(tmp_path):
    engine = {"python": "/env/bin/python", "root": "/engine", "args": ["--profile", "4"], "model_folders": ["/m1"]}
    sp = make_spawn(engine, tmp_path, tmp_path / "engine" / "gpu0", "gpu0", "GPU-x", passthrough=False)
    assert sp.python == "/env/bin/python" and sp.pidfile == tmp_path / "run" / "worker-gpu0.pid"
    assert sp.args == ("--root", "/engine", "--state", str(tmp_path / "engine" / "gpu0"), "--models", "/m1",
                       "--", "--profile", "4")
    assert sp.env["HOME"] == str(tmp_path / "engine-home") and sp.env["CUDA_VISIBLE_DEVICES"] == "GPU-x"


def test_orphan_from_an_earlier_controller_is_killed(tmp_path):
    script = tmp_path / "main.py"
    script.write_text("import time\ntime.sleep(60)\n")
    other = subprocess.Popen([sys.executable, str(script)])
    stranger = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        pidfile = tmp_path / "worker.pid"
        start = supervisor._start_time(other.pid)
        pidfile.write_text(json.dumps({"pid": other.pid, "start": start}))
        kill_orphan(pidfile, script)
        assert other.wait(5) == -9 and not pidfile.exists()
        pidfile.write_text(json.dumps({"pid": stranger.pid, "start": supervisor._start_time(stranger.pid)}))
        kill_orphan(pidfile, script)
        assert stranger.poll() is None, "a process that is not our worker is never touched"
        pidfile.write_text("not json")
        kill_orphan(pidfile, script)
        assert not pidfile.exists()
    finally:
        for p in (other, stranger):
            if p.poll() is None:
                p.kill()
                p.wait()


def test_exit_text_names_the_signal():
    assert supervisor.exit_text(-11) == "Engine stopped unexpectedly (signal SIGSEGV)"
    assert supervisor.exit_text(1) == "Engine stopped unexpectedly (exit code 1)"


async def test_worker_dies_when_the_controller_end_closes(tmp_path):
    sup = Supervisor(spawn(tmp_path), Recorder())
    await sup.start()
    pid = sup.pid
    sup._writer.close()
    for _ in range(100):
        if sup.pid is None:
            break
        await asyncio.sleep(0.05)
    assert sup.pid is None
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


async def test_start_during_a_stop_waits_for_the_old_process(tmp_path):
    sup = Supervisor(spawn(tmp_path, "ignore-stop"), Recorder(), stop_grace=0.3, term_grace=0.3)
    await sup.start()
    old = sup.pid
    stopping = asyncio.create_task(sup.stop())
    await asyncio.sleep(0.05)
    await sup.start()
    await stopping
    assert sup.state == "ready" and sup.pid not in (None, old)
    with pytest.raises(ProcessLookupError):
        os.kill(old, 0)
    await sup.stop()
