"""Drive the hub's /mcp endpoint with the official MCP SDK client (run by a separate venv's python).

Usage: python -I mcp_driver.py URL KEY -> prints one JSON report on stdout. The key goes as `Authorization: Bearer`
in the client's headers, as Open WebUI sends it (on every request, initialize included).
Works with mcp 1.x (ClientSession + streamablehttp_client) and 2.x (Client, era auto-negotiation).
"""
from __future__ import annotations

import asyncio
import json
import sys
from importlib.metadata import version
from typing import Any


def field(obj: Any, camel: str, snake: str) -> Any:
    """1.x models use camelCase attributes, 2.x snake_case."""
    return getattr(obj, snake) if hasattr(obj, snake) else getattr(obj, camel)


def text(result: Any) -> tuple[bool, str]:
    return bool(field(result, "isError", "is_error")), "".join(getattr(c, "text", "") for c in result.content)


async def v1(url: str, headers: dict) -> dict:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            return {"protocol": init.protocolVersion, "server": init.serverInfo.name,
                    **await calls(session.list_tools, session.call_tool)}


async def v2(url: str, headers: dict) -> dict:
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    http = httpx2.AsyncClient(headers=headers)
    async with Client(streamable_http_client(url, http_client=http)) as client:
        init = client.session.initialize_result
        if init is None:
            return {"protocol": "modern (no initialize)", "server": None}
        return {"protocol": field(init, "protocolVersion", "protocol_version"),
                "server": field(init, "serverInfo", "server_info").name, **await calls(client.list_tools,
                                                                                       client.call_tool)}


async def calls(list_tools: Any, call_tool: Any) -> dict:
    tools = await list_tools()
    listed = text(await call_tool("list_image_models", {}))
    try:
        bad = text(await call_tool("generate_image", {"prompt": "x"}))
    except Exception as e:  # a client may refuse bad arguments itself
        bad = (True, f"client refused: {type(e).__name__}")
    return {"tools": sorted(t.name for t in tools.tools), "listed": listed, "bad": bad}


async def main() -> None:
    url, headers = sys.argv[1], {"Authorization": f"Bearer {sys.argv[2]}"}
    major = int(version("mcp").split(".")[0])
    report = await (v1 if major == 1 else v2)(url, headers)
    report.update(sdk=version("mcp"))
    print(json.dumps(report))


if __name__ == "__main__":
    asyncio.run(main())
