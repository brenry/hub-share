"""The guard: Host allow-list and security headers for everything, then per-route admission.

Route classes:
  public  shell pages            any paired device's address
  pair    /pair, /api/pair, assets  also loopback, and anyone while a pairing code is open
  screen  API, /bus, /files ...   screen cookie `<id>.<secret>`, only from that device's addresses
`/mcp` admits itself (core/mcp.py): the Origin check, the Assistant switch, then its own Bearer key.
Mutating browser requests need the exact Origin and a JSON or image content type, which
forces a CORS preflight that is never granted. No CORS headers are ever sent.
"""
from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.exceptions import HTTPException
from starlette.requests import HTTPConnection, Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from starlette.websockets import WebSocket

from hub.core.api import Device, Invalid
from hub.core.devices import Devices, is_loopback
from hub.core.messages import Refused

CSP = ("default-src 'self'; img-src 'self' blob: data:; connect-src 'self'; style-src 'self'; font-src 'self'; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
HEADERS = [(b"content-security-policy", CSP.encode()), (b"x-frame-options", b"DENY"),
           (b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"),
           (b"cross-origin-opener-policy", b"same-origin"), (b"cross-origin-resource-policy", b"same-origin")]
COOKIE = "hub_screen"
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
JSON_TYPES = {"application/json"}
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
SOUND_TYPES = {"audio/wav"}
BODY_TYPES = {"json": JSON_TYPES, "image": IMAGE_TYPES, "sound": SOUND_TYPES, "any": JSON_TYPES | IMAGE_TYPES}
STATUS = {"invalid": 400, "forbidden": 403, "not_found": 404, "queue_full": 409, "rate": 429, "unavailable": 503}


class Refusal(Exception):
    def __init__(self, status: int, text: str) -> None:
        super().__init__(text)
        self.status, self.text = status, text


class Gate:
    """Decides who may use a route. Shared by HTTP routes, WebSocket routes and the MCP endpoint."""

    def __init__(self, devices: Devices, hosts: frozenset[str]) -> None:
        self.devices, self.hosts = devices, hosts
        self._fails: dict[str, deque[float]] = {}
        self._blocked: dict[str, float] = {}

    def repair(self, peer: str, name: str | None) -> str:
        cmd = f'hub pair --name "{name}"' if name else 'hub pair --name "<device name>"'
        return f"Pair this device again. Not allowed from {peer}. On the server run: {cmd}"

    def origin_ok(self, conn: HTTPConnection) -> bool:
        origin = conn.headers.get("origin")
        return origin is not None and origin.lower() == "http://" + conn.headers.get("host", "").lower()

    def admit(self, conn: HTTPConnection, auth: str) -> Device | None:
        peer = conn.client.host if conn.client else ""
        is_ws = conn.scope["type"] == "websocket"
        mutating = is_ws or conn.scope.get("method") in MUTATING
        if mutating and not self.origin_ok(conn):
            raise Refusal(403, "Origin not allowed")
        dev = self.devices.verify(conn.cookies.get(COOKIE))
        if auth == "pair":
            if is_loopback(peer) or self.devices.known_addr(peer) or self.devices.pairing_open():
                return dev if dev and self.devices.from_addr(dev, peer) else None
            raise Refusal(403, self.repair(peer, dev.name if dev else None))
        if dev is not None and not self.devices.from_addr(dev, peer):
            raise Refusal(403, self.repair(peer, dev.name))
        if dev is not None or (auth == "public" and self.devices.known_addr(peer)):
            return dev
        if self.devices.known_addr(peer):
            raise Refusal(401, "This screen isn't paired")
        raise Refusal(403, self.repair(peer, None))

    # ---------------------------------------------------------------- pairing rate limit
    def pair_blocked(self, peer: str) -> bool:
        until = self._blocked.get(peer, 0.0)
        if until <= time.monotonic():
            self._blocked.pop(peer, None)
            return False
        return True

    def pair_failed(self, peer: str) -> None:
        now = time.monotonic()
        fails = self._fails.setdefault(peer, deque())
        fails.append(now)
        while fails and fails[0] < now - 60:
            fails.popleft()
        if len(fails) >= 5:
            self._blocked[peer] = now + 600
            fails.clear()


def refusal_response(path: str, status: int, text: str) -> Response:
    if path.startswith(("/api/", "/mcp")):
        return JSONResponse({"code": "forbidden" if status == 403 else "unpaired", "text": text}, status)
    return PlainTextResponse(text, status)


def error_response(e: Exception) -> Response:
    if isinstance(e, Invalid):
        return JSONResponse({"code": "invalid", "field": e.field, "text": e.text}, 400)
    if isinstance(e, Refused):
        return JSONResponse({"code": e.code, "text": e.text}, STATUS.get(e.code, 400))
    if isinstance(e, json.JSONDecodeError):
        return JSONResponse({"code": "invalid", "text": "Send valid JSON"}, 400)
    return JSONResponse({"code": "internal", "text": f"Something went wrong in the hub: {type(e).__name__}"}, 500)


def _content_ok(request: Request, body: str) -> bool:
    if request.method not in MUTATING:
        return True
    has_body = request.headers.get("content-length", "0") != "0" or "transfer-encoding" in request.headers
    if request.method != "POST" and not has_body:
        return True
    ctype = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    return ctype in BODY_TYPES[body]


def http_route(gate: Gate, path: str, method: str, fn: Callable[[Request], Awaitable[Any]], auth: str,
               limit: int = 65_536, body: str = "json") -> Route:
    """A Starlette route whose endpoint runs admission, the content-type rule and a body cap first."""

    async def endpoint(request: Request) -> Response:
        try:
            request.state.device = gate.admit(request, auth)
        except Refusal as r:
            return refusal_response(request.url.path, r.status, r.text)
        if not _content_ok(request, body):
            return JSONResponse({"code": "invalid", "text": "Send JSON or an image with the right content type"}, 415)
        try:
            result = await fn(request)
        except HTTPException:
            raise
        except Exception as e:
            return error_response(e)
        if isinstance(result, Response):
            return result
        if result is None:
            return Response(status_code=204)
        return JSONResponse(result)

    return Route(path, endpoint, methods=[method], max_body_size=limit)


def ws_route(gate: Gate, path: str, fn: Callable[[WebSocket, Device], Awaitable[None]], auth: str,
             unpaired_close: int | None = None) -> WebSocketRoute:
    """Refused sockets get HTTP 403 at the handshake; an unpaired screen may get a close code instead."""

    async def endpoint(ws: WebSocket) -> None:
        try:
            device = gate.admit(ws, auth)
        except Refusal as r:
            if r.status == 401 and unpaired_close is not None:
                await ws.accept()
                await ws.close(unpaired_close)
            else:
                await ws.close(1008)
            return
        if device is None:
            await ws.close(1008)
            return
        await fn(ws, device)

    return WebSocketRoute(path, endpoint)


class Guard:
    """Outermost middleware: exact Host check, security headers, `no-store` by default."""

    def __init__(self, app: ASGIApp, gate: Gate) -> None:
        self.app, self.gate = app, gate

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        host = dict(scope["headers"]).get(b"host", b"").decode("latin-1").lower()
        if host not in self.gate.hosts:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await self._wrap(PlainTextResponse("Unknown host name", 400), scope, receive, send)
            return
        await self._wrap(self.app, scope, receive, send)

    @staticmethod
    async def _wrap(app: ASGIApp, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                names = {k.lower() for k, _ in headers}
                headers += [(k, v) for k, v in HEADERS if k not in names]
                if b"cache-control" not in names:
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        await app(scope, receive, send_headers)
