"""A sound the Hub keeps: a WAV, its sound and nothing else. Stdlib only.

The engine writes its own settings (the prompt among them) into a WAV it makes (upstream `save_audio_metadata`,
shared/utils/media_recording.py:44-45). `strip` writes the file again with only the chunks that are the sound:
`fmt `, `fact` (when there) and `data`, in that order; any other chunk (`LIST`/`INFO`, `id3 `, a `JUNK` pad) goes.
A file that is not RIFF/WAVE, or whose format is neither PCM nor IEEE float (plain or as WAVE_FORMAT_EXTENSIBLE),
raises ValueError and is left as it was. `facts` reads its length from `fmt ` and the size of `data`; nothing is
decoded. `pad` writes a copy whose sound runs on in silence to a length (a clip that must hold the whole
sound). `speech_span` is how long the sound is heard, first sound to last.
"""
from __future__ import annotations

import math
import os
import struct
from pathlib import Path

KEEP = (b"fmt ", b"fact", b"data")
PCM, FLOAT, EXTENSIBLE = 1, 3, 0xFFFE


def chunks(raw: bytes) -> dict[bytes, bytes]:
    """{chunk id: its bytes} of a RIFF/WAVE file, the first of each id; ValueError when it is not one."""
    if len(raw) < 12 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    found: dict[bytes, bytes] = {}
    at = 12
    while at + 8 <= len(raw):
        kind, size = raw[at:at + 4], struct.unpack("<I", raw[at + 4:at + 8])[0]
        body = raw[at + 8:at + 8 + size]
        if len(body) < size and kind != b"data":
            raise ValueError("a WAV chunk is cut short")
        found.setdefault(kind, body)
        at += 8 + size + (size & 1)
    fmt = found.get(b"fmt ")
    if fmt is None or len(fmt) < 16 or b"data" not in found:
        raise ValueError("a WAV file without its format or its sound")
    tag = struct.unpack("<H", fmt[:2])[0]
    if tag == EXTENSIBLE and len(fmt) >= 26:
        tag = struct.unpack("<H", fmt[24:26])[0]       # the sub-format GUID's first two bytes
    if tag not in (PCM, FLOAT):
        raise ValueError("a WAV format the hub does not read")
    return found


def strip(path: Path) -> None:
    """Write `path` again holding `fmt `, `fact` and `data` only (atomically: a temp file beside it, replaced)."""
    found = chunks(path.read_bytes())
    body = b"WAVE"
    for kind in KEEP:
        if kind in found:
            data = found[kind]
            body += kind + struct.pack("<I", len(data)) + data + (b"\x00" if len(data) & 1 else b"")
    tmp = path.with_name(f".{path.name}.hub-strip")
    try:
        tmp.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def facts(path: Path) -> dict[str, float]:
    """{seconds}: the sound's length, from its format's byte rate and the size of its sound."""
    found = chunks(path.read_bytes())
    rate = struct.unpack("<I", found[b"fmt "][8:12])[0]
    if rate <= 0:
        raise ValueError("a WAV file with no byte rate")
    return {"seconds": round(len(found[b"data"]) / rate, 2)}


def exact(path: Path) -> float:
    """The sound's length in seconds, unrounded (`facts` rounds to the hundredth)."""
    found = chunks(path.read_bytes())
    rate = struct.unpack("<I", found[b"fmt "][8:12])[0]
    if rate <= 0:
        raise ValueError("a WAV file with no byte rate")
    return len(found[b"data"]) / rate


def pad(src: Path, dest: Path, seconds: float) -> bool:
    """Write `dest`: `src`'s sound, then silence up to `seconds` (whole sample frames, rounded up), with `fmt ` and
    `data` only (a `fact` would state the old length), atomically. False, and nothing written, when `src` already
    lasts that long."""
    found = chunks(src.read_bytes())
    fmt, data = found[b"fmt "], found[b"data"]
    rate, align, bits = (struct.unpack("<I", fmt[4:8])[0], struct.unpack("<H", fmt[12:14])[0],
                         struct.unpack("<H", fmt[14:16])[0])
    if rate <= 0 or align <= 0:
        raise ValueError("a WAV file with no sample rate")
    data = data[:len(data) // align * align]
    want = math.ceil(seconds * rate - 1e-9) * align
    if len(data) >= want:
        return False
    silence = (b"\x80" if bits == 8 else b"\x00") * (want - len(data))     # 8-bit PCM is unsigned
    body = b"WAVE"
    for kind, part in ((b"fmt ", fmt), (b"data", data + silence)):
        body += kind + struct.pack("<I", len(part)) + part + (b"\x00" if len(part) & 1 else b"")
    tmp = dest.with_name(f".{dest.name}.hub-pad")
    try:
        tmp.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return True


QUIET = 0.012                                  # the engine's own quiet line, RMS on ±1 (upstream dialogue.py:25)


def _samples(found: dict[bytes, bytes]) -> tuple[list[float], int, int]:
    """(every sample as a float on ±1, the sample rate, the channels) of PCM 8/16/24/32-bit or float WAV data."""
    fmt, data = found[b"fmt "], found[b"data"]
    tag, channels, rate, _, align, bits = struct.unpack("<HHIIHH", fmt[:16])
    if tag == EXTENSIBLE and len(fmt) >= 26:
        tag = struct.unpack("<H", fmt[24:26])[0]
    if rate <= 0 or channels <= 0:
        raise ValueError("a WAV file with no sample rate")
    width = bits // 8
    n = len(data) // max(1, width)
    data = data[:n * width]
    if tag == FLOAT and bits == 32:
        flat = list(struct.unpack(f"<{n}f", data))
    elif tag == PCM and bits == 16:
        flat = [v / 32768.0 for v in struct.unpack(f"<{n}h", data)]
    elif tag == PCM and bits == 32:
        flat = [v / 2147483648.0 for v in struct.unpack(f"<{n}i", data)]
    elif tag == PCM and bits == 24:
        flat = [int.from_bytes(data[i:i + 3], "little", signed=True) / 8388608.0 for i in range(0, n * 3, 3)]
    elif tag == PCM and bits == 8:
        flat = [(b - 128) / 128.0 for b in data]
    else:
        raise ValueError("a WAV format the hub does not read")
    return flat, rate, channels


def speech_span(path: Path, quiet: float = QUIET) -> float | None:
    """Seconds from the first 10 ms window above `quiet` (RMS over all channels) to the end of the last; None when
    none is above it. The engine trims a turn by the same line (upstream dialogue.py:288-298)."""
    flat, rate, channels = _samples(chunks(path.read_bytes()))
    hop = max(1, round(rate * 0.01)) * channels
    loud = [i for i in range(0, len(flat), hop)
            if (w := flat[i:i + hop]) and math.sqrt(sum(v * v for v in w) / len(w)) >= quiet]
    if not loud:
        return None
    return (min(len(flat), loud[-1] + hop) - loud[0]) / channels / rate
