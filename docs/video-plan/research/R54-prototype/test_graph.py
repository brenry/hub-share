"""Tests of graph.py with the real ffmpeg (/usr/bin/ffmpeg 6.1) on synthetic takes (synth.py, bench.scene)."""
import copy
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench  # noqa: E402
import graph as G  # noqa: E402
import place as P  # noqa: E402
import synth  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(G.FFMPEG), reason="no ffmpeg")
DEPTH = G.DUCK["depth_db"]                      # the stated duck: 10 dB


@pytest.fixture(scope="module")
def scene(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("takes"))
    rows, takes = bench.scene(d, room=True)
    takes["e1"] = synth.take(synth.clicks(os.path.join(d, "e1.wav"), 2000), "effect")
    rows["events"].append({"id": "e1", "kind": "cue", "cue": "effect", "start_ms": 7600, "end_ms": 9600})
    return d, rows, takes


def out(d, name):
    return os.path.join(d, "out-" + name + ".wav")


def test_master_meets_r128_with_a_peak_to_limit(scene):
    d, rows, takes = scene
    m = takes["e1"]["measured"]
    assert m["true_peak_dbtp"] + m["gain_db"] > 1.0                   # the levelled clicks peak over 0 dBTP
    p = P.place(rows, takes, {"Character 1": {"gain_db": 6.0}})              # and one speaker 6 dB hot
    info = G.render(p, out(d, "master"))
    i, tp = synth.ebur(out(d, "master"))
    assert abs(i - G.TARGET["lufs"]) <= 1.0, i
    assert tp <= G.TARGET["true_peak_dbtp"], tp
    assert abs(synth.seconds(out(d, "master")) - p["length_ms"] / 1000) < 0.001
    assert info["runs"] == 2 and abs(info["pre_lufs"] - i) > 2               # the master did move it


def test_one_pass_loudnorm_overshoots_the_true_peak(scene, monkeypatch):
    """Finding: the design's loudnorm + alimiter at 0.891 (-1.0) lets the true peak through over -1 dBTP."""
    d, rows, takes = scene
    p = P.place(rows, takes, {"Character 1": {"gain_db": 6.0}})
    monkeypatch.setattr(G, "MARGIN_DB", 0.0)
    G.render(p, out(d, "ln1"), master="loudnorm")
    assert synth.ebur(out(d, "ln1"))[1] > G.TARGET["true_peak_dbtp"]


def test_speech_onsets_at_the_placed_times(scene):
    d, rows, takes = scene
    lines = {**rows, "events": [e for e in rows["events"] if e["kind"] == "line"]}
    p = P.place(lines, {k: v for k, v in takes.items() if k != "room"})
    G.render(p, out(d, "dialogue"))                                    # the whole master path: limiter latency too
    found = synth.onsets(out(d, "dialogue"))
    clips = sorted((c["at_ms"], c["at_ms"] + c["out_ms"] - c["in_ms"]) for c in p["clips"].values())
    expected, sounding = [], -1000
    for a, b in clips:
        if a - sounding >= 60:                                         # an overlap starts in sound: not an onset
            expected.append(a)
        sounding = max(sounding, b)
    assert len(expected) >= 10
    for a in expected:
        assert min(abs(a - f) for f in found) <= 20, (a, found)


def test_music_ducked_by_the_stated_depth(scene):
    d, rows, takes = scene
    p = P.place(rows, takes)
    G.render(p, out(d, "music"), solo={"music"})
    inside, between = bench.ducking(p, out(d, "music"))
    assert abs((between - inside) - DEPTH) <= 0.5, (inside, between)
    spans = G.speech_spans(p["lanes"], G.DUCK["attack_ms"] + G.DUCK["release_ms"])
    onset = [synth.rms_db(out(d, "music"), a, a + 150) for a, _ in spans]
    assert max(onset) <= between - DEPTH + 0.5                          # already down when each line starts


def test_sidechain_barely_ducks(scene):
    """Finding: threshold 0.05, ratio 6, attack 200, release 600 under dialogue at -23 LUFS."""
    d, rows, takes = scene
    p = P.place(rows, takes)
    G.render(p, out(d, "music-sc"), solo={"music"}, duck="sidechain")
    inside, between = bench.ducking(p, out(d, "music-sc"))
    assert between - inside < 3.0


def test_reaction_fade_reads_decay(scene):
    d, rows, takes = scene
    p = P.place(rows, takes, {"reaction": {"duck": False}})              # c3 ends as l8 starts: no duck in the way
    c2, c3 = p["clips"]["c2"], p["clips"]["c3"]
    assert c2["fade_out_ms"] == c3["fade_out_ms"] == P.REACTION_FADE_MIN    # decay 600 // 2, and a dead cut
    G.render(p, out(d, "reaction"), solo={"reaction"})
    end = c3["at_ms"] + c3["out_ms"] - c3["in_ms"]                      # c3's take is cut dead at its end
    middle = synth.rms_db(out(d, "reaction"), c3["at_ms"] + 300, end - 300)
    last = synth.rms_db(out(d, "reaction"), end - 50, end)
    assert middle - last >= 15.0, (middle, last)                          # 18.3 dB measured


