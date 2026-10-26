"""The joins of a spoken line sent as several turns: each run of the engine's join silence taken out and
the two sides crossfaded at equal power, so the turns flow into each other with no cut to dead silence. Stdlib only.

The engine generates each turn as its own pass, cuts it 0.14 s after its last word (and before its first), and joins
the turns with exactly `round(0.18 × rate)` sample frames of zeros (the speech model's upstream `dialogue.py:22`,
`:24`, `:440-442`); no caller can set either. `smooth` finds those runs (every channel zero, exactly that long). When
it finds one fewer than the turns, it writes the WAV again (atomically: a temp file beside it, then replaced) with
each run removed and the end of one turn overlapping the start of the next by `overlap` seconds, the first fading
out as cos and the second in as sin over the same frames. Any other count, an overlap of 0, or a format other than
PCM 16/24/32-bit or IEEE float leaves the file as it was. The words are untouched: the overlap (at most 0.14 s, the
setting's range) lies inside the pad the engine leaves around them.
"""
from __future__ import annotations

import math
import os
import re
import struct
from typing import Any

from . import faces, judge, takemeasure
from .tasks import SPEAKER

# The engine names this module reads: none. The numbers below mirror upstream dialogue.py (cited above).
READS: dict[str, dict[str, str]] = {c: {} for c in ("wgp", "api", "definition", "settings", "generate_video",
                                                    "suffixes")}
PAUSE_SECONDS = 0.18           # the zeros between two turns, dialogue.py:22
PAD_SECONDS = 0.14             # what the engine leaves after a last word and before a first, dialogue.py:24
PCM, FLOAT, EXTENSIBLE = 1, 3, 0xFFFE
_CODES = {(PCM, 2): "h", (PCM, 4): "i", (FLOAT, 4): "f", (FLOAT, 8): "d"}


def _chunks(raw: bytes) -> list[tuple[bytes, bytes]]:
    """The chunks of a RIFF/WAVE file in order; ValueError when it is not one."""
    if len(raw) < 12 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    out, at = [], 12
    while at + 8 <= len(raw):
        kind, size = raw[at:at + 4], struct.unpack("<I", raw[at + 4:at + 8])[0]
        out.append((kind, raw[at + 8:at + 8 + size]))
        at += 8 + size + (size & 1)
    return out


def _format(fmt: bytes) -> tuple[int, int, int, int] | None:
    """(tag, channels, rate, bytes per sample) of a format this module mixes, else None."""
    if len(fmt) < 16:
        return None
    tag, channels, rate, _, align, bits = struct.unpack("<HHIIHH", fmt[:16])
    if tag == EXTENSIBLE and len(fmt) >= 26:
        tag = struct.unpack("<H", fmt[24:26])[0]       # the sub-format GUID's first two bytes
    width = bits // 8
    ok = channels > 0 and rate > 0 and bits % 8 == 0 and align == channels * width and (
        (tag == PCM and width in (2, 3, 4)) or (tag == FLOAT and width in (4, 8)))
    return (tag, channels, rate, width) if ok else None


