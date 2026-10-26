"""A clip is only its frames and sound: what the muxer wrote about the file is cut out.

Applied once, where an engine's MP4 lands in the clips root. The file is walked as ISO-BMFF boxes, never decoded:
every `udta` box goes (top level, and inside `moov`, its tracks and their media boxes), and so does a `meta`
box sitting directly under `moov` (encoder tags, `©too`/`©cmt`, iTunes-style `ilst` items). Parent sizes are
fixed, 64-bit box headers keep their form, and the top-level boxes keep their order. Only `moov` is read into
memory; `mdat` and the rest are streamed. When a box ahead of the media data shrinks or goes, the chunk offsets
in `stco`/`co64` follow the data. A fragmented file (`moof`, `sidx`...) carries offsets the walk does not
rewrite, so there each cut box becomes a zeroed `free` box of the same size instead and nothing moves.
A file that does not walk as an MP4 raises ValueError.

`facts` reads the same walk for what a clip is: the first video track's size (`tkhd`, 16.16 fixed), its length
(`mdhd` timescale and duration), its frame count (`stts`, checked against `stsz`) and whether any track is sound
(`hdlr` 'soun'). Nothing is decoded; a file the walk refuses (chunk offsets outside the media data included), or
one without a readable video track, raises ValueError.
"""
from __future__ import annotations

import os
import struct
from collections.abc import Callable
from pathlib import Path
from typing import Any, BinaryIO, NamedTuple

WALK = {b"moov", b"trak", b"mdia", b"minf", b"stbl"}   # containers opened on the way to tags and chunk tables
FRAGMENTS = {b"moof", b"mfra", b"sidx", b"ssix"}       # their offsets point across boxes: nothing may move
MOOV_CAP = 256 << 20                                    # a movie header larger than this is not one an engine wrote
COPY = 1 << 20

Move = Callable[[int], int]


class Box(NamedTuple):
    kind: bytes
    start: int        # from the start of whatever holds it
    head: int         # 8, or 16 for a 64-bit size
    size: int         # header included


def strip(path: Path) -> bool:
    """Rewrite the MP4 at `path` without its tags. -> whether anything changed. Raises ValueError for a file that
    is not an MP4 this walk can read, OSError when it cannot be read or written."""
    try:
        return _strip(path)
    except struct.error:
        raise ValueError("A box is torn") from None


def facts(path: Path) -> dict[str, Any]:
    """-> {w, h, fps, frames, seconds, audio} of the MP4 at `path`, from its boxes alone. Raises ValueError for a
    file the walk refuses or without a readable video track, OSError when it cannot be read."""
    try:
        with open(path, "rb") as src:
            boxes, moov, raw = _movie(src)
        traks = [body for kind, body in _kids(memoryview(raw)[moov.head:]) if kind == b"trak"]
        handlers = [bytes(_one(t, b"mdia", b"hdlr")[8:12]) for t in traks]
        inside = _mover(boxes, moov, moov.size)              # every chunk must lie in the media data
        for t in traks:
            for kind, body in _kids(_one(t, b"mdia", b"minf", b"stbl")):
                if kind in (b"stco", b"co64"):
                    _offsets(body, kind == b"co64", inside)
        if b"vide" not in handlers:
            raise ValueError("A clip has no video track")
        return {**_video(traks[handlers.index(b"vide")]), "audio": b"soun" in handlers}
    except struct.error:
        raise ValueError("A box is torn") from None


