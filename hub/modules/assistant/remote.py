"""The Open WebUI chats the conversation uses (tool-server mode): made one at a time, deleted when done with.

Each deletion is checked. Open WebUI may refuse one (an API key limited to some endpoints, `utils/auth.py`; an
account without the delete permission, `routers/chats.py`) or answer too late; the chat then stays, so after every
turn and at start every other chat titled "Hub" is deleted (`leftovers`), and a refusal is shown once in the chat
as an error line with Open WebUI's own reason. Nothing is written anywhere.
"""
from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from hub.core.api import Invalid

from . import link

if TYPE_CHECKING:
    from .routes import AssistantCtx


async def leftovers(host: str, port: int, key: str, spare: str | None) -> str | None:
    """Delete every chat named like the hub's that Open WebUI still has but `spare` (the one in use): one left by a
    delete that was refused or timed out, or by a crash. -> None when all went, else Open WebUI's reason for a
    refused delete. A list that cannot be read (Open WebUI still starting, say) waits for the next sweep."""
    try:
        payload = link.answer(*await link.call(host, port, key, "GET", "/api/v1/chats/", limit=link.FORGET_S))
    except Invalid:
        return None
    reason = None
    for chat in payload if isinstance(payload, list) else []:
        if isinstance(chat, dict) and chat.get("title") == link.HUB_CHAT and isinstance(chat.get("id"), str) \
                and chat["id"] != spare:
            reason = await delete(host, port, key, chat["id"]) or reason
    return reason


async def delete(host: str, port: int, key: str, chat_id: str) -> str | None:
    """Delete one of the hub's Open WebUI chats. -> None when it is gone (or was already), else Open WebUI's reason
    in one line (a refused key, a missing permission, no answer in time)."""
    try:
        status, data = await link.call(host, port, key, "DELETE", f"/api/v1/chats/{quote(chat_id, safe='')}",
                                       limit=link.FORGET_S)
    except Invalid as e:
        return e.text
    if status in (200, 404):
        return None
    return link._detail(data) or f"Open WebUI answered HTTP {status}"


class Remote:
    """The chat-keeping half of `Chat`: its Open WebUI chat, the jobs that delete them, and what a refusal says."""
    ctx: AssistantCtx
    remote: str | None
    cleanup: set[asyncio.Task[Any]]
    lock: asyncio.Lock
    told: str | None

    def config(self) -> dict: ...
    def add(self, role: str, text: str, **extra: Any) -> dict: ...

    def keep(self, job: asyncio.Task[Any]) -> None:
        """A background job that stopping the module waits for."""
        self.cleanup.add(job)
        job.add_done_callback(self.cleanup.discard)

    async def sweep(self) -> None:
        """Delete every chat of the hub's still in Open WebUI but the one in use; nothing to do with no link set."""
        c = self.config()
        if not c["key"]:
            return
        async with self.lock:
            with contextlib.suppress(Invalid):
                host, port = link.endpoint(c["url"])
                self.refused(await leftovers(host, port, c["key"], self.remote))

    async def forget(self, remote: str) -> None:
        """Delete one Open WebUI chat of the conversation's; a refusal is shown, and the next sweep tries again."""
        c = self.config()
        with contextlib.suppress(Invalid):
            host, port = link.endpoint(c["url"])
            self.refused(await delete(host, port, c["key"], remote))

    def refused(self, reason: str | None) -> None:
        """Open WebUI kept a chat of the hub's: say why, once per reason."""
        if reason and reason != self.told:
            self.told = reason
            self.add("error", f"Open WebUI did not delete the Hub's old chat: {reason}")

    async def open_remote(self, host: str, port: int, key: str, model: str) -> str:
        """The conversation's Open WebUI chat, made in a job of its own: if the turn is cancelled (New chat, stop)
        while Open WebUI makes it, the chat is deleted as soon as its id arrives, so none is left behind."""
        job = asyncio.get_running_loop().create_task(link.new_chat(host, port, key, model))
        try:
            return await asyncio.shield(job)
        except asyncio.CancelledError:
            self.keep(job)
            job.add_done_callback(self.orphaned)
            raise

    def orphaned(self, job: asyncio.Task[str]) -> None:
        """A chat made for a turn that was cancelled meanwhile: delete it."""
        if not job.cancelled() and job.exception() is None:
            self.keep(asyncio.get_running_loop().create_task(self.forget(job.result())))

