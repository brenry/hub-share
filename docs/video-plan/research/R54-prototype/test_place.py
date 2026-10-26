"""Tests of place.py (pure): the script-wide map, its refusals and limits."""
import math
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import place as P  # noqa: E402

T = P.TURN_MS


def line(i, who, a, b):
    return {"id": i, "kind": "line", "speaker": who, "start_ms": a, "end_ms": b}


def tk(kept, lead=200, **more):
    return {"file": "x.wav", "measured": {"speech_start_ms": lead, "speech_end_ms": lead + kept, "gain_db": 0.0,
                                          **more}}


def run(events, takes, shots=(), **kw):
    rows = {"shots": [{"id": i, "start_ms": a, "end_ms": b} for i, a, b in shots], "events": events}
    return P.place(rows, takes, **kw)


def at(p, ident):
    return p["clips"][ident]["at_ms"]


def test_right_behind_across_a_shot_boundary():
    ev = [line("l1", "A", 1000, 3000), line("l2", "B", 3000, 5000)]          # l2 opens shot s2
    shots = [("s1", 0, 3000), ("s2", 3000, 6000)]
    p = run(ev, {"l1": tk(2500), "l2": tk(1500)}, shots)
    assert at(p, "l1") == 1000
    assert at(p, "l2") == 1000 + 2500 + T                                   # the measured end, not the shot's start
    assert p["shots"][1]["start_ms"] == 1000 + 2500 + T                      # the cut moves with the line
    assert run(ev, {"l1": tk(2500), "l2": tk(1500)})["clips"] == p["clips"]  # shots are never read for sound


def test_made_pause_kept_by_the_running_offset():
    ev = [line("l1", "A", 0, 2000), line("l2", "B", 3500, 5500), line("l3", "A", 5500, 7000)]
    for kept in (1000, 1820, 3000):                                         # short, as planned, long
        p = run(ev, {"l1": tk(kept), "l2": tk(1820), "l3": tk(1000)})
        assert at(p, "l2") - (kept + T) == 1500                             # the 1.5 s pause, exactly
        assert at(p, "l3") == at(p, "l2") + 1820 + T


def test_overlap_on_its_own_lane_with_rising_breakpoints():
    ev = [line("l1", "A", 0, 3000), line("l2", "B", 2000, 4000), line("l3", "A", 4000, 5000)]
    p = run(ev, {"l1": tk(3600), "l2": tk(1500), "l3": tk(800)})
    a, b = p["clips"]["l1"], p["clips"]["l2"]
    assert b["at_ms"] < a["at_ms"] + a["out_ms"] - a["in_ms"]                # they sound together
    assert b["at_ms"] == round(2000 * (3600 + T) / 3000)                     # the interruption point, mapped
    names = {lane["name"]: [c["id"] for c in lane["clips"]] for lane in p["lanes"]}
    assert names["A"] == ["l1", "l3"] and names["B"] == ["l2"]
    keys, vals = zip(*p["map"])
    assert all(x < y for x, y in zip(keys, keys[1:])) and all(x <= y for x, y in zip(vals, vals[1:]))
    assert at(p, "l3") == max(3600, b["at_ms"] - 0 + 1500) + T              # behind whichever ends later


def test_overlap_that_overruns_pushes_what_follows():
    ev = [line("l1", "A", 0, 3000), line("l2", "B", 2000, 2800), line("l3", "A", 3000, 4000)]
    p = run(ev, {"l1": tk(2000), "l2": tk(2500), "l3": tk(800)})
    end_b = at(p, "l2") + 2500 + T
    assert end_b > 2000 + T and at(p, "l3") == end_b


def test_overlap_of_one_speaker_with_the_same_speaker_is_refused():
    ev = [line("l1", "A", 0, 3000), line("l2", "A", 2000, 4000)]
    with pytest.raises(P.Refused, match="same speaker"):
        run(ev, {"l1": tk(1000), "l2": tk(1000)})


def test_overrun_pushes_every_later_event():
    ev = [line("l1", "A", 0, 2000), line("l2", "B", 2000, 4000), line("l3", "A", 5000, 7000),
          {"id": "c1", "kind": "cue", "cue": "reaction", "start_ms": 4000, "end_ms": 5000},
          {"id": "p1", "kind": "pose", "character": "A", "start_ms": 5000, "end_ms": 7000},
          {"id": "f1", "kind": "panel", "at_ms": 6000}]
    takes = {"l1": tk(1820), "l2": tk(1820), "l3": tk(1820), "c1": tk(800, decay_ms=300)}
    base = run(ev, takes)
    long = run(ev, {**takes, "l2": tk(1820 + 700)})
    assert at(long, "l1") == at(base, "l1")
    for ident in ("l3", "c1"):
        assert at(long, ident) - at(base, ident) == 700
    assert long["measured"]["p1"]["start_ms"] - base["measured"]["p1"]["start_ms"] == 700
    assert long["measured"]["f1"]["at_ms"] - base["measured"]["f1"]["at_ms"] == 700
    assert base["clips"]["c1"]["at_ms"] == base["measured"]["l2"]["end_ms"] + T   # anchored at l2's end


