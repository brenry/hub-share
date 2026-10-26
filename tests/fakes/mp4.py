"""Small MP4-shaped files (stdlib) and a reader for them.

`tiny_mp4`: `ftyp`, a `moov` holding an `mvhd` and a video track (and, with `audio`, a sound track) down to their
sample tables, and an `mdat` of filler bytes the chunk tables point into; its facts are the arguments (960x544,
24 fps, 124 frames by default). `tagged_mp4`: a video track of `CHUNKS` placed in the `mdat` where its chunk table
(`stco`, or `co64` with 64-bit box headers and version-1 `tkhd`/`mdhd`) says, and the tags a muxer leaves: `udta`
at the top level, in `moov` and in the track, and a `meta`/`ilst` under `moov`. `read` walks any of them box by box.
"""
from __future__ import annotations

import struct

CHUNKS = (b"frame-one", b"frame-two!", b"frame-three")
TAGS = (b"\xa9too", b"\xa9cmt", b"ilst")
OPEN = {b"moov": 0, b"trak": 0, b"mdia": 0, b"minf": 0, b"stbl": 0, b"udta": 0, b"meta": 4, b"ilst": 0}
MVHD_BODY = struct.pack(">B3xIIII", 0, 0, 0, 1000, 5000) + bytes(80)
SCALE = 12288                                          # the video timescale an MP4 muxer picks for 24 fps
FTYP = b"isom" + struct.pack(">I", 512) + b"isomiso2avc1mp41"


def box(kind: bytes, payload: bytes, large: bool = False) -> bytes:
    if large:
        return struct.pack(">I4sQ", 1, kind, 16 + len(payload)) + payload
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def full(kind: bytes, payload: bytes) -> bytes:
    return box(kind, bytes(4) + payload)              # version 0, no flags


def trak(handler: bytes, w: int, h: int, scale: int, delta: int, frames: int, offsets: list[int],
         large: bool = False, extra: bytes = b"") -> bytes:
    """A track down to its sample tables: `frames` samples of `delta` ticks at `scale`, the chunk table `offsets`;
    `large`: version-1 `tkhd`/`mdhd` and a `co64`. `extra` goes at the end of the `trak` (its tags)."""
    size, length = struct.pack(">II", w << 16, h << 16), frames * delta
    if large:
        tkhd = box(b"tkhd", b"\x01" + bytes(87) + size)
        mdhd = box(b"mdhd", struct.pack(">B3xQQIQ", 1, 0, 0, scale, length) + bytes(4))
    else:
        tkhd = full(b"tkhd", bytes(72) + size)
        mdhd = full(b"mdhd", struct.pack(">IIII", 0, 0, scale, length) + bytes(4))
    runs = [(frames - 1, delta), (1, delta)] if frames > 1 else [(frames, delta)]   # two runs: the count is summed
    stts = full(b"stts", struct.pack(">I", len(runs)) + b"".join(struct.pack(">II", *r) for r in runs))
    stsz = full(b"stsz", struct.pack(">II", 1, frames))
    fmt = ">Q" if large else ">I"
    table = full(b"co64" if large else b"stco", struct.pack(">I", len(offsets)) +
                 b"".join(struct.pack(fmt, o) for o in offsets))
    stbl = box(b"stbl", full(b"stsd", struct.pack(">I", 0)) + stts + stsz + table)
    hdlr = full(b"hdlr", bytes(4) + handler + bytes(12) + b"Track\0")
    return box(b"trak", tkhd + box(b"mdia", mdhd + hdlr + box(b"minf", stbl)) + extra)