def runs(data: bytes, align: int, frames: int) -> list[tuple[int, int]]:
    """The runs of exactly `frames` all-zero sample frames in `data`, as byte spans (start, end) on frame bounds."""
    out = []
    for m in re.finditer(rb"\x00{%d,}" % (frames * align), data):
        start, end = -(-m.start() // align) * align, m.end() // align * align
        if (end - start) // align == frames:
            out.append((start, end))
    return out


def _decode(part: bytes, tag: int, width: int) -> list[float]:
    if width == 3:
        return [int.from_bytes(part[k:k + 3], "little", signed=True) / 8388608 for k in range(0, len(part), 3)]
    values = struct.unpack(f"<{len(part) // width}{_CODES[(tag, width)]}", part)
    return [v / (1 << (8 * width - 1)) for v in values] if tag == PCM else list(values)


def _encode(values: list[float], tag: int, width: int) -> bytes:
    if tag == FLOAT:
        return struct.pack(f"<{len(values)}{_CODES[(tag, width)]}", *values)
    top = (1 << (8 * width - 1)) - 1
    whole = [max(-top - 1, min(top, round(v * (top + 1)))) for v in values]
    if width == 3:
        return b"".join(v.to_bytes(3, "little", signed=True) for v in whole)
    return struct.pack(f"<{len(whole)}{_CODES[(tag, width)]}", *whole)


def crossfade(a: bytes, b: bytes, frames: int, channels: int, tag: int, width: int) -> bytes:
    """`a` then `b`, the last `frames` of `a` and the first of `b` laid over each other: `a` × cos, `b` × sin."""
    align = channels * width
    frames = min(frames, len(a) // align, len(b) // align)
    if frames <= 0:
        return a + b
    tail, head = _decode(a[len(a) - frames * align:], tag, width), _decode(b[:frames * align], tag, width)
    mixed = []
    for k in range(frames * channels):
        t = (k // channels + 0.5) / frames * math.pi / 2
        mixed.append(tail[k] * math.cos(t) + head[k] * math.sin(t))
    return a[:len(a) - frames * align] + _encode(mixed, tag, width) + b[frames * align:]


def smooth(path: str, turns: int, overlap: float) -> bool:
    """Write `path` again with its `turns - 1` joins crossfaded over `overlap` s. False, the file left as it was,
    when the overlap is 0, the format is not one this module mixes, or the join runs are not `turns - 1`."""
    if overlap <= 0 or turns < 2:
        return False
    with open(path, "rb") as f:
        found = _chunks(f.read())
    fmt = next((body for kind, body in found if kind == b"fmt "), None)
    data = next((body for kind, body in found if kind == b"data"), None)
    form = _format(fmt) if fmt is not None else None
    if form is None or data is None:
        return False
    tag, channels, rate, width = form
    align = channels * width
    data = data[:len(data) // align * align]
    joins = runs(data, align, round(PAUSE_SECONDS * rate))
    if len(joins) != turns - 1:
        return False
    cuts = [0, *(k for span in joins for k in span), len(data)]
    out, fade = data[cuts[0]:cuts[1]], round(min(overlap, PAD_SECONDS) * rate)
    for k in range(2, len(cuts), 2):
        out = crossfade(out, data[cuts[k]:cuts[k + 1]], fade, channels, tag, width)
    body = b"WAVE"
    for kind, part in ((b"fmt ", fmt), (b"data", out)):
        body += kind + struct.pack("<I", len(part)) + part + (b"\x00" if len(part) & 1 else b"")
    tmp = os.path.join(os.path.dirname(path), f".{os.path.basename(path)}.hub-join")
    try:
        with open(tmp, "wb") as f:
            f.write(b"RIFF" + struct.pack("<I", len(body)) + body)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return True


def finish(request: Any, sent: dict, files: list[str]) -> dict[str, Any] | None:
    """After a task: a spoken line the adapter sent as more than one turn (`Speaker 1:` blocks in the script) has its
    joins smoothed by the request's `join_seconds` (a file that cannot be read is left as it was); then, when the
    request asks for it (`judge`), the words judge hears the line and its verdict is returned for
    `task_done` (`{"words": …}`), None when there is none; with `measure` the take's boundaries and
    loudness beside it (`{"measure": …}`, `takemeasure`); a sound with `measure`, its measurement
    without words (and its decay with `decay`). A clip with identity pictures and `judge` set is scored
    by the face judge (`faces.score`): `{"face": …}`; with `words` its soundtrack is heard as a
    line is: `{"words": …}` beside it."""
    if getattr(request, "kind", None) == "video":
        verdict = _faces(request, sent, files)
        if getattr(request, "judge", None) and getattr(request, "words", None) and files:
            heard = judge.words(files[-1], str(request.words))
            verdict = {**(verdict or {}), "words": heard} if heard is not None else verdict
        return verdict
    if getattr(request, "kind", None) == "sound":           # a cue or the room, measured when asked
        if not files or not getattr(request, "measure", False):
            return None
        return {"measure": takemeasure.measure(files[-1], None, decay=bool(getattr(request, "decay", False)))}
    if getattr(request, "kind", None) != "speech":
        return None
    turns = str(sent.get("prompt") or "").count(SPEAKER)
    if turns >= 2 and getattr(request, "join_seconds", None):
        for path in files:
            try:
                smooth(path, turns, float(request.join_seconds))
            except (OSError, ValueError, struct.error):
                pass                               # the line plays as the engine made it
    if not files or not (getattr(request, "judge", False) or getattr(request, "measure", False)):
        return None
    verdict = judge.words(files[-1], str(getattr(request, "prompt", "") or "")) if getattr(
        request, "judge", False) else None
    out: dict[str, Any] = {"words": verdict} if verdict is not None else {}
    if getattr(request, "measure", False):                 # a Track take, measured on arrival
        out["measure"] = takemeasure.measure(files[-1], verdict)
    return out or None


def _faces(request: Any, sent: dict, files: list[str]) -> dict[str, Any] | None:
    """The judges on a landed clip: the face and frame judges for the characters in the request's identity pictures
    (by name; nameless ones as one), the mouth judge for the speaker (with no identity picture, on the
    largest face when the clip has a kept soundtrack); a continue is judged from its new frames on. None when no
    judge was asked, or nothing here is for one (no identity, no soundtrack)."""
    from . import upstream  # late: the facts file; upstream imports this module

    device = getattr(request, "judge", None)
    identities = [r for r in getattr(request, "references", []) if getattr(r, "role", None) == "identity"]
    if not device or not files or not (identities or getattr(request, "sound", None)):
        return None
    people: dict[str, list[str]] = {}
    for r in identities:
        people.setdefault(str(r.name or "the character"), []).append(r.path)
    continued = any(getattr(r, "role", None) == "source" for r in getattr(request, "references", []))
    new = max(1, int(getattr(request, "frames", 0) or 0) - 1) if continued else None   # a continue grows by n − 1
    try:
        return faces.score(files[-1], people, upstream.facts_file()["faces"], str(device),
                           float(getattr(request, "judge_bar", 0.3) or 0.3), new_frames=new,
                           speaker=getattr(request, "speaker", None))
    except Exception as exc:  # noqa: BLE001  (the judge is advice)
        return {"face": None, "why": (str(exc).strip().splitlines() or [type(exc).__name__])[0][:160]}
