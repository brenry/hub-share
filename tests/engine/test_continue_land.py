"""Continue a clip, landing: a continue's clip lands in `clips/<day>/<time>.mp4` like any clip (no folder per scene);
two continues of one clip are two clips side by side; the source stays where it is."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from hub.core import api, clip, engine, enginecat, supervisor
from hub.worker import enginewire, probe
from tests.engine.continue_kit import PRUNED, dump_catalog
from tests.engine.helpers import make_engine_root
from tests.engine.test_engine_lane import Events, Probes, settings
from tests.fakes.mp4 import tiny_mp4

DAY, STEM = "2026-10-14", "101500-123"


def made(outbox: Path, name: str = "x.mp4") -> str:
    (outbox / name).write_bytes(tiny_mp4(frames=247, audio=True))
    return str(outbox / name)


def test_two_clips_land_flat_in_the_day_folder(tmp_path):
    outbox, outputs, clips = tmp_path / "outbox", tmp_path / "outputs", tmp_path / "clips"
    outbox.mkdir()
    first = enginecat.land(made(outbox), outbox, outputs, clips)
    time.sleep(0.002)
    second = enginecat.land(made(outbox, "y.mp4"), outbox, outputs, clips)
    today = time.strftime("%Y-%m-%d")
    for landed in (first, second):                       # c1573bb: every clip flat in the clips root, its time its name
        parts = landed["id"].split("/")
        assert (parts[0], len(parts), landed["kind"]) == ("clips", 2, "clip") and parts[1].endswith(".mp4")
        assert parts[1].startswith(f"{today} ") and (clips / parts[1]).is_file()
    assert first["id"] != second["id"] and sorted(p.name for p in clips.iterdir()) == sorted(
        i.rsplit("/", 1)[1] for i in (first["id"], second["id"])), "files only, no folder"
    assert not any(outbox.iterdir())


@pytest.fixture(autouse=True)
def quick_backoff(monkeypatch):
    monkeypatch.setattr(supervisor, "BACKOFF_S", (0.05, 0.1, 0.2))


async def test_the_lane_lands_a_continue_in_the_day_folder(tmp_path):
    [model] = [m for m in dump_catalog(tmp_path / "cat") if m["id"] == PRUNED]
    root = make_engine_root(tmp_path, "upstream")
    data = tmp_path / "data"
    lane, _ = engine.create(settings(root), data, Probes(None))
    day = data / "clips" / DAY
    day.mkdir(parents=True)
    (day / f"{STEM}.mp4").write_bytes(tiny_mp4(w=544, h=960, frames=124, audio=True))
    source = os.path.realpath(day / f"{STEM}.mp4")
    task = enginewire.request_wire(probe.continue_request(model, source, 544, 960, 141, 2, 1, "on"))
    ev = Events()
    try:
        await lane.run(api.Job(id="j_1", kind="generate-image.image", tool="generate-image", state="running",
                               plan=api.JobPlan("image", PRUNED, (task,), {"kind": "clip"})), ev)
        [out] = ev.of("output")
        assert out["item"].count("/") == 1 and out["kind"] == "clip" and (out["w"], out["h"]) == (544, 960)
        assert clip.facts(data / out["item"])["frames"] == 124 + 140, "the source plus N - 1 new frames"
        assert (day / f"{STEM}.mp4").is_file() and not any(p.is_dir() for p in day.iterdir()), "the source stays"
    finally:
        await lane.stop()
