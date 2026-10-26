"""Controller <-> worker wire format, shared by both sides (stdlib only, Python 3.10+).

NDJSON over a socketpair: one JSON object per line, at most MAX_LINE bytes.

Controller -> worker (`op`):
  run     {job, task, request}         one picture, clip or join, in the Hub's words (`engineapi`: a
                                       `PictureRequest`, `ClipRequest` or `JoinRequest`, plus its `kind`);
                                       the worker's adapter turns it into the engine's task
  cancel  {job}                        cooperative; the task ends with ok=false, stage "cancelled"
  query   {id, what: "catalog"}        read-only engine facts
  stop    {}                           exit now (frees the CUDA context)

Worker -> controller (`ev`):
  ready      {pid, engine:{api, version, settings_version}}
  fatal      {text}                    start failed; the worker exits
  model      {state: loading|loaded, model, rss_mb}
  progress   {job, task, phase, step, steps, pct, text}
  output     {job, task, file}         absolute path in the outbox
  task_done  {job, task, ok, seconds, model, peak_vram_mb, peak_rss_mb, error?:{stage, text}}
                                       stage: cancelled | oom | generation | runtime (`engineapi.STAGES`)
  reply      {id, data} | {id, error}
"""
from __future__ import annotations

import json
from typing import Any

PROTO = 2
MAX_LINE = 1 << 20

# The worker's environment: offline, no telemetry, no bytecode written into the engine root.
OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "DO_NOT_TRACK": "1",
    "GRADIO_ANALYTICS_ENABLED": "False",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONNOUSERSITE": "1",
    "PYTHONUNBUFFERED": "1",
}


class ProtocolError(Exception):
    """A malformed or oversized line."""


def encode(message: dict[str, Any]) -> bytes:
    data = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(data) > MAX_LINE:
        raise ProtocolError("message too large")
    return data


def decode(line: bytes) -> dict[str, Any]:
    if len(line) > MAX_LINE:
        raise ProtocolError("message too large")
    try:
        value = json.loads(line)
    except ValueError:
        raise ProtocolError("message is not JSON") from None
    if not isinstance(value, dict):
        raise ProtocolError("message is not an object")
    return value


class LineBuffer:
    """Splits a byte stream into lines; refuses a line longer than MAX_LINE."""

    def __init__(self) -> None:
        self._buf = b""

    def feed(self, chunk: bytes) -> list[bytes]:
        self._buf += chunk
        *lines, self._buf = self._buf.split(b"\n")
        if len(self._buf) > MAX_LINE:
            raise ProtocolError("message too large")
        return [line for line in lines if line.strip()]
