"""Tests for the R53 prototype; the worked example is three_camera.json beside this file."""
import json
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import projection as P  # noqa: E402

SET = json.load(open(os.path.join(HERE, "three_camera.json")))
PLAN = SET["floor_plan"]
PEOPLE = {p["name"]: P.person(PLAN, p) for p in SET["staging"]["people"]}
J, K, D = PEOPLE["Character 1"], PEOPLE["Character 2"], PEOPLE["Character 3"]
ALL = [J, K, D]
PROPS = [e for e in PLAN["elements"]]
MARK_OF = {p["mark"]: p["name"] for p in SET["staging"]["people"]}


def cam(name, **kw):
    return P.camera_setup(PLAN, name, **kw)


# ---------------------------------------------------------------- lens and pinhole
def test_lens_matches_zettl_field_of_view():
    """Zettl pp. 42-43: a 17-170 mm zoom (1-inch Plumbicon) sees 4.5 m wide at 6 m zoomed out, 1/10 of it zoomed in."""
    for f, width in ((17, 4.5), (170, 0.45)):
        w = 2 * 6.0 * math.tan(math.radians(P.hfov(f)) / 2)
        assert w == pytest.approx(width, rel=0.02)
    assert P.f_from_hfov(P.hfov(35)) == pytest.approx(35)


def test_pinhole_centre_edges_and_aspects():
    s = {"x": 0, "y": 0, "z": 1.5, "pan": 90, "tilt": 0, "f_mm": 17}
    assert P.project(s, (0, 6, 1.5))[:2] == pytest.approx((0.5, 0.5))
    half = 6 * math.tan(math.radians(P.hfov(17)) / 2)
    assert P.project(s, (half, 6, 1.5))[0] == pytest.approx(1.0)       # right edge, 4:3
    assert P.project(s, (-half, 6, 1.5))[0] == pytest.approx(0.0)
    wide = P.project(s, (half, 6, 2.0), P.ASPECTS["16:9"])
    assert wide[0] == pytest.approx(0.5 + 0.5 * 0.75)                   # 16:9: same vertical angle, wider view
    assert wide[1] == pytest.approx(P.project(s, (half, 6, 2.0))[1])    # v unchanged between aspects
    assert P.project(s, (0, -1, 1.5)) is None                           # behind the lens
    assert P.to_pixels((0.5, 0.5), "sketch 16:9") == (288, 160) and P.to_pixels((1, 1)) == (640, 480)


def test_people_stand_on_the_platform():
    assert [p["base_z"] for p in ALL] == [0.3, 0.3, 0.3]
    assert P.point_at(J, 0.0)[2] == pytest.approx(0.3 + 1.78)
    assert P.point_at(K, 0.0)[2] < P.point_at(J, 0.0)[2] - 0.3        # seated crown well below the standing lead
    assert P.point_at(K, 1.0)[2] == pytest.approx(0.3)                 # feet on the platform, forward of the chair


# ---------------------------------------------------------------- the worked example's cameras
def test_cameras_numbered_left_to_right():                              # Zettl p. 454; R50 ST-5
    xs = [c["x"] for c in PLAN["cameras"] if c["name"] in "123"]
    assert xs == sorted(xs)


def test_default_lenses_within_zettls_zoom():                           # Zettl p. 34: 17-170 mm
    assert all(17 <= c["default_lens_mm"] <= 170 for c in PLAN["cameras"])


@pytest.mark.parametrize("name", ["1", "2", "3"])
def test_each_camera_frames_what_the_plan_says(name):
    """Zettl pp. 426-427: from the extreme left the seated speaker, the other cross-shoots the lead; Katz p. 133: the middle
    camera has the group; Zettl p. 274: the lead screen-left, the lead's close-up looking right."""
    c = next(c for c in PLAN["cameras"] if c["name"] == name)
    lay = P.layout(cam(name), ALL, PROPS)
    want = {MARK_OF[m] for m in c["covers"]["on"]}
    assert {n for n in ("Character 1", "Character 2", "Character 3") if lay[n]["head_in"]} == want
    for n in want:
        assert lay[n]["framing"] == c["covers"]["framing"]
        assert not lay[n]["face_hidden"]
    if name == "2":
        assert lay["Character 1"]["head"][0] < lay["Character 2"]["head"][0] < lay["Character 3"]["head"][0]
    else:
        n = want.pop()
        assert lay[n]["side"] == "front"
        assert P.headroom_ok(lay[n], "MCU") and P.leadroom_ok(lay[n])
    if name == "3":
        assert lay["Character 1"]["looks"] == "screen-right"


