"""Safetensors headers without torch: 8-byte little-endian length, then a JSON header.

Metadata values are strings (JSON inside them is decoded twice). Bad or oversized headers
count as "no metadata"; the LoRA still lists.
"""
from __future__ import annotations

import base64
import json
import re
import struct
from typing import Any

CAP = 100 * 1024 * 1024


def read(path: str, cap: int = CAP) -> tuple[dict[str, str], dict[str, Any]] | None:
    """(metadata, tensors) or None for anything that is not a sane safetensors header."""
    try:
        with open(path, "rb") as f:
            head = f.read(8)
            if len(head) != 8:
                return None
            (size,) = struct.unpack("<Q", head)
            if not 0 < size <= cap:
                return None
            raw = f.read(size)
        header = json.loads(raw) if len(raw) == size else None
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(header, dict):
        return None
    meta = header.pop("__metadata__", None)
    meta = {str(k): v for k, v in meta.items() if isinstance(v, str)} if isinstance(meta, dict) else {}
    return meta, header


def _phrases(value: Any) -> list[str]:
    items = value if isinstance(value, list) else re.split(r"[,;\n]", str(value or ""))
    return [str(item).strip()[:80] for item in items if str(item).strip()]


def _json(meta: dict[str, str], key: str) -> Any:
    try:
        return json.loads(meta.get(key) or "null")
    except ValueError:
        return None


def _first(meta: dict[str, str], *keys: str) -> str | None:
    return next((meta[k].strip() for k in keys if meta.get(k, "").strip() not in ("", "None")), None)


def summary(meta: dict[str, str], tensors: dict[str, Any]) -> dict[str, Any]:
    """The few facts the panel shows: title, trigger words, recommended weight, whether a cover is embedded."""
    triggers = _phrases(meta.get("modelspec.trigger_phrase"))
    artifact = _json(meta, "sd.artifact.v1")
    artifact = artifact if isinstance(artifact, dict) else {}
    for phrase in _phrases(artifact.get("triggers") or []):
        if phrase.lower() not in (t.lower() for t in triggers):
            triggers.append(phrase)
    weight = artifact.get("recommended_weight")
    return {
        "title": _first(meta, "modelspec.title"),
        "triggers": triggers[:20],
        "weight": float(weight) if isinstance(weight, (int, float)) and 0 <= weight <= 2 else None,
        "thumb": str(meta.get("modelspec.thumbnail", "")).startswith("data:image"),
    }


def thumbnail(path: str) -> bytes | None:
    """The embedded `modelspec.thumbnail` image bytes (read only when a cover is drawn)."""
    parsed = read(path)
    value = parsed[0].get("modelspec.thumbnail", "") if parsed else ""
    if not value.startswith("data:image") or "," not in value:
        return None
    try:
        return base64.b64decode(value.split(",", 1)[1], validate=False)
    except ValueError:
        return None