def test_room_present_is_steady_and_not_ducked_absent_is_left_out(scene):
    d, rows, takes = scene
    p = P.place(rows, takes)
    G.render(p, out(d, "room"), solo={"room"})
    assert abs(synth.seconds(out(d, "room")) - p["length_ms"] / 1000) < 0.001
    windows = [synth.rms_db(out(d, "room"), a, a + 1000) for a in range(1000, p["length_ms"] - 1000, 1000)]
    assert max(windows) - min(windows) <= 3.0, windows                  # looped, never ducked, no hole
    q = P.place(rows, {k: v for k, v in takes.items() if k != "room"})
    assert q["notes"] == [P.NO_ROOM]
    G.render(q, out(d, "noroom"))
    assert abs(synth.ebur(out(d, "noroom"))[0] - G.TARGET["lufs"]) <= 1.0


def test_remix_of_30_s_12_lines_4_lanes_in_seconds(scene):
    d, rows, takes = scene
    rows = {**rows, "events": [e for e in rows["events"] if e["id"] != "e1"]}
    p = P.place(rows, {k: v for k, v in takes.items() if k != "room"})
    assert len(p["lanes"]) == 4 and len([c for c in p["clips"].values() if c["kind"] == "line"]) == 12
    assert 29_000 <= p["length_ms"] <= 32_000
    t0 = time.monotonic()
    P.place(rows, {k: v for k, v in takes.items() if k != "room"})
    info = G.render(p, out(d, "timed"))
    took = time.monotonic() - t0
    print(f"\nre-mix 30 s / 12 lines / 4 lanes: {took:.2f} s (place + {info['runs']} ffmpeg runs)")
    assert took < 5.0


def test_400_clips_go_through_a_graph_file(scene):
    """The reader's cap (400 clips) with a ducked bed: the graph passes 128 KiB, Linux's limit for one argument."""
    d, rows, takes = scene
    events = [{"id": f"l{k}", "kind": "line", "speaker": f"S{k % 16}", "start_ms": 3000 * k,
               "end_ms": 3000 * k + 2000} for k in range(399)]
    events.append({"id": "m1", "kind": "cue", "cue": "music", "start_ms": 0, "end_ms": 30000})
    many = {f"l{k}": copy.deepcopy(takes["l1"]) for k in range(399)}
    p = P.place({"events": events}, {**many, "m1": takes["c1"]})
    assert len(p["lanes"]) == 17
    t0 = time.monotonic()
    info = G.render(p, out(d, "big"))
    print(f"\n400 clips, {p['length_ms'] / 60000:.1f} min, {info['graph_chars']} chars: {time.monotonic() - t0:.1f} s")
    assert info["graph_chars"] > 131_072 > G.ARG_SAFE           # so it went through -filter_complex_script
    assert abs(synth.ebur(out(d, "big"))[0] - G.TARGET["lufs"]) <= 1.0


def test_finding_spec_half_decay_fade_leaves_a_dead_cut_dead(scene):
    """The design's reaction fade: a reaction fades out over decay_ms // 2, at least 10 ms. A take whose sound stops
    dead measures decay_ms 0, gets 10 ms, and still stops dead; place.py's floor (REACTION_FADE_MIN) does not."""
    d, rows, takes = scene
    p = P.place(rows, takes, {"reaction": {"duck": False}})
    c3 = p["clips"]["c3"]
    c3["fade_out_ms"] = max(10, takes["c3"]["measured"]["decay_ms"] // 2)
    G.render(p, out(d, "reaction-spec"), solo={"reaction"})
    end = c3["at_ms"] + c3["out_ms"] - c3["in_ms"]
    middle = synth.rms_db(out(d, "reaction-spec"), c3["at_ms"] + 300, end - 300)
    assert middle - synth.rms_db(out(d, "reaction-spec"), end - 50, end) < 3.0


def test_finding_spec_clip_chain_comes_out_short(scene):
    """The design's clip chain (atrim, asetpts, format, gain, fades, adelay) then the lane's apad + atrim=end: in
    ffmpeg 6.1 adelay's lead-in frames carry no pts, so atrim=end cuts the lane far short of L."""
    d, rows, takes = scene
    m = takes["l12"]["measured"]
    a, b = m["speech_start_ms"] / 1000, m["speech_end_ms"] / 1000
    chain = (f"atrim=start={a}:end={b},asetpts=PTS-STARTPTS,{G.FMT},volume=0dB,afade=t=in:st=0:d=0.01,"
             f"adelay=27587|27587,apad=whole_dur=31,atrim=end=31")
    synth.ff("-i", takes["l12"]["file"], "-af", chain, "-c:a", "pcm_s16le", out(d, "spec-chain"))
    assert synth.seconds(out(d, "spec-chain")) < 29.0                    # expected 31.0; the clip itself is lost
    synth.ff("-i", takes["l12"]["file"], "-af", chain.replace("27587|27587", "27587|27587,asetpts=N/SR/TB"),
             "-c:a", "pcm_s16le", out(d, "fixed-chain"))
    assert synth.seconds(out(d, "fixed-chain")) == 31.0
