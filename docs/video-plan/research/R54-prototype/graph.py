"""R54 prototype: the mix's ffmpeg graph (blueprint §12.5), from `place.place`'s placement.

Per clip (one `-i` each): atrim to its measured in/out, 48 kHz stereo float, its measured gain, its fades (a room clip
looped to the track's length). Each clip carries its lane's gain; clips are laid on the
fewest tracks that never overlap, per group (dialogue, ducked beds, the rest): on a track the first clip is delayed to
its place and every clip padded to the next one's place, joined by `concat` (exact samples); tracks summed (`amix
normalize=0`), padded and cut to the length. The ducked lanes' sum (DUCKED in place.py) pressed under the dialogue by
one volume envelope computed from the placed dialogue clips (`duck="envelope"`, the choice) or by `sidechaincompress` keyed by the
dialogue sum (`duck="sidechain"`, kept for the comparison). All lanes summed -> `[pre]`.

The master (`master=`): "gain" (the choice): run 1 writes `[pre]` as float WAV and reads ebur128's Summary `I:`
(`-v info`, parsed after `Summary:` as takemeasure.py does); run 2 applies `target - I` dB, a 4x-oversampled
`alimiter` at the target true peak less `MARGIN_DB`, back to 48 kHz, 16-bit WAV. "loudnorm" (one pass)
and "loudnorm2" (two-pass, linear) for the comparison. `solo`: a set of lane names, summed after gain and duck, no
master (a stem; also how the tests hear one lane).
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import time

FFMPEG = "/usr/bin/ffmpeg"
RATE = 48_000
FMT = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
DUCK = {"depth_db": 10.0, "attack_ms": 200, "release_ms": 600}   # R42 §2: the engine mixer's depth, attack, release
SIDECHAIN = {"threshold": 0.05, "ratio": 6, "attack": 200, "release": 600}
TARGET = {"lufs": -23.0, "true_peak_dbtp": -1.0}                  # EBU R 128 (takejudge.PARAMS)
MARGIN_DB = 0.5                 # the limiter sits this far under the target true peak (README: why)
ARG_SAFE = 100_000             # chars: a longer graph goes through -filter_complex_script
FRAME = 240                     # samples per frame for the envelope (5 ms steps)
_I = re.compile(r"^\s*I:\s*(\S+)\s*LUFS", re.MULTILINE)
_PEAK = re.compile(r"True peak:\s*\n\s*Peak:\s*(\S+)\s*dBFS")


def s(ms: float) -> str:
    return f"{ms / 1000:.3f}"


def clip_chain(k: int, c: dict, length: int, until: int, first: bool) -> str:
    """One clip, padded with silence to `until` (the next clip's place on its track, or the end), in exact samples;
    the first clip of a track is delayed to its place, the others follow by `concat`, so a lane costs its length,
    not clips x length."""
    kept = c["out_ms"] - c["in_ms"]
    out = [f"atrim=start={s(c['in_ms'])}:end={s(c['out_ms'])}", "asetpts=PTS-STARTPTS", FMT]
    span = kept
    if c.get("loop"):
        span = length - c["at_ms"]
        out += [f"aloop=loop=-1:size={kept * RATE // 1000}", f"atrim=end_sample={span * RATE // 1000}",
                "asetpts=N/SR/TB"]
    out.append(f"volume={c['gain_db']:.2f}dB")
    if c["fade_in_ms"]:
        out.append(f"afade=t=in:st=0:d={s(min(c['fade_in_ms'], span))}")
    if c["fade_out_ms"]:
        d = min(c["fade_out_ms"], span)
        out.append(f"afade=t=out:st={s(span - d)}:d={s(d)}")
    start = 0 if first else c["at_ms"]
    if first and c["at_ms"]:
        out += [f"adelay=delays={c['at_ms']}:all=1", "asetpts=N/SR/TB"]   # 6.1: adelay's lead-in frames have no pts
    n = (until - start) * RATE // 1000
    out += [f"apad=whole_len={n}", f"atrim=end_sample={n}", "asetpts=N/SR/TB"]
    return f"[{k}:a]" + ",".join(out) + f"[c{k}]"


def tracks(clips: list[dict]) -> list[list[dict]]:
    """A lane's clips on as few tracks as never overlap (two reactions may overlap on one lane)."""
    out: list[list[dict]] = []
    for c in sorted(clips, key=lambda c: (c["at_ms"], c["id"])):
        free = next((t for t in out if _end(t[-1]) <= c["at_ms"]), None)
        if free is None:
            out.append([c])
        else:
            free.append(c)
    return out


def _end(c: dict) -> int:
    return c.get("until_ms", c["at_ms"] + c["out_ms"] - c["in_ms"]) if c.get("loop") else \
        c["at_ms"] + c["out_ms"] - c["in_ms"]


def speech_spans(lanes: list[dict], gap_ms: int) -> list[tuple[int, int]]:
    """The placed dialogue sound, merged where two spans are closer than `gap_ms` (the bed stays down across a turn)."""
    spans = sorted((c["at_ms"], c["at_ms"] + c["out_ms"] - c["in_ms"]) for lane in lanes
                   if lane["kind"] == "dialogue" for c in lane["clips"])
    out: list[list[int]] = []
    for a, b in spans:
        if out and a - out[-1][1] < gap_ms:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def envelope(spans: list[tuple[int, int]], duck: dict = DUCK) -> str:
    """volume's expression: down by depth_db from attack_ms before each span to its end, back up over release_ms.
    The spans are merged at attack + release, so the trapezoids never overlap; they sit in a binary tree of `if`s
    (ffmpeg evaluates only the branch taken), so each frame costs log(spans), not spans."""
    if not spans:
        return "1"
    att, rel = duck["attack_ms"] / 1000, duck["release_ms"] / 1000

    def tree(part: list[tuple[int, int]]) -> str:
        if len(part) == 1:
            a, b = part[0][0] / 1000 - att, part[0][1] / 1000 + rel
            return f"clip((t-{a:.3f})/{att:.3f},0,1)*clip(({b:.3f}-t)/{rel:.3f},0,1)"
        m = len(part) // 2
        cut = (part[m - 1][1] / 1000 + rel + part[m][0] / 1000 - att) / 2
        return f"if(lt(t,{cut:.3f}),{tree(part[:m])},{tree(part[m:])})"
    return f"pow(10,-{duck['depth_db'] / 20:.4f}*{tree(spans)})"


def premaster(p: dict, duck: str = "envelope", solo: set | None = None) -> tuple[list[str], str]:
    """(input files, filter_complex ending in [pre]). A lane is the record's grouping, not a stream: each clip carries
    its lane's gain, and the clips are laid on the fewest non-overlapping tracks per group (dialogue, ducked beds,
    the rest), so the graph costs groups x length, not lanes x length."""
    length, lanes = p["length_ms"], p["lanes"]
    heard = [lane for lane in lanes if solo is None or lane["name"] in solo]
    dialogue_heard = any(lane["kind"] == "dialogue" for lane in heard)
    if duck == "sidechain":                          # the key needs all the dialogue, heard or not
        heard += [lane for lane in lanes if lane["kind"] == "dialogue" and lane not in heard]
    has_dialogue = any(lane["kind"] == "dialogue" for lane in lanes)

    def group(lane: dict) -> str:
        if lane["kind"] == "dialogue":
            return "dialogue"
        return "beds" if lane["duck"] and has_dialogue and duck != "none" else "plain"
    inputs, chains, outs = [], [], {}
    for name in ("dialogue", "beds", "plain"):
        clips = [{**c, "gain_db": c["gain_db"] + lane["gain_db"]} for lane in heard if group(lane) == name
                 for c in lane["clips"]]
        labels = []
        for t, track in enumerate(tracks(clips)):
            parts = []
            for j, c in enumerate(track):
                until = track[j + 1]["at_ms"] if j + 1 < len(track) else length
                chains.append(clip_chain(len(inputs), c, length, until, j == 0))
                parts.append(f"[c{len(inputs)}]")
                inputs.append(c["file"])
            if len(parts) > 1:
                chains.append("".join(parts) + f"concat=n={len(parts)}:v=0:a=1[{name}{t}]")
                parts = [f"[{name}{t}]"]
            labels += parts
        if labels:
            chains.append(_sum(labels) + f"apad=whole_len={length * RATE // 1000},"
                          f"atrim=end_sample={length * RATE // 1000}[{name}]")
            outs[name] = f"[{name}]"
    if "beds" in outs and duck == "envelope":        # one envelope on the ducked beds' sum: the expression once
        expr = envelope(speech_spans(lanes, DUCK["attack_ms"] + DUCK["release_ms"]))
        chains.append(f"[beds]asetnsamples=n={FRAME}:p=0,volume=volume='{expr}':eval=frame[ducked]")
        outs["beds"] = "[ducked]"
    elif "beds" in outs and duck == "sidechain":     # the compressor, for the comparison (keyed by the dialogue)
        sc = ":".join(f"{a}={b}" for a, b in SIDECHAIN.items())
        chains.append(f"[dialogue]asplit=2[dkey][dout];[beds][dkey]sidechaincompress={sc}[ducked]")
        outs.update(beds="[ducked]", dialogue="[dout]" if dialogue_heard else None)
        if not dialogue_heard:
            chains.append("[dout]anullsink")
    chains.append(_sum([v for v in outs.values() if v]) + "anull[pre]")
    return inputs, ";".join(chains)


def _sum(labels: list[str]) -> str:
    """Labels summed at equal level (`normalize=0`), ready for one more filter."""
    if len(labels) == 1:
        return labels[0]
    return "".join(labels) + f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,"


def limiter(length: int, target: dict = TARGET) -> str:
    limit = 10 ** ((target["true_peak_dbtp"] - MARGIN_DB) / 20)
    return (f"aresample=192000,alimiter=limit={limit:.4f}:attack=5:release=50:level=0:latency=1,"
            f"aresample=48000,atrim=end={s(length)}")


def _run(argv: list[str]) -> str:
    done = subprocess.run(argv, capture_output=True, timeout=600, check=False)
    text = done.stderr.decode("utf-8", "replace")
    if done.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {text.strip().splitlines()[-1] if text.strip() else done.returncode}")
    return text


def summary(text: str) -> tuple[float | None, float | None]:
    """ebur128's Summary I (LUFS) and true peak (dBFS), read after `Summary:` only; non-finite -> None."""
    tail = text[text.rfind("Summary:"):] if "Summary:" in text else ""
    i, pk = _I.search(tail), _PEAK.search(tail)
    vals = [float(m.group(1)) if m else None for m in (i, pk)]
    return tuple(v if v is not None and math.isfinite(v) else None for v in vals)   # type: ignore[return-value]


def _head(ffmpeg: str, inputs: list[str]) -> list[str]:
    argv = [ffmpeg, "-hide_banner", "-nostdin", "-v", "info", "-y"]
    for f in inputs:
        argv += ["-i", f]
    return argv


def render(p: dict, out: str, master: str = "gain", duck: str = "envelope", solo: set | None = None,
           ffmpeg: str = FFMPEG, target: dict = TARGET) -> dict:
    """The WAV at `out`; -> {seconds, runs, pre_lufs?, graph_chars}."""
    t0 = time.monotonic()
    inputs, graph = premaster(p, duck, solo)
    head, wav = _head(ffmpeg, inputs), ["-c:a", "pcm_s16le", "-ar", str(RATE), "-ac", "2", out]
    info: dict = {"graph_chars": len(graph), "runs": 1}
    lim = limiter(p["length_ms"], target)
    lufs, tp = target["lufs"], target["true_peak_dbtp"]
    scripts: list[str] = []

    def fc(text: str) -> list[str]:
        """The graph as one argument, or from a file past ARG_SAFE (Linux refuses one argument over 128 KiB)."""
        if len(text) <= ARG_SAFE:
            return ["-filter_complex", text]
        path = f"{out}.{len(scripts)}.graph"
        with open(path, "w") as f:
            f.write(text)
        scripts.append(path)
        return ["-filter_complex_script", path]
    try:
        _master(p, out, master, solo, head, wav, graph, lim, lufs, tp, ffmpeg, info, fc)
    finally:
        for path in scripts:
            os.unlink(path)
    info["seconds"] = round(time.monotonic() - t0, 3)
    return info


def _master(p, out, master, solo, head, wav, graph, lim, lufs, tp, ffmpeg, info, fc) -> None:  # noqa: ANN001
    if solo is not None:
        _run(head + [*fc(graph), "-map", "[pre]"] + wav)
    elif master == "gain":
        pre = out + ".pre.wav"
        text = _run(head + [*fc(graph + ";[pre]ebur128[m]"), "-map", "[m]",
                            "-c:a", "pcm_f32le", pre])
        info["pre_lufs"] = got = summary(text)[0]
        gain = 0.0 if got is None else lufs - got
        try:
            _run([ffmpeg, "-hide_banner", "-nostdin", "-v", "info", "-y", "-i", pre,
                  "-af", f"volume={gain:.2f}dB,{lim}"] + wav)
        finally:
            os.unlink(pre)
        info["runs"] = 2
    elif master == "loudnorm":
        _run(head + [*fc(graph + f";[pre]loudnorm=I={lufs}:TP={tp}:LRA=20,{lim}[out]"),
                     "-map", "[out]"] + wav)
    elif master == "loudnorm2":
        text = _run(head + [*fc(graph + f";[pre]loudnorm=I={lufs}:TP={tp}:LRA=20:print_format=json"
                                    "[m]"), "-map", "[m]", "-f", "null", "-"])
        m = json.loads(text[text.rfind("{"):text.rfind("}") + 1])
        ln = (f"loudnorm=I={lufs}:TP={tp}:LRA=20:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
              f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
              "linear=true")
        _run(head + [*fc(graph + f";[pre]{ln},{lim}[out]"), "-map", "[out]"] + wav)
        info["runs"] = 2
    else:
        raise ValueError(f"master {master!r}")
