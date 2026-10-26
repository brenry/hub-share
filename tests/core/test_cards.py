"""Settings view and edits, cards, the Network card (devices, pairing links) and the Assistant card (MCP switch)."""
from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path

import pytest

from hub.core.mcp import DEFAULT as MCP_DEFAULT
from hub.core.mcp import McpAccess
from hub.core.store import JsonDoc
from hub.settings import profile_choices, video_profile_choices
from tests.core.harness import Hub, start_hub


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    h = await start_hub(tmp_path / "data", settings={"modules": {"loras": {"folders": ["/models/loras"]}},
                                                     "engine": {"root": str(tmp_path), "python": "/bin/sh"}})
    yield h
    await h.close()


async def test_settings_view_and_live_edit(hub: Hub, tmp_path: Path) -> None:
    c = hub.pair()
    w = await hub.screen(c, "workspace", "w")
    view = (await hub.http("GET", "/api/settings", cookie=c)).json()
    assert view["engine"] == {"root": str(tmp_path), "python": "/bin/sh", "ok": True, "profile": "engine",
                              "profiles": profile_choices(), "profile_video": "same",
                              "video_profiles": video_profile_choices()}
    assert view["video_tiers"] == {"names": [], "offered": []}, "no engine here: no catalog, no sizes"
    assert view["lora_folders"] == ["/models/loras"] and view["image_model_folders"] == []
    assert view["drive"] == "" and "outputs" not in view and "inputs" not in view
    assert view["gpus"] == [{"name": "Fake RTX", "total_mb": 32 * 1024}]
    assert view["vram"] == {"idle_unload": True, "idle_minutes": 10, "clip_previews": False}
    assert view["version"] == "0.1.0"
    edit = {"vram": {"idle_minutes": 25}, "diagnostics": True}
    r = await hub.http("PATCH", "/api/settings", cookie=c, json_body=edit)
    assert r.status == 200 and r.json()["vram"]["idle_minutes"] == 25 and r.json()["diagnostics"] is True
    pushed = await w.recv("settings")
    assert pushed["d"] == {"diagnostics": True,
                           "vram": {"idle_unload": True, "idle_minutes": 25, "clip_previews": False}}
    assert json.loads((hub.data / "settings.json").read_text())["vram"]["idle_minutes"] == 25
    bad = await hub.http("PATCH", "/api/settings", cookie=c, json_body={"server": {"port": 1}})
    assert bad.status == 400 and bad.json()["field"] == "(edit)"
    bad = await hub.http("PATCH", "/api/settings", cookie=c, json_body={"vram": {"idle_minutes": 1}})
    assert bad.status == 400 and bad.json()["field"] == "vram.idle_minutes"


async def test_the_memory_profile_is_shown_saved_and_checked(hub: Hub) -> None:
    c = hub.pair()
    choices = (await hub.http("GET", "/api/settings", cookie=c)).json()["engine"]["profiles"]
    assert [p["value"] for p in choices] == ["engine", 1, 2, 3, 3.5, 4, 4.5, 5]
    assert choices[0]["label"] == "Engine's own" and choices[-1]["label"] == "5 · Very low RAM / low VRAM, fail safe"
    r = await hub.http("PATCH", "/api/settings", cookie=c, json_body={"engine": {"profile": 3.5}})
    assert r.status == 200 and r.json()["engine"]["profile"] == 3.5
    assert json.loads((hub.data / "settings.json").read_text())["engine"]["profile"] == 3.5
    bad = await hub.http("PATCH", "/api/settings", cookie=c, json_body={"engine": {"profile": 6}})
    assert bad.status == 400 and bad.json()["field"] == "engine.profile"
    r = await hub.http("PATCH", "/api/settings", cookie=c, json_body={"engine": {"profile": "engine"}})
    assert r.json()["engine"]["profile"] == "engine" and hub.core.settings["engine"]["profile"] == "engine"


