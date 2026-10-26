"""Bus envelope, limits, roles, lanes, error and close codes."""
from __future__ import annotations

import json
import re
from typing import Any

PROTO = 1
MAX_BYTES = 65_536
MAX_LINES = 16
RATE_PER_S = 30.0
RATE_BURST = 60.0
QUEUE_LIMIT = 256
STRIKES = 3

ROLES = ("workspace", "media", "aux")
CORE_LANES = ("presence", "focus", "jobs", "gpu", "media", "settings")
DEFAULT_LANES: dict[str, tuple[str, ...]] = {
    "workspace": ("presence", "jobs", "gpu", "settings"),
    "media": ("presence", "focus", "media", "jobs", "settings"),   # jobs: the judges' verdict on a clip
    "aux": ("presence", "focus", "settings"),
}

CLOSE_OFF = 4000
CLOSE_RESTART = 4001
CLOSE_UNPAIRED = 4003
CLOSE_PROTOCOL = 4008
CLOSE_REPLACED = 4009
CLOSE_TOO_MANY = 4013
CLOSE_RATE = 4029
CLOSE_SLOW = 4030
CLOSE_TOO_BIG = 1009

_TYPE = re.compile(r"^[a-z0-9_.]{1,64}$")
ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class ProtocolError(Exception):
    """A malformed envelope or a message this screen may not send."""


class Refused(Exception):
    """A request the controller turns down: becomes a bus `error` (or an HTTP status)."""

    def __init__(self, code: str, text: str) -> None:
        super().__init__(text)
        self.code, self.text = code, text


def parse(raw: str) -> dict:
    """Validate one inbound frame. -> {"t", "id", "re", "d"}."""
    try:
        env = json.loads(raw)
    except json.JSONDecodeError:
        raise ProtocolError("Not valid JSON") from None
    if not isinstance(env, dict) or set(env) - {"t", "id", "re", "d"}:
        raise ProtocolError("Unknown envelope fields")
    t = env.get("t")
    if not isinstance(t, str) or not _TYPE.match(t):
        raise ProtocolError("Missing or bad message type")
    for key in ("id", "re"):
        if key in env and (not isinstance(env[key], str) or not ID.match(env[key])):
            raise ProtocolError(f"Bad {key}")
    d = env.get("d")
    if d is not None and not isinstance(d, dict):
        raise ProtocolError("d must be an object or null")
    return {"t": t, "id": env.get("id"), "re": env.get("re"), "d": d or {}}


_NONE: Any = object()


def msg(t: str, d: Any = _NONE, *, id: str | None = None, re: str | None = None) -> dict:
    """An envelope. `d=None` is sent as an explicit null (e.g. `focus` with no tool)."""
    out: dict[str, Any] = {"t": t}
    if id is not None:
        out["id"] = id
    if re is not None:
        out["re"] = re
    if d is not _NONE:
        out["d"] = d
    return out


def error(code: str, text: str, *, re: str | None = None, field: str | None = None) -> dict:
    d: dict[str, Any] = {"code": code, "text": text}
    if field is not None:
        d["field"] = field
    return msg("error", d, re=re)


def encode(m: dict) -> str:
    return json.dumps(m, separators=(",", ":"), ensure_ascii=False)
