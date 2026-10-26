"""Small WAV files (stdlib) for the sound tests: `tiny_wav` is `seconds` of silence at `rate` Hz, 16-bit, `channels`
channels; `tagged` puts the chunks an engine leaves (a `LIST`/`INFO` holding text, a `JUNK` pad) around the sound,
`float32` writes IEEE float samples with a `fact` chunk. `chunk_ids` lists a file's chunks in order."""
from __future__ import annotations

import struct

SECRET = b"a prompt that must not stay"


def _chunk(kind: bytes, data: bytes) -> bytes:
    return kind + struct.pack("<I", len(data)) + data + (b"\x00" if len(data) & 1 else b"")


def _riff(*chunks: bytes) -> bytes:
    body = b"WAVE" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _fmt(tag: int, channels: int, rate: int, bits: int) -> bytes:
    align = channels * bits // 8
    return _chunk(b"fmt ", struct.pack("<HHIIHH", tag, channels, rate, rate * align, align, bits))


def tiny_wav(seconds: float = 1.0, rate: int = 32_000, channels: int = 2, tagged: bool = False) -> bytes:
    data = _chunk(b"data", b"\x00\x00" * channels * int(rate * seconds))
    tags = (_chunk(b"LIST", b"INFO" + _chunk(b"ICMT", SECRET + b"\x00")), _chunk(b"JUNK", b"\x00" * 6))
    extra = tags if tagged else ()
    return _riff(_fmt(1, channels, rate, 16), *extra, data)


def float32(seconds: float = 1.0, rate: int = 32_000) -> bytes:
    frames = int(rate * seconds)
    return _riff(_fmt(3, 1, rate, 32), _chunk(b"fact", struct.pack("<I", frames)),
                 _chunk(b"LIST", b"INFO" + _chunk(b"ISFT", b"x\x00")), _chunk(b"data", b"\x00" * 4 * frames))


def chunk_ids(raw: bytes) -> list[bytes]:
    out, at = [], 12
    while at + 8 <= len(raw):
        size = struct.unpack("<I", raw[at + 4:at + 8])[0]
        out.append(raw[at:at + 4])
        at += 8 + size + (size & 1)
    return out
