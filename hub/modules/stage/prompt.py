"""The pans' prompts: the Stage fields as typed, one a line, then, when the pan's Prompt box holds any
non-space character, "\n\n" and the box byte for byte. Nothing else: no label, default, keep sentence or fixed text
of the Hub's.

*Build:* `<Picture N> - <keep>` for each picture with a Keep line (an empty Keep sends no line), the Description,
each piece. *Change:* the change's words, the Description and what the set holds after the change (`held`).
*House:* the era, size, dress and hair (`era` required). *House change:* its words, then the house fields. Every
field is one line (whitespace closed up) with `<` and `>` removed, so no typed word reads as a label; the
box is not a field and goes as typed. The prompt is sent whole, whatever its length.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from hub.core.api import Invalid

SEPARATOR = "\n\n"
NO_ERA = "Say the audience's era"
HOUSE_FIELDS = ("era", "size", "dress", "hair")


def line(value: Any) -> str:
    """`value` as one line: `<` and `>` removed, whitespace closed up; anything but text is ""."""
    return " ".join(value.replace("<", " ").replace(">", " ").split()) if isinstance(value, str) else ""


def _finish(a: Sequence[str], box: Any) -> str:
    """A's lines that hold text, joined by "\n"; then "\n\n" and the box when it holds text."""
    text = "\n".join(t for t in a if t)
    if isinstance(box, str) and box.strip():
        text += SEPARATOR + box
    return text


def build(pictures: Sequence[Mapping[str, Any]], description: Any, pieces: Sequence[Any], box: Any = "") -> str:
    """The build's prompt: `pictures` in box order, each {keep}."""
    lines = [f"<Picture {n}> - {keep}" for n, p in enumerate(pictures, 1) if (keep := line(p.get("keep")))]
    return _finish([*lines, line(description), *(line(p) for p in pieces)], box)


def held(record: Mapping[str, Any]) -> list[str]:
    """What the set holds: its elements, then each prop with its place words."""
    props = [p for p in record.get("props") or [] if isinstance(p, dict)]
    return [*(line(e) for e in record.get("elements") or [] if isinstance(e, str)),
            *(" ".join(t for t in (line(p.get("name")), line((p.get("place") or {}).get("words"))) if t)
              for p in props)]


def change(words: Any, op: Mapping[str, Any], after: Mapping[str, Any], box: Any = "") -> str:
    """The change's prompt: `after` is the record with the change applied (`change.apply`); `op` is not sent."""
    return _finish([line(words), line(after.get("description")), *held(after)], box)


def house_lines(house: Mapping[str, Any]) -> list[str]:
    """The house fields as typed, era first; no era: refused."""
    if not line(house.get("era")):
        raise Invalid("era", NO_ERA)
    return [line(house.get(k)) for k in HOUSE_FIELDS]


def house(words: Mapping[str, Any], box: Any = "") -> str:
    """The house's prompt from `words` {era, dress, hair, size}."""
    return _finish(house_lines(words), box)


def house_change(words: Any, house_words: Mapping[str, Any], box: Any = "") -> str:
    """The house change's prompt: its words, then the house fields."""
    return _finish([line(words), *house_lines(house_words)], box)
