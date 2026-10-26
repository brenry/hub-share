"""The real controller (core) with the real engine lane, worker and modules, on the fake engine."""
from __future__ import annotations

import sys

from hub.core import engine
from hub.settings import DEFAULTS
from tests.core.harness import start_hub
from tests.engine.helpers import make_engine_root, snapshot
from tests.fakes.fake_probes import FakeProbes


async def test_generate_over_the_bus_into_media(tmp_path):
    root = make_engine_root(tmp_path, "legacy")
    before = snapshot(root)
    settings = {"engine": {"python": sys.executable, "root": str(root), "args": [], "model_folders": []},
                "gpus": [{"id": "gpu0", "index": 0, "uuid": "GPU-fake-0", "engine": True}]}
    probes = FakeProbes()
    lane, _ = engine.create({**DEFAULTS, **settings}, tmp_path / "data", probes)
    hub = await start_hub(tmp_path / "data", lanes=[lane], modules="discover", probes=probes, settings=settings)
    try:
        cookie = hub.pair()
        models = (await hub.http("GET", "/api/generate-image/models", cookie)).json()
        assert {m["id"] for m in models} >= {"flux2_klein_9b", "z_image"}
        loras = (await hub.http("GET", "/api/loras?model=flux2_klein_9b", cookie)).json()
        assert [i["id"] for i in loras] == ["flux2_klein_9b/grain.safetensors"], "legacy engines: flat folder"
        w = await hub.screen(cookie, "workspace", "w")
        m = await hub.screen(cookie, "media", "m")
        params = {"model": "flux2_klein_9b", "mode": "new", "prompt": "a cat\nwith a hat", "width": 512,
                  "height": 512, "images": 2, "steps": 3, "guidance": None, "seed": {"mode": "fixed", "value": 5},
                  "loras": [{"id": "flux2_klein_9b/grain.safetensors", "strength": 0.8}]}
        await w.send("job.submit", {"tool": "generate-image", "kind": "image", "params": params}, id="r1")
        assert (await w.recv(where=lambda x: x.get("re") == "r1"))["d"]["state"] == "queued"
        done = await w.recv("job", where=lambda x: x["d"]["state"] in ("done", "failed"), timeout=30)
        assert done["d"]["state"] == "done" and len(done["d"]["outputs"]) == 2
        gens = [(await m.recv("generation", timeout=5))["d"]["item"] for _ in range(2)]
        assert [g["id"] for g in gens] == done["d"]["outputs"]
        page = (await hub.http("GET", "/api/media?limit=10", cookie)).json()
        assert [i["id"] for i in page["items"]] == list(reversed(done["d"]["outputs"]))
        assert all("meta" not in i for i in page["items"])
        for item in page["items"]:
            data = (await hub.http("GET", f"/files/{item['id']}", cookie)).body
            assert b"tEXt" not in data and b"iTXt" not in data, "plain files"
            assert "seed" not in item["id"] and "cat" not in item["id"]
        assert hub.core.vram.snapshot()["gpus"][0]["lanes"][0]["model"] == "flux2_klein_9b"
        erased = await hub.http("POST", "/api/media/delete", cookie, json_body={"ids": [gens[0]["id"]]})
        assert erased.json() == {"ids": [gens[0]["id"]]}
    finally:
        await hub.close()
        await lane.stop()
    assert snapshot(root) == before