def test_the_map_is_monotonic_on_random_scripts():
    rnd = random.Random(54)
    for _ in range(300):
        ev, takes, t = [], {}, 0
        for k in range(rnd.randint(1, 14)):
            t += rnd.choice([0, 0, 0, rnd.randint(1, 2000), -rnd.randint(1, 1500)])
            t = max(0, t)
            length = rnd.randint(400, 4000)
            ev.append(line(f"l{k}", f"S{k}", t, t + length))
            takes[f"l{k}"] = tk(max(1, length + rnd.randint(-1500, 1500) - T))
            t += length
        ev += [{"id": f"f{j}", "kind": "panel", "at_ms": rnd.randint(0, t + 1000)} for j in range(5)]
        p = run(ev, takes)
        keys, vals = zip(*p["map"])
        assert all(x < y for x, y in zip(keys, keys[1:])) and all(x <= y for x, y in zip(vals, vals[1:]))
        grid = [P.interp(p["map"], x) for x in range(0, t + 2000, 37)]
        assert all(x <= y for x, y in zip(grid, grid[1:]))
        panels = sorted((e["at_ms"], p["measured"][e["id"]]["at_ms"]) for e in ev if e["kind"] == "panel")
        assert all(a[1] <= b[1] for a, b in zip(panels, panels[1:]))


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, True, "3"])
def test_non_finite_numbers_are_refused_in_one_line(bad):
    for where in ("gain_db", "speech_end_ms"):
        take = tk(1000)
        take["measured"][where] = bad
        with pytest.raises(P.Refused) as e:
            run([line("l1", "A", 0, 2000)], {"l1": take})
        assert "\n" not in str(e.value) and "l1" in str(e.value)
    with pytest.raises(P.Refused):
        run([line("l1", "A", 0, bad)], {"l1": tk(1000)})


def test_a_ninth_speaker_and_the_cast_limit():
    def cast(n):
        ev = [line(f"l{k}", f"S{k}", 2000 * k, 2000 * k + 2000) for k in range(n)]
        ev.append({"id": "c1", "kind": "cue", "cue": "music", "start_ms": 0, "end_ms": 1000})
        return run(ev, {**{f"l{k}": tk(1500) for k in range(n)}, "c1": tk(900), "room": tk(2000)})
    assert len(cast(9)["lanes"]) == 9 + 2                     # 11; a 12-lane cap only holds 8 + 4
    assert len(cast(16)["lanes"]) == 18 and P.MAX_LANES == P.MAX_CAST + 4 == 20
    with pytest.raises(P.Refused, match="17 speakers"):
        cast(17)


def test_shot_minimum_moves_cuts_never_clips():
    ev = [line("l1", "A", 0, 2000), line("l2", "B", 2000, 4000), line("l3", "A", 4000, 6000)]
    takes = {"l1": tk(1820), "l2": tk(300), "l3": tk(1820)}                  # l2 comes back 1.5 s short
    shots = [("s1", 0, 2000), ("s2", 2000, 4000), ("s3", 4000, 6000)]
    p = run(ev, takes, shots)
    s2 = p["shots"][1]
    assert P.interp(p["map"], 4000) - P.interp(p["map"], 2000) == 300 + T < 1000
    assert s2["end_ms"] - s2["start_ms"] == 1000                             # the picture holds 1 s
    assert p["shots"][2]["start_ms"] == s2["end_ms"]
    assert p["clips"] == run(ev, takes)["clips"]                             # the sound did not move
    assert at(p, "l3") == 1820 + T + 300 + T


def test_room_absent_is_a_note_and_present_is_the_last_lane_looped():
    ev = [line("l1", "A", 0, 2000)]
    p = run(ev, {"l1": tk(1820)})
    assert p["notes"] == [P.NO_ROOM] and all(lane["kind"] != "room" for lane in p["lanes"])
    p = run(ev, {"l1": tk(1820), "room": tk(500)})
    room = p["lanes"][-1]
    assert room["kind"] == "room" and not room["duck"] and room["clips"][0]["loop"]
    assert room["clips"][0]["until_ms"] == p["length_ms"] and p["notes"] == []


