"""The VRAM manager and the image lane: the reading follows residency changes within 3 s, only a
residency move reads again, and the snapshot names the lane's model and state."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from tests.core.test_vram import make, run_job
from tests.fakes.fake_probes import GB


def lanes(hub: object) -> dict[str, tuple[str | None, str]]:
    gpu = hub.core.vram.snapshot()["gpus"][0]  # type: ignore[attr-defined]
    return {x["kind"]: (x["model"], x["state"]) for x in gpu["lanes"]}


def used(m: dict) -> int:
    return m["d"]["gpus"][0]["used_mb"]


async def test_the_reading_follows_a_load_and_an_unload_within_3_s(tmp_path: Path) -> None:
    hub, lane, probes = await make(tmp_path, vram={"idle_unload": False})
    vram = hub.core.vram
    vram.share_s = 30.0  # without the residency rule every event would reuse the boot reading
    try:
        w = await hub.screen(hub.pair(), "workspace", "w")
        loaded = time.monotonic()
        await run_job(hub, w)                                    # Flux loads: 12 000 MB
        assert vram.snapshot()["gpus"][0]["used_mb"] == 12_000    # read at the load, not shared with the boot
        probes.set_procs({lane.pid: 14_000})                      # the worker keeps filling memory after the event
        await w.recv("gpu", where=lambda m: used(m) == 14_000, timeout=3)
        assert time.monotonic() - loaded < 3                      # the default settle (2 s) meets the 3 s promise
        vram.settle_s, reads = 0.2, probes.reads
        await asyncio.sleep(0.5)
        assert probes.reads == reads                              # nothing polls after it
        lane.model = None                                         # the worker went away on its own
        lane._usage(0)
        lane.on_change()
        assert vram.snapshot()["gpus"][0]["used_mb"] == 0 and probes.reads == reads + 1
        await asyncio.sleep(0.5)
        assert probes.reads == reads + 2                          # and once more when it has settled
    finally:
        await hub.close()


async def test_a_release_reads_fresh_and_only_a_residency_move_reads_again(tmp_path: Path) -> None:
    hub, lane, probes = await make(tmp_path, vram={"idle_unload": False})
    vram = hub.core.vram
    vram.share_s, vram.settle_s = 30.0, 0.05
    try:
        w = await hub.screen(hub.pair(), "workspace", "w")
        await run_job(hub, w)
        await w.recv("gpu", where=lambda m: used(m) == 12_000, timeout=3)
        assert await vram.release(["image.gpu0"], "owner") is True
        assert vram.snapshot()["gpus"][0]["used_mb"] == 0         # read after the memory came back, not shared
        await asyncio.sleep(0.2)
        reads = probes.reads
        lane.on_change()                                          # nothing moved: the reading is shared
        await asyncio.sleep(0.2)
        assert probes.reads == reads
        lane.model = "flux"                                       # resident again: read at once
        lane._usage(12_000)
        lane.on_change()
        vram.close()                                              # the hub stops before it settles
        await asyncio.sleep(0.2)
        assert probes.reads == reads + 1
    finally:
        await hub.close()


async def test_the_lane_names_its_model_and_state(tmp_path: Path) -> None:
    hub, lane, probes = await make(tmp_path, vram={"idle_unload": False})
    vram, shots, publish = hub.core.vram, [], hub.core.vram.publish
    vram.publish = lambda: (shots.append(lanes(hub)), publish())  # type: ignore[method-assign]
    try:
        assert lanes(hub) == {"image": (None, "idle")}
        vram.learn("vram", "flux", "GPU-fake-0", 8 * GB)
        lane.gate = asyncio.Event()
        w = await hub.screen(hub.pair(), "workspace", "w")
        await w.send("job.submit", {"tool": "gen", "kind": "image", "params": {}}, id="r")
        await w.recv("job", where=lambda x: x["d"]["state"] == "running")
        assert {"image": ("flux", "loading")} in shots
        assert lanes(hub) == {"image": ("flux", "busy")}
        assert hub.core.vram.engines() == {"image.gpu0": "busy"}
        lane.gate.set()
        await w.recv("job", where=lambda x: x["d"]["state"] == "done")
        assert lanes(hub) == {"image": ("flux", "ready")}
        assert await vram.release(["image.gpu0"], "owner") is True
        assert {"image": ("flux", "unloading")} in shots
        assert lanes(hub) == {"image": (None, "idle")}
    finally:
        await hub.close()
