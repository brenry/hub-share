"""The hub's line to Open WebUI: how it reads awkward or hostile answers, byte by byte.

A raw fake Open WebUI on 127.0.0.1 reads one request, then writes exactly the bytes a test asks for.
"""
from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.assistant import chat, link
from tests.core.harness import Hub, own_modules, start_hub

Script = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]
OK = json.dumps({"choices": [{"message": {"role": "assistant", "content": "Raw hello."}}]}).encode()
# Open WebUI's words (open_webui/constants.py ERROR_MESSAGES)
NOT_FOUND = "We could not find what you're looking for :/"
INVALID_TOKEN = "Your session has expired or the token is invalid. Please sign in again."
ACCESS_PROHIBITED = ("You do not have permission to access this resource. Please contact your administrator for "
                     "assistance.")


class RawOpenWebUI:
    """A bare socket server: reads one request, then `script` writes whatever the test wants."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.heads: list[bytes] = []
        self.script: Script | None = None
        self.dropped = asyncio.Event()   # the hub closed the connection while the script waited

    async def start(self, host: str = "127.0.0.1") -> RawOpenWebUI:
        self.server = await asyncio.start_server(self.handle, host, 0)
        self.host, self.port = host, self.server.sockets[0].getsockname()[1]
        return self

    async def handle(self, r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        head = await r.readuntil(b"\r\n\r\n")
        length = re.search(rb"Content-Length: (\d+)", head)
        assert length is not None
        self.heads.append(head)
        data = await r.readexactly(int(length[1]))
        self.requests.append({"body": json.loads(data) if data else None})
        try:
            if self.script is not None:
                await self.script(r, w)
        except ConnectionError:
            pass
        finally:
            w.close()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def ask(self) -> str:
        return await link.ask(self.host, self.port, "k", "q", [{"role": "user", "content": "hi"}])

    async def close(self) -> None:
        self.server.close()
        self.server.close_clients()


async def hang(r: asyncio.StreamReader, w: asyncio.StreamWriter, fake: RawOpenWebUI) -> None:
    """Never answer; note when the hub gives up and closes the connection."""
    await r.read()
    fake.dropped.set()


def answer(*pieces: bytes, pause: float = 0.0) -> Script:
    """A script that writes `pieces` one after another, with a pause between them."""
    async def script(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        for piece in pieces:
            w.write(piece)
            await w.drain()
            await asyncio.sleep(pause)
    return script


def chunked(data: bytes, size: int) -> bytes:
    parts = [data[i:i + size] for i in range(0, len(data), size)]
    return b"".join(b"%x\r\n%s\r\n" % (len(p), p) for p in parts) + b"0\r\n\r\n"


@pytest.fixture
async def raw():  # type: ignore[no-untyped-def]
    fake = await RawOpenWebUI().start()
    yield fake
    await fake.close()


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    h = await start_hub(tmp_path / "data", modules=own_modules())
    yield h
    await h.close()


def test_endpoint_accepts_only_loopback_over_http() -> None:
    assert link.endpoint("http://127.0.0.1:3000") == ("127.0.0.1", 3000)
    assert link.endpoint(" http://127.0.0.1 ") == ("127.0.0.1", 80)
    assert link.endpoint("http://127.0.0.1:3000/") == ("127.0.0.1", 3000)   # a pasted trailing slash
    assert link.endpoint("http://[::1]:3000") == ("::1", 3000)
    for bad in ("http://192.168.0.10:3000", "http://localhost:3000", "https://127.0.0.1:3000", "127.0.0.1:3000",
                "", None, "http://0.0.0.0:3000", "http://127.0.0.1:99999", "http://127.0.0.1:abc",
                "http://127.0.0.1:0", "http://127.0.0.1:3000/api", "http://127.0.0.1:3000?a=1",
                "http://u:p@127.0.0.1:3000"):
        with pytest.raises(Invalid):
            link.endpoint(bad)


HEAD = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"


def full(value: Any, status: bytes = b"200 OK") -> bytes:
    """A whole answer with a Content-Length."""
    data = value if isinstance(value, bytes) else json.dumps(value).encode()
    return b"HTTP/1.1 %s\r\nContent-Length: %d\r\n\r\n%s" % (status, len(data), data)


@pytest.mark.parametrize("script", [
    answer(HEAD + b"Transfer-Encoding: chunked\r\n\r\n", *re.findall(b".{1,9}", chunked(OK, 7), re.S), pause=0.01),
    answer(HEAD + b"Connection: close\r\n\r\n", OK[:5], OK[5:20], OK[20:], pause=0.05),
    answer(b"HTTP/1.1 100 Continue\r\n\r\n", full(OK)),
], ids=["chunked", "until-close", "100-continue"])
async def test_awkward_but_valid_answers_are_read(raw: RawOpenWebUI, script: Script) -> None:
    raw.script = script
    assert await raw.ask() == "Raw hello."


@pytest.mark.parametrize("script, text", [
    (answer(HEAD + b"Content-Length: %d\r\n\r\n" % (link.MAX_REPLY + 1)), link.TOO_MUCH),
    (answer(HEAD + b"Transfer-Encoding: chunked\r\n\r\nffffffffffffffff\r\n"), link.TOO_MUCH),
    (answer(HEAD + b"Transfer-Encoding: chunked\r\n\r\nzz\r\n"), link.UNREADABLE),
    (answer(HEAD + b"Content-Length: -4\r\n\r\n"), link.UNREADABLE),
    (answer(b"SSH-2.0-OpenSSH\r\n\r\n"), link.UNREADABLE),
    (answer(HEAD + b"Content-Length: 50\r\n\r\n{"), link.STOPPED),
    (answer(), link.STOPPED),
    (answer(full({"choices": [{"message": {"content": None}}]})), link.NO_TEXT),
    (answer(full({"detail": [{"msg": "bad"}]}, b"422 Unprocessable")), "Open WebUI answered HTTP 422"),
], ids=["oversize-length", "huge-chunk", "bad-hex", "negative-length", "not-http", "cut-short", "closed",
        "null-content", "list-detail"])
async def test_bad_answers_become_one_plain_sentence(raw: RawOpenWebUI, script: Script, text: str) -> None:
    raw.script = script
    with pytest.raises(Invalid) as e:
        await raw.ask()
    assert e.value.text == text


async def test_a_long_body_without_a_length_is_cut_off(raw: RawOpenWebUI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(link, "MAX_REPLY", 100)
    raw.script = answer(HEAD + b"Connection: close\r\n\r\n", *[b"x" * 40] * 5, pause=0.01)
    with pytest.raises(Invalid) as e:
        await raw.ask()
    assert e.value.text == link.TOO_MUCH


async def test_a_silent_open_webui_times_out(raw: RawOpenWebUI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(link, "TIMEOUT_S", 0.3)
    raw.script = lambda r, w: hang(r, w, raw)
    with pytest.raises(Invalid) as e:
        await raw.ask()
    assert e.value.text == "Open WebUI took longer than 10 minutes to answer"
    await asyncio.wait_for(raw.dropped.wait(), 2)


async def test_the_host_header_brackets_ipv6() -> None:
    assert b"\r\nHost: [::1]:3000\r\n" in link._request("GET", "/api/models", "::1", 3000, "k")
    assert b"\r\nHost: 127.0.0.1:3000\r\n" in link._request("GET", "/api/models", "127.0.0.1", 3000, "k")
    try:
        fake = await RawOpenWebUI().start("::1")
    except OSError:
        pytest.skip("no IPv6 loopback here")
    fake.script = answer(full(OK))
    try:
        assert await fake.ask() == "Raw hello."
        assert b"\r\nHost: [::1]:%d\r\n" % fake.port in fake.heads[0]
    finally:
        await fake.close()


@pytest.mark.parametrize("status, detail, text", [
    (b"401 Unauthorized", NOT_FOUND, link.GONE),   # routers/chats.py get_chat_by_id for a chat that is not there
    (b"404 Not Found", NOT_FOUND, link.GONE),
    (b"401 Unauthorized", INVALID_TOKEN, link.KEY_REFUSED),
    (b"401 Unauthorized", "Not authenticated", link.KEY_REFUSED),
    (b"401 Unauthorized", ACCESS_PROHIBITED, link.KEY_REFUSED),
    (b"403 Forbidden", NOT_FOUND, link.KEY_REFUSED),
], ids=["gone-401", "gone-404", "bad-key", "no-key", "pending-user", "forbidden"])
async def test_a_chat_deleted_in_open_webui_is_told_apart_from_a_refused_key(
        raw: RawOpenWebUI, status: bytes, detail: str, text: str) -> None:
    raw.script = answer(full({"detail": detail}, status))
    with pytest.raises(Invalid) as e:
        await link.saved(raw.host, raw.port, "k", "chat-1", "m1")
    assert e.value.text == text
    assert b"GET /api/v1/chats/chat-1 HTTP/1.1\r\n" in raw.heads[0]


async def test_a_tool_turn_into_a_chat_deleted_in_open_webui_is_gone(raw: RawOpenWebUI) -> None:
    """main.py chat_completion answers a chat the key does not own (or no longer has) with 404."""
    raw.script = answer(full({"detail": "Something went wrong :/"}, b"404 Not Found"))
    with pytest.raises(Invalid) as e:
        await link.complete(raw.host, raw.port, "k", {"model": "q", "chat_id": "chat-1", "id": "m1"})
    assert (e.value.field, e.value.text) == ("chat", link.GONE)


async def test_clearing_mid_answer_leaves_nothing_behind(hub: Hub, raw: RawOpenWebUI) -> None:
    cookie = hub.pair()
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": raw.url, "key": "k", "model": "q"})
    raw.script = lambda r, w: hang(r, w, raw)
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
    for _ in range(100):
        if raw.requests:
            break
        await asyncio.sleep(0.02)
    assert raw.requests and chat.get(hub.core.ctxs["assistant"]).busy
    cleared = (await hub.http("DELETE", "/api/assistant/chat", cookie)).json()
    assert cleared == {"busy": False, "messages": [], "model": "q"}
    await asyncio.wait_for(raw.dropped.wait(), 2)
    await asyncio.sleep(0.05)
    assert (await hub.http("GET", "/api/assistant/chat", cookie)).json() == cleared
    assert chat.get(hub.core.ctxs["assistant"]).task is None