async def test_cards_list_and_push(hub: Hub) -> None:
    c = hub.pair()
    w = await hub.screen(c, "workspace", "w")
    cards = (await hub.http("GET", "/api/cards", cookie=c)).json()
    assert cards == [
        {"module": "network", "title": "Network", "order": 900, "summary": f"Port {hub.port} · 1 device connected",
         "status": "ok"},
        {"module": "assistant", "title": "Assistant", "order": 920, "summary": "Off", "status": "off"}]
    hub.core.mcp.set_enabled(True)
    pushed = await w.recv("cards", where=lambda m: m["d"][1]["summary"] != "Off")
    assert pushed["d"][1] == {"module": "assistant", "title": "Assistant", "order": 920,
                              "summary": "On · no calls yet", "status": "ok"}


async def test_network_view_rename_remove_and_pair_link(hub: Hub) -> None:
    me = hub.pair(name="Desk")
    other = hub.pair(name="Laptop")
    view = (await hub.http("GET", "/api/network", cookie=me)).json()
    assert view["server"] == {"bind": ["127.0.0.1"], "port": hub.port, "listening": ["127.0.0.1"], "missing": [],
                              "hosts": [f"127.0.0.1:{hub.port}", f"localhost:{hub.port}"]}
    rows = {d["name"]: d for d in view["devices"]}
    assert rows["Desk"]["you"] is True and rows["Laptop"]["you"] is False and rows["Desk"]["addrs"] == ["127.0.0.1"]
    assert "key_hash" not in json.dumps(view)
    laptop_id = other.split(".")[0]
    line = await hub.screen(other, "media", "lap")
    r = await hub.http("PATCH", f"/api/network/devices/{laptop_id}", cookie=me, json_body={"name": "desk"})
    assert r.status == 400 and r.json()["text"] == "Another device already has that name"
    r = await hub.http("PATCH", f"/api/network/devices/{laptop_id}", cookie=me, json_body={"name": "Tablet"})
    assert r.json() == {"id": laptop_id, "name": "Tablet"}
    me_id = me.split(".")[0]
    r = await hub.http("DELETE", f"/api/network/devices/{me_id}", cookie=me)
    assert r.status == 400 and r.json()["text"] == "This is the device you are using"
    assert (await hub.http("DELETE", f"/api/network/devices/{laptop_id}", cookie=me)).json() == {"ok": True}
    assert await line.closed() == 4003
    r = await hub.http("POST", "/api/network/pair", cookie=me, json_body={"name": "Kitchen"})
    link = r.json()["link"]
    assert link.startswith(f"http://127.0.0.1:{hub.port}/pair#c=") and r.json()["expires"] > 0
    cards = (await hub.http("GET", "/api/cards", cookie=me)).json()
    assert cards[0]["summary"] == 'Pairing open for "Kitchen"' and cards[0]["status"] == "attention"
    code = link.split("#c=")[1]
    assert (await hub.http("POST", "/api/pair", json_body={"code": code})).status == 200
    bad = await hub.http("POST", "/api/network/pair", cookie=me, json_body={"name": ""})
    assert bad.status == 400


