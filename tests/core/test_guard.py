"""The guard over real HTTP and WebSocket: Host, Origin, content types, cookies, pairing."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.core.harness import Hub, own_modules, start_hub
from tests.fakes.screen import http, ws_status

CSP_START = "default-src 'self'"


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    h = await start_hub(tmp_path / "data", modules=own_modules(), dist=tmp_path / "no-ui")
    yield h
    await h.close()


async def test_host_rules(hub: Hub) -> None:
    p = hub.port
    assert (await http(p, "GET", "/api/cards", host=f"127.0.0.1:{p}")).status == 403  # unpaired, but host ok
    for bad in ("evil.example", f"evil.example:{p}", "127.0.0.1", f"127.0.0.1:{p + 1}", f"[::1]:{p}"):
        r = await http(p, "GET", "/", host=bad)
        assert r.status == 400 and r.text == "Unknown host name"
        assert r.headers["content-security-policy"].startswith(CSP_START)
    assert (await http(p, "GET", "/", host=f"LOCALHOST:{p}")).status == 403
    assert (await http(p, "GET", "/", host="")).status == 400
    assert await ws_status(p, "/bus", {"Origin": f"http://evil.example:{p}"}, host=f"evil.example:{p}") == 403


async def test_shell_needs_a_paired_address_and_pairing_is_open_to_loopback(hub: Hub, tmp_path: Path) -> None:
    r = await hub.http("GET", "/")
    assert r.status == 403 and 'hub pair --name "<device name>"' in r.text
    assert (await hub.http("GET", "/pair")).status == 200
    cookie = hub.pair()
    r = await hub.http("GET", "/", cookie=cookie)
    assert r.status == 200 and r.text == "Hub is running. Its interface is not installed."
    assert (await hub.http("GET", "/media")).status == 200
    assert (await hub.http("GET", "/screen/3")).status == 200
    assert (await hub.http("GET", "/screen/12")).status == 404


async def test_screen_routes_check_the_cookie(hub: Hub) -> None:
    assert (await hub.http("GET", "/api/cards")).status == 403
    cookie = hub.pair()
    assert (await hub.http("GET", "/api/cards", cookie=cookie)).status == 200
    tampered = cookie[:-2] + ("AA" if not cookie.endswith("AA") else "BB")
    r = await hub.http("GET", "/api/cards", cookie=tampered)
    assert r.status == 401 and r.json()["text"] == "This screen isn't paired"
    assert (await hub.http("GET", "/api/cards", cookie="d_nothere1.secret")).status == 401


async def test_a_moved_device_is_told_to_pair_again(hub: Hub) -> None:
    cookie = hub.pair(name="Desktop", addr="192.0.2.50")
    r = await hub.http("GET", "/", cookie=cookie)
    assert r.status == 403
    assert r.text == ('Pair this device again. Not allowed from 127.0.0.1. On the server run: '
                      'hub pair --name "Desktop"')
    assert (await hub.http("GET", "/api/network", cookie=cookie)).json()["code"] == "forbidden"
    assert await ws_status(hub.port, "/bus", {"Origin": hub.origin, "Cookie": f"hub_screen={cookie}"}) == 403


async def test_origin_and_content_type_on_mutations(hub: Hub) -> None:
    cookie = hub.pair()
    body = {"vram": {"idle_minutes": 15}}
    assert (await hub.http("PATCH", "/api/settings", cookie=cookie, json_body=body)).status == 200
    for origin in (None, "null", f"http://127.0.0.1:{hub.port + 1}", "http://evil.example"):
        headers = {"Origin": origin} if origin else {}
        r = await hub.http("PATCH", "/api/settings", cookie=cookie, json_body=body, headers=headers, origin=False)
        assert r.status == 403, origin
    r = await hub.http("PATCH", "/api/settings", cookie=cookie, body='{"diagnostics":true}',
                       headers={"Content-Type": "text/plain"})
    assert r.status == 415
    r = await hub.http("POST", "/api/network/pair", cookie=cookie, body="")
    assert r.status == 415
    assert "access-control-allow-origin" not in r.headers


async def test_body_caps(hub: Hub) -> None:
    cookie = hub.pair()
    big = '{"name":"' + "x" * 5000 + '"}'
    r = await hub.http("POST", "/api/network/pair", cookie=cookie, body=big,
                       headers={"Content-Type": "application/json"})
    assert r.status == 413
    r = await hub.http("PATCH", "/api/settings", cookie=cookie, body="{bad json",
                       headers={"Content-Type": "application/json"})
    assert r.status == 400 and r.json()["text"] == "Send valid JSON"


async def test_pairing_flow_and_rate_limit(hub: Hub) -> None:
    code, _ = hub.core.devices.mint_code("Desktop")
    r = await hub.http("POST", "/api/pair", json_body={"code": code}, origin=False)
    assert r.status == 403  # a code needs the page's Origin
    r = await hub.http("POST", "/api/pair", json_body={"code": code})
    assert r.status == 200 and r.json()["device"]["name"] == "Desktop" and "secret" not in r.json()
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Max-Age=34560000" in cookie
    value = cookie.split(";")[0].split("=", 1)[1]
    assert (await hub.http("GET", "/api/cards", cookie=value)).status == 200
    assert (await hub.http("POST", "/api/pair", json_body={"code": code})).status == 400
    for _ in range(4):  # failures 2 to 5 within a minute (the first was the used code)
        assert (await hub.http("POST", "/api/pair", json_body={"code": "wrong-code-123"})).status == 400
    good, _ = hub.core.devices.mint_code("Laptop")
    assert (await hub.http("POST", "/api/pair", json_body={"code": good})).status == 429


async def test_mcp_takes_its_own_key_and_that_key_never_opens_the_api(hub: Hub) -> None:
    hub.core.mcp.set_enabled(True)
    body, auth = '{"jsonrpc":"2.0","id":1,"method":"ping"}', {"Authorization": f"Bearer {hub.core.mcp.key()}"}
    ok = await hub.http("POST", "/mcp", body=body, headers={"Content-Type": "application/json", **auth}, origin=False)
    assert ok.status == 200
    assert (await hub.http("GET", "/api/cards", headers=auth)).status in (401, 403)
    assert (await hub.http("GET", "/api/cards", headers={"Authorization": "Bearer anything"})).status in (401, 403)


async def test_security_headers_on_success_and_errors(hub: Hub) -> None:
    cookie = hub.pair()
    for path, status in (("/api/cards", 200), ("/nothing", 404), ("/files/out/x.svg", 404)):
        r = await hub.http("GET", path, cookie=cookie)
        assert r.status == status
        assert r.headers["content-security-policy"].startswith(CSP_START)
        assert "form-action 'none'" in r.headers["content-security-policy"]
        assert r.headers["x-frame-options"] == "DENY" and r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert r.headers["cross-origin-resource-policy"] == "same-origin"
        assert r.headers["cache-control"] == "no-store"
        assert "server" not in r.headers


async def test_built_ui_is_served_with_the_right_cache_rules(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Hub</title>")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("nope")
    hub = await start_hub(tmp_path / "data", dist=dist)
    try:
        cookie = hub.pair()
        r = await hub.http("GET", "/", cookie=cookie)
        assert r.status == 200 and r.headers["cache-control"] == "no-store" and r.text.startswith("<!doctype")
        assert r.headers["content-type"] == "text/html; charset=utf-8"
        assert "Max-Age=34560000" in r.headers["set-cookie"]
        r = await hub.http("GET", "/assets/index-abc123.js")
        assert r.status == 200 and r.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert (await hub.http("GET", "/assets/../secret.txt")).status == 404
        assert (await hub.http("GET", "/assets/%2e%2e/secret.txt")).status == 404
        assert (await hub.http("GET", "/pair")).text.startswith("<!doctype")
    finally:
        await hub.close()
