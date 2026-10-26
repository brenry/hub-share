"""The ffmpeg command line of a join (the Edit Video tab's Save), pure: the request and each input's probe facts in,
the argv out (no file is read or written here). Stdlib only, as the rest of the worker.

The request (a `JoinRequest` on the wire, the sequence module's one task):

    {"items": [{"path", "in", "out", "fps", "w", "h", "frames", "audio", "sound"}], "canvas": {"w", "h", "fps"},
     "audio": [{"path", "at_ms", "in", "out", "fps"}], "crf": int, "preset": str, "out_kind": "mp4" | "wav"}

`in`/`out` are frames of the item (`out` exclusive; a sound counts milliseconds, `fps` 1000); the canvas is the first
clip's. An MP4, every item whole and every input with the same video stream (codec, profile, size, pixel format,
rate, `extradata_hash`) and the same sound (codec, rate, channels) or no sound anywhere, and nothing on track 2
(`audio`): the copy path (concat demuxer, `-c copy`). Otherwise the encode path: each input trimmed by frame, fitted
inside the canvas (letterboxed), set to its rate and joined by `concat`, sound trimmed by time; an input without
sound gets silence when another has sound. A WAV (`out_kind` "wav"): track 1's sounds trimmed and joined, or silence
as long as track 2 when track 1 is empty; 16-bit PCM, 48 kHz, stereo.

Track 2: each item one more input, trimmed, set to 48 kHz stereo, delayed to its `at_ms` (`adelay`
per channel) and mixed under track 1's sound by `amix` (`duration=first`, so the file keeps track 1's length) at
equal levels: `normalize=0` where the installed ffmpeg's `amix` has it, else `volume=<inputs>` after the mix.

A track-2 item may carry `level` (a factor), `fade_in` / `fade_out` (milliseconds) and `duck`; they
become `volume`, `afade` at its two ends (before the delay) and, ducked, `sidechaincompress` keyed by track 1's
sound (`asplit` from `[base]`), the item first padded and cut to the file's length so both inputs run together; the
request's `duck` holds the compressor's threshold, ratio, attack and release. Without any of them the command is
exactly the one above.
"""
from __future__ import annotations

import os
from typing import Any, NamedTuple

HEAD = ("-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-progress", "pipe:1")
TAIL = ("-map_metadata", "-1", "-movflags", "+faststart")
VIDEO_KEYS = (("codec", "codec_name"), ("profile", "profile"), ("w", "width"), ("h", "height"),
              ("pix_fmt", "pix_fmt"), ("fps", "r_frame_rate"), ("extradata_hash", "extradata_hash"))
AUDIO_KEYS = (("codec", "codec_name"), ("rate", "sample_rate"), ("channels", "channels"))
SOUND_FORMAT = "aresample=48000,aformat=channel_layouts=stereo"


class Command(NamedTuple):
    path: str                 # "copy" or "encode"
    argv: list[str]
    listing: str | None       # the concat list file's text (copy path), else None
    list_file: str            # <state>/join-<job>.txt
    out: str                  # <state>/outbox/join-<job>.mp4
    expect: int               # the frames the joined clip should have
    fps: float                # the canvas rate (progress counts its frames)
    n: int                    # the items joined
    kind: str = "mp4"         # "mp4" or "wav"
    seconds: float = 0.0      # a WAV's expected length (its check); progress then counts hundredths of a second


def probe_argv(ffprobe: str, path: str) -> list[str]:
    """The one probe of an input."""
    return [ffprobe, "-v", "error", "-show_streams", "-show_data_hash", "CRC32", "-of", "json", path]