def test_reverse_frames_the_house_and_no_one_on_stage():
    s = cam("rev")
    a = PLAN["audience_area"]
    u, v, _ = P.project(s, (a["x"], a["y"], 1.0))
    assert 0 < u < 1 and 0 < v < 1
    lay = P.layout(s, ALL)
    assert not any(lay[n]["in_frame"] for n in lay)


def test_side_shown_and_depth_order():
    lay = P.layout(cam("2"), ALL, PROPS)
    assert lay["Character 2"]["side"] == "left" and lay["Character 2"]["looks"] == "screen-left"   # the seated speakers turned to the lead
    assert lay["Character 1"]["depth_rank"] < lay["Character 2"]["depth_rank"] < lay["Character 3"]["depth_rank"]
    assert "low_table" in lay["Character 3"]["occluded_by"] and lay["Character 3"]["hidden_points"] == ["feet"]
    a = math.radians(K["facing_deg"] + 180)                                 # behind the seated speaker, looking at that speaker's back
    behind = {"x": K["x"] + 3 * math.cos(a), "y": K["y"] + 3 * math.sin(a), "z": 1.5, "pan": K["facing_deg"],
              "tilt": 0, "f_mm": 30}
    assert P.layout(behind, [K])["Character 2"]["side"] == "back"


# ---------------------------------------------------------------- solving named framings
@pytest.mark.parametrize("code", ["XCU", "CU", "MCU", "MS", "MLS", "LS", "ELS"])
def test_frame_single_hits_katz_line_and_headroom(code):
    s = P.frame_single(cam("2"), K, code)
    rec = P.layout(s, [K])["Character 2"]
    assert rec["framing"] == code
    assert P.headroom_ok(rec, code)
    if code not in ("LS", "ELS"):
        assert P.project(s, P.framing_point(K, code))[1] == pytest.approx(1.0, abs=1e-4)


def test_close_shot_by_name_and_fixed_lens():
    s = P.frame_single(cam("1"), K, "close shot")
    assert P.read_framing(s, K) == "MCU" and 17 <= s["f_mm"] <= 170
    fixed = P.frame_single(cam("1"), K, "CU", f_mm=50.0)               # a prime: solve the distance instead
    assert fixed["f_mm"] == 50.0 and P.read_framing(fixed, K) == "CU"
    d = math.hypot(fixed["x"] - K["x"], fixed["y"] - K["y"])
    assert 1.0 < d < 4.0
    assert P.line_side((J["x"], J["y"]), (K["x"], K["y"]), (fixed["x"], fixed["y"])) == \
        P.line_side((J["x"], J["y"]), (K["x"], K["y"]), (cam("1")["x"], cam("1")["y"]))


def test_two_shot_character_1_and_2():
    s = P.frame_group(cam("2"), [J, K], "MS")
    lay = P.layout(s, ALL, PROPS)
    assert lay["Character 1"]["head_in"] and lay["Character 2"]["head_in"] and not lay["Character 3"]["head_in"]
    assert lay["Character 1"]["head"][0] < 0.5 < lay["Character 2"]["head"][0]
    assert (lay["Character 1"]["head"][0] + lay["Character 2"]["head"][0]) / 2 == pytest.approx(0.5, abs=1e-4)
    assert min(lay["Character 1"]["headroom"], lay["Character 2"]["headroom"]) == pytest.approx(0.10, abs=1e-4)


def test_ots_on_character_2_over_1():
    s, why = P.frame_ots(cam("1"), K, J)
    assert why and "ots_position" in why                                # camera 1 is not behind Character 1's shoulder
    place = P.ots_position(K, J)
    s, why = P.frame_ots(place, K, J)
    assert why is None
    lay = P.layout(s, ALL)
    assert lay["Character 2"]["head"][0] == pytest.approx(P.OTS_U, abs=1e-4) and not lay["Character 2"]["face_hidden"]
    assert lay["Character 1"]["in_frame"] and lay["Character 1"]["depth_rank"] < lay["Character 2"]["depth_rank"]
    assert P.same_side((J["x"], J["y"]), (K["x"], K["y"]), cam("2"), s)   # the OTS place is inside the semicircle


