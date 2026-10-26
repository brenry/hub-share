"""The mix's ffmpeg runs (blueprint §12.5; R54's `graph.py`): a `JoinRequest` with `lanes`, in the
join's runner (`join.py`: ffmpeg found, cancel, death signal, progress, the length check, one output). Stdlib only.

Per clip (one `-i` each): `atrim` to its kept span, 48 kHz stereo float, its gain and its lane's in dB, its fades; a
`loop` clip (the room) looped to the mix's length. The clips are grouped (`dialogue`; `beds`: the ducked reaction,
effect and music lanes when a dialogue lane exists; `plain`: the room and every other lane) and in each group laid on
as few tracks as never overlap: on a track the first clip is delayed to its place (`adelay`, then `asetpts=N/SR/TB`:
in ffmpeg 6.1 `adelay`'s lead-in frames carry no pts) and every clip padded in samples to the next one's place, joined
by `concat`; a group's tracks summed (`amix normalize=0`, or `volume=<k>` after it), padded and cut to the length.
`beds` is pressed under the speech by one volume envelope from the placed dialogue clips (`DUCK`: 10 dB, down over
the 200 ms before each span, back over the 600 ms after it, spans under 800 ms apart merged), written as a binary tree
of `if`s. The groups summed -> `[pre]`. The room is never ducked.

The master, two runs of one task: run 1 writes `[pre]` as float to `<state>/mix-<job>-pre.wav` at `-v info` with
`ebur128`; its `then` reads `I:` after the last `Summary:` from run 1's err file and gives run 2: the gain to the
target, a 4x-oversampled `alimiter` `MARGIN_DB` under the target true peak with `latency=1`, back to 48 kHz, cut to the
length, 16-bit PCM in the outbox. Run 2's list file is the pre-master, so the runner removes it whatever the end; a
graph past `ARG_SAFE` characters goes by `-filter_complex_script` from `<state>/mix-<job>.graph` (run 1's list file,
removed the same way). `solo` k: one run, only lane k heard (the envelope still from every dialogue lane), no master.
"""
from __future__ import annotations

import math
import os
import re
from collections.abc import Callable
from typing import Any

try:
    from . import joincmd
except ImportError:  # run as a script by the engine's Python
    import joincmd

RATE = 48_000
FMT = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
DUCK = {"depth_db": 10.0, "attack_ms": 200, "release_ms": 600}   # R42 §2: the engine mixer's depth; R54
MARGIN_DB = 0.5                  # the limiter this far under the target true peak (R54: -1.5 dBTP measured)
ARG_SAFE = 100_000               # characters: Linux refuses one argument over 128 KiB
FRAME = 240                      # samples per frame under the envelope (5 ms steps)
KINDS = ("dialogue", "reaction", "effect", "music", "room")
ENDLESS = math.inf                  # no most milliseconds of the Hub's on a mix
GAIN = {"clip": (-60.0, 40.0), "lane": (-60.0, 24.0), "lufs": (-70.0, 0.0), "true_peak_dbtp": (-20.0, 0.0)}
GATE = -70.0
GONE_TAKE = "A take of the mix is gone from Sounds"
EMPTY = "The mix holds no take"
_I = re.compile(r"^\s*I:\s*(\S+)\s*LUFS", re.MULTILINE)          # takemeasure's, copied: join imports no adapter
WAV16 = ("-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", "-map_metadata", "-1")


class Run:
    """`joincmd.Command`'s fields plus `then`: None, or (run 1) the err file -> the next run. Once `then` has given
    the next run, `out` is the chain's last file (the one the runner sends)."""

    def __init__(self, argv: list[str], listing: str | None, list_file: str, out: str, length_ms: int,
                 then: Callable[[str], Run] | None = None) -> None:
        self.path, self.argv, self.listing, self.list_file, self.kind, self.n = "encode", argv, listing, list_file, \
            "wav", 1
        self.expect, self.fps, self.seconds = length_ms // 10, 100.0, length_ms / 1000
        self._out, self._then, self.next = out, then, None
        self.then = None if then is None else self._chain

    def _chain(self, err_file: str) -> Run:
        assert self._then is not None
        self.next = self._then(err_file)
        return self.next

    @property
    def out(self) -> str:
        return self.next.out if self.next is not None else self._out


