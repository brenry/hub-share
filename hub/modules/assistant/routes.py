"""Assistant routes: the card (GET|PATCH /api/assistant, with `mcp_key`; clients are memory only, last 10 minutes;
POST /api/assistant/mcp-key -> {mcp_key} makes a new MCP key, the old one stops working at once), the Open WebUI
link settings (PATCH /api/assistant/openwebui; GET .../models and .../tool-servers list Open WebUI's) and the
chat (GET|POST|DELETE /api/assistant/chat; DELETE is New chat and emits `chat.cleared`)."""
from __future__ import annotations

from typing import Any, Protocol

from starlette.requests import Request
from starlette.responses import JSONResponse

from hub.core.api import CardState, Ctx, Invalid

from . import chat


class McpAdmin(Protocol):
    """The core-owned surface the controller hands this module as `ctx.mcp`."""

    endpoints: list[str]

    def state(self) -> dict: ...
    def key(self) -> str: ...
    def rotate_key(self) -> str: ...
    def set_enabled(self, on: bool) -> None: ...
    def clients(self) -> list[dict]: ...


class PortAdmin(Protocol):
    port: int

    def set_port(self, port: int) -> None: ...


class AssistantCtx(Ctx, Protocol):
    mcp: McpAdmin
    network: PortAdmin


def _view(ctx: AssistantCtx) -> dict:
    link = chat.get(ctx).config()
    return {**ctx.mcp.state(), "endpoints": list(ctx.mcp.endpoints),
            "clients": ctx.mcp.clients(), "port": ctx.network.port,
            "openwebui": {"url": link["url"], "model": link["model"], "key": bool(link["key"]), "tools": link["tools"],
                          "keep": link["keep"], "context": link["context"]}}


async def view(ctx: AssistantCtx, request: Request) -> dict:
    return _view(ctx)


async def switch(ctx: AssistantCtx, request: Request) -> dict:
    body: Any = await request.json()
    on = body.get("on") if isinstance(body, dict) else None
    if not isinstance(on, bool):
        raise Invalid("on", "on must be true or false")
    ctx.mcp.set_enabled(on)
    return _view(ctx)


async def rotate_key(ctx: AssistantCtx, request: Request) -> dict:
    """A new MCP key, shown this once; the old one stops working at once (paste the new one into Open WebUI)."""
    return {"mcp_key": ctx.mcp.rotate_key()}


def card(ctx: AssistantCtx) -> CardState:
    if not ctx.mcp.state()["on"]:
        return CardState("Off", "off")
    clients = ctx.mcp.clients()
    refused = next((c for c in clients if c["status"].startswith("Refused")), None)
    if refused is not None:
        return CardState(f"Refused a call from {refused['addr']}", "attention")
    if not clients:
        return CardState("On · no calls yet", "ok")
    return CardState(f"On · {len(clients)} client{'' if len(clients) == 1 else 's'}", "ok")


async def chat_view(ctx: Ctx, request: Request) -> dict:
    return chat.get(ctx).view()


async def chat_send(ctx: Ctx, request: Request) -> JSONResponse:
    body: Any = await request.json()
    text = body.get("text") if isinstance(body, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise Invalid("text", "Write a message")
    session = chat.get(ctx)
    if session.busy:
        return JSONResponse({"code": "busy", "text": "The assistant is busy"}, 409)
    return JSONResponse({"turn": session.send(text.strip())}, 202)


async def chat_clear(ctx: Ctx, request: Request) -> dict:
    """New chat: the conversation goes, here and in Open WebUI, and the core hears `chat.cleared` (the Generate screen
    empties the prompt box and the assistant's draft with it)."""
    session = chat.get(ctx)
    session.clear()
    ctx.emit(chat.CLEARED, {})
    return session.view()


async def set_port(ctx: AssistantCtx, request: Request) -> dict:
    """Save a new port and restart the hub on it (screens must then open the new address)."""
    body: Any = await request.json()
    port = body.get("port") if isinstance(body, dict) else None
    ctx.network.set_port(port)
    return {"port": port, "endpoints": [e.replace(f":{ctx.network.port}/", f":{port}/") for e in ctx.mcp.endpoints]}


async def openwebui(ctx: AssistantCtx, request: Request) -> dict:
    """Where the chat goes: Open WebUI's address (loopback), the API key, the model name and the tool server; and
    `keep`, how many exchanges the conversation keeps (1 to 20); `context`, the tokens the model may read (0 leaves
    it to Open WebUI, else 2048 to 131072)."""
    chat.get(ctx).configure(await request.json())
    return _view(ctx)


async def openwebui_models(ctx: AssistantCtx, request: Request) -> dict:
    """Open WebUI's model list with the saved address and key; also the connection test."""
    return await chat.get(ctx).list_models()


async def openwebui_tool_servers(ctx: AssistantCtx, request: Request) -> dict:
    """Open WebUI's MCP tool servers with the saved address and key (an admin's key), for the tool server pick."""
    return await chat.get(ctx).list_tool_servers()
