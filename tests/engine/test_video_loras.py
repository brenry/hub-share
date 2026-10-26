"""The Storyboard's Video LoRAs: their own folder in Settings (apart from the LoRA folders), each file with a
toggle and a strength; only the toggled-on ones go into each Storyboard clip, after the model card's. Neutral names
only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hub import settings as S
from hub.modules.director import render, routes, videoloras
from hub.settings_edit import ui_patch
from tests.engine.helpers import FakeRequest
from tests.engine.test_script_render import cat, ctx, two_shots  # noqa: F401  (the fixtures)


def test_settings_take_the_video_lora_folders_apart(tmp_path: Path) -> None:
    folder = tmp_path / "video loras"
    folder.mkdir()
    new = ui_patch(S.validate(S.DEFAULTS), {"modules": {"director": {"video_lora_folders": [str(folder)]}}})
    assert new["modules"]["director"]["video_lora_folders"] == [str(folder)]
    assert new["modules"].get("loras", {}).get("folders", []) == []


async def test_only_toggled_ones_reach_a_storyboard_clip(ctx: Any, tmp_path: Path) -> None:  # noqa: F811
    folder = tmp_path / "vl"
    (folder / "sub").mkdir(parents=True)
    for n in ("lora 1.safetensors", "sub/lora 2.safetensors", "note.txt"):
        (folder / n).write_bytes(b"x")
    ctx.settings = {"video_lora_folders": [str(folder)]}
    got = videoloras.listing(ctx)["loras"]
    assert [x["name"] for x in got] == ["lora 1.safetensors", "lora 2.safetensors"] and not any(x["on"] for x in got)
    one = got[0]["path"]
    videoloras.change(ctx, {"path": one, "on": True, "strength": 0.7})
    await two_shots(ctx)
    render.running.clear()
    job = await routes.post_render(ctx, FakeRequest(body=json.dumps({"name": "Script 1"}).encode()))
    task = ctx.jobs.get(job["job"]).plan.tasks[0]
    sent = json.dumps(task)
    assert one in sent and "0.7" in sent and "lora 2" not in sent, sent[:400]
