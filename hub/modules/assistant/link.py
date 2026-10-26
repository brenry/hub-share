"""The hub's line to Open WebUI: plain HTTP/1.1 over a socket to a loopback address, nothing else.

Every call carries the API key as a Bearer token and reads one answer; every failure becomes one plain sentence
(`Invalid`). Calls: the model list, a completion (with a chat id, Open WebUI runs tools and saves the reply in
that chat), the tool servers (an admin's key only), and a chat's making, reading, listing and deletion.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
from typing import Any
from urllib.parse import quote, urlsplit

from hub.core.api import Invalid

TIMEOUT_S = 600.0
FORGET_S = 30.0
MAX_REPLY = 4 << 20
MAX_HEADERS = 100
SLOW = "Open WebUI took longer than 10 minutes to answer"
REFUSED = "Open WebUI is not answering on that address"
STOPPED = "Open WebUI stopped answering"
UNREADABLE = "Open WebUI sent something the hub cannot read"
TOO_MUCH = "Open WebUI sent more than the hub will read"
NO_TEXT = "Open WebUI sent a reply with no text"
KEY_REFUSED = "Open WebUI refused the key (Settings -> Account -> API keys)"
NOT_ADMIN = "Open WebUI shows its tool servers only to an admin's key"
JUST_ADDRESS = "Use just the address and port, like http://127.0.0.1:3000"
GONE = "The Open WebUI chat for this conversation is gone; the next message starts a new one"
# Open WebUI's own words for a refused key or a missing permission; any other 401/404 on a chat means it is gone.
PROHIBITED = "You do not have permission to access this resource."
KEY_REFUSALS = ("Not authenticated", "Invalid token", "Your session has expired or the token is invalid.",
                "401 Unauthorized", "User mismatch.", PROHIBITED)


def endpoint(url: Any) -> tuple[str, int]:
    """Open WebUI's address as (ip, port): a numeric loopback address only (the hub reaches nothing else)."""
    parts = urlsplit(str(url or "").strip())
    if parts.scheme != "http" or not parts.hostname:
        raise Invalid("url", "Use an address like http://127.0.0.1:3000")
    if parts.path not in ("", "/") or parts.query or parts.fragment or "@" in parts.netloc:
        raise Invalid("url", JUST_ADDRESS)
    try:
        ip = ipaddress.ip_address(parts.hostname)
    except ValueError:
        raise Invalid("url", "Use 127.0.0.1, not a name") from None
    if not ip.is_loopback:
        raise Invalid("url", "Open WebUI must be on this computer: use 127.0.0.1")
    try:
        port = parts.port
    except ValueError:
        raise Invalid("url", JUST_ADDRESS) from None
    if port == 0:
        raise Invalid("url", JUST_ADDRESS)
    return ip.compressed, port or 80


def printable(text: str) -> bool:
    """True when every character is plain printable ASCII (nothing that could break a request line)."""
    return all(" " <= ch <= "~" for ch in text)


async def _read_head(r: asyncio.StreamReader) -> tuple[int, dict[str, str]]:
    """One status line and its headers."""
    line = await r.readline()
    if not line:
        raise Invalid("url", STOPPED)
    parts = line.decode("latin-1").split(" ", 2)
    if len(parts) < 2 or not parts[0].startswith("HTTP/") or not parts[1].isdecimal():
        raise Invalid("url", UNREADABLE)
    headers: dict[str, str] = {}
    while (h := await r.readline()) not in (b"\r\n", b"\n"):
        if not h:
            raise Invalid("url", STOPPED)
        if len(headers) >= MAX_HEADERS:
            raise Invalid("url", UNREADABLE)
        name, _, value = h.decode("latin-1").partition(":")
        headers[name.strip().lower()] = value.strip()
    return int(parts[1]), headers