def _video(trak: memoryview) -> dict[str, Any]:
    tkhd, mdhd = _one(trak, b"tkhd"), _one(trak, b"mdia", b"mdhd")
    w, h = (round(v / 65536) for v in struct.unpack_from(">II", tkhd, 88 if tkhd[0] == 1 else 76))
    scale, length = struct.unpack_from(">IQ" if mdhd[0] == 1 else ">II", mdhd, 20 if mdhd[0] == 1 else 12)
    stbl = _one(trak, b"mdia", b"minf", b"stbl")
    tables = dict(_kids(stbl))
    counts = []
    if b"stts" in tables:
        (n,) = struct.unpack_from(">I", tables[b"stts"], 4)
        if 8 + 8 * n > len(tables[b"stts"]):
            raise ValueError("A time table is torn")
        counts.append(sum(c for c, _ in struct.iter_unpack(">II", tables[b"stts"][8:8 + 8 * n])))
    if b"stsz" in tables:
        counts.append(struct.unpack_from(">I", tables[b"stsz"], 8)[0])
    if not counts or len(set(counts)) != 1:
        raise ValueError("The frame count is missing or the sample tables disagree")
    frames = counts[0]
    if not (w and h and scale and length and frames):
        raise ValueError("The video track has no size, length or frames")
    return {"w": w, "h": h, "fps": round(frames * scale / length, 3), "frames": frames,
            "seconds": round(length / scale, 3)}


def _kids(view: memoryview) -> list[tuple[bytes, memoryview]]:
    """The boxes tiling `view`, as (type, body after the header)."""
    out: list[tuple[bytes, memoryview]] = []
    pos = 0
    while pos < len(view):
        box = _head(bytes(view[pos:pos + 16]), pos, len(view) - pos)
        out.append((box.kind, view[pos + box.head:pos + box.size]))
        pos += box.size
    return out


def _one(view: memoryview, *path: bytes) -> memoryview:
    """The body of the first box down `path` (types, one level each)."""
    for kind in path:
        found = [body for k, body in _kids(view) if k == kind]
        if not found:
            raise ValueError(f"A track has no {kind.decode()} box")
        view = found[0]
    return view


def _movie(src: BinaryIO) -> tuple[list[Box], Box, bytes]:
    """The top-level boxes, the `moov` among them and its bytes."""
    boxes = _top(src, os.fstat(src.fileno()).st_size)
    moov = next(b for b in boxes if b.kind == b"moov")
    if moov.size > MOOV_CAP:
        raise ValueError("The movie header is too large")
    src.seek(moov.start)
    raw = src.read(moov.size)
    if len(raw) != moov.size:
        raise ValueError("The movie header is torn")
    return boxes, moov, raw


def _strip(path: Path) -> bool:
    with open(path, "rb") as src:
        boxes, moov, raw = _movie(src)
        pad = any(b.kind in FRAGMENTS for b in boxes)
        kept = boxes if pad else [b for b in boxes if b.kind != b"udta"]
        size = len(_rebuild(raw, moov, pad, lambda off: off))    # chunk tables keep their width: values never resize
        new = _rebuild(raw, moov, pad, (lambda off: off) if pad else _mover(kept, moov, size))
        if new == raw and not any(b.kind == b"udta" for b in boxes):
            return False
        tmp = path.with_name(f".{path.name}.clean")
        try:
            with open(tmp, "wb") as dst:
                for b in kept:
                    if b is moov:
                        dst.write(new)
                    elif b.kind == b"udta":                     # fragmented: the same room, empty
                        dst.write(_boxhead(b"free", b.size, b.head == 16))
                        _zeros(dst, b.size - b.head)
                    else:
                        _copy(src, dst, b.start, b.size)
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    return True


def _head(raw: bytes, pos: int, room: int) -> Box:
    """The box whose header starts `raw` (at `pos`, with `room` bytes left in its parent)."""
    if len(raw) < 8 or room < 8:
        raise ValueError("A box is torn")
    size, kind = struct.unpack_from(">I4s", raw)
    head = 8
    if size == 1:
        if len(raw) < 16:
            raise ValueError("A box is torn")
        size, head = struct.unpack_from(">Q", raw, 8)[0], 16
    elif size == 0:                                     # runs to the end of its parent
        size = room
    if size < head or size > room:
        raise ValueError("A box size does not fit")
    if not all(0x20 <= c < 0x7F or c == 0xA9 for c in kind):
        raise ValueError("A box has no readable type")
    return Box(kind, pos, head, size)


