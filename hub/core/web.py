"""The shell pages (`web/dist/index.html`), hashed assets, and `POST /api/pair`.

A pairing code needs the page's exact Origin (the guard checks it) and answers with the HttpOnly cookie.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import BaseRoute

from hub.core.api import Invalid
from hub.core.devices import Devices
from hub.core.guard import COOKIE, Gate, http_route

COOKIE_AGE = 34_560_000
PLACEHOLDER = "Hub is running. Its interface is not installed."


def set_cookie(response: Response, value: str) -> None:
    response.set_cookie(COOKIE, value, max_age=COOKIE_AGE, path="/", httponly=True, samesite="strict")


def web_routes(gate: Gate, devices: Devices, dist: Path) -> list[BaseRoute]:
    index, assets = dist / "index.html", Path(os.path.realpath(dist / "assets"))

    async def page(request: Request) -> Response:
        n = request.path_params.get("n")
        if n is not None and not 1 <= n <= 9:
            return PlainTextResponse("Not Found", 404)
        if not index.is_file():
            return PlainTextResponse(PLACEHOLDER)
        response = FileResponse(index, media_type="text/html; charset=utf-8", headers={"cache-control": "no-store"})
        if request.state.device is not None:
            set_cookie(response, request.cookies[COOKIE])
        return response

    async def asset(request: Request) -> Response:
        path = Path(os.path.realpath(assets / request.path_params["path"]))
        if os.path.commonpath([assets, path]) != str(assets) or not path.is_file():
            return PlainTextResponse("Not Found", 404)
        return FileResponse(path, headers={"cache-control": "public, max-age=31536000, immutable"})

    async def pair(request: Request) -> Response:
        peer = request.client.host if request.client else ""
        if gate.pair_blocked(peer):
            return JSONResponse({"code": "rate", "text": "Too many tries. Wait 10 minutes."}, 429)
        body: Any = await request.json()
        code = body.get("code") if isinstance(body, dict) else None
        if not isinstance(code, str):
            raise Invalid("code", "Open the pairing link again")
        result = devices.redeem(code, peer)
        if result is None:
            gate.pair_failed(peer)
            return JSONResponse({"code": "invalid", "text": "That pairing link is not valid any more"}, 400)
        device, secret = result
        response = JSONResponse({"device": {"id": device.id, "name": device.name}})
        set_cookie(response, f"{device.id}.{secret}")
        return response

    shell = [http_route(gate, p, "GET", page, "public") for p in ("/", "/media", "/clips", "/screen/{n:int}")]
    return [*shell, http_route(gate, "/pair", "GET", page, "pair"),
            http_route(gate, "/assets/{path:path}", "GET", asset, "pair"),
            http_route(gate, "/api/pair", "POST", pair, "pair", limit=4096)]