class _Body:
    """Up to MAX_REPLY bytes of a body, or nothing when `keep` is false (read to its end so the exchange finishes)."""

    def __init__(self, keep: bool) -> None:
        self.keep, self.data = keep, bytearray()

    def add(self, size: int) -> None:
        if self.keep and len(self.data) + size > MAX_REPLY:
            raise Invalid("url", TOO_MUCH)

    def take(self, chunk: bytes) -> None:
        if self.keep:
            self.data += chunk


async def _read_chunked(r: asyncio.StreamReader, body: _Body) -> None:
    """A chunked body, each chunk checked against the limit before it is read."""
    while True:
        size = int(bytes((await r.readline()).split(b";")[0].strip()), 16)
        if size < 0:
            raise Invalid("url", UNREADABLE)
        body.add(size)
        if size == 0:
            return
        while size:
            part = await r.readexactly(min(size, 65536))
            body.take(part)
            size -= len(part)
        await r.readline()


async def _read_to_end(r: asyncio.StreamReader, body: _Body) -> None:
    while chunk := await r.read(65536):
        body.add(len(chunk))
        body.take(chunk)


async def _read_body(r: asyncio.StreamReader, headers: dict[str, str], keep: bool) -> bytes:
    body = _Body(keep)
    if headers.get("transfer-encoding", "").lower() == "chunked":
        await _read_chunked(r, body)
    elif "content-length" not in headers:
        await _read_to_end(r, body)
    else:
        length = headers["content-length"]
        if not length.isdecimal():
            raise Invalid("url", UNREADABLE)
        body.add(int(length))
        left = int(length)
        while left:
            part = await r.readexactly(min(left, 65536))
            body.take(part)
            left -= len(part)
    return bytes(body.data)


async def _exchange(host: str, port: int, request: bytes, keep: bool) -> tuple[int, bytes]:
    """Send one request and read the final answer (any 1xx interim answers are skipped)."""
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(request)
        await writer.drain()
        status, headers = await _read_head(reader)
        while 100 <= status < 200:
            status, headers = await _read_head(reader)
        return status, await _read_body(reader, headers, keep or status != 200)
    finally:
        writer.close()


def _request(method: str, path: str, host: str, port: int, key: str, body: bytes = b"") -> bytes:
    name = f"[{host}]" if ":" in host else host
    head = (f"{method} {path} HTTP/1.1\r\nHost: {name}:{port}\r\nContent-Type: application/json\r\n"
            f"Authorization: Bearer {key}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n")
    return head.encode() + body


async def call(host: str, port: int, key: str, method: str, path: str, body: Any = None, *,
               keep: bool = True, limit: float | None = None) -> tuple[int, bytes]:
    """One exchange with Open WebUI; every failure becomes one plain sentence. `keep=False` reads a 200 answer to
    its end without keeping it."""
    data = b"" if body is None else json.dumps(body).encode()
    try:
        async with asyncio.timeout(TIMEOUT_S if limit is None else limit):
            return await _exchange(host, port, _request(method, path, host, port, key, data), keep)
    except TimeoutError:
        raise Invalid("url", SLOW) from None
    except ConnectionRefusedError:
        raise Invalid("url", REFUSED) from None
    except (OSError, asyncio.IncompleteReadError):
        raise Invalid("url", STOPPED) from None
    except ValueError:
        raise Invalid("url", UNREADABLE) from None


def _detail(data: bytes) -> str | None:
    try:
        payload = json.loads(data)
    except (ValueError, RecursionError):
        return None
    detail = payload.get("detail") if isinstance(payload, dict) else None
    return detail.strip()[:300] if isinstance(detail, str) and detail.strip() else None


def answer(status: int, data: bytes, field: str = "model") -> Any:
    """The JSON of a 200 answer, or a plain sentence saying why there is none."""
    if status in (401, 403):
        raise Invalid("key", KEY_REFUSED)
    if status != 200:
        raise Invalid(field, _detail(data) or f"Open WebUI answered HTTP {status}")
    try:
        return json.loads(data)
    except (ValueError, RecursionError):
        raise Invalid("url", f"{UNREADABLE} (HTTP {status})") from None