def _tiny_moov(at: int, w: int, h: int, fps: int, frames: int, audio: bool) -> bytes:
    tracks = trak(b"vide", w, h, SCALE, SCALE // fps, frames, [at])
    if audio:                                          # AAC: 1024 samples a packet at 48 kHz, as long as the video
        tracks += trak(b"soun", 0, 0, 48000, 1024, -(-frames * 48000 // (fps * 1024)), [at])
    return box(b"moov", box(b"mvhd", MVHD_BODY) + tracks)


def tiny_mp4(size: int = 5000, *, w: int = 960, h: int = 544, fps: int = 24, frames: int = 124,
             audio: bool = False) -> bytes:
    """An MP4 of exactly `size` bytes (at least 1000) whose tracks say `w`x`h`, `fps`, `frames` (and sound with
    `audio`); the `mdat` bytes count up so a range is easy to check, and every chunk offset points at its start."""
    ftyp = box(b"ftyp", FTYP)
    at = len(ftyp) + len(_tiny_moov(0, w, h, fps, frames, audio)) + 8
    head = ftyp + _tiny_moov(at, w, h, fps, frames, audio)
    if size < len(head) + 8 + 1:
        raise ValueError("too small for an MP4")
    filler = bytes(i % 251 for i in range(size - len(head) - 8))
    return head + box(b"mdat", filler)


def _moov(offsets: list[int], large: bool) -> bytes:
    tags = box(b"udta", box(b"\xa9cmt", b"seed 1234"))
    video = trak(b"vide", 960, 544, SCALE, SCALE // 24, len(offsets), offsets, large, tags)
    item = box(b"\xa9too", box(b"data", struct.pack(">II", 1, 0) + b"Encoder 61.1"))
    meta = full(b"meta", full(b"hdlr", bytes(4) + b"mdir" + b"appl" + bytes(9)) + box(b"ilst", item))
    udta = box(b"udta", meta + box(b"\xa9too", b"Encoder 61.1"))
    under = full(b"meta", full(b"hdlr", bytes(4) + b"mdir" + bytes(13)) +
                 box(b"ilst", box(b"\xa9cmt", box(b"data", struct.pack(">II", 1, 0) + b"a prompt"))))
    return box(b"moov", box(b"mvhd", MVHD_BODY) + video + udta + under, large)


def tagged_mp4(moov_first: bool = True, large: bool = False) -> bytes:
    """A tagged MP4 whose chunk table points at `CHUNKS` in its `mdat`; `large`: 64-bit `moov`/`mdat` and `co64`."""
    ftyp = box(b"ftyp", FTYP)
    top_udta = box(b"udta", box(b"\xa9cmt", b"made on a box"))
    lead = b"\x00lead\x00"                             # the first chunk is not at the start of the data
    payload = lead + b"".join(CHUNKS)
    starts = [len(lead) + sum(map(len, CHUNKS[:k])) for k in range(len(CHUNKS))]
    mdat_head = 16 if large else 8
    if moov_first:
        data_at = len(ftyp) + len(_moov([0] * len(CHUNKS), large)) + len(top_udta) + mdat_head
        moov = _moov([data_at + s for s in starts], large)
        return ftyp + moov + top_udta + box(b"mdat", payload, large)
    data_at = len(ftyp) + mdat_head
    return ftyp + box(b"mdat", payload, large) + _moov([data_at + s for s in starts], large) + top_udta


def read(data: bytes, start: int = 0, end: int | None = None,
         path: tuple[bytes, ...] = ()) -> list[tuple[tuple[bytes, ...], int, int, int]]:
    """Every box as (path, start, header length, size); ValueError when the sizes do not tile."""
    end = len(data) if end is None else end
    out: list[tuple[tuple[bytes, ...], int, int, int]] = []
    pos = start
    while pos < end:
        if end - pos < 8:
            raise ValueError("a torn box")
        size, kind = struct.unpack_from(">I4s", data, pos)
        head = 8
        if size == 1:
            size, head = struct.unpack_from(">Q", data, pos + 8)[0], 16
        elif size == 0:
            size = end - pos
        if size < head or pos + size > end:
            raise ValueError("a box that does not fit")
        here = (*path, kind)
        out.append((here, pos, head, size))
        if kind in OPEN:
            out += read(data, pos + head + OPEN[kind], pos + size, here)
        pos += size
    return out


def chunk_offsets(data: bytes) -> list[int]:
    [(path, pos, head, _)] = [b for b in read(data) if b[0][-1] in (b"stco", b"co64")]
    (count,) = struct.unpack_from(">I", data, pos + head + 4)
    fmt = ">Q" if path[-1] == b"co64" else ">I"
    return [o for (o,) in struct.iter_unpack(fmt, data[pos + head + 8:pos + head + 8 + count * struct.calcsize(fmt)])]


def chunks(data: bytes) -> list[bytes]:
    """The bytes the chunk table points at, as long as each of `CHUNKS`."""
    return [data[o:o + len(c)] for o, c in zip(chunk_offsets(data), CHUNKS, strict=True)]
