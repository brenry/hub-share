"""R54 prototype: the worked scene (30 s, 12 lines, two speakers, a reaction and a music lane: 4 lanes; the room
optional) and the comparison of the master and duck modes. `python3 bench.py` prints the numbers the README cites."""
from __future__ import annotations

import os
import sys
import tempfile
import time

import graph
import place
import synth

# (id, speaker, planned start, planned end, take: lead, speech, tail ms, amp)
LINES = [
    ("l1", "Character 1", 500, 2700, (300, 2000, 400, 0.30)),
    ("l2", "Character 2", 2700, 4900, (250, 2400, 300, 0.08)),     # right behind, measured 200 ms long: pushes
    ("l3", "Character 1", 4900, 6900, (200, 1600, 500, 0.50)),     # right behind, short: pulls back
    ("l4", "Character 2", 8400, 10600, (300, 2000, 300, 0.20)),    # a made pause of 1.5 s
    ("l5", "Character 1", 10600, 12800, (200, 2000, 200, 0.30)),
    ("l6", "Character 2", 12000, 14000, (300, 1800, 300, 0.25)),   # a written overlap (interrupts l5)
    ("l7", "Character 1", 14000, 16200, (300, 2000, 300, 0.30)),
    ("l8", "Character 2", 17200, 19400, (300, 2000, 300, 0.12)),
    ("l9", "Character 1", 19400, 21600, (200, 2600, 200, 0.30)),   # long: pushes l10..l12
    ("l10", "Character 2", 21600, 23800, (300, 2000, 300, 0.30)),
    ("l11", "Character 1", 24800, 27000, (300, 2000, 300, 0.40)),
    ("l12", "Character 2", 27000, 29200, (300, 1800, 300, 0.30)),
]
SHOTS = [("s1", 0, 6900), ("s2", 6900, 12800), ("s3", 12800, 21600), ("s4", 21600, 30000)]


def scene(folder: str, room: bool = False, lines: list | None = None) -> tuple[dict, dict]:
    """(rows, takes) with every take a real WAV in `folder`, measured as the Hub measures it."""
    rows = {"cast": ["Character 1", "Character 2"], "shots": [{"id": i, "start_ms": a, "end_ms": b} for i, a, b in SHOTS],
            "events": []}
    takes = {}
    for ident, who, a, b, (lead, speech, tail, amp) in lines or LINES:
        rows["events"].append({"id": ident, "kind": "line", "speaker": who, "start_ms": a, "end_ms": b})
        freq = 220 if who == "Character 1" else 330
        takes[ident] = synth.take(synth.voice(os.path.join(folder, f"{ident}.wav"), freq, lead, speech, tail, amp),
                                  "line")
    rows["events"] += [
        {"id": "c1", "kind": "cue", "cue": "music", "start_ms": 0, "end_ms": 30000},
        {"id": "c2", "kind": "cue", "cue": "reaction", "start_ms": 6900, "end_ms": 8400},     # in the made pause
        {"id": "c3", "kind": "cue", "cue": "reaction", "start_ms": 16200, "end_ms": 17200},
        {"id": "p1", "kind": "pose", "character": "Character 1", "start_ms": 2700, "end_ms": 4900},
        {"id": "f1", "kind": "panel", "at_ms": 13000}]
    takes["c1"] = synth.take(synth.music(os.path.join(folder, "c1.wav"), 31000), "music")
    takes["c2"] = synth.take(synth.noise(os.path.join(folder, "c2.wav"), "pink", 1400, 0.4, 100, 600, 200),
                             "reaction", 600)
    takes["c3"] = synth.take(synth.noise(os.path.join(folder, "c3.wav"), "pink", 1000, 0.4, 100, 0, 200),
                             "reaction", 0)
    if room:
        takes["room"] = synth.take(synth.noise(os.path.join(folder, "room.wav"), "brown", 2000, 0.05), "room")
    return rows, takes


def ducking(p: dict, path: str) -> tuple[float, float]:
    """The music stem's mean level (dB) inside the placed speech and in the gaps long enough to come back up, each
    window kept clear of the ramps."""
    spans = graph.speech_spans(p["lanes"], graph.DUCK["attack_ms"] + graph.DUCK["release_ms"])
    inside = [synth.rms_db(path, a + 100, b - 100) for a, b in spans if b - a > 400]
    gaps = [(b1 + graph.DUCK["release_ms"] + 100, a2 - graph.DUCK["attack_ms"] - 100)
            for (_, b1), (a2, _) in zip(spans, spans[1:])]
    between = [synth.rms_db(path, a, b) for a, b in gaps if b - a >= 200]
    return sum(inside) / len(inside), sum(between) / len(between)


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        t0 = time.monotonic()
        rows, takes = scene(d)
        print(f"takes made and measured: {time.monotonic() - t0:.2f} s")
        t0 = time.monotonic()
        p = place.place(rows, takes)
        print(f"place: {1000 * (time.monotonic() - t0):.1f} ms, {len(p['lanes'])} lanes, length {p['length_ms']} ms")
        for master in ("gain", "loudnorm", "loudnorm2"):
            for duck in ("envelope", "sidechain"):
                out = os.path.join(d, f"{master}-{duck}.wav")
                info = graph.render(p, out, master=master, duck=duck)
                i, tp = synth.ebur(out)
                stem = os.path.join(d, f"stem-{duck}.wav")
                graph.render(p, stem, duck=duck, solo={"music"})
                inside, between = ducking(p, stem)
                print(f"{master:9} {duck:9} {info['seconds']:.2f} s ({info['runs']} runs)  I {i} LUFS  TP {tp} dBTP"
                      f"  length {synth.seconds(out):.3f} s  music in speech {inside:.1f}, between {between:.1f}"
                      f" (duck {between - inside:.1f} dB)")
        rows, takes = scene(d, room=True)
        p = place.place(rows, takes)
        info = graph.render(p, os.path.join(d, "mix-room.wav"))
        print(f"with room: {len(p['lanes'])} lanes, {info['seconds']:.2f} s, graph {info['graph_chars']} chars")
        takes["e1"] = synth.take(synth.clicks(os.path.join(d, "e1.wav"), 2000), "effect")
        m = takes["e1"]["measured"]
        print(f"clicks: {m['lufs']} LUFS, {m['true_peak_dbtp']} dBTP, gain {m['gain_db']} -> peaks at "
              f"{m['true_peak_dbtp'] + m['gain_db']:.1f} dBTP in the mix")
        for at in (7600, 9000, 15000):            # in the made pause (unducked), under l4 (ducked), in a gap
            rows2 = {**rows, "events": rows["events"] + [{"id": "e1", "kind": "cue", "cue": "effect",
                                                          "start_ms": at, "end_ms": at + 2000}]}
            p = place.place(rows2, takes, {"Character 1": {"gain_db": 6.0}})
            got = []
            for margin in (0.0, 0.5):
                graph.MARGIN_DB = margin
                for master in ("gain", "loudnorm", "loudnorm2"):
                    graph.render(p, os.path.join(d, "peak.wav"), master=master)
                    i, tp = synth.ebur(os.path.join(d, "peak.wav"))
                    got.append(f"{master}@{margin}: {i}/{tp}")
            print(f"effect at {at}: " + " | ".join(got))
        graph.MARGIN_DB = 0.5


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
