"""The official MCP SDK clients (Open WebUI's mcp==1.27.2 and the current 2.x) against the real /mcp endpoint.

The SDK is a test-only dependency kept OUT of the hub venv. Point HUB_MCP_VENVS at one or more venv
folders (os.pathsep-separated), each with `pip install mcp==<version>`; otherwise these tests skip.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from hub.modules.generate_image import manifest as generate_image
from hub.modules.loras import manifest as loras
from tests.core.harness import start_hub

DRIVER = Path(__file__).with_name("mcp_driver.py")
VENVS = [Path(p) for p in os.environ.get("HUB_MCP_VENVS", "").split(os.pathsep) if p]
PYTHONS = [v / "bin" / "python" for v in VENVS if (v / "bin" / "python").exists()]
pytestmark = pytest.mark.skipif(not PYTHONS, reason="set HUB_MCP_VENVS to venvs with the official mcp client")


@pytest.mark.parametrize("python", PYTHONS, ids=[p.parent.parent.name for p in PYTHONS])
async def test_official_client_initializes_lists_and_calls(tmp_path: Path, python: Path) -> None:
    hub = await start_hub(tmp_path / "data", modules=[generate_image.MODULE, loras.MODULE])
    try:
        hub.core.mcp.set_enabled(True)
        proc = await asyncio.create_subprocess_exec(str(python), "-I", str(DRIVER), f"{hub.origin}/mcp",
                                                    hub.core.mcp.key(),
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), 60)
        assert proc.returncode == 0, err.decode()[-2000:]
        report = json.loads(out.decode().strip().splitlines()[-1])
        assert report["protocol"] == "2025-11-25" and report["server"] == "hub"
        assert report["tools"] == ["direct_clip", "generate_image", "get_generate_image_settings", "list_characters",
                                   "list_image_models", "list_loras", "set_generate_image_settings"], \
            "seven generated tools, none by hand"
        assert report["listed"] == [True, "No engine is set up on this server"], "a plain reason, not a crash"
        assert report["bad"][0] is True
        assert report["bad"][1] == "unknown argument prompt" or report["bad"][1].startswith("client refused"), \
            "an unknown argument to generate_image is one plain line"
        clients = hub.core.mcp.clients()
        assert clients and clients[0]["addr"] == "127.0.0.1" and clients[0]["status"] == "OK"
    finally:
        await hub.close()