async def ask(host: str, port: int, key: str, model: str, messages: list[dict], extra: dict | None = None) -> str:
    """One chat completion, no tools, no chat kept in Open WebUI; `extra` adds fields to the body (the `params`
    settings.params gives). -> the reply text."""
    body = {"model": model, "messages": messages, "stream": False, **(extra or {})}
    payload = answer(*await call(host, port, key, "POST", "/api/chat/completions", body))
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = None
    if not isinstance(content, str):
        raise Invalid("model", NO_TEXT)
    return content


async def models(host: str, port: int, key: str) -> list[str]:
    """The model names Open WebUI lists for this key (GET /api/models). Proves the address and the key."""
    payload = answer(*await call(host, port, key, "GET", "/api/models"), field="url")
    found = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(found, list):
        raise Invalid("url", UNREADABLE)
    return [m["id"] for m in found if isinstance(m, dict) and isinstance(m.get("id"), str)]


async def tool_servers(host: str, port: int, key: str) -> list[dict]:
    """The MCP tool servers set in Open WebUI (Admin Settings -> External Tools): [{id, name}]."""
    status, data = await call(host, port, key, "GET", "/api/v1/configs/tool_servers")
    if status == 401 and (_detail(data) or "").startswith(PROHIBITED):   # get_admin_user's refusal
        raise Invalid("key", NOT_ADMIN)
    payload = answer(status, data, field="url")
    found = payload.get("TOOL_SERVER_CONNECTIONS") if isinstance(payload, dict) else None
    if not isinstance(found, list):
        raise Invalid("url", UNREADABLE)
    servers = []
    for c in found:
        if not isinstance(c, dict):
            continue
        info = c.get("info")
        sid = info.get("id") if isinstance(info, dict) else None
        if c.get("type") != "mcp" or not isinstance(sid, str) or not sid:
            continue
        name = info.get("name") if isinstance(info.get("name"), str) and info.get("name") else sid
        servers.append({"id": sid, "name": name})
    return servers


HUB_CHAT = "Hub"


async def new_chat(host: str, port: int, key: str, model: str) -> str:
    """An empty Open WebUI chat for this conversation. -> its id."""
    body = {"chat": {"title": HUB_CHAT, "models": [model], "history": {"messages": {}, "currentId": None},
                     "messages": []}}
    payload = answer(*await call(host, port, key, "POST", "/api/v1/chats/new", body))
    found = payload.get("id") if isinstance(payload, dict) else None
    if not isinstance(found, str) or not found:
        raise Invalid("url", UNREADABLE)
    return found


async def complete(host: str, port: int, key: str, body: dict) -> None:
    """A completion into a saved chat: Open WebUI runs its whole loop (model, tools, model again), saves the reply
    there and only then answers with `null`, which is read and dropped. A chat deleted meanwhile answers 404: GONE."""
    status, data = await call(host, port, key, "POST", "/api/chat/completions", body, keep=False)
    if status == 404:
        raise Invalid("chat", GONE)
    if status != 200:
        answer(status, data)


async def saved(host: str, port: int, key: str, chat_id: str, message_id: str) -> dict:
    """One message as Open WebUI saved it in the chat (content, output items, error). A chat deleted in Open WebUI
    meanwhile is GONE."""
    status, data = await call(host, port, key, "GET", f"/api/v1/chats/{quote(chat_id, safe='')}")
    if status in (401, 404) and not (_detail(data) or "").startswith(KEY_REFUSALS):
        raise Invalid("chat", GONE)
    payload = answer(status, data)
    try:
        found = payload["chat"]["history"]["messages"][message_id]
    except (KeyError, TypeError):
        found = None
    if not isinstance(found, dict):
        raise Invalid("model", "Open WebUI saved no reply for this message")
    return found
