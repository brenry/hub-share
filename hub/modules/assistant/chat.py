"""The assistant's chat: one conversation in memory for the session, carried by Open WebUI.

Each message goes to Open WebUI's chat API on this computer with the conversation so far; Open WebUI applies the
model and system prompt set there and its reply is shown. The hub adds nothing to the text. A message with role
"error" says in plain words why there was no reply; it is never sent on. A message with role "hub" is the Hub's own
line (a module's `chat.note` event): shown at once as a reply is, and sent on the next `user` message as a
`user` message "Hub note: <text>" right before it (turns.notes). Only the link settings are on disk
(openwebui.json, settings.py).

With a tool server picked, Open WebUI runs tools only for a reply saved in one of its chats, so the conversation
gets one Open WebUI chat: made at its first message, read after each reply for its text, deleted at New chat, when
the session ends and when the module stops; leftovers are swept after every turn and at start (remote.py). Open
WebUI answers such
a turn only when its whole loop is done; the hub then reads the saved reply. The chat shows the `user` messages and the
replies: a tool call shows as what it did (the draft panel, the settings, the prompt box after a push), never as a
line. Each reply keeps, in memory only, the `output` items Open WebUI saved with it (its tool calls and results)
and sends them back on the next turn, as Open WebUI's own chat does: Open WebUI turns them into the tool calls the
model made (utils/middleware.py `process_messages_with_output`), so the model sees what it did and keeps calling.
Sent as text only, every earlier settings request looks answered in words. A tools-only turn shows nothing but is
kept for the model. New chat emits
`chat.cleared` (routes.chat_clear), which the Generate screen hears: its prompt box and the draft empty with the
conversation.

Only the last `keep` exchanges are kept (Settings -> Assistant, "Replies kept"; turns.py): after each turn every
older message is deleted, not hidden, so it is neither shown nor sent again, and the Open WebUI chat that held their
replies is deleted; the next turn makes a new, empty one. Open WebUI reads a chat's saved messages only for a
`user_message`, which the hub never sends, so the kept replies still reach the model with their `output` items.
Their tool results go cut to one short line, all but the newest exchange's (turns.lean); the messages kept here
stay whole. Every completion carries the "Context length" setting as `params.num_ctx` unless it is 0 (settings.py).
A planning ask given a schema (the "ask" service) also carries it as `response_format` (settings.held).
"""
from __future__ import annotations

import asyncio
import contextlib
import secrets
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hub.core.api import Ctx, Invalid

from . import link, settings, turns
from .remote import Remote

if TYPE_CHECKING:
    from .routes import AssistantCtx

FIELDS = ("id", "role", "text", "at")
EXTRA = ("seconds",)
WIRE_ROLES = ("user", "assistant")
HUB = "hub"                                    # the Hub's own line; sent on as a note (turns.notes), never as itself
NOTE = "chat.note"                             # the core event a module emits with {"text"} to add one
BROKEN = "Something went wrong in the hub"
CLEARED = "chat.cleared"                       # the core event New chat emits; generate_image listens
ACCESS_OFF = "Assistant access is off, so Open WebUI cannot reach the Hub tools"
NO_MODEL = "Set the Open WebUI model name in Settings -> Assistant"

_chats: dict[Path, Chat] = {}


def ran_tools(output: Any) -> bool:
    """Whether a saved reply's output items hold a tool call (Open WebUI's `function_call` items)."""
    return isinstance(output, list) and any(isinstance(i, dict) and i.get("type") == "function_call" for i in output)


def _error(message: dict) -> str | None:
    found = message.get("error")
    if isinstance(found, dict):
        found = found.get("content")
    if found is None or found is False:
        return None
    return str(found).strip()[:300] or "Open WebUI could not answer"