def test_refusals_a_reader_would_make():
    ev = [line("l1", "A", 0, 2000), line("l2", "B", 2000, 4000)]
    with pytest.raises(P.Refused, match="l2 has no take"):
        run(ev, {"l1": tk(1000)})
    with pytest.raises(P.Refused, match="gain_db"):
        run(ev, {"l1": tk(1000, gain_db=43.0), "l2": tk(1000)})              # takejudge can write up to +46.9
    with pytest.raises(P.Refused, match="lane A: gain_db"):
        run(ev, {"l1": tk(1000), "l2": tk(1000)}, lanes_before={"A": {"gain_db": -80}})
    many = [line(f"l{k}", f"S{k % 3}", 1000 * k, 1000 * k + 1000) for k in range(1001)]
    with pytest.raises(P.Refused, match="1001 clips"):
        run(many, {f"l{k}": tk(500) for k in range(1001)})
    one = [line(f"l{k}", "S0", 1000 * k, 1000 * k + 1000) for k in range(401)]
    with pytest.raises(P.Refused, match="lane S0: 401 clips"):
        run(one, {f"l{k}": tk(500) for k in range(401)})
    with pytest.raises(P.Refused, match="silent"):
        run(ev, {"l1": {"file": "x", "measured": {"speech_start_ms": None, "speech_end_ms": None}},
                 "l2": tk(1)})


def test_lane_state_kept_and_fades():
    ev = [line("l1", "A", 0, 2000),
          {"id": "c1", "kind": "cue", "cue": "reaction", "start_ms": 2000, "end_ms": 4000},
          {"id": "c2", "kind": "cue", "cue": "reaction", "start_ms": 5000, "end_ms": 6000},
          {"id": "c3", "kind": "cue", "cue": "music", "start_ms": 0, "end_ms": 6000}]
    takes = {"l1": tk(1820), "c1": tk(2000, decay_ms=700), "c2": tk(1000, decay_ms=0), "c3": tk(6000)}
    p = run(ev, takes, lanes_before={"reaction": {"gain_db": -3.0, "duck": False}})
    lanes = {lane["name"]: lane for lane in p["lanes"]}
    assert lanes["reaction"]["gain_db"] == -3.0 and lanes["reaction"]["duck"] is False
    assert lanes["music"]["duck"] is True
    assert p["clips"]["c1"]["fade_out_ms"] == 350                            # half its measured decay
    assert p["clips"]["c2"]["fade_out_ms"] == P.REACTION_FADE_MIN            # cut dead in the take: a fade made
    assert (p["clips"]["l1"]["fade_in_ms"], p["clips"]["c3"]["fade_out_ms"]) == (10, 1000)


def design_placement(lines, takes):
    """The design's placement as written: map from (0, 0); at = map(start); (start, at) added when start is after the
    last breakpoint; (end, at + kept + TURN) added only when both times are after the last breakpoint's."""
    bp, ats = [(0, 0)], {}
    for ln in sorted(lines, key=lambda e: (e["start_ms"], e["id"])):
        m = takes[ln["id"]]["measured"]
        kept = m["speech_end_ms"] - m["speech_start_ms"]
        at = P.interp(bp, ln["start_ms"])
        if ln["start_ms"] > bp[-1][0]:
            bp.append((ln["start_ms"], at))
        if ln["end_ms"] > bp[-1][0] and at + kept + T > bp[-1][1]:
            bp.append((ln["end_ms"], at + kept + T))
        ats[ln["id"]] = (at, at + kept)
    return ats


def test_finding_spec_drops_an_interruptions_overrun():
    """B interrupts A and is planned to end inside A, but its take runs long: the design adds no breakpoint, so C (right
    behind A) starts while B is still speaking, an overlap nobody wrote. place.py raises P instead."""
    ev = [line("A", "J", 0, 3000), line("B", "K", 2000, 2800), line("C", "J", 3000, 4000)]
    takes = {"A": tk(2800), "B": tk(2500), "C": tk(800)}
    spec = design_placement(ev, takes)
    assert spec["C"][0] < spec["B"][1]                                       # C runs into B
    ours = run(ev, takes)
    assert at(ours, "C") == ours["measured"]["B"]["end_ms"] + T


def test_finding_spec_leaves_dead_air_after_a_short_interruption():
    """B interrupts A and is planned to end 1 s after A, but its take comes back short (ends before A's sound): the
    design maps C (right behind B) at slope 1 past A's end breakpoint: 1 s of silence nobody wrote. place.py: C follows
    the last sound by the turn pause."""
    ev = [line("A", "J", 0, 3000), line("B", "K", 2000, 4000), line("C", "J", 4000, 5000)]
    takes = {"A": tk(3300), "B": tk(600), "C": tk(800)}
    spec = design_placement(ev, takes)
    last_sound = max(spec["A"][1], spec["B"][1])
    assert spec["C"][0] - last_sound == 1000 + T
    ours = run(ev, takes)
    assert at(ours, "C") - max(ours["measured"]["A"]["end_ms"], ours["measured"]["B"]["end_ms"]) == T
