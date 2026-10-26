"""R54 prototype: synthetic takes made by ffmpeg's lavfi, measured as the Hub measures a take (
takemeasure.py: silencedetect -45 dB / 0.15 s regions, ebur128 at -v info read after `Summary:`), and the probes the
tests read a mix with (ebur128, silencedetect onsets, RMS of a window). Stdlib + ffmpeg only."""
from __future__ import annotations

import re
import subprocess
import wave
from array import array
from math import log10, sqrt

import graph

LEVELS = {"line": -23.0, "effect": -27.0, "reaction": -27.0, "music": -33.0, "room": -45.0}   # LUFS per kind
_START = re.compile(r"silence_start:\s*(-?[0-9.]+)")
_END = re.compile(r"silence_end:\s*(-?[0-9.]+)")


def ff(*args: str) -> str:
    done = subprocess.run([graph.FFMPEG, "-hide_banner", "-nostdin", "-v", "info", "-y", *args],
                          capture_output=True, timeout=120, check=False)
    text = done.stderr.decode("utf-8", "replace")
    if done.returncode:
        raise RuntimeError(text.strip().splitlines()[-1])
    return text


def voice(path: str, freq: float, lead_ms: int, speech_ms: int, tail_ms: int, amp: float) -> str:
    """A 'voice': a tone with 3.7 Hz syllable modulation, silent lead and tail; mono 24 kHz like a TTS take."""
    a, b, total = lead_ms / 1000, (lead_ms + speech_ms) / 1000, (lead_ms + speech_ms + tail_ms) / 1000
    expr = f"if(between(t\\,{a}\\,{b})\\,{amp}*sin(2*PI*{freq}*t)*(0.55+0.45*sin(2*PI*3.7*(t-{a})))\\,0)"
    ff("-f", "lavfi", "-i", f"aevalsrc=exprs={expr}:s=24000:d={total}", "-c:a", "pcm_s16le", path)
    return path


def noise(path: str, color: str, ms: int, amp: float, lead_ms: int = 0, decay_ms: int = 0, tail_ms: int = 0) -> str:
    """Noise (an audience, a room): `decay_ms` of fade at its end (0 = cut dead), stereo 48 kHz."""
    d = ms / 1000
    af = [f"afade=t=out:st={(ms - decay_ms) / 1000}:d={decay_ms / 1000}"] if decay_ms else []
    af += [f"adelay=delays={lead_ms}:all=1"] if lead_ms else []
    af += [f"apad=pad_dur={tail_ms / 1000}"] if tail_ms else []
    ff("-f", "lavfi", "-i", f"anoisesrc=color={color}:amplitude={amp}:d={d}:sample_rate=48000:seed=7",
       *(["-af", ",".join(af)] if af else []), "-ac", "2", "-c:a", "pcm_s16le", path)
    return path


def music(path: str, ms: int, amp: float = 0.2) -> str:
    """A steady chord (330, 415, 494 Hz), stereo 48 kHz."""
    expr = f"{amp}*(sin(2*PI*330*t)+sin(2*PI*415*t)+sin(2*PI*494*t))/3"
    ff("-f", "lavfi", "-i", f"aevalsrc=exprs={expr}|{expr}:s=48000:d={ms / 1000}", "-c:a", "pcm_s16le", path)
    return path


def clicks(path: str, ms: int, every: int = 4800, amp: float = 0.99) -> str:
    """Two-sample clicks every `every` samples: ~30 dB peak-to-loudness, so a levelled clip peaks over -1 dBTP."""
    expr = f"if(lt(mod(n\\,{every})\\,2)\\,{amp}\\,0)"
    ff("-f", "lavfi", "-i", f"aevalsrc=exprs={expr}:s=48000:d={ms / 1000}", "-ac", "2", "-c:a", "pcm_s16le", path)
    return path


def ebur(path: str, trim: tuple[float, float] | None = None) -> tuple[float | None, float | None]:
    af = (f"atrim=start={trim[0]:.3f}:end={trim[1]:.3f}," if trim else "") + "ebur128=peak=true"
    return graph.summary(ff("-i", path, "-af", af, "-f", "null", "-"))


def silences(path: str, noise_db: str = "-45dB", d: float = 0.15) -> list[tuple[float, float | None]]:
    text = ff("-i", path, "-af", f"silencedetect=noise={noise_db}:d={d}", "-f", "null", "-")
    out, start = [], None
    for line in text.splitlines():
        for m in _START.finditer(line):
            start = float(m.group(1))
        for m in _END.finditer(line):
            out.append((start if start is not None else 0.0, float(m.group(1))))
            start = None
    if start is not None:
        out.append((start, None))
    return out


def seconds(path: str) -> float:
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def measure(path: str, kind: str, decay_ms: int | None = None) -> dict:
    """The take's record as the Hub's take measure writes it: sound start/end (first region's start, last region's
    end), loudness of that slice, the gain to its kind's anchor."""
    length = seconds(path)
    quiet = [(a, length if b is None else b) for a, b in silences(path)]
    at, spans = 0.0, []
    for a, b in sorted(quiet):
        if a > at:
            spans.append((at, a))
        at = max(at, b)
    if at < length:
        spans.append((at, length))
    start, end = spans[0][0], spans[-1][1]
    lufs, tp = ebur(path, (start, end))
    m = {"speech_start_ms": round(start * 1000), "speech_end_ms": round(end * 1000), "lufs": lufs,
         "true_peak_dbtp": tp, "gain_db": round(LEVELS[kind] - lufs, 1)}
    if decay_ms is not None:
        m["decay_ms"] = decay_ms
    return m


def take(path: str, kind: str, decay_ms: int | None = None) -> dict:
    return {"file": path, "measured": measure(path, kind, decay_ms)}


def onsets(path: str, noise_db: str = "-50dB", d: float = 0.05) -> list[float]:
    """Where sound begins after each silence (ms), the file's own start included when it starts sounding."""
    quiet = silences(path, noise_db, d)
    out = [round(b * 1000) for a, b in quiet if b is not None]
    if not quiet or quiet[0][0] > 0.001:
        out.insert(0, 0)
    return out


def rms_db(path: str, a_ms: int, b_ms: int) -> float:
    """RMS level (dBFS) of a 16-bit WAV between two times, both channels."""
    with wave.open(path) as w:
        rate, ch = w.getframerate(), w.getnchannels()
        w.setpos(round(a_ms * rate / 1000))
        data = array("h", w.readframes(round((b_ms - a_ms) * rate / 1000)))
    if not data:
        return -200.0
    mean = sum(x * x for x in data) / len(data)
    return 10 * log10(mean / 32768 ** 2) if mean > 0 else -200.0