class Chat(Remote):
    def __init__(self, ctx: AssistantCtx) -> None:
        self.ctx = ctx
        self.settings = ctx.doc("openwebui", dict(settings.DEFAULTS))
        self.messages: list[dict] = []
        self.busy = False
        self.task: asyncio.Task[None] | None = None
        self.remote: str | None = None          # the conversation's Open WebUI chat id (tools only)
        self.cleanup: set[asyncio.Task[Any]] = set()
        self.lock = asyncio.Lock()              # a sweep never deletes the chat a turn is making
        self.told: str | None = None            # the last refusal shown

    # ------------------------------------------------------------- settings
    def config(self) -> dict:
        return settings.read(self.settings.get())

    def configure(self, changes: Any) -> dict:
        self.settings.patch(settings.clean(changes))
        return self.config()

    async def list_models(self) -> dict:
        """Open WebUI's model list with the saved address and key: -> {ok, text, models}. The screen picks from it."""
        c = self.config()
        try:
            host, port = link.endpoint(c["url"])
            names = await link.models(host, port, c["key"])
        except Invalid as e:
            return {"ok": False, "text": e.text, "models": []}
        if not names:
            return {"ok": False, "text": "Connected, key accepted, but Open WebUI lists no models", "models": []}
        return {"ok": True, "text": f"Connected · {len(names)} model{'' if len(names) == 1 else 's'}", "models": names}

    async def list_tool_servers(self) -> dict:
        """Open WebUI's MCP tool servers: -> {ok, text, servers: [{id, name}]}. The screen picks from it."""
        c = self.config()
        try:
            host, port = link.endpoint(c["url"])
            found = await link.tool_servers(host, port, c["key"])
        except Invalid as e:
            return {"ok": False, "text": e.text, "servers": []}
        n = len(found)
        text = f"{n} tool server{'' if n == 1 else 's'}" if n else "Open WebUI has no MCP tool servers"
        return {"ok": True, "text": text, "servers": found}

    # ------------------------------------------------------------- state
    def view(self) -> dict:
        c = self.config()
        shown = [{**{k: m[k] for k in FIELDS}, **{k: m.get(k) for k in EXTRA}} for m in self.messages
                 if m["role"] != "assistant" or m["text"].strip()]          # a tools-only turn is not a line
        return {"busy": self.busy, "messages": shown, "model": c["model"] or None}

    def changed(self) -> None:
        self.ctx.bus.publish("chat", "assistant.chat", self.view(), key="chat")

    def add(self, role: str, text: str, **extra: Any) -> dict:
        msg = {"id": secrets.token_hex(6), "role": role, "text": text, "at": time.time(), **extra}
        self.messages.append(msg)
        self.changed()
        return msg

    def note(self, text: str) -> dict:
        """The Hub's own line: in the conversation and on the screen at once, busy turn or not."""
        return self.add(HUB, text)

    def send(self, text: str) -> str:
        """Start a turn; -> the `user` message's id. The caller checks `busy` first."""
        self.busy = True
        turn = self.add("user", text)["id"]
        self.task = asyncio.get_running_loop().create_task(self.turn())
        return turn

    def clear(self) -> None:
        """New chat: the hub stops waiting and deletes the Open WebUI chat. A turn Open WebUI is already running still
        finishes there (its tool calls may still reach the hub); its late saves land in the deleted chat."""
        if self.task is not None:
            self.task.cancel()
        remote, self.remote = self.remote, None
        if remote is not None:
            self.keep(asyncio.get_running_loop().create_task(self.forget(remote)))
        self.messages, self.busy, self.task = [], False, None
        self.changed()

    def purge(self) -> None:
        """Delete every message before the last `keep` exchanges and the Open WebUI chat that held their replies."""
        self.messages, gone = turns.purge(self.messages, self.config()["keep"])
        if gone and self.remote is not None:
            self.keep(asyncio.get_running_loop().create_task(self.forget(self.remote)))
            self.remote = None

    # ------------------------------------------------------------- the turn
    def wire(self) -> list[dict]:
        """The conversation as Open WebUI's own chat sends it: the `user` messages and the replies, each reply with the
        `output` items Open WebUI saved for it (its tool calls and results); error lines stay here; the Hub's lines go
        as notes before the next `user` message (turns.notes). Tool results of exchanges before the newest go cut to
        their first line (turns.lean)."""
        out = []
        for m in self.messages:
            if m["role"] in WIRE_ROLES or m["role"] == HUB:
                item = {"role": m["role"], "content": m["text"]}
                if m.get("output"):
                    item["output"] = m["output"]
                out.append(item)
        return turns.lean(turns.notes(out))

    async def reply(self, started: float) -> None:
        """Open WebUI's answer to the conversation so far, added as a message. In tool-server mode a turn that ran
        tools and said nothing adds nothing; a turn that did neither is "no reply"."""
        c = self.config()
        if not c["model"]:
            raise Invalid("model", NO_MODEL)
        host, port = link.endpoint(c["url"])
        if not c["tools"]:
            text = await link.ask(host, port, c["key"], c["model"], self.wire(), settings.params(c))
            self.add("assistant", text, seconds=round(time.monotonic() - started, 1))
            return
        if not self.ctx.mcp.state()["on"]:
            raise Invalid("tools", ACCESS_OFF)
        async with self.lock:
            if self.remote is None:
                self.remote = await self.open_remote(host, port, c["key"], c["model"])
        message_id = str(uuid.uuid4())
        try:
            await link.complete(host, port, c["key"], {
                "model": c["model"], "messages": self.wire(), "stream": True,
                "tool_ids": [f"server:mcp:{c['tools']}"], "chat_id": self.remote, "id": message_id,
                **settings.params(c)})
            saved = await link.saved(host, port, c["key"], self.remote, message_id)
        except Invalid as e:
            if e.text == link.GONE:
                self.remote = None   # deleted in Open WebUI: the next message makes a new one
            raise
        content = saved.get("content")
        text = content.strip() if isinstance(content, str) else ""
        output = saved.get("output") if isinstance(saved.get("output"), list) else []
        tools = ran_tools(output)
        if text or tools:
            self.add("assistant", content if text else "", seconds=round(time.monotonic() - started, 1),
                     **({"output": output} if output else {}))
        error = _error(saved)
        if error is not None:
            raise Invalid("model", error)
        if not text and not tools:
            raise Invalid("model", link.NO_TEXT)

    async def turn(self) -> None:
        """One turn: the reply, or an "error" message saying in plain words why there is none."""
        started = time.monotonic()
        try:
            await self.reply(started)
        except Invalid as e:
            self.add("error", e.text)
        except Exception:
            self.add("error", BROKEN)
        self.purge()
        self.busy, self.task = False, None
        self.changed()
        if self.config()["tools"]:                 # only tool-server turns make Open WebUI chats
            self.keep(asyncio.get_running_loop().create_task(self.sweep()))


