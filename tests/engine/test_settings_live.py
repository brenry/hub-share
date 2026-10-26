"""Settings edits apply live: engine paths and model folders restart the worker on next use,
LoRA folders rescan, media folders re-root (with the same confinement); every window hears it."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from PIL import Image

from hub.core import engine
from hub.core.engine import EngineLane
from hub.core.supervisor import Spawn, worker_env
from hub.modules.generate_image import manifest as gi_manifest
from hub.modules.generate_image import models as gi_models
from hub.settings import DEFAULTS, load
from tests.core.fake_lane import FakeLane
from tests.core.harness import start_hub
from tests.engine.helpers import FAKE_WORKER, make_engine_root, snapshot, task, write_lora
from tests.engine.test_engine_lane import Events, job
from tests.fakes.fake_probes import FakeProbes

PRESENT = {"flux2_klein_9b", "flux2_klein_base_9b", "z_image", "qwen_image_21_7B"}


async def _engine_hub(tmp_path: Path, **extra: dict):
    root = make_engine_root(tmp_path)
    settings = {"engine": {"python": sys.executable, "root": str(root), "args": [], "model_folders": []},
                "gpus": [{"id": "gpu0", "index": 0, "uuid": "GPU-fake-0", "engine": True}], **extra}
    probes = FakeProbes()
    lane, _ = engine.create({**DEFAULTS, **settings}, tmp_path / "data", probes)
    hub = await start_hub(tmp_path / "data", lanes=[lane], modules="discover", probes=probes, settings=settings)
    return root, lane, hub


async def test_engine_paths_and_model_folders_stop_the_worker_and_drop_the_catalog(tmp_path: Path) -> None:
    root, lane, hub = await _engine_hub(tmp_path)
    weights = tmp_path / "weights"
    weights.mkdir()
    before = snapshot(weights)
    try:
        cookie = hub.pair()
        w = await hub.screen(cookie, "workspace", "w")
        assert {m["id"] for m in (await hub.http("GET", "/api/generate-image/models", cookie)).json()} >= PRESENT
        await lane.sup.start()
        assert lane.sup.pid is not None and lane._catalog is not None
        key = lane.catalog_key
        r = await hub.http("PATCH", "/api/settings", cookie, json_body={"engine": {"model_folders": [str(weights)]}})
        assert r.status == 200 and r.json()["image_model_folders"] == [str(weights)]
        assert lane.sup.pid is None and lane._catalog is None and lane.catalog_key != key
        assert lane.sup.spawn.args[lane.sup.spawn.args.index("--models") + 1] == str(weights)
        assert (await w.recv("settings"))["d"]["vram"]["idle_minutes"] == 10
        assert load(tmp_path / "data")["engine"]["model_folders"] == [str(weights)]
        python = tmp_path / "py"
        python.symlink_to(sys.executable)
        r = await hub.http("PATCH", "/api/settings", cookie, json_body={"engine": {"python": str(python)}})
        assert r.status == 200 and lane.sup.spawn.python == str(python)
        models = (await hub.http("GET", "/api/generate-image/models", cookie)).json()
        assert {m["id"] for m in models} >= PRESENT, "the next use starts the worker with the new values"
        assert lane._catalog is not None and lane.sup.pid is None
        refused = await hub.http("PATCH", "/api/settings", cookie, json_body={"engine": {"root": str(weights)}})
        assert refused.status == 400 and refused.json()["text"] == "No wgp.py in this folder"
        assert hub.core.settings["engine"]["root"] == str(root)
    finally:
        await hub.close()
        await lane.stop()
    assert snapshot(weights) == before


async def test_a_running_job_finishes_before_the_worker_restarts(tmp_path: Path) -> None:
    lane = EngineLane("image.gpu0", None, Spawn(sys.executable, ("--root", str(tmp_path), "--state",
                      str(tmp_path / "s"), "--", "slow"), worker_env(tmp_path / "h", "0"), tmp_path / "w.pid",
                      FAKE_WORKER), tmp_path, tmp_path / "s", "key")
    running = asyncio.create_task(lane.run(job(task("fake_model", steps=3)), Events()))
    while not lane.busy():
        await asyncio.sleep(0.01)
    await lane.configure({"root": str(tmp_path), "python": sys.executable, "args": ["slow"], "model_folders": []},
                         [], restart=True)
    assert lane.sup.pid is not None and lane._restart, "the job keeps its worker"
    await running
    assert lane.sup.pid is None and not lane._restart
    await lane.stop()


async def test_model_list_follows_the_model_folders(tmp_path: Path) -> None:
    """Weights landing in a model folder (one level down too) change the key, so the list is read again."""
    root, lane, hub = await _engine_hub(tmp_path)
    weights = tmp_path / "weights" / "flux2"
    weights.mkdir(parents=True)
    await asyncio.gather(*gi_manifest._warm)       # the screen's warm-up fetch is not one of the fetches counted
    fetched = 0
    real = lane._fetch_catalog

    async def counting() -> None:
        nonlocal fetched
        fetched += 1
        await real()

    lane._fetch_catalog = counting  # type: ignore[method-assign]
    try:
        cookie = hub.pair()
        await hub.http("PATCH", "/api/settings", cookie, json_body={"engine": {"model_folders": [str(weights.parent)]}})
        for _ in range(2):
            assert (await hub.http("GET", "/api/generate-image/models", cookie)).status == 200
        assert fetched == 1, "unchanged folders: the catalog is reused"
        await asyncio.sleep(0.01)
        (weights / "flux-2-klein-9b.safetensors").write_bytes(b"\0")
        assert (await hub.http("GET", "/api/generate-image/models", cookie)).status == 200
        assert fetched == 2, "a new weight file: the list is checked again"
    finally:
        await hub.close()
        await lane.stop()


async def test_lora_folders_rescan_and_are_never_written(tmp_path: Path) -> None:
    mine = tmp_path / "my_loras"
    write_lora(mine / "flux2_klein_9b" / "neon.safetensors", {"modelspec.title": "Neon"})
    before = snapshot(mine)
    root, lane, hub = await _engine_hub(tmp_path)
    emitted: list[str] = []
    emit = hub.core.events.emit
    hub.core.events.emit = lambda e, d: (emitted.append(e), emit(e, d))[1]  # type: ignore[method-assign]
    url = "/api/loras?model=flux2_klein_9b"
    try:
        cookie = hub.pair()
        ids = {i["id"] for i in (await hub.http("GET", url, cookie)).json()}
        assert "flux2_klein_9b/neon.safetensors" not in ids
        catalog = lane._catalog
        r = await hub.http("PATCH", "/api/settings", cookie, json_body={"modules": {"loras": {"folders": [str(mine)]}}})
        assert r.status == 200 and r.json()["lora_folders"] == [str(mine)]
        assert [e for e in emitted if e != "sketch.ready"] == ["settings.lora_folders"] and lane._catalog is catalog, \
            "a rescan, not an engine restart"                   # Generate's list answered says ready
        await asyncio.gather(*hub.core.events._tasks)
        found = {i["id"]: i for i in (await hub.http("GET", url, cookie)).json()}
        assert found["flux2_klein_9b/neon.safetensors"]["name"] == "Neon" and ids < set(found)
        model = gi_models.find(await lane.query("models"), "flux2_klein_9b")
        neon = mine / "flux2_klein_9b" / "neon.safetensors"
        assert gi_models.lora_name(model, "flux2_klein_9b/neon.safetensors") == str(neon), "a full path"
        assert gi_models.lora_name(model, "flux2_klein_9b/grain.safetensors") == "grain.safetensors"
        assert hub.core.ctxs["loras"].settings["folders"] == [str(mine)]
        await hub.http("PATCH", "/api/settings", cookie, json_body={"modules": {"loras": {"folders": []}}})
        assert {i["id"] for i in (await hub.http("GET", url, cookie)).json()} == ids
    finally:
        await hub.close()
        await lane.stop()
    assert snapshot(mine) == before


def _png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 24), (200, 90, 40)).save(path)
    return path


async def test_one_drive_folder_temp_stays_the_hubs_own(tmp_path: Path) -> None:
    data = tmp_path / "data"
    probes = FakeProbes()
    lane = FakeLane(data / "outputs", probes)
    hub = await start_hub(data, lanes=[lane], modules="discover", probes=probes)
    _png(data / "outputs" / "2026-10-01" / "t.png")
    folder = tmp_path / "ComfyUI"
    kept = _png(folder / "image" / "kept.png")
    secret = _png(tmp_path / "secret.png")
    os.symlink(secret, folder / "image" / "escape.png")
    try:
        cookie = hub.pair()
        w = await hub.screen(cookie, "workspace", "w")
        assert "drive" not in hub.core.files.roots
        for origin in (None, "http://evil.example"):
            headers = {"Origin": origin} if origin else {}
            r = await hub.http("PATCH", "/api/settings", cookie, json_body={"paths": {"drive": str(folder)}},
                               headers=headers, origin=False)
            assert r.status == 403
        for key in ("outputs", "inputs", "archive"):
            r = await hub.http("PATCH", "/api/settings", cookie, json_body={"paths": {key: str(folder)}})
            assert r.status == 400 and r.json()["field"] == "paths", key
        (data / "engine" / "gpu0" / "outbox").mkdir(parents=True, exist_ok=True)
        for inside in (data / "outputs", data / "engine" / "gpu0" / "outbox", data):
            r = await hub.http("PATCH", "/api/settings", cookie, json_body={"paths": {"drive": str(inside)}})
            assert r.status == 400 and r.json() == {
                "code": "invalid", "field": "paths.drive", "text": "That is the Hub's own folder; pick your own folder"}
        r = await hub.http("PATCH", "/api/settings", cookie, json_body={"paths": {"drive": str(folder)}})
        assert r.status == 200 and r.json()["drive"] == str(folder) and "outputs" not in r.json()
        assert hub.core.files.roots["drive"] == folder and hub.core.files.roots["out"] == data / "outputs"
        await w.recv("settings")
        page = (await hub.http("GET", "/api/media?limit=10", cookie)).json()
        assert [i["id"] for i in page["items"]] == ["out/2026-10-01/t.png"], "the Temp is where it was"
        ok = await hub.http("GET", "/files/drive/image/kept.png", cookie)
        assert ok.status == 200 and ok.headers["content-type"] == "image/png" and kept.is_file()
        for path in ("/files/drive/image/escape.png", "/files/drive/image/..%2F..%2Fsecret.png",
                     "/thumbs/drive/image/escape.png/96"):
            assert (await hub.http("GET", path, cookie)).status == 404, path
        assert load(data)["paths"] == {"drive": str(folder), "characters": ""}
    finally:
        await hub.close()