async def test_assistant_switch_then_the_key_gate_mcp(hub: Hub) -> None:
    c = hub.pair()
    view = (await hub.http("GET", "/api/assistant", cookie=c)).json()
    assert "mcp_key" not in view, "the key is shown once, when made; never in a view"
    assert view == {"on": False, "endpoints": [f"http://127.0.0.1:{hub.port}/mcp"], "clients": [], "port": hub.port,
                    "openwebui": {"url": "http://127.0.0.1:3000", "model": "", "key": False, "tools": "",
                                  "keep": 6, "context": 8192}}
    key = hub.core.mcp.key()
    assert isinstance(key, str) and len(key) >= 43

    async def ping(auth: str | None = f"Bearer {key}") -> tuple[int, str]:
        hdrs = {"Content-Type": "application/json", **({"Authorization": auth} if auth else {})}
        r = await hub.http("POST", "/mcp", body='{"jsonrpc":"2.0","id":1,"method":"ping"}', origin=False, headers=hdrs)
        return r.status, r.body.decode()

    assert (await ping())[0] == 503 and (await ping(None))[0] == 503, "Off: 503 whatever key is sent"
    on = (await hub.http("PATCH", "/api/assistant", cookie=c, json_body={"on": True})).json()
    assert on["on"] is True and "mcp_key" not in on
    assert await ping(None) == (401, "MCP key missing or wrong")
    assert await ping("Bearer nope") == (401, "MCP key missing or wrong")
    assert await ping(key) == (401, "MCP key missing or wrong"), "the Bearer scheme is required"
    assert (await hub.http("GET", "/api/assistant", cookie=c)).json()["clients"][0]["status"] == \
        "Refused: MCP key missing or wrong"
    assert (await ping())[0] == 200 and (await ping(f"bearer  {key} "))[0] == 200
    clients = (await hub.http("GET", "/api/assistant", cookie=c)).json()["clients"]
    assert clients[0]["addr"] == "127.0.0.1" and clients[0]["status"] == "OK"
    assert (await hub.http("GET", "/api/cards", cookie=c)).json()[1]["summary"] == "On · 1 client"
    rotated = await hub.http("POST", "/api/assistant/mcp-key", cookie=c, json_body={})
    new = rotated.json()["mcp_key"]
    assert rotated.status == 200 and rotated.json() == {"mcp_key": new} and new != key
    assert (await ping())[0] == 401 and (await ping(f"Bearer {new}"))[0] == 200, "the old key stops at once"
    lan = await hub.http("POST", "/mcp", body='{"jsonrpc":"2.0","id":1,"method":"ping"}', origin=False,
                         headers={"Content-Type": "application/json", "Authorization": f"Bearer {new}",
                                  "X-Forwarded-For": "192.168.0.50"})
    assert lan.status == 200, "the peer address is the socket's, never a header"
    assert (await hub.http("POST", "/api/assistant/mcp-key")).status in (401, 403), "a paired screen only"
    assert (await hub.http("PATCH", "/api/assistant", cookie=c, json_body={"on": "yes"})).status == 400
    await hub.http("PATCH", "/api/assistant", cookie=c, json_body={"on": False})
    assert (await ping(f"Bearer {new}"))[0] == 503
    hub.core.store.flush()
    assert json.loads((hub.data / "core" / "mcp.json").read_text())["key"] == new


def test_the_key_is_made_once(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    doc = JsonDoc(path, MCP_DEFAULT)
    key = McpAccess(doc).key()
    doc.flush()
    assert McpAccess(JsonDoc(path, MCP_DEFAULT)).key() == key


def test_what_an_older_hub_kept_is_scrubbed_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"version": 1, "enabled": True, "key_hash": "sha256:abc", "max_proposals": 5,
                                "proposal_ttl_min": 30}))
    doc = JsonDoc(path, MCP_DEFAULT)
    access = McpAccess(doc)
    doc.flush()
    assert access.state()["on"] is True and set(json.loads(path.read_text())) == {"version", "enabled", "key"}


async def test_the_port_changes_from_settings_then_the_hub_restarts(hub: Hub) -> None:
    import json as _json
    restarts: list[int] = []
    hub.core.restart_service = lambda: restarts.append(1)
    c = hub.pair()
    for bad in (80, 70000, "x", hub.port):
        assert (await hub.http("PATCH", "/api/assistant/port", cookie=c, json_body={"port": bad})).status == 400
    # A port free now: a fixed one in the kernel's ephemeral range can be held by an open connection of the suite.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    r = await hub.http("PATCH", "/api/assistant/port", cookie=c, json_body={"port": free})
    assert r.status == 200 and r.json()["endpoints"] == [f"http://127.0.0.1:{free}/mcp"]
    hub.core.store.flush()
    assert _json.loads((hub.data / "settings.json").read_text())["server"]["port"] == free
    assert (hub.data / "run" / "restart").exists()
    await asyncio.sleep(1.2)
    assert restarts == [1]


async def test_restart_from_settings(hub: Hub) -> None:
    restarts: list[int] = []
    hub.core.restart_service = lambda: restarts.append(1)
    c = hub.pair()
    assert (await hub.http("POST", "/api/settings/restart", json_body={})).status == 401, "a paired screen only"
    r = await hub.http("POST", "/api/settings/restart", cookie=c, json_body={})
    assert r.status == 200 and r.json() == {"restarting": True}
    assert (hub.data / "run" / "restart").exists()
    await asyncio.sleep(0.7)
    assert restarts == [1]