def get(ctx: Ctx) -> Chat:
    found = _chats.get(ctx.data_dir)
    if found is None:
        raise Invalid("chat", "The assistant is not running")
    return found


async def ask(ctx: Ctx, messages: list[dict], schema: dict | None = None) -> tuple[str, str]:
    """The "ask" service other modules use (the Director): the model named in Settings -> Assistant asked
    once with these messages, no tools, no chat kept, nothing written -> (the model's name, its reply). With no
    messages nothing is asked: (the name, "") says which model will answer, or refuses as a turn would. A `schema`
    goes with the ask so the backend in Settings -> Assistant holds the reply to it (settings.held)."""
    c = settings.read(ctx.doc("openwebui", dict(settings.DEFAULTS)).get())
    if not c["model"]:
        raise Invalid("model", NO_MODEL)
    host, port = link.endpoint(c["url"])
    if not messages:
        return c["model"], ""
    return c["model"], await link.ask(host, port, c["key"], c["model"], messages,
                                         {**settings.params(c), **settings.held(schema)})


async def start(ctx: AssistantCtx) -> None:
    (ctx.data_dir / "session.json").unlink(missing_ok=True)   # a chat file left by an older hub
    _chats[ctx.data_dir] = Chat(ctx)
    ctx.offer("ask", lambda messages, schema=None: ask(ctx, messages, schema))
    ctx.offer("said", lambda: (c := _chats.get(ctx.data_dir)) and turns.said(c.messages, c.busy))
    _chats[ctx.data_dir].keep(asyncio.get_running_loop().create_task(_chats[ctx.data_dir].sweep()))


async def on_session_ended(ctx: Ctx, data: dict) -> None:
    """The session ended: the conversation is gone here and in Open WebUI."""
    found = _chats.get(ctx.data_dir)
    if found is not None:
        found.clear()
        found.keep(asyncio.get_running_loop().create_task(found.sweep()))


async def on_note(ctx: Ctx, data: dict) -> None:
    """A module's `chat.note` {"text"}: the Hub's line in the conversation. With no text, nothing is added."""
    found, text = _chats.get(ctx.data_dir), data.get("text")
    if found is not None and isinstance(text, str) and text.strip():
        found.note(text)


async def stop(ctx: Ctx) -> None:
    """End the hub's side of the chat (as New chat does) and wait until its Open WebUI chats are deleted."""
    found = _chats.pop(ctx.data_dir, None)
    if found is None:
        return
    if found.task is not None:
        found.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await found.task
    if found.remote is not None:
        await found.forget(found.remote)
    while found.cleanup:   # a chat still being made adds its own deletion when it arrives
        await asyncio.gather(*found.cleanup, return_exceptions=True)
