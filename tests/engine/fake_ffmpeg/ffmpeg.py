"""A fake ffmpeg for the join's command lines. It reads what the real one would make from its arguments (the
concat list's files whole, or the graph's `trim`/`scale`/`fps` at the canvas rate), prints `-progress` lines (one
`out_time_us=N/A` first) and writes a `tiny_mp4` of those frames (plus `off`) at the canvas size, with sound when
the command maps `[a]` or the listed clips have it. A `.wav` output is a `tiny_wav` as long as track 1's
trimmed sounds or the silence the graph names (plus `off_seconds`). `-h filter=amix` prints a help text naming
`normalize` unless the config says `no_normalize`."""
from __future__ import annotations

import re
import signal
import sys
import time

import fakelib


def unquote(line: str) -> str:
    """A concat list line `file '<path>'` (a `'` inside written `'\\''`) -> the path."""
    body = line.strip()[len("file "):]
    return body[1:-1].replace("'\\''", "'")


def planned(args: list[str]) -> tuple[int, int, int, float, bool, str | None]:
    """-> frames, w, h, rate, sound, and the concat list's text."""
    inputs = [args[k + 1] for k, a in enumerate(args) if a == "-i"]
    if "concat" in args and "-filter_complex" not in args:
        with open(inputs[0], encoding="utf-8") as f:
            text = f.read()
        clips = [fakelib.facts(unquote(x)) for x in text.splitlines() if x.strip()]
        first = clips[0]
        return (sum(c["frames"] for c in clips), first["w"], first["h"], first["fps"],
                any(c["audio"] for c in clips), text)
    graph = args[args.index("-filter_complex") + 1]
    rate = float(re.search(r"fps=([0-9.]+)", graph).group(1))
    w, h = (int(x) for x in re.search(r"scale=(\d+):(\d+)", graph).groups())
    trims = [(int(a), int(b)) for a, b in re.findall(r"trim=start_frame=(\d+):end_frame=(\d+)", graph)]
    clips = inputs[:len(trims)]                 # track 2's inputs come after the clips
    frames = sum(round((b - a) * rate / fakelib.facts(path)["fps"]) for (a, b), path in zip(trims, clips, strict=True))
    return frames, w, h, rate, "[a]" in args, None


def wav_seconds(args: list[str]) -> float:
    """A WAV graph's length: track 1's trimmed sounds (`[aN]`), or the silence that stands for it (`[base]`/`[a]`)."""
    graph = args[args.index("-filter_complex") + 1]
    spans = re.findall(r"atrim=start=([0-9.]+):end=([0-9.]+),[^;]*\[a\d+\]", graph)
    silence = re.findall(r"anullsrc=r=48000:cl=stereo,atrim=duration=([0-9.]+)\[(?:base|a)\]", graph)
    return sum(float(b) - float(a) for a, b in spans) + sum(float(x) for x in silence)


def say(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def main() -> int:
    folder, args, config = fakelib.start()
    if args[:3] == ["-hide_banner", "-h", "filter=amix"]:
        fakelib.record(folder, "ffmpeg", args)
        sys.stdout.write("Filter amix\n  inputs  dropout_transition  weights\n" if config.get("no_normalize")
                         else "Filter amix\n  inputs  dropout_transition  weights  normalize\n")
        return 0
    if args[:3] == ["-hide_banner", "-h", "filter=sidechaincompress"]:
        fakelib.record(folder, "ffmpeg", args)
        sys.stdout.write("Unknown filter 'sidechaincompress'.\n" if config.get("no_duck")
                         else "Filter sidechaincompress\n  threshold  ratio  attack  release\n")
        return 0
    if config.get("ignore_term"):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if args[-1].endswith(".wav"):
        seconds = wav_seconds(args) + float(config.get("off_seconds") or 0)
        fakelib.record(folder, "ffmpeg", args)
        say("out_time_us=N/A\nprogress=continue")
        if config.get("exit"):
            return int(config["exit"])
        with open(args[-1], "wb") as f:
            f.write(fakelib.tiny_wav(seconds=seconds))
        say(f"out_time_us={round(seconds * 1e6)}\nprogress=end")
        return 0
    frames, w, h, rate, sound, text = planned(args)
    fakelib.record(folder, "ffmpeg", args, **({"list": text} if text is not None else {}))
    frames += int(config.get("off") or 0)
    say("frame=0\nout_time_us=N/A\nprogress=continue")
    say(f"frame={frames // 2}\nout_time_us={round(frames // 2 / rate * 1e6)}\nprogress=continue")
    time.sleep(float(config.get("sleep") or 0))
    if config.get("exit"):
        sys.stderr.write("".join(f"{x}\n" for x in config.get("stderr") or []))
        return int(config["exit"])
    with open(args[-1], "wb") as f:
        f.write(fakelib.tiny_mp4(w=w, h=h, fps=round(rate), frames=frames, audio=sound))
    say(f"frame={frames}\nout_time_us={round(frames / rate * 1e6)}\nprogress=end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