def facts(probed: dict[str, Any] | None) -> dict[str, Any]:
    """ffprobe's JSON -> {"v": {codec, profile, w, h, pix_fmt, fps, extradata_hash} | None, "a": {codec, rate,
    channels} | None}, from the first video and the first audio stream."""
    streams = list((probed or {}).get("streams") or [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    return {"v": None if video is None else {k: video.get(src) for k, src in VIDEO_KEYS},
            "a": None if audio is None else {k: audio.get(src) for k, src in AUDIO_KEYS}}


def whole(item: dict[str, Any]) -> bool:
    return int(item["in"]) == 0 and int(item["out"]) == int(item["frames"])


def copyable(items: list[dict[str, Any]], probed: list[dict[str, Any]]) -> bool:
    """The copy path's condition: every item whole, one video stream (with its `extradata_hash`) and one sound."""
    if not items or len(probed) != len(items) or not all(whole(i) for i in items):
        return False
    videos, sounds = [p.get("v") for p in probed], [p.get("a") for p in probed]
    if videos[0] is None or videos[0].get("extradata_hash") is None or any(v != videos[0] for v in videos):
        return False
    return all(a is None for a in sounds) or all(a is not None and a == sounds[0] for a in sounds)


def quote(path: str) -> str:
    """A concat list line's path: single-quoted, a `'` inside written `'\\''`."""
    return "'" + path.replace("'", "'\\''") + "'"


def listing(items: list[dict[str, Any]]) -> str:
    return "".join(f"file {quote(str(i['path']))}\n" for i in items)


def num(x: float) -> str:
    """A number for an ffmpeg option: a decimal, never an expression."""
    return f"{x:.6f}"


def _sound(k: int, item: dict[str, Any], label: str, delay: str = "") -> str:
    """Input k's sound, frames `in` to `out` of the item kept (by time), at 48 kHz stereo."""
    lo, hi, fps = int(item["in"]), int(item["out"]), float(item["fps"])
    return f"[{k}:a]atrim=start={num(lo / fps)}:end={num(hi / fps)},asetpts=PTS-STARTPTS,{SOUND_FORMAT}{delay}[{label}]"


def graph(items: list[dict[str, Any]], canvas: dict[str, Any], force_sound: bool = False,
          label: str = "a") -> tuple[str, bool]:
    """The encode path's filter graph and whether it has sound (`force_sound`: silence for every item without);
    the joined sound is `[<label>]`."""
    w, h, rate = int(canvas["w"]), int(canvas["h"]), num(float(canvas["fps"]))
    sound = force_sound or any(bool(i.get("audio")) for i in items)
    chains, pads = [], []
    for k, item in enumerate(items):
        lo, hi, fps = int(item["in"]), int(item["out"]), float(item["fps"])
        chains.append(f"[{k}:v]trim=start_frame={lo}:end_frame={hi},setpts=PTS-STARTPTS,"
                      f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
                      f"setsar=1,fps={rate},format=yuv420p[v{k}]")
        pads.append(f"[v{k}]")
        if not sound:
            continue
        if item.get("audio"):
            chains.append(_sound(k, item, f"a{k}"))
        else:
            chains.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={num(hi / fps - lo / fps)}[a{k}]")
        pads.append(f"[a{k}]")
    tail = f"concat=n={len(items)}:v=1:a=1[v][{label}]" if sound else f"concat=n={len(items)}:v=1:a=0[v]"
    chains.append("".join(pads) + tail)
    return ";".join(chains), sound


def sound_end(placed: list[dict[str, Any]]) -> float:
    """Where track 2's last item ends, in seconds."""
    return max((int(p["at_ms"]) / 1000 + (int(p["out"]) - int(p["in"])) / float(p["fps"]) for p in placed),
               default=0.0)


def sound_graph(items: list[dict[str, Any]], placed: list[dict[str, Any]], label: str) -> tuple[str, float]:
    """A WAV's track 1: its sounds trimmed and joined as `[<label>]`, or silence as long as track 2; and its
    seconds."""
    if not items:
        seconds = sound_end(placed)
        return f"anullsrc=r=48000:cl=stereo,atrim=duration={num(seconds)}[{label}]", seconds
    chains = [_sound(k, item, f"a{k}") for k, item in enumerate(items)]
    chains.append("".join(f"[a{k}]" for k in range(len(items))) + f"concat=n={len(items)}:v=0:a=1[{label}]")
    seconds = sum((int(i["out"]) - int(i["in"])) / float(i["fps"]) for i in items)
    return ";".join(chains), seconds


def shape(item: dict[str, Any]) -> str:
    """A track-2 item's level and fades as filters after its format; "" when it has none."""
    kept = (int(item["out"]) - int(item["in"])) / float(item["fps"])
    level = float(item.get("level", 1))
    fade_in, fade_out = int(item.get("fade_in") or 0), int(item.get("fade_out") or 0)
    out = [f"volume={num(level)}"] if level != 1 else []
    if fade_in:
        out.append(f"afade=t=in:st=0:d={num(min(fade_in / 1000, kept))}")
    if fade_out:
        d = min(fade_out / 1000, kept)
        out.append(f"afade=t=out:st={num(kept - d)}:d={num(d)}")
    return "".join(f",{f}" for f in out)


DUCK = {"threshold": 0.05, "ratio": 6.0, "attack": 50.0, "release": 400.0}   # the request's `duck`, else these


def ducker(duck: dict[str, Any] | None) -> str:
    """The compressor keyed by track 1, with the request's numbers."""
    d = {**DUCK, **(duck or {})}
    return "sidechaincompress=" + ":".join(f"{k}={num(float(d[k]))}" for k in DUCK)


def mix(first: int, placed: list[dict[str, Any]], normalize: bool, end: float | None = None,
        duck: dict[str, Any] | None = None) -> str:
    """Track 2's inputs (numbered from `first`) delayed to their places and mixed under `[base]` as `[a]`; a ducked
    one pressed by `[base]` first, `end` being the file's seconds."""
    ducked = [m for m, p in enumerate(placed) if p.get("duck")] if end else []
    chains, pads = [], ["[base0]" if ducked else "[base]"]
    if ducked:
        chains.append(f"[base]asplit={len(ducked) + 1}[base0]" + "".join(f"[sc{m}]" for m in ducked))
    for m, p in enumerate(placed):
        delay = int(p["at_ms"])
        tail = f"{shape(p)},adelay={delay}|{delay}"
        if m in ducked:
            tail += f",apad=whole_dur={num(float(end or 0))},atrim=end={num(float(end or 0))}"
        chains.append(_sound(first + m, p, f"s{m}", tail))
        if m in ducked:
            chains.append(f"[s{m}][sc{m}]{ducker(duck)}[d{m}]")
        pads.append(f"[d{m}]" if m in ducked else f"[s{m}]")
    n = len(placed) + 1
    tail = (f"amix=inputs={n}:duration=first:dropout_transition=0:normalize=0[a]" if normalize
            else f"amix=inputs={n}:duration=first:dropout_transition=0,volume={n}[a]")
    return ";".join([*chains, "".join(pads) + tail])


def expected(items: list[dict[str, Any]], canvas: dict[str, Any], copy: bool) -> int:
    """The copy path keeps every frame; the encode path makes each kept span at the canvas rate."""
    if copy:
        return sum(int(i["frames"]) for i in items)
    rate = float(canvas["fps"])
    return sum(round((int(i["out"]) - int(i["in"])) * rate / float(i["fps"])) for i in items)


def _wav(request: dict[str, Any], ffmpeg: str, state: str, job: str, normalize: bool) -> Command:
    items, placed = list(request["items"]), list(request.get("audio") or [])
    list_file = os.path.join(state, f"join-{job}.txt")
    out = os.path.join(state, "outbox", f"join-{job}.wav")
    text, seconds = sound_graph(items, placed, "base" if placed else "a")
    if placed:
        text = f"{text};{mix(len(items), placed, normalize, seconds, request.get('duck'))}"
    inputs = [arg for i in [*items, *placed] for arg in ("-i", str(i["path"]))]
    argv = [ffmpeg, *HEAD, *inputs, "-filter_complex", text, "-map", "[a]", "-c:a", "pcm_s16le", "-ar", "48000",
            "-ac", "2", "-map_metadata", "-1", out]
    return Command("encode", argv, None, list_file, out, round(seconds * 100), 100.0, len(items) + len(placed),
                   "wav", seconds)


def build(request: dict[str, Any], probed: list[dict[str, Any]], ffmpeg: str, state: str, job: str,
          normalize: bool = True) -> Command:
    """The join's command for `request`, given each input's `facts` (in item order). `normalize`: whether the
    installed ffmpeg's `amix` takes `normalize` (read only when track 2 holds something). With nothing on track 2,
    an MP4's argv is the copy or encode path alone."""
    if request.get("out_kind", "mp4") == "wav":
        return _wav(request, ffmpeg, state, job, normalize)
    items, canvas = list(request["items"]), dict(request["canvas"])
    placed = list(request.get("audio") or [])
    list_file = os.path.join(state, f"join-{job}.txt")
    out = os.path.join(state, "outbox", f"join-{job}.mp4")
    if not placed and copyable(items, probed):
        argv = [ffmpeg, *HEAD, "-f", "concat", "-safe", "0", "-i", list_file, "-map", "0", "-c", "copy", *TAIL, out]
        return Command("copy", argv, listing(items), list_file, out, expected(items, canvas, True),
                       float(canvas["fps"]), len(items))
    text, sound = graph(items, canvas, bool(placed), "base" if placed else "a")
    if placed:
        end = sum((int(i["out"]) - int(i["in"])) / float(i["fps"]) for i in items)
        text = f"{text};{mix(len(items), placed, normalize, end, request.get('duck'))}"
    inputs = [arg for i in [*items, *placed] for arg in ("-i", str(i["path"]))]
    argv = [ffmpeg, *HEAD, *inputs, "-filter_complex", text, "-map", "[v]", *(["-map", "[a]"] if sound else []),
            "-c:v", "libx264", "-crf", str(int(request["crf"])), "-preset", str(request["preset"]),
            "-pix_fmt", "yuv420p", *(["-c:a", "aac", "-b:a", "192k", "-ar", "48000"] if sound else []), *TAIL, out]
    return Command("encode", argv, None, list_file, out, expected(items, canvas, False), float(canvas["fps"]),
                   len(items))
