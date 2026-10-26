"""Network card routes: GET /api/network, PATCH|DELETE /api/network/devices/{id}, POST /api/network/pair."""
from __future__ import annotations

from typing import Any, Protocol

from starlette.requests import Request

from hub.core.api import CardState, CardStatus, Ctx, Invalid


class NetworkAdmin(Protocol):
    """The core-owned surface the controller hands this module as `ctx.network`."""

    def view(self, current: str | None) -> dict: ...
    def rename(self, device_id: str, name: str) -> dict: ...
    def remove(self, device_id: str, current: str | None) -> None: ...
    def pair_link(self, name: str) -> dict: ...
    def card(self) -> tuple[str, CardStatus]: ...


class NetworkCtx(Ctx, Protocol):
    network: NetworkAdmin


def _current(request: Request) -> str | None:
    device = request.state.device
    return device.id if device is not None else None


async def _body(request: Request) -> dict:
    body: Any = await request.json()
    if not isinstance(body, dict):
        raise Invalid("body", "Send a JSON object")
    return body


async def view(ctx: NetworkCtx, request: Request) -> dict:
    return ctx.network.view(_current(request))


async def rename(ctx: NetworkCtx, request: Request) -> dict:
    return ctx.network.rename(request.path_params["id"], (await _body(request)).get("name"))


async def remove(ctx: NetworkCtx, request: Request) -> dict:
    ctx.network.remove(request.path_params["id"], _current(request))
    return {"ok": True}


async def pair(ctx: NetworkCtx, request: Request) -> dict:
    body = await _body(request)
    return ctx.network.pair_link(body.get("name"))


def card(ctx: NetworkCtx) -> CardState:
    summary, status = ctx.network.card()
    return CardState(summary, status)
