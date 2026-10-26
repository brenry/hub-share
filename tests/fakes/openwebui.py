"""A fake Open WebUI on 127.0.0.1 that records every request it gets, and the helpers the assistant tests share
(test_assistant_chat.py, test_assistant_tools.py, test_assistant_purge.py, test_assistant_cleanup.py)."""
from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from tests.core.harness import Hub
from tests.fakes.screen import Screen


class FakeOpenWebUI:
    """Answers like Open WebUI on the paths the hub uses; `status` and `reply` set what a plain completion gets.

    A completion into a chat (stream true, chat_id, id) saves `output` as that chat's message, the way Open WebUI's
    streaming handler does (a chat that is gone keeps nothing), and then answers JSON `null` as Open WebUI does; the
    alternate case, `stream_as = "sse"`, answers with a slow event stream instead. `making` holds back the answer
    to POST /api/v1/chats/new for that many seconds after the chat is made.

    GET /api/v1/chats/ lists every chat with its title (`titles`, "Hub" when unset), as Open WebUI's chat list does.
    DELETE answers `delete_status`: 200 (or 404) deletes the chat; any other status keeps it and answers
    {"detail": `delete_detail`}, as Open WebUI does for a key or a user without the delete permission."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.reply: Any = {"choices": [{"message": {"role": "assistant", "content": "Hello from Open WebUI."}}]}
        self.status = 200
        self.raw: bytes | None = None
        self.models: Any = {"data": [{"id": "q", "name": "q"}, {"id": "gemma3:12b", "name": "gemma3:12b"}]}
        self.servers: Any = {"TOOL_SERVER_CONNECTIONS": SERVERS}
        self.servers_status = 200
        self.chats: dict[str, dict[str, dict]] = {}
        self.output: list[dict] = TOOL_OUTPUT
        self.content = "Queued a red fox."
        self.error: Any = None
        self.stream_as = "null"
        self.made = 0
        self.making = 0.0
        self.titles: dict[str, str] = {}
        self.delete_status = 200
        self.delete_detail = "You do not have permission to access this resource."
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def record(self, body: Any) -> None:
                fake.requests.append({"method": self.command, "path": self.path,
                                      "auth": self.headers.get("Authorization"), "body": body})

            def do_GET(self) -> None:
                self.record(None)
                if self.path == "/api/v1/configs/tool_servers":
                    return self.send(fake.servers, fake.servers_status)
                if self.path.split("?")[0] == "/api/v1/chats/":
                    return self.send([{"id": k, "title": fake.titles.get(k, "Hub"), "updated_at": 0,
                                       "created_at": 0} for k in list(fake.chats)])
                if self.path.startswith("/api/v1/chats/"):
                    found = fake.chats.get(self.path.removeprefix("/api/v1/chats/"))
                    if found is None:
                        return self.send({"detail": "We could not find what you're looking for :/"}, 401)
                    return self.send({"id": self.path.rsplit("/", 1)[1], "title": "Hub",
                                      "chat": {"history": {"messages": found}}})
                self.send(fake.models if fake.status == 200 else fake.reply, fake.status)

            def do_DELETE(self) -> None:
                self.record(None)
                if fake.delete_status not in (200, 404):
                    return self.send({"detail": fake.delete_detail}, fake.delete_status)
                found = fake.chats.pop(self.path.removeprefix("/api/v1/chats/"), None)
                self.send(found is not None, fake.delete_status)

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                self.record(body)
                if self.path == "/api/v1/chats/new":
                    fake.made += 1
                    chat_id = f"chat-{fake.made}"
                    fake.chats[chat_id] = {}
                    time.sleep(fake.making)
                    return self.send({"id": chat_id, "title": body["chat"]["title"], "chat": body["chat"]})
                if body.get("stream") and body.get("chat_id"):
                    saved = {"id": body["id"], "role": "assistant", "content": fake.content, "done": True,
                             "output": fake.output}
                    if fake.error is not None:
                        saved["error"] = fake.error
                    if body["chat_id"] in fake.chats:
                        fake.chats[body["chat_id"]][body["id"]] = saved
                    return self.stream() if fake.stream_as == "sse" else self.send(None)
                if fake.raw is not None:
                    return self.send_bytes(fake.raw, fake.status)
                self.send(fake.reply, fake.status)

            def send(self, value: Any, status: int = 200) -> None:
                self.send_bytes(json.dumps(value).encode(), status)

            def send_bytes(self, data: bytes, status: int) -> None:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def stream(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for event in (b'data: {"choices": [{"delta": {"content": "Queued"}}]}\n\n', b"data: [DONE]\n\n"):
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(event), event))
                    self.wfile.flush()
                    time.sleep(0.2)   # a slow stream: the hub waits for the end
                self.wfile.write(b"0\r\n\r\n")

            def log_message(self, *a: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


SERVERS = [
    {"url": "http://127.0.0.1:8770/mcp", "path": "", "type": "mcp", "auth_type": "bearer", "key": "secret",
     "config": {"enable": True}, "info": {"id": "hub", "name": "Hub", "description": ""}},
    {"url": "http://127.0.0.1:9000", "path": "openapi.json", "type": "openapi", "auth_type": "none", "key": "",
     "config": {}, "info": {"id": "weather", "name": "Weather"}},
    {"url": "http://127.0.0.1:9100/mcp", "path": "", "type": "mcp", "auth_type": "none", "key": "", "config": {},
     "info": {"id": "notes"}},
]
# Output items as Open WebUI's streaming handler saves them (utils/middleware.py: function_call items carry the
# model's arguments as a JSON string; function_call_output carries the tool's text and completed|failed).
TOOL_OUTPUT = [
    {"type": "function_call", "id": "call_0", "call_id": "call_0", "name": "hub_set_generate_image_settings",
     "arguments": '{"draft": "a red fox in snow"}', "status": "completed"},
    {"type": "function_call_output", "id": "fco_0", "call_id": "call_0",
     "output": [{"type": "input_text", "text": '{"draft": "a red fox in snow", "model": "z_image"}'}],
     "status": "completed"},
    {"type": "function_call", "id": "call_1", "call_id": "call_1", "name": "hub_generate_image",
     "arguments": "{}", "status": "completed"},
    {"type": "function_call_output", "id": "fco_1", "call_id": "call_1",
     "output": [{"type": "input_text", "text": '{"state": "queued"}'}], "status": "completed"},
    {"type": "function_call", "id": "call_2", "call_id": "call_2", "name": "hub_get_generate_image_settings",
     "arguments": "{}", "status": "failed"},
    {"type": "function_call_output", "id": "fco_2", "call_id": "call_2",
     "output": [{"type": "input_text", "text": "Error: no model"}], "status": "failed"},
    {"type": "message", "id": "msg_1", "status": "completed", "role": "assistant",
     "content": [{"type": "output_text", "text": "Queued a red fox."}]},
]


async def settled(w: Screen, count: int) -> dict:
    m = await w.recv("assistant.chat", where=lambda m: not m["d"]["busy"] and len(m["d"]["messages"]) == count)
    return m["d"]


SWEEP = "/api/v1/chats/"   # the list a sweep reads after each tool-server turn (remote.py)


def calls(owui: FakeOpenWebUI) -> list[dict[str, Any]]:
    """The requests a turn makes: everything but the sweep's look for leftover chats (none in these tests, so it
    deletes nothing); test_assistant_cleanup.py checks the sweep itself."""
    return [r for r in owui.requests if r["path"] != SWEEP]


async def until(check: Callable[[], bool], seconds: float = 3.0) -> None:
    for _ in range(int(seconds / 0.02)):
        if check():
            return
        await asyncio.sleep(0.02)
    assert check()


async def tool_hub(hub: Hub, owui: FakeOpenWebUI) -> tuple[str, Screen]:
    cookie = hub.pair()
    await hub.http("PATCH", "/api/assistant/openwebui", cookie,
                   {"url": owui.url, "key": "sk-abc", "model": "q", "tools": "hub"})
    assert (await hub.http("PATCH", "/api/assistant", cookie, {"on": True})).json()["on"] is True
    return cookie, await hub.screen(cookie, "workspace", "w")