def _top(src: BinaryIO, total: int) -> list[Box]:
    """The top-level boxes; they must tile the file, start with `ftyp` and hold exactly one `moov`."""
    boxes: list[Box] = []
    pos = 0
    while pos < total:
        src.seek(pos)
        box = _head(src.read(16), pos, total - pos)
        boxes.append(box)
        pos += box.size
    if not boxes or boxes[0].kind != b"ftyp":
        raise ValueError("Not an MP4")
    if sum(b.kind == b"moov" for b in boxes) != 1:
        raise ValueError("An MP4 has one movie header")
    return boxes


def _mover(kept: list[Box], moov: Box, size: int) -> Move:
    """Old file offset -> new one, for an offset inside a kept top-level box other than `moov`."""
    spans: list[tuple[int, int, int]] = []           # old start, old end, shift
    pos = 0
    for b in kept:
        spans.append((b.start, b.start + b.size, pos - b.start))
        pos += size if b is moov else b.size

    def move(off: int) -> int:
        for (start, end, shift), b in zip(spans, kept, strict=True):
            if start <= off < end and b is not moov:
                return off + shift
        raise ValueError("A chunk offset points outside the media data")
    return move


def _rebuild(raw: bytes, box: Box, pad: bool, move: Move) -> bytes:
    """`raw` (one whole container box) again without its tags, its chunk offsets moved."""
    view = memoryview(raw)
    body = _children(view[box.head:box.size], box.kind, pad, move)
    return _boxhead(box.kind, box.head + len(body), box.head == 16) + body


def _children(view: memoryview, parent: bytes, pad: bool, move: Move) -> bytes:
    out: list[bytes] = []
    pos = 0
    while pos < len(view):
        box = _head(bytes(view[pos:pos + 16]), pos, len(view) - pos)
        raw = view[pos:pos + box.size]
        if box.kind == b"udta" or (parent == b"moov" and box.kind == b"meta"):
            if pad:
                out.append(_boxhead(b"free", box.size, box.head == 16) + bytes(box.size - box.head))
        elif box.kind in WALK:
            out.append(_rebuild(bytes(raw), box._replace(start=0), pad, move))
        elif box.kind in (b"stco", b"co64"):
            out.append(bytes(raw[:box.head]) + _offsets(raw[box.head:], box.kind == b"co64", move))
        else:
            out.append(bytes(raw))
        pos += box.size
    return b"".join(out)


def _offsets(body: memoryview, wide: bool, move: Move) -> bytes:
    """A chunk offset table (version/flags, count, offsets) with every offset moved."""
    if len(body) < 8:
        raise ValueError("A chunk table is torn")
    (count,) = struct.unpack_from(">I", body, 4)
    width, fmt, limit = (8, ">Q", 1 << 64) if wide else (4, ">I", 1 << 32)
    end = 8 + count * width
    if end > len(body):
        raise ValueError("A chunk table is torn")
    moved = [move(off) for (off,) in struct.iter_unpack(fmt, body[8:end])]
    if any(not 0 <= off < limit for off in moved):
        raise ValueError("A chunk offset does not fit")
    return bytes(body[:8]) + b"".join(struct.pack(fmt, off) for off in moved) + bytes(body[end:])


def _boxhead(kind: bytes, size: int, large: bool) -> bytes:
    """A header for a box of `size` bytes (header included), in the form the box had."""
    if large:
        return struct.pack(">I4sQ", 1, kind, size)
    if size > 0xFFFFFFFF:
        raise ValueError("A box outgrew its header")
    return struct.pack(">I4s", size, kind)


def _copy(src: BinaryIO, dst: BinaryIO, start: int, size: int) -> None:
    src.seek(start)
    left = size
    while left:
        chunk = src.read(min(COPY, left))
        if not chunk:
            raise ValueError("The file ended early")
        dst.write(chunk)
        left -= len(chunk)


def _zeros(dst: BinaryIO, size: int) -> None:
    block = bytes(min(COPY, size))
    while size:
        dst.write(block[:min(COPY, size)])
        size -= min(COPY, size)

