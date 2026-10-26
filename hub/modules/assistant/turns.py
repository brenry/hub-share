"""How much of the conversation is kept: the last `keep` exchanges (Settings -> Assistant, "Replies kept", a whole
number from 1 to 20, 6 unless set). An exchange is one `user` message and every message after it up to the next
one: the reply, a turn that ran tools and said nothing, an error line. After each turn everything older is deleted
(`purge`): it is neither shown, nor sent to Open WebUI, nor kept anywhere. A changed number applies when the
next turn ends.

What is sent of the kept exchanges is lean (`lean`): the newest exchange (the message being answered and anything
after it) goes as it is; in every older one, each tool result inside a reply's `output` items goes as its first line
cut to 120 characters. A tool result repeats the settings it set (the whole draft, as JSON), so a few exchanges of
them overflow a small model's context (Ollama's default is 4096 tokens). The tool calls themselves go whole, so the
model still sees that it acts through tools and the draft it wrote. Only the copy that is sent is cut; the kept
messages are not changed.

A Hub line (role "hub") belongs to the exchange it arrived in and starts none; it is sent (`notes`) as a
user message "Hub note: <text>" right before the next `user` message, so the newest `user` message is still the typed
one.

`said` gives the Director the newest `user` message, word for word, while the turn runs (the "said"
service)."""
from __future__ import annotations

from typing import Any

from hub.core.api import Invalid

KEEP, LOW, HIGH = 6, 1, 20
CUT = 120                      # characters an older tool result keeps of its first line
LABEL = "Replies kept"
TEXT = f"{LABEL} must be a whole number from {LOW} to {HIGH}"


def count(value: Any) -> int:
    """A valid `keep` from the screen, or Invalid."""
    if isinstance(value, bool) or not isinstance(value, int) or not LOW <= value <= HIGH:
        raise Invalid("keep", TEXT)
    return value


def saved(value: Any) -> int:
    """The `keep` read from disk: the default when it is missing or not a whole number, held within the bounds."""
    if isinstance(value, bool) or not isinstance(value, int):
        return KEEP
    return min(max(value, LOW), HIGH)


def purge(messages: list[dict], keep: int) -> tuple[list[dict], int]:
    """-> (the messages of the last `keep` exchanges, how many older ones were deleted). The older ones are emptied
    as well, so nothing that still points at one can read it."""
    starts = [i for i, m in enumerate(messages) if m["role"] == "user"]
    if len(starts) <= keep:
        return messages, 0
    first = starts[-keep]
    for m in messages[:first]:
        m.clear()
    return messages[first:], first


def said(messages: list[dict], busy: bool) -> dict | None:
    """While a turn is `busy`, the newest `user` message as typed -> {id, text, first} (`first`: it is
    the conversation's only `user` message); None when idle or with none."""
    mine = [m for m in messages if m.get("role") == "user"] if busy else []
    return {"id": mine[-1]["id"], "text": mine[-1]["text"], "first": len(mine) == 1} if mine else None


NOTE = "Hub note: "


def notes(sent: list[dict]) -> list[dict]:
    """The conversation as it is sent (chat.wire's messages, a Hub line as role "hub") with each Hub line made a user
    message `Hub note: <text>` placed right before the first user message after it, in their order; a Hub line with
    no user message after it is not sent (a line that lands during a turn goes on the next). With no Hub line, the
    list given, as it is."""
    if not any(m.get("role") == "hub" for m in sent):
        return sent
    out: list[dict] = []
    held: list[dict] = []
    for m in sent:
        if m.get("role") == "hub":
            held.append({"role": "user", "content": f"{NOTE}{m['content']}"})
            continue
        if m.get("role") == "user":
            out += held
            held = []
        out.append(m)
    return out


def lean(sent: list[dict]) -> list[dict]:
    """The conversation as it is sent (chat.wire's messages), with every exchange before the newest one's tool results
    cut to `brief` form. New lists and dicts where anything is cut; the messages given are not changed."""
    last = max((i for i, m in enumerate(sent) if m.get("role") == "user"), default=0)
    return [{**m, "output": [_result(x) for x in m["output"]]} if i < last and isinstance(m.get("output"), list)
            else m for i, m in enumerate(sent)]


def _result(item: Any) -> Any:
    """A `function_call_output` item with its text in brief form and no images; any other item as it is. Its type,
    ids and status stay, so Open WebUI still pairs the result with its call (utils/misc.py
    `convert_output_to_messages`)."""
    if not isinstance(item, dict) or item.get("type") != "function_call_output":
        return item
    found = item.get("output")
    if isinstance(found, str):
        text = found
    elif isinstance(found, list):
        text = "".join(str(p.get("text", "")) for p in found if isinstance(p, dict) and p.get("type") == "input_text")
    else:
        text = ""
    return {**item, "output": [{"type": "input_text", "text": brief(text)}]}


def brief(text: str) -> str:
    """The first line of `text`, cut to CUT characters; "…" ends it when anything was left out."""
    whole = text.strip()
    line = whole.split("\n", 1)[0].rstrip()
    short = line[:CUT].rstrip()
    return short if short == whole else f"{short}…"
