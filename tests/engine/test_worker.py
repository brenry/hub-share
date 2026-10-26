"""The real worker process against a fake engine in both flavours (legacy = the fork HocusPocus carries, upstream)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.engine.helpers import ENGINE_PYTHON, WORKER, Worker, make_engine_root, snapshot, task

FLAVOURS = ("legacy", "upstream")


def received(w: Worker) -> dict:
    """What the engine got for the last task (the fake records it)."""
    return json.loads((w.state / "settings" / "last_task.json").read_text())


def plain_png(path: str) -> bool:
    data = Path(path).read_bytes()
    return data.startswith(b"\x89PNG") and b"tEXt" not in data and b"iTXt" not in data and b"zTXt" not in data


@pytest.fixture(params=FLAVOURS)
def worker(request, tmp_path):
    root = make_engine_root(tmp_path, request.param)
    w = Worker(root, tmp_path / "state", "--profile", "4")
    w.root, w.state, w.flavour = root, tmp_path / "state", request.param
    yield w
    w.close()


def ready(w: Worker) -> dict:
    return w.until(lambda m: m["ev"] in ("ready", "fatal"))[-1]


def run(w: Worker, job: str = "j1", **settings) -> list[dict]:
    w.send({"op": "run", "job": job, "task": 1, "request": task(**settings)})
    return w.until(lambda m: m["ev"] == "task_done")


def test_ready_reports_the_flavour(worker):
    msg = ready(worker)
    assert msg["ev"] == "ready" and msg["proto"] == 2 and msg["pid"] == worker.proc.pid
    assert msg["engine"]["api"] == worker.flavour


def test_catalog_lists_image_models_with_engine_facts(worker):
    ready(worker)
    worker.send({"op": "query", "id": "q1", "what": "catalog"})
    data = worker.until(lambda m: m["ev"] == "reply")[-1]["data"]
    models = {m["id"]: m for m in data["models"] if m["kind"] == "image"}
    assert set(models) == {"flux2_klein_9b", "flux2_klein_base_9b", "z_image", "qwen_image_21_7B", "krea2_turbo_edit"}
    klein, base, qwen = models["flux2_klein_9b"], models["flux2_klein_base_9b"], models["qwen_image_21_7B"]
    assert klein["defaults"]["num_inference_steps"] == 4 and klein["guidance_key"] is None
    assert base["guidance_key"] == "guidance_scale" and base["defaults"]["guidance_scale"] == 4
    assert klein["ref_choices"] == ["", "KI", "I"] and models["z_image"]["ref_choices"] == []
    assert qwen["block"] == 32 and qwen["lora_dirs"] == [str(worker.root / "loras" / "qwen21")]
    assert models["krea2_turbo_edit"]["status"] == "missing" and klein["status"] == "available"
    assert klein["lora_recursive"] is (worker.flavour == "upstream")
    assert data["engine"]["api"] == worker.flavour and data["engine"]["root"] == str(worker.root)


def test_one_prompt_plain_file_nothing_added(worker):
    ready(worker)
    got = run(worker, prompt="line one\nline two")
    outputs = [m for m in got if m["ev"] == "output"]
    assert got[-1]["ok"] is True and len(outputs) == 1
    sent = received(worker)
    assert sent["num_inference_steps"] == 4, "model defaults, not the engine's generic 30"
    assert sent["prompt"] == "line one\nline two"
    assert sent["multi_prompts_gen_type"] == (2 if worker.flavour == "legacy" else "FG")
    assert sent["prompt_enhancer"] == "" and sent["negative_prompt"] == "" and sent["alt_prompt"] == ""
    assert plain_png(outputs[0]["file"]), "no metadata in the image"
    name = Path(outputs[0]["file"]).name
    assert "line" not in name and "seed" not in name, "the file name says nothing"


def test_progress_and_model_events(worker):
    ready(worker)
    got = run(worker, steps=3)
    kinds = [m["ev"] for m in got]
    assert kinds[0] == "model" and got[0]["state"] == "loading" and got[0]["model"] == "flux2_klein_9b"
    assert {"state": "loaded", "model": "flux2_klein_9b"}.items() <= next(
        m for m in got if m["ev"] == "model" and m["state"] == "loaded").items()
    steps = [m for m in got if m["ev"] == "progress" and m["phase"] == "inference"]
    assert [m["step"] for m in steps] == [1, 2, 3] and steps[-1]["steps"] == 3
    done = got[-1]
    assert done["ok"] and done["model"] == "flux2_klein_9b" and done["job"] == "j1" and done["peak_rss_mb"] > 0
    again = run(worker, job="j2", steps=1)
    assert not any(m["ev"] == "model" for m in again), "a warm model is not reloaded"


def test_loras_by_flavour(worker):
    ready(worker)
    names = ["style/ink.safetensors"] if worker.flavour == "upstream" else ["grain.safetensors"]
    got = run(worker, loras=[(n, 0.8) for n in names])
    assert got[-1]["ok"] is True
    sent = received(worker)
    assert sent["activated_loras"] == names and sent["loras_multipliers"] == "0.8"


def test_legacy_lora_names_become_file_names(tmp_path):
    root = make_engine_root(tmp_path, "legacy")
    w = Worker(root, tmp_path / "state")
    try:
        ready(w)
        got = run(w, loras=[("grain.safetensors", 1.2)])
        assert got[-1]["ok"]
        missing = run(w, job="j2", loras=[("nope.safetensors", 1)])
        assert missing[-1]["ok"] is False and "missing" in missing[-1]["error"]["text"]
    finally:
        w.close()


def test_cancel_mid_task_and_before_start(worker):
    ready(worker)
    worker.send({"op": "run", "job": "j1", "task": 1, "request": task(prompt="SLOW", steps=20)})
    worker.until(lambda m: m["ev"] == "progress" and m["phase"] == "inference")
    worker.send({"op": "cancel", "job": "j1"})
    done = worker.until(lambda m: m["ev"] == "task_done")[-1]
    assert done["ok"] is False and done["error"] == {"stage": "cancelled", "text": "Cancelled"}
    worker.send({"op": "cancel", "job": "j2"})
    worker.send({"op": "run", "job": "j2", "task": 1, "request": task()})
    done = worker.until(lambda m: m["ev"] == "task_done")[-1]
    assert done["job"] == "j2" and done["error"]["stage"] == "cancelled"


def test_out_of_memory_is_one_plain_line(worker):
    ready(worker)
    done = run(worker, prompt="OOM please")[-1]
    assert done["ok"] is False and done["error"] == {"stage": "oom", "text": "Out of GPU memory"}


def test_busy_worker_refuses_a_second_task(worker):
    ready(worker)
    worker.send({"op": "run", "job": "j1", "task": 1, "request": task(prompt="SLOW", steps=4)})
    worker.send({"op": "run", "job": "j9", "task": 1, "request": task()})
    refused = worker.until(lambda m: m["ev"] == "task_done")[-1]
    assert refused["job"] == "j9" and refused["error"]["text"] == "The engine is busy"
    assert worker.until(lambda m: m["ev"] == "task_done")[-1]["ok"]


def test_eof_means_the_controller_is_gone(worker):
    ready(worker)
    worker.sock.close()
    assert worker.proc.wait(5) == 0


def test_stop_exits_at_once(worker):
    ready(worker)
    worker.send({"op": "stop"})
    assert worker.proc.wait(5) == 0


def test_start_failure_is_fatal_and_exits(tmp_path):
    root = make_engine_root(tmp_path)
    (root / "fake_engine.json").unlink()
    w = Worker(root, tmp_path / "state")
    try:
        msg = ready(w)
        assert msg["ev"] == "fatal" and msg["text"].startswith("The engine could not start:")
        assert w.proc.wait(5) == 1
    finally:
        w.close()


def test_wrong_parent_exits_immediately(tmp_path):
    root = make_engine_root(tmp_path)
    w = Worker(root, tmp_path / "state", parent=1)
    try:
        assert w.proc.wait(5) == 0
    finally:
        w.close()


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_nothing_is_written_in_the_engine_root(tmp_path, flavour):
    """Config, per-model settings and outputs go to hub data; the engine root and LoRA folders stay as they were."""
    root = make_engine_root(tmp_path, flavour)
    for key in ("z_image", "qwen21", "krea2", "wan"):
        (root / "loras" / key).rmdir()          # missing family folders must not be created either
    state = tmp_path / "state"
    (state / "config").mkdir(parents=True)
    for folder in (root, state / "config"):
        (folder / "error_queue.zip").write_bytes(b"a queue an older engine run wrote out, prompts and all")
    before = snapshot(root)
    w = Worker(root, state)
    try:
        ready(w)
        w.send({"op": "query", "id": "q", "what": "catalog"})
        w.until(lambda m: m["ev"] == "reply")
        assert run(w, model="z_image")[-1]["ok"]
        assert run(w, job="j2", loras=[("grain.safetensors", 1)])[-1]["ok"]
    finally:
        w.close()
    after = snapshot(root)
    assert after == {k: v for k, v in before.items() if k != "error_queue.zip"}, "only the old queue file is gone"
    config = json.loads((state / "config" / "wgp_config.json").read_text())
    assert "services" not in config and config["image_output_codec"] == "png"
    assert config["metadata_type"] == "none" and config["enhancer_enabled"] == 0 and config["save_queue_if_crash"] == 0
    assert config["save_path"] == str(state / "outbox") and config["checkpoints_paths"] == ["ckpts"]
    assert sorted(p.name for p in state.iterdir()) == ["config", "outbox", "settings"]
    assert sorted(p.name for p in (state / "config").iterdir()) == ["wgp_config.json"], "no queue file"


def test_dump_catalog_for_the_owner(tmp_path):
    root = make_engine_root(tmp_path, "legacy")
    out = tmp_path / "catalog.json"
    before = snapshot(root)
    result = subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--dump-catalog", str(out)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and result.stdout == "" and result.stderr == ""
    data = json.loads(out.read_text())
    assert data["engine"]["api"] == "legacy" and [m["kind"] for m in data["models"]].count("image") == 5
    assert snapshot(root) == before


def test_netguard_blocks_outbound_and_lookups():
    code = (
        "import socket, sys; sys.path.insert(0, sys.argv[1]); import netguard; netguard.install()\n"
        "a, b = socket.socketpair(); a.sendall(b'x')\n"
        "for call in (lambda: socket.create_connection(('192.0.2.1', 80), timeout=1),"
        "             lambda: socket.getaddrinfo('example.com', 80),"
        "             lambda: socket.gethostbyaddr('192.0.2.1'),"
        "             lambda: socket.getnameinfo(('192.0.2.1', 80), 0)):\n"
        "    try: call(); print('open')\n"
        "    except PermissionError: print('blocked')\n")
    out = subprocess.run([sys.executable, "-I", "-c", code, str(WORKER.parent)], capture_output=True, text=True,
                         timeout=30)
    assert out.stdout.split() == ["blocked"] * 4



def test_scratch_is_tidied_so_an_empty_folder_never_hides_a_real_bundle(tmp_path):
    """A failed fetch leaves scratch/pose (empty) and scratch/.cache; both go at start, real files stay."""
    from hub.worker import wan2gp

    scratch = tmp_path / "config" / "ckpts"
    (scratch / "pose").mkdir(parents=True)
    (scratch / ".cache" / "huggingface" / "download").mkdir(parents=True)
    (scratch / "depth").mkdir()
    (scratch / "depth" / "model.pth").write_bytes(b"x")
    paths = wan2gp.search_paths(str(tmp_path / "config"), [])
    assert paths == [str(scratch)]
    assert not (scratch / "pose").exists() and not (scratch / ".cache").exists()
    assert (scratch / "depth" / "model.pth").is_file(), "a real file and its folder stay"
