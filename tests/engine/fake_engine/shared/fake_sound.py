"""The fake engine's sound: a short silent WAV at the engine's 32 kHz, with the task's settings in a `LIST`/`INFO`
chunk as the real engine keeps them in the file (upstream `save_audio_metadata`), which the Hub strips."""
from __future__ import annotations

import struct
import wave

RATE = 32_000


def write(path: str, seconds: float, comment: str) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"\x00\x00\x00\x00" * int(RATE * seconds))
    text = comment.encode("utf-8") + b"\x00"
    text += b"\x00" * (len(text) % 2)
    info = b"INFO" + b"ICMT" + struct.pack("<I", len(text)) + text
    with open(path, "r+b") as f:
        data = f.read()
        data += b"LIST" + struct.pack("<I", len(info)) + info
        f.seek(0)
        f.write(data[:4] + struct.pack("<I", len(data) - 8) + data[8:])
