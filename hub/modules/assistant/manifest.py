"""Assistant: the Settings card (MCP access on/off and key, the Open WebUI link) and the chat box, via Open WebUI.

The MCP endpoint itself is core (`POST /mcp`); deleting this folder removes the card and the chat.
"""
from __future__ import annotations

from hub.core.api import Card, Module, Route

from . import chat, routes

MODULE = Module(
    id="assistant",
    title="Assistant",
    routes=(Route("GET", "", routes.view),
            Route("PATCH", "", routes.switch, body_limit=1024),
            Route("POST", "/mcp-key", routes.rotate_key, body_limit=256),
            Route("PATCH", "/port", routes.set_port, body_limit=256),
            Route("PATCH", "/openwebui", routes.openwebui, body_limit=4096),
            Route("GET", "/openwebui/models", routes.openwebui_models),
            Route("GET", "/openwebui/tool-servers", routes.openwebui_tool_servers),
            Route("GET", "/chat", routes.chat_view),
            Route("POST", "/chat", routes.chat_send),
            Route("DELETE", "/chat", routes.chat_clear)),
    lanes=("chat",),
    card=Card(title="Assistant", order=920, state=routes.card),
    start=chat.start,
    stop=chat.stop,
    listens={"session.ended": chat.on_session_ended, chat.NOTE: chat.on_note},
)
