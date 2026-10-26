"""The Open WebUI link settings (Settings -> Assistant), saved in openwebui.json: the address, the API key, the model
name, the tool server, `keep` (how many exchanges the conversation keeps, turns.py) and `context` (the tokens the
model may read: 0 leaves it to Open WebUI and Ollama, otherwise a whole number from 2048 to 131072, 8192 unless set).

With `context` set, every completion the hub asks for carries `params: {"num_ctx": N}`. Open WebUI merges request
params over the model's own (main.py `merge_model_params`) and, for a model Ollama serves, hands them to Ollama as
its options (utils/payload.py `apply_params_to_form_data`), so Ollama loads the model with that context instead of
its default of 4096 tokens, which a conversation with tool results overflows after a few exchanges.
"""
from __future__ import annotations

from typing import Any

from hub.core.api import Invalid

from . import link, turns

CONTEXT, CONTEXT_LOW, CONTEXT_HIGH = 8192, 2048, 131072
CONTEXT_LABEL = "Context length"
CONTEXT_TEXT = f"{CONTEXT_LABEL} must be 0 or a whole number from {CONTEXT_LOW} to {CONTEXT_HIGH}"
DEFAULTS: dict[str, Any] = {"url": "http://127.0.0.1:3000", "key": "", "model": "", "tools": "", "keep": turns.KEEP,
                            "context": CONTEXT}
LABELS = {"url": "The address", "key": "The key", "model": "The model name", "tools": "The tool server",
          "keep": turns.LABEL, "context": CONTEXT_LABEL}
NUMBERS = ("keep", "context")


def context(value: Any) -> int:
    """A valid `context` from the screen, or Invalid."""
    if isinstance(value, bool) or not isinstance(value, int) or \
            not (value == 0 or CONTEXT_LOW <= value <= CONTEXT_HIGH):
        raise Invalid("context", CONTEXT_TEXT)
    return value


def saved_context(value: Any) -> int:
    """The `context` read from disk: the default when it is missing or not a whole number, 0 when 0 or below,
    else held within the bounds."""
    if isinstance(value, bool) or not isinstance(value, int):
        return CONTEXT
    return 0 if value <= 0 else min(max(value, CONTEXT_LOW), CONTEXT_HIGH)


def read(saved: dict) -> dict:
    """The settings as the hub uses them: what is saved, the default for anything missing or malformed."""
    texts = {k: v if isinstance(v := saved.get(k), str) else d for k, d in DEFAULTS.items() if k not in NUMBERS}
    return {**texts, "keep": turns.saved(saved.get("keep")), "context": saved_context(saved.get("context"))}


def clean(changes: Any) -> dict:
    """The changes from the screen, checked: -> what to save, or Invalid naming the field."""
    if not isinstance(changes, dict) or not changes or set(changes) - set(DEFAULTS):
        raise Invalid("settings", "Only url, key, model, tools, keep and context can change")
    out: dict[str, Any] = {}
    for k, v in changes.items():
        if k == "keep":
            out[k] = turns.count(v)
        elif k == "context":
            out[k] = context(v)
        elif not isinstance(v, str):
            raise Invalid(k, f"{k} must be text")
        elif not link.printable(v.strip()):
            raise Invalid(k, f"{LABELS[k]} may only contain letters, numbers and punctuation")
        else:
            out[k] = v.strip()
    if "url" in out:
        link.endpoint(out["url"])
    return out


def params(config: dict) -> dict:
    """The request fields that carry `context` to Open WebUI: {} when it is 0 (Open WebUI and Ollama decide)."""
    return {"params": {"num_ctx": config["context"]}} if config["context"] else {}


def held(schema: dict | None) -> dict:
    """The request field that holds the reply to `schema`: OpenAI's `response_format` json_schema,
    which Open WebUI hands to Ollama as `format` (utils/payload.py) and forwards as is to an OpenAI-style server;
    {} for None (a chat turn)."""
    if schema is None:
        return {}
    return {"response_format": {"type": "json_schema", "json_schema": {"name": "hub_plan", "schema": schema}}}