def s(ms: float) -> str:
    return f"{ms / 1000:.3f}"


def _n(ms: int) -> int:
    return ms * RATE // 1000


def _end(c: dict[str, Any], length: int) -> int:
    return length if c["loop"] else c["at_ms"] + c["out_ms"] - c["in_ms"]


def clip_chain(k: int, c: dict[str, Any], length: int, until: int, first: bool) -> str:
    """Input k as clip `c` of its track, padded in samples to `until` (the next clip's place on the track, or the
    length); the track's first clip delayed to its place."""
    kept = c["out_ms"] - c["in_ms"]
    out = [f"atrim=start={s(c['in_ms'])}:end={s(c['out_ms'])}", "asetpts=PTS-STARTPTS", FMT]
    span = kept
    if c["loop"]:
        span = length - c["at_ms"]
        out += [f"aloop=loop=-1:size={_n(kept)}", f"atrim=end_sample={_n(span)}", "asetpts=N/SR/TB"]
    out.append(f"volume={c['gain_db']:.2f}dB")
    if c["fade_in"]:
        out.append(f"afade=t=in:st=0:d={s(min(c['fade_in'], span))}")
    if c["fade_out"]:
        d = min(c["fade_out"], span)
        out.append(f"afade=t=out:st={s(span - d)}:d={s(d)}")
    start = 0 if first else c["at_ms"]
    if first and c["at_ms"]:
        out += [f"adelay=delays={c['at_ms']}:all=1", "asetpts=N/SR/TB"]
    n = _n(until - start)
    out += [f"apad=whole_len={n}", f"atrim=end_sample={n}", "asetpts=N/SR/TB"]
    return f"[{k}:a]" + ",".join(out) + f"[c{k}]"


def tracks(clips: list[dict[str, Any]], length: int) -> list[list[dict[str, Any]]]:
    """Clips on as few tracks as never overlap, by (place, input order)."""
    out: list[list[dict[str, Any]]] = []
    for c in sorted(clips, key=lambda c: (c["at_ms"], c["order"])):
        free = next((t for t in out if _end(t[-1], length) <= c["at_ms"]), None)
        if free is None:
            out.append([c])
        else:
            free.append(c)
    return out


def speech_spans(lanes: list[dict[str, Any]], gap_ms: int) -> list[tuple[int, int]]:
    """The placed dialogue clips' sound, spans closer than `gap_ms` merged."""
    spans = sorted((c["at_ms"], c["at_ms"] + c["out_ms"] - c["in_ms"]) for lane in lanes
                   if lane["kind"] == "dialogue" for c in lane["clips"])
    out: list[list[int]] = []
    for a, b in spans:
        if out and a - out[-1][1] < gap_ms:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def envelope(spans: list[tuple[int, int]]) -> str:
    """`volume`'s expression: down `depth_db` from `attack_ms` before each span to its end, back over `release_ms`."""
    if not spans:
        return "1"
    att, rel = DUCK["attack_ms"] / 1000, DUCK["release_ms"] / 1000

    def tree(part: list[tuple[int, int]]) -> str:
        if len(part) == 1:
            a, b = part[0][0] / 1000 - att, part[0][1] / 1000 + rel
            return f"clip((t-{a:.3f})/{att:.3f},0,1)*clip(({b:.3f}-t)/{rel:.3f},0,1)"
        m = len(part) // 2
        cut = (part[m - 1][1] / 1000 + rel + part[m][0] / 1000 - att) / 2
        return f"if(lt(t,{cut:.3f}),{tree(part[:m])},{tree(part[m:])})"
    return f"pow(10,-{DUCK['depth_db'] / 20:.4f}*{tree(spans)})"


