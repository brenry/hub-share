"""The in-house MCP endpoint: `POST /mcp`, JSON-RPC 2.0, MCP 2025-11-25, tools only.

Stateless (no session id), JSON replies only, GET and DELETE answer 405, notifications 202.
Versions negotiated: 2025-11-25, 2025-06-18, 2025-03-26. An unsupported `MCP-Protocol-Version`
gets 400 with a plain-text body, which newer (2026-07-28) clients treat as "fall back to
initialize". A present but foreign `Origin` gets 403.

Two gates, in this order: the Assistant switch (Off -> 503, whatever key is sent, so Off never says whether a key
is right), then the key (`Authorization: Bearer <key>`; missing or wrong -> 401). The key is made once with
`secrets.token_urlsafe(32)`, kept in core/mcp.json beside the switch, shown on the Assistant card and pasted into
Open WebUI's tool server (Auth: Bearer), which sends it on every request, the initialize handshake included:
v0.11.4 builds `Authorization: Bearer <key>` for auth_type "bearer" (utils/tools.py:150-151, utils/headers.py:29-31),
hands it to `MCPClient.connect` (utils/middleware.py:2365-2378), which gives it to `streamablehttp_client` (utils/mcp/
client.py:67-73) and so to the httpx client's default headers (utils/mcp/client.py:39-43) used for every POST.
"""
from __future__ import annotations

import hmac
import json
import secrets
import time
from collections.abc import Callable
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from hub import VERSION
from hub.core.api import Invalid
from hub.core.features import Tool
from hub.core.guard import Gate
from hub.core.messages import Refused
from hub.core.schema import check
from hub.core.store import JsonDoc

VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
DEFAULT = {"version": 1, "enabled": False}
CLIENT_WINDOW_S = 600
MAX_CLIENTS = 8
BODY_LIMIT = 1 << 20
RETIRED = ("key_hash", "max_proposals", "proposal_ttl_min")   # what an older hub kept here; scrubbed from disk


class McpAccess:
    """On/off, the key and recent clients (memory only). The Assistant card drives it."""

    def __init__(self, doc: JsonDoc, on_change: Callable[[], None] = lambda: None) -> None:
        self.doc, self.on_change = doc, on_change
        if set(RETIRED) & set(doc.get()):
            doc.replace({k: v for k, v in doc.get().items() if k not in RETIRED})
        if not isinstance(doc.get().get("key"), str) or not doc.get()["key"]:
            doc.patch({"key": secrets.token_urlsafe(32)})
        self.endpoints: list[str] = []
        self._clients: dict[str, dict] = {}

    def state(self) -> dict:
        return {"on": bool(self.doc.get().get("enabled"))}

    def key(self) -> str:
        return str(self.doc.get()["key"])

    def rotate_key(self) -> str:
        """A new key; the old one stops working at once."""
        self.doc.patch({"key": secrets.token_urlsafe(32)})
        self.on_change()
        return self.key()

    def key_ok(self, authorization: str | None) -> bool:
        scheme, _, given = (authorization or "").strip().partition(" ")
        return scheme.lower() == "bearer" and hmac.compare_digest(given.strip().encode(), self.key().encode())

    def set_enabled(self, on: bool) -> None:
        self.doc.patch({"enabled": bool(on)})
        self.on_change()

    def seen(self, addr: str, name: str | None, status: str) -> None:
        old = self._clients.pop(addr, {})
        self._clients[addr] = {"addr": addr, "name": name or old.get("name"), "at": time.time(), "status": status}
        while len(self._clients) > MAX_CLIENTS:
            self._clients.pop(next(iter(self._clients)))
        if old.get("status") != status or not old:
            self.on_change()

    def clients(self) -> list[dict]:
        cutoff = time.time() - CLIENT_WINDOW_S
        return [dict(c) for c in reversed(self._clients.values()) if c["at"] >= cutoff]


def _rpc(rid: Any, result: Any = None, code: int | None = None, message: str = "") -> dict:
    if code is None:
        return {"jsonrpc": "2.0", "id": rid, "result": result}
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