# ---------------------------------------------------------------- the checks
def test_180_degree_line():
    a, b = (J["x"], J["y"]), (K["x"], K["y"])
    c1, c2, c3 = cam("1"), cam("2"), cam("3")
    assert P.same_side(a, b, c1, c2) and P.same_side(a, b, c2, c3)
    across = {"x": 0.5, "y": 4.2, "z": 1.5, "pan": -110, "tilt": -5, "f_mm": 25}
    assert not P.same_side(a, b, c2, across)
    wide2 = P.layout(P.frame_group(c2, [J, K], "MS"), ALL)
    wide3 = P.layout(P.frame_group(c3, [J, K], "MS"), ALL)
    rev = P.layout(P.frame_group(across, [J, K], "MS"), ALL)
    assert P.screen_order_kept(wide2, wide3, "Character 1", "Character 2") is True
    assert P.screen_order_kept(wide2, rev, "Character 1", "Character 2") is False   # the flip SW-15 refuses
    assert P.screen_order_kept(wide2, P.layout(c1, ALL), "Character 1", "Character 2") is None


def test_matched_pairs():
    s1, s3 = cam("1"), cam("3")
    ok, why = P.matched_pair(s1, K, s3, J)
    assert ok, why
    ok, why = P.matched_pair(s1, K, P.frame_single(cam("3"), J, "CU"), J)
    assert not ok and any("framing" in w for w in why) and any("lens" in w for w in why)
    near = P.frame_single(dict(cam("3"), x=0.5, y=-0.5), J, "MCU")
    ok, why = P.matched_pair(s1, K, near, J)
    assert not ok and any("distance" in w for w in why)


def test_headroom_and_lead_room_fail_when_off():
    s = P.frame_single(cam("1"), K, "MCU")
    bad = P.layout(dict(s, tilt=s["tilt"] + 0.6), [K])["Character 2"]
    assert not P.headroom_ok(bad, "MCU")
    centred = P.layout(P.frame_single(cam("1"), K, "MCU", u_head=0.5), [K])["Character 2"]
    assert not P.leadroom_ok(centred)                                   # looks off screen-left with no room there
    assert P.leadroom_ok(P.layout(s, [K])["Character 2"])


# ---------------------------------------------------------------- moves
def test_push_in_zoom_is_eased_and_keeps_the_seated_speaker_framed():
    path = P.push_in(cam("1"), K, "MS", "CU", 48)
    assert len(path) == 48
    assert P.read_framing(path[0], K) == "MS" and P.read_framing(path[-1], K) == "CU"
    logs = [math.log(s["f_mm"]) for s in path]
    steps = [b - a for a, b in zip(logs, logs[1:])]
    assert all(x > 0 for x in steps) and steps[0] < steps[23] > steps[-1]   # ease in and out
    assert all(P.layout(s, [K])["Character 2"]["head_in"] for s in path)
    assert {s["x"] for s in path} == {cam("1")["x"]}                         # a zoom: the camera stays
    r = P.rates(path)
    assert r["zoom_stops_s"] > 0 and r["travel_m_s"] == 0


def test_push_in_dolly_keeps_the_lens():
    path = P.push_in(cam("1"), K, "MS", "MCU", 72, dolly=True)
    assert {round(s["f_mm"], 9) for s in path} == {round(path[0]["f_mm"], 9)}
    d = [math.hypot(s["x"] - K["x"], s["y"] - K["y"]) for s in path]
    assert all(b < a for a, b in zip(d, d[1:])) and P.read_framing(path[-1], K) == "MCU"
    assert P.rates(path)["travel_m_s"] > 0


def test_pan_takes_the_short_way():
    a = {"x": 0, "y": 0, "z": 1.5, "pan": 170, "tilt": 0, "f_mm": 20}
    path = P.move(a, dict(a, pan=-170), 5, "linear")
    assert path[2]["pan"] == pytest.approx(180) and P.rates(path, 24)["pan_deg_s"] == pytest.approx(5 * 24)


def test_prototype_stays_small():
    assert sum(1 for _ in open(os.path.join(HERE, "projection.py"))) < 400