def groups(request: dict[str, Any]) -> dict[str, list[list[dict[str, Any]]]]:
    """{group: its tracks} of the lanes heard (all, or lane `solo`), each clip carrying its lane's gain."""
    lanes, length, solo = request["lanes"], int(request["length_ms"]), request.get("solo")
    dialogue = any(lane["kind"] == "dialogue" for lane in lanes)
    out: dict[str, list[dict[str, Any]]] = {"dialogue": [], "beds": [], "plain": []}
    order = 0
    for k, lane in enumerate(lanes):
        if solo is not None and k != solo:
            continue
        name = "dialogue" if lane["kind"] == "dialogue" else "beds" if lane["duck"] and dialogue else "plain"
        for c in lane["clips"]:
            out[name].append({**c, "gain_db": float(c["gain_db"]) + float(lane["gain_db"]), "order": order})
            order += 1
    return {g: tracks(clips, length) for g, clips in out.items() if clips}


def uses_amix(request: dict[str, Any]) -> bool:
    found = groups(request)
    return len(found) > 1 or any(len(t) > 1 for t in found.values())


def _sum(labels: list[str], normalize: bool) -> str:
    if len(labels) == 1:
        return labels[0]
    k = len(labels)
    return "".join(labels) + (f"amix=inputs={k}:duration=longest:dropout_transition=0:normalize=0," if normalize
                              else f"amix=inputs={k}:duration=longest:dropout_transition=0,volume={k},")


def premaster(request: dict[str, Any], normalize: bool) -> tuple[list[str], str]:
    """(input files, the graph ending in `[pre]`)."""
    length = int(request["length_ms"])
    inputs: list[str] = []
    chains: list[str] = []
    outs: list[str] = []
    for name, laid in groups(request).items():
        labels = []
        for t, track in enumerate(laid):
            parts = []
            for j, c in enumerate(track):
                until = track[j + 1]["at_ms"] if j + 1 < len(track) else length
                chains.append(clip_chain(len(inputs), c, length, until, j == 0))
                parts.append(f"[c{len(inputs)}]")
                inputs.append(str(c["path"]))
            if len(parts) > 1:
                chains.append("".join(parts) + f"concat=n={len(parts)}:v=0:a=1[{name}{t}]")
                parts = [f"[{name}{t}]"]
            labels += parts
        chains.append(_sum(labels, normalize) + f"apad=whole_len={_n(length)},atrim=end_sample={_n(length)}[{name}]")
        if name == "beds":
            expr = envelope(speech_spans(request["lanes"], DUCK["attack_ms"] + DUCK["release_ms"]))
            chains.append(f"[beds]asetnsamples=n={FRAME}:p=0,volume=volume='{expr}':eval=frame[ducked]")
            name = "ducked"
        outs.append(f"[{name}]")
    chains.append(_sum(outs, normalize) + "anull[pre]")
    return inputs, ";".join(chains)


def gain_of(text: str, lufs: float) -> float:
    """The gain to `lufs` from ebur128's `I:` after the last `Summary:`; 0.0 when there is none, it is not finite, or
    it is at or below the gate."""
    tail = text[text.rfind("Summary:"):] if "Summary:" in text else ""
    found = _I.search(tail)
    try:
        got = float(found.group(1)) if found else None
    except ValueError:
        got = None
    return 0.0 if got is None or not math.isfinite(got) or got <= GATE else lufs - got


def limit(true_peak_dbtp: float) -> float:
    return 10 ** ((true_peak_dbtp - MARGIN_DB) / 20)