class McpEndpoint:
    def __init__(self, gate: Gate, access: McpAccess, tools: dict[str, tuple[Tool, Any]]) -> None:
        self.gate, self.access, self.tools = gate, access, tools

    def route(self) -> Route:
        return Route("/mcp", self.endpoint, methods=["GET", "POST", "DELETE"], max_body_size=BODY_LIMIT)

    async def endpoint(self, request: Request) -> Response:
        if request.method != "POST":
            return Response(status_code=405, headers={"allow": "POST"})
        if "origin" in request.headers and not self.gate.origin_ok(request):
            return PlainTextResponse("Origin not allowed", 403)
        if not self.access.state()["on"]:
            return PlainTextResponse("Assistant access is off", 503)
        peer = request.client.host if request.client else ""
        if not self.access.key_ok(request.headers.get("authorization")):
            self.access.seen(peer, None, "Refused: MCP key missing or wrong")
            return PlainTextResponse("MCP key missing or wrong", 401)
        version = request.headers.get("mcp-protocol-version")
        if version is not None and version not in VERSIONS:
            self.access.seen(peer, None, "Refused: unsupported protocol version")
            return PlainTextResponse("Unsupported MCP-Protocol-Version", 400)
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            return PlainTextResponse("Send JSON", 415)
        try:
            msg = json.loads(await request.body())
        except ValueError:
            return JSONResponse(_rpc(None, code=-32700, message="Parse error"), 400)
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return JSONResponse(_rpc(None, code=-32600, message="Invalid request"), 400)
        if "method" not in msg:
            return Response(status_code=202) if "id" in msg else JSONResponse(_rpc(None, code=-32600,
                                                                                    message="Invalid request"), 400)
        method, params, rid = msg["method"], msg.get("params") or {}, msg.get("id")
        if not isinstance(method, str) or not isinstance(params, dict):
            return JSONResponse(_rpc(None, code=-32600, message="Invalid request"), 400)
        if "id" not in msg:
            return Response(status_code=202)
        if isinstance(rid, bool) or not isinstance(rid, (str, int)):
            return JSONResponse(_rpc(None, code=-32600, message="Invalid request id"), 400)
        name = None
        if method == "initialize" and isinstance(params.get("clientInfo"), dict):
            raw = params["clientInfo"].get("name")
            name = raw[:60] if isinstance(raw, str) else None
        self.access.seen(peer, name, "OK")
        return JSONResponse(await self.handle(rid, method, params))

    async def handle(self, rid: Any, method: str, params: dict) -> dict:
        if method == "initialize":
            asked = params.get("protocolVersion")
            return _rpc(rid, {"protocolVersion": asked if asked in VERSIONS else VERSIONS[0],
                              "capabilities": {"tools": {"listChanged": False}},
                              "serverInfo": {"name": "hub", "version": VERSION}})
        if method == "ping":
            return _rpc(rid, {})
        if method == "tools/list":
            return _rpc(rid, {"tools": [{"name": t.name, "description": t.description, "inputSchema": t.input_schema}
                                        for t, _ in self.tools.values()]})
        if method == "tools/call":
            entry = self.tools.get(params.get("name")) if isinstance(params.get("name"), str) else None
            if entry is None:
                return _rpc(rid, code=-32602, message=f"Unknown tool: {params.get('name')}")
            return _rpc(rid, await self.call(entry, params.get("arguments")))
        return _rpc(rid, code=-32601, message=f"Method not found: {method}")

    async def call(self, entry: tuple[Tool, Any], arguments: Any) -> dict:
        tool, ctx = entry
        try:
            result = await tool.fn(ctx, check(tool.input_schema, arguments))
            text, error = json.dumps(result, separators=(",", ":"), ensure_ascii=False), False
        except (Invalid, Refused) as e:
            text, error = e.text, True
        except Exception:
            text, error = "Something went wrong in the hub", True
        return {"content": [{"type": "text", "text": text}], "isError": error}
