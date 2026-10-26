"""A simulated screen (one bus line) plus raw HTTP and WebSocket-handshake helpers for tests."""
from __future__ import annotations

import asyncio
import base64
import json
import os
from dataclasses import dataclass, field
from typing import Any

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed


@dataclass
class Resp:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")


async def http(port: int, method: str, path: str, headers: dict[str, str] | None = None, body: bytes | str = b"",
               host: str | None = None) -> Resp:
    """One HTTP/1.1 request on a fresh connection. `host=""` sends no Host header."""
    data = body.encode() if isinstance(body, str) else body
    hdrs = {"Host": f"127.0.0.1:{port}" if host is None else host, **(headers or {}), "Connection": "close"}
    if host == "":
        del hdrs["Host"]
    if (data or method in ("POST", "PUT", "PATCH")) and "Content-Length" not in hdrs:
        hdrs["Content-Length"] = str(len(data))
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    head = f"{method} {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in hdrs.items()) + "\r\n"
    writer.write(head.encode("latin-1") + data)
    await writer.drain()
    raw = await asyncio.wait_for(reader.read(), 10)
    writer.close()
    top, _, rest = raw.partition(b"\r\n\r\n")
    lines = top.decode("latin-1").split("\r\n")
    headers_out: dict[str, str] = {}
    for line in lines[1:]:
        k, _, v = line.partition(":")
        headers_out[k.strip().lower()] = (headers_out[k.strip().lower()] + ", " if k.strip().lower() in headers_out
                                          else "") + v.strip()
    return Resp(int(lines[0].split()[1]), headers_out, rest)


async def ws_status(port: int, path: str, headers: dict[str, str], host: str | None = None) -> int:
    """Send a WebSocket upgrade and return the HTTP status (101 accepted, 403 refused)."""
    key = base64.b64encode(os.urandom(16)).decode()
    hdrs = {"Host": host or f"127.0.0.1:{port}", "Upgrade": "websocket", "Connection": "Upgrade",
            "Sec-WebSocket-Key": key, "Sec-WebSocket-Version": "13", **headers}
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write((f"GET {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in hdrs.items()) + "\r\n").encode())
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), 5)
    writer.close()
    return int(line.split()[1])


@dataclass
class Screen:
    ws: ClientConnection
    seen: list[dict] = field(default_factory=list)
    buffer: list[dict] = field(default_factory=list)
    welcome: dict = field(default_factory=dict)

    @classmethod
    async def open(cls, port: int, cookie: str | None, origin: str | None = "default", path: str = "/bus") -> Screen:
        headers = {"Cookie": f"hub_screen={cookie}"} if cookie else {}
        ws = await connect(f"ws://127.0.0.1:{port}{path}", additional_headers=headers, open_timeout=5,
                           origin=f"http://127.0.0.1:{port}" if origin == "default" else origin)  # type: ignore[arg-type]
        return cls(ws)

    async def hello(self, role: str, screen: str, label: str | None = None, subs: list[str] | None = None) -> dict:
        await self.send("hello", {"proto": 1, "role": role, "screen": screen, "label": label, "subs": subs}, id="h1")
        self.welcome = (await self.recv("welcome"))["d"]
        return self.welcome

    async def send(self, t: str, d: Any = None, id: str | None = None, re: str | None = None) -> None:
        env: dict[str, Any] = {"t": t}
        if id is not None:
            env["id"] = id
        if re is not None:
            env["re"] = re
        if d is not None:
            env["d"] = d
        await self.ws.send(json.dumps(env))

    async def recv(self, t: str | None = None, timeout: float = 3.0, where: Any = None) -> dict:
        """The oldest not-yet-taken message of type `t` matching `where` (everything is kept in `seen`)."""
        def match(m: dict) -> bool:
            return (t is None or m["t"] == t) and (where is None or bool(where(m)))

        for i, m in enumerate(self.buffer):
            if match(m):
                return self.buffer.pop(i)

        async def wait() -> dict:
            while True:
                m = json.loads(await self.ws.recv())
                self.seen.append(m)
                if match(m):
                    return m
                self.buffer.append(m)
        return await asyncio.wait_for(wait(), timeout)

    async def closed(self, timeout: float = 5.0) -> int | None:
        """Wait for the server to close the line; -> close code."""
        try:
            await asyncio.wait_for(self._drain(), timeout)
        except ConnectionClosed:
            pass
        await self.ws.wait_closed()
        return self.ws.close_code

    async def _drain(self) -> None:
        while True:
            self.seen.append(json.loads(await self.ws.recv()))

    async def close(self) -> None:
        await self.ws.close()
