"""Media's bar: reset the seed to random (Generate windows hear it) and clear the GPU cache from the Media screen."""
from __future__ import annotations

from pathlib import Path

from hub.modules.generate_image.manifest import MODULE as GEN
from hub.modules.media.manifest import MODULE as MEDIA
from tests.core.harness import start_hub


async def test_random_seed_resets_the_current_models_seed_and_tells_the_workspace(tmp_path: Path) -> None:
    hub = await start_hub(tmp_path / "data", modules=[GEN, MEDIA])
    try:
        c = hub.pair()
        w = await hub.screen(c, "workspace", "w")
        draft = {"model": "m1", "advancedByModel": {"m1": {"steps": 8, "seed": {"mode": "fixed", "value": 42}},
                                                   "m2": {"seed": {"mode": "fixed", "value": 7}}}}
        assert (await hub.http("PUT", "/api/generate-image/draft", c, json_body=draft)).status == 200
        r = await hub.http("POST", "/api/generate-image/seed/random", c, json_body={})
        assert r.status == 200
        got = (await hub.http("GET", "/api/generate-image/draft", c)).json()
        assert got["advancedByModel"]["m1"] == {"steps": 8, "seed": {"mode": "random"}}
        assert got["advancedByModel"]["m2"]["seed"]["mode"] == "fixed", "only the current model"
        await w.recv("generate-image.draft")
    finally:
        await hub.close()