def build(request: dict[str, Any], ffmpeg: str, state: str, job: str, normalize: bool) -> Run:
    """The mix's first (or only) run; pure."""
    length = int(request["length_ms"])
    inputs, graph = premaster(request, normalize)
    graph_file = os.path.join(state, f"mix-{job}.graph")
    pre = os.path.join(state, f"mix-{job}-pre.wav")
    out = os.path.join(state, "outbox", f"join-{job}.wav")
    ins = [a for path in inputs for a in ("-i", path)]

    def fc(text: str) -> tuple[list[str], str | None]:
        if len(text) <= ARG_SAFE:
            return ["-filter_complex", text], None
        return ["-filter_complex_script", graph_file], text
    if request.get("solo") is not None:
        args, listing = fc(graph)
        return Run([ffmpeg, *joincmd.HEAD, *ins, *args, "-map", "[pre]", *WAV16, out], listing, graph_file, out,
                   length)
    target = request["target"]
    args, listing = fc(graph + ";[pre]ebur128[m]")
    argv = [ffmpeg, "-hide_banner", "-nostdin", "-v", "info", "-y", "-progress", "pipe:1", *ins, *args, "-map", "[m]",
            "-c:a", "pcm_f32le", "-ar", "48000", "-ac", "2", "-map_metadata", "-1", pre]

    def master(err_file: str) -> Run:
        try:
            with open(err_file, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            text = ""
        gain = gain_of(text, float(target["lufs"]))
        af = (f"volume={gain:.2f}dB,aresample=192000,alimiter=limit={limit(float(target['true_peak_dbtp'])):.4f}:"
              f"attack=5:release=50:level=0:latency=1,aresample=48000,atrim=end={s(length)}")
        return Run([ffmpeg, *joincmd.HEAD, "-i", pre, "-af", af, *WAV16, out], None, pre, out, length)
    return Run(argv, listing, graph_file, pre, length, master)


def _number(x: Any, lo: float, hi: float, whole: bool) -> bool:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return False
    return lo <= x <= hi and (not whole or x == int(x))


def problem(request: dict[str, Any]) -> str | None:
    """The one line a mix request is refused with, or None."""
    lanes, length = request.get("lanes") or [], request.get("length_ms")
    if not lanes or any(not lane.get("clips") for lane in lanes) or not _number(length, 1, ENDLESS, True):
        return EMPTY
    for lane in lanes:
        if lane["kind"] not in KINDS:
            return f"The lane {lane['name']} is of no kind a mix knows"
        if lane["duck"] and lane["kind"] in ("room", "dialogue"):
            return f"The {lane['kind']} lane is never ducked"
        if not _number(lane["gain_db"], *GAIN["lane"], False):
            return f"The lane {lane['name']}'s gain is not a number of {GAIN['lane'][0]:g} to {GAIN['lane'][1]:g} dB"
        for c in lane["clips"]:
            if not all(_number(c[k], 0, ENDLESS, True) for k in ("at_ms", "in_ms", "out_ms", "fade_in", "fade_out")) \
                    or c["out_ms"] <= c["in_ms"] or c["at_ms"] >= length:
                return f"A clip of the lane {lane['name']} is not placed inside the mix"
            if not _number(c["gain_db"], *GAIN["clip"], False):
                return f"A clip of the lane {lane['name']} has a gain that is not a number of -60 to 40 dB"
    solo = request.get("solo")
    if solo is not None and not 0 <= solo < len(lanes):
        return "The stem names no lane of the mix"
    target = request.get("target")
    if solo is None and (not isinstance(target, dict) or not all(_number(target.get(k), *GAIN[k], False)
                                                                 for k in ("lufs", "true_peak_dbtp"))):
        return "The mix's loudness target is not a number in range"
    return None


def prepare(job: str, request: dict[str, Any], state: str, ffmpeg: str, normalize: Callable[[str], bool]) -> Run:
    """The checks, then the mix's run; a refusal is a `ValueError` with its one line."""
    if any(not os.path.isfile(str(c.get("path"))) for lane in request.get("lanes") or [] for c in lane["clips"]):
        raise ValueError(GONE_TAKE)
    found = problem(request)
    if found is not None:
        raise ValueError(found)
    return build(request, ffmpeg, state, job, normalize(ffmpeg) if uses_amix(request) else True)
