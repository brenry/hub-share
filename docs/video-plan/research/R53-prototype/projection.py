"""R53 reference prototype: a set's floor plan projected through a setup into a frame layout (stdlib math only).

Conventions (note §2): metres; origin = centre of the stage's downstage edge at floor level; x to camera-right
as seen from the house, y upstage (away from the house), z up. Plan angles in degrees counter-clockwise from +x seen
from above: 90 faces upstage, -90 faces the house. Tilt positive up. Screen: u 0..1 left to right, v 0..1 top to bottom.
A setup is {x, y, z, pan, tilt, f_mm}; the lens is a focal length on a sensor 9.6 mm high (Zettl's 1-inch Plumbicon).
"""
import math

SENSOR_H_MM = 9.6        # 1-inch Plumbicon image 12.8 x 9.6 mm; Zettl pp. 42-43: 17 mm sees 4.5 m wide at 6 m
ASPECTS = {"4:3": 4 / 3, "16:9": 16 / 9}     # same vertical angle in both; 16:9 sees more at the sides
CANVAS = {"control 4:3": (640, 480), "sketch 4:3": (512, 384), "sketch 16:9": (576, 320)}   # blueprint §20.3, §18.1
FPS = 24                 # R48 §7: 362 frames = 15.08 s
SEAT_H = 0.45            # assumption: chair seat above the floor it stands on
WIDTH_K = 0.26           # assumption: body box width / height (shoulders)
# Katz fig. 6.1 (p. 122): the frame's lower edge as a fraction of standing height down from the crown, measured off
# the printed figure (crown 189 px, soles 1507 px at 150 dpi; R53 note §3).
KATZ = {"extreme_close_up": 0.118, "medium_close_up": 0.130, "full_close_up": 0.175, "wide_close_up": 0.207,
        "close_shot": 0.260, "medium_close_shot": 0.384, "medium_shot": 0.468, "medium_full_shot": 0.722,
        "full_shot": 1.010}
CODES = {"XCU": "extreme_close_up", "CU": "wide_close_up", "MCU": "close_shot", "MS": "medium_shot",
         "MLS": "medium_full_shot", "LS": "full_shot"}      # assumption: the Hub's codes -> Katz's lines
NAMES = {"close shot": "MCU", "close-up": "CU", "medium shot": "MS", "full shot": "LS", "long shot": "LS",
         "extreme close-up": "XCU", "wide shot": "ELS", "extreme long shot": "ELS"}
HEADROOM = {"XCU": (-0.20, 0.0), "CU": (0.03, 0.12), "MCU": (0.04, 0.14), "MS": (0.05, 0.15),
            "MLS": (0.05, 0.18), "LS": (0.05, 0.20), "ELS": (0.05, 0.75)}   # assumption (Zettl p. 78 gives no number)
ELS_BAND = (0.55, 0.80)  # assumption: an extreme long shot puts crown and feet at these v (person 25% of frame)
LAND = {"crown": 0.0, "head": 0.06, "chin": 0.112, "shoulders": 0.175, "waist": 0.384, "hips": 0.468,
        "knees": 0.722, "feet": 1.0}
LEAD_K, LEAD_TOL = 0.17, 0.08   # assumption: full profile puts the head 0.17 off centre (near a third), +-0.08
OTS_U = 0.64             # assumption: the OTS subject's head on the third away from the foreground shoulder

def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

def wrap(a):
    return (a + 180.0) % 360.0 - 180.0

def bearing(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))

def f_from_hfov(hfov_deg, aspect=4 / 3):
    return SENSOR_H_MM * aspect / 2 / math.tan(math.radians(hfov_deg) / 2)

def hfov(f_mm, aspect=4 / 3):
    return math.degrees(2 * math.atan(SENSOR_H_MM * aspect / 2 / f_mm))

# ---------------------------------------------------------------- the plan
def _local(box, x, y):
    """(x, y) in a box's own frame (its centre, turned by its rot_deg)."""
    a, dx, dy = math.radians(-box[2]), x - box[0], y - box[1]
    return (dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a))

def base_z(plan, x, y):
    """The floor a person stands on: the highest walkable element under (x, y), else the floor."""
    tops = [b[6] for b in (_solid(e) for e in plan["elements"] if e.get("walkable"))
            if all(abs(c) <= h for c, h in zip(_local(b, x, y), b[3:5]))]
    return max(tops, default=0.0)

def camera_setup(plan, name, f_mm=None, pan=None, tilt=None):
    c = next(c for c in plan["cameras"] if c["name"] == name)
    f = f_mm or c.get("default_lens_mm") or f_from_hfov(c["horizontal_fov_deg"])
    aim = c.get("default_aim", {})
    return {"camera": name, "x": c["x"], "y": c["y"], "z": c["height"], "f_mm": f,
            "pan": aim.get("pan_deg", 90.0) if pan is None else pan,
            "tilt": aim.get("tilt_deg", 0.0) if tilt is None else tilt}

def person(plan, p):
    """A staged person with the base_z filled from the plan (a copy)."""
    q = dict(p)
    q.setdefault("base_z", base_z(plan, p["x"], p["y"]))
    return q

def point_at(p, f):
    """The body point at Katz fraction f (0 crown .. 1 soles). Sitting: torso lowered onto the seat, thighs forward."""
    h, z0 = p["height_m"], p.get("base_z", 0.0)
    a = math.radians(p.get("facing_deg", -90.0))
    fx, fy, hip = math.cos(a), math.sin(a), LAND["hips"]
    if p.get("posture") != "sit" or f <= hip:
        drop = h * (1 - hip) - (SEAT_H + 0.05) if p.get("posture") == "sit" else 0.0
        return (p["x"], p["y"], z0 + h * (1 - f) - drop)
    seg = [(hip, SEAT_H + 0.05, 0.0), (LAND["knees"], SEAT_H + 0.08, 0.45), (1.0, 0.0, 0.5), (1.1, -0.1, 0.5)]
    for (f0, z_a, d_a), (f1, z_b, d_b) in zip(seg, seg[1:]):
        if f <= f1:
            t = (f - f0) / (f1 - f0)
            z, d = z_a + (z_b - z_a) * t, d_a + (d_b - d_a) * t
            return (p["x"] + fx * d, p["y"] + fy * d, z0 + z)
    return (p["x"], p["y"], z0)

def framing_point(p, code):
    return point_at(p, KATZ[CODES[code]])

# ---------------------------------------------------------------- the camera
def basis(s):
    th, ph = math.radians(s["pan"]), math.radians(s["tilt"])
    fw = (math.cos(ph) * math.cos(th), math.cos(ph) * math.sin(th), math.sin(ph))
    rt = (math.sin(th), -math.cos(th), 0.0)
    up = (rt[1] * fw[2] - rt[2] * fw[1], rt[2] * fw[0] - rt[0] * fw[2], rt[0] * fw[1] - rt[1] * fw[0])
    return rt, up, fw

def project(s, pt, aspect=4 / 3):
    """(u, v, depth) of a world point, or None behind the lens. Pinhole: u = 0.5 + x/(z tan(h/2))/2."""
    rt, up, fw = basis(s)
    d = (pt[0] - s["x"], pt[1] - s["y"], pt[2] - s["z"])
    zc = _dot(d, fw)
    if zc <= 1e-6:
        return None
    tv = SENSOR_H_MM / 2 / s["f_mm"]
    return (0.5 + _dot(d, rt) / zc / (tv * aspect) / 2, 0.5 - _dot(d, up) / zc / tv / 2, zc)

def to_pixels(uv, canvas="control 4:3"):
    w, h = CANVAS[canvas]
    return (uv[0] * w, uv[1] * h)

def side_shown(p, s):
    """front/left/right/back: the person's facing against the direction to the lens; `looks` screen-left/right."""
    rel = wrap(bearing((p["x"], p["y"]), (s["x"], s["y"])) - p.get("facing_deg", -90.0))
    side = "front" if abs(rel) <= 45 else "back" if abs(rel) >= 135 else ("left" if rel > 0 else "right")
    a = math.radians(p.get("facing_deg", -90.0))
    lr = _dot((math.cos(a), math.sin(a), 0.0), basis(s)[0])
    looks = "camera" if abs(rel) <= 15 else "away" if abs(rel) >= 165 else ("screen-right" if lr > 0 else "screen-left")
    return side, looks, rel

def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

def _solid(item):
    """An item as an oriented box (cx, cy, rot_deg, half_w, half_d, z0, z1); a person is the body's box."""
    if "height_m" in item:
        z0 = item.get("base_z", 0.0)
        return (item["x"], item["y"], item.get("facing_deg", 0.0), 0.15, item["height_m"] * WIDTH_K / 2,
                z0, point_at(item, 0.0)[2])
    hw, hd = (item["r"], item["r"]) if item["shape"] == "circle" else (item["w"] / 2, item["d"] / 2)
    z0 = item.get("z0", 0.0)
    return (item["x"], item["y"], item.get("rot_deg", 0.0), hw, hd, z0, z0 + item["height"])

def _blocks(s, pt, box):
    """True when the box cuts the line of sight from the lens to pt before it arrives (slab test, local frame)."""
    o, e = _local(box, s["x"], s["y"]) + (s["z"],), _local(box, pt[0], pt[1]) + (pt[2],)
    t0, t1 = 0.0, 1.0
    for i, (lo, hi) in enumerate(((-box[3], box[3]), (-box[4], box[4]), (box[5], box[6]))):
        d = e[i] - o[i]
        if abs(d) < 1e-12:
            if not lo <= o[i] <= hi:
                return False
            continue
        ta, tb = sorted(((lo - o[i]) / d, (hi - o[i]) / d))
        t0, t1 = max(t0, ta), min(t1, tb)
    return t0 <= t1 and t0 < 0.98

def _corners(box):
    """The eight corners of a solid (a circle's are its bounding square's)."""
    a = math.radians(box[2])
    return [(box[0] + sx * box[3] * math.cos(a) - sy * box[4] * math.sin(a),
             box[1] + sx * box[3] * math.sin(a) + sy * box[4] * math.cos(a), z)
            for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)) for z in (box[5], box[6])]

def layout(s, people, props=(), aspect=4 / 3):
    """The frame layout: per person in_frame, head/feet (u, v), scale, side, framing read back, depth, occluders."""
    out = {}
    for p in people:
        pts = {k: project(s, point_at(p, f), aspect) for k, f in LAND.items()}
        rec = {"kind": "person", "in_frame": False, "head_in": False}
        out[p["name"]] = rec
        if any(v is None for v in pts.values()):
            continue
        head, crown, feet = pts["head"], pts["crown"], pts["feet"]
        hw = p["height_m"] * WIDTH_K / 2 / head[2] / (SENSOR_H_MM / 2 / s["f_mm"] * aspect) / 2
        box = (min(v[0] for v in pts.values()) - hw, crown[1], max(v[0] for v in pts.values()) + hw,
               max(v[1] for v in pts.values()))
        side, looks, rel = side_shown(p, s)
        rec.update(in_frame=_overlap(box, (0, 0, 1, 1)), head_in=0 <= head[0] <= 1 and 0 <= head[1] <= 1,
                   head=head[:2], feet=feet[:2], crown=crown[:2], box=box, depth=head[2], scale=box[3] - box[1],
                   side=side, looks=looks, rel_deg=rel, headroom=crown[1], framing=read_framing(s, p, aspect))
    for el in props:
        pts = [project(s, q, aspect) for q in _corners(_solid(el))]
        if any(v is None for v in pts):
            out[el["name"]] = {"kind": "prop", "in_frame": False}
            continue
        box = (min(v[0] for v in pts), min(v[1] for v in pts), max(v[0] for v in pts), max(v[1] for v in pts))
        out[el["name"]] = {"kind": "prop", "in_frame": _overlap(box, (0, 0, 1, 1)), "box": box,
                           "depth": min(v[2] for v in pts)}
    seen = sorted((n for n, r in out.items() if r["in_frame"]), key=lambda n: out[n]["depth"])
    solids = {i["name"]: _solid(i) for i in list(people) + list(props)}
    for rank, n in enumerate(seen):
        out[n]["depth_rank"] = rank
    for p in people:
        r = out[p["name"]]
        if not r["in_frame"]:
            continue
        mine = (p["name"], p.get("on"))
        hits = {k: [m for m in seen if m not in mine and _blocks(s, point_at(p, LAND[k]), solids[m])]
                for k in ("head", "shoulders", "waist", "knees", "feet")}
        r["occluded_by"] = sorted({m for v in hits.values() for m in v})
        r["face_hidden"] = bool(hits["head"])
        r["hidden_points"] = [k for k, v in hits.items() if v]
    return out

def read_framing(s, p, aspect=4 / 3):
    """Which named framing the frame's bottom edge makes on this person (the nearest Katz line, or LS/ELS)."""
    feet, crown = project(s, point_at(p, 1.0), aspect), project(s, point_at(p, 0.0), aspect)
    if feet and crown and feet[1] <= 1.0:
        return "ELS" if feet[1] - crown[1] <= ELS_BAND[1] - ELS_BAND[0] + 0.05 else "LS"
    return min(CODES, key=lambda c: abs((project(s, framing_point(p, c), aspect) or (0, 9))[1] - 1.0))

# ---------------------------------------------------------------- solving a named framing
def _lin(a, b):
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        for r in range(n):
            if r != c and m[c][c]:
                k = m[r][c] / m[c][c]
                m[r] = [x - k * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]

def _newton(res, x, steps=40):
    for _ in range(steps):
        r0 = res(x)
        if max(abs(v) for v in r0) < 1e-7:
            break
        cols = []
        for i in range(len(x)):
            h = 1e-6 * max(1.0, abs(x[i]))
            xi = x[:i] + [x[i] + h] + x[i + 1:]
            cols.append([(a - b) / h for a, b in zip(res(xi), r0)])
        dx = _lin([[cols[j][i] for j in range(len(x))] for i in range(len(r0))], [-v for v in r0])
        x = [a + b for a, b in zip(x, dx)]
    return x

def _uv(s, pt, aspect):
    return project(s, pt, aspect) or (9.0, 9.0, 0.0)

def _start(cam, pts, aspect):
    """A first guess: aim at the points' middle, lens to fit their vertical spread."""
    mx, my, mz = (sum(p[i] for p in pts) / len(pts) for i in range(3))
    dist = math.hypot(mx - cam["x"], my - cam["y"])
    el = [math.degrees(math.atan2(p[2] - cam["z"], dist)) for p in pts]
    span = max(max(el) - min(el), 1.0) * 1.3
    return [bearing((cam["x"], cam["y"]), (mx, my)), (max(el) + min(el)) / 2,
            SENSOR_H_MM / 2 / math.tan(math.radians(span) / 2)]

def lead_target(p, cam):
    side, looks, rel = side_shown(p, dict(cam, pan=bearing((cam["x"], cam["y"]), (p["x"], p["y"]))))
    k = LEAD_K * abs(math.sin(math.radians(rel)))
    return 0.5 - k if looks == "screen-right" else 0.5 + k if looks == "screen-left" else 0.5

def frame_single(cam, p, code, aspect=4 / 3, f_mm=None, u_head=None):
    """Aim and lens (or, with f_mm fixed, the distance along the subject->camera line) that frame p at `code`."""
    code = NAMES.get(code, code)
    lo, hi = HEADROOM[code]
    top_v, bot_v, bot_pt = ((lo + hi) / 2, 1.0, framing_point(p, code)) if code != "ELS" else \
        (ELS_BAND[0], ELS_BAND[1], point_at(p, 1.0))
    crown = point_at(p, 0.0)
    u_t = lead_target(p, cam) if u_head is None else u_head
    head = point_at(p, LAND["head"])
    def setup(x):
        s = dict(cam, pan=x[0], tilt=x[1], f_mm=x[2] if f_mm is None else f_mm)
        if f_mm is not None:
            b = math.radians(bearing((p["x"], p["y"]), (cam["x"], cam["y"])))
            s.update(x=p["x"] + x[2] * math.cos(b), y=p["y"] + x[2] * math.sin(b))
        return s
    def res(x):
        s = setup(x)
        return [_uv(s, head, aspect)[0] - u_t, _uv(s, crown, aspect)[1] - top_v, _uv(s, bot_pt, aspect)[1] - bot_v]
    x0 = _start(cam, [crown, bot_pt], aspect)
    if f_mm is not None:
        x0[2] = math.hypot(p["x"] - cam["x"], p["y"] - cam["y"]) * f_mm / x0[2]
    return setup(_newton(res, x0))

def frame_group(cam, people, code="MS", aspect=4 / 3, margin=0.05):
    """Two-shot / three-shot: the group centred, the highest crown at the headroom, the lowest framing line at the
    bottom edge; widened if any box would cross the side margins."""
    code = NAMES.get(code, code)
    top_v = sum(HEADROOM[code]) / 2
    crowns = [point_at(p, 0.0) for p in people]
    bots = [framing_point(p, code) if code != "ELS" else point_at(p, 1.0) for p in people]
    heads = [point_at(p, LAND["head"]) for p in people]
    def res(x, wide=False):
        s = dict(cam, pan=x[0], tilt=x[1], f_mm=x[2])
        us = [_uv(s, h, aspect)[0] for h in heads]
        r = [(min(us) + max(us)) / 2 - 0.5, min(_uv(s, c, aspect)[1] for c in crowns) - top_v]
        if not wide:
            return r + [max(_uv(s, b, aspect)[1] for b in bots) - 1.0]
        lay = layout(s, people, aspect=aspect)
        return r + [max(lay[p["name"]]["box"][2] for p in people) - min(lay[p["name"]]["box"][0] for p in people)
                    - (1 - 2 * margin)]
    x = _newton(res, _start(cam, crowns + bots, aspect))
    s = dict(cam, pan=x[0], tilt=x[1], f_mm=x[2])
    lay = layout(s, people, aspect=aspect)
    if any(lay[p["name"]]["box"][0] < margin or lay[p["name"]]["box"][2] > 1 - margin for p in people):
        x = _newton(lambda y: res(y, wide=True), x)
        s = dict(cam, pan=x[0], tilt=x[1], f_mm=x[2])
    return s

def frame_ots(cam, subject, over, code="MCU", aspect=4 / 3):
    """OTS on `subject` over `over`'s shoulder: subject framed at `code` on the far third; ok when `over` is nearer,
    in frame on the near side and does not hide the subject's face."""
    c = (cam["x"], cam["y"])
    near_left = wrap(bearing(c, (over["x"], over["y"])) - bearing(c, (subject["x"], subject["y"]))) > 0
    s = frame_single(cam, subject, code, aspect, u_head=OTS_U if near_left else 1 - OTS_U)
    lay = layout(s, [subject, over], aspect=aspect)
    o, t = lay[over["name"]], lay[subject["name"]]
    edge_ok = o["in_frame"] and ((o["box"][0] < 0.35) if near_left else (o["box"][2] > 0.65))
    why = None if edge_ok and o["depth"] < t["depth"] and not t.get("face_hidden") else \
        f"{over['name']} is not a foreground shoulder from camera {cam.get('camera')}: use ots_position()"
    return s, why

def ots_position(subject, over, back=1.0, side=0.6, house=(0.0, -6.0)):
    """A camera place behind `over` on the subject->over line, `side` m toward the house (the line's camera side), at
    the subject's eye level (Zettl pp. 346-347). back, side: assumption."""
    a, b = (subject["x"], subject["y"]), (over["x"], over["y"])
    t = math.radians(bearing(a, b))
    n = (-math.sin(t), math.cos(t))
    if line_side(a, b, (b[0] + n[0], b[1] + n[1])) != line_side(a, b, house):
        n = (-n[0], -n[1])
    return {"camera": f"ots_{over['name']}", "x": b[0] + back * math.cos(t) + side * n[0],
            "y": b[1] + back * math.sin(t) + side * n[1], "z": point_at(subject, LAND["head"])[2],
            "pan": 0.0, "tilt": 0.0, "f_mm": 50.0}

# ---------------------------------------------------------------- the checks
def line_side(a, b, c):
    """+1 / -1 / 0: the side of the line a->b (plan) that point c is on."""
    k = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return 0 if abs(k) < 1e-9 else (1 if k > 0 else -1)

def same_side(a, b, prev_cam, next_cam):
    """The 180-degree rule (Katz p. 130; Zettl pp. 270-272): both cameras within one semicircle of the line a-b."""
    return line_side(a, b, (prev_cam["x"], prev_cam["y"])) * line_side(a, b, (next_cam["x"], next_cam["y"])) > 0

def screen_order_kept(lay1, lay2, a, b):
    """True/False when a and b are both in both frames (their left/right order kept), None otherwise."""
    if not all(lay[n]["head_in"] for lay in (lay1, lay2) for n in (a, b)):
        return None
    return (lay1[a]["head"][0] < lay1[b]["head"][0]) == (lay2[a]["head"][0] < lay2[b]["head"][0])

def matched_pair(s1, p1, s2, p2, aspect=4 / 3, dist_tol=0.10, lens_tol=0.10, sight_tol_deg=10.0):
    """Two singles cut together: one framing, lens and subject distance within tolerance, sight lines at the same
    angle from the lens (S&B pp. 33-34 via R49; Katz pp. 176, 179). Tolerances: assumption. -> (ok, reasons)."""
    why = []
    d1 = math.dist((s1["x"], s1["y"], s1["z"]), point_at(p1, LAND["head"]))
    d2 = math.dist((s2["x"], s2["y"], s2["z"]), point_at(p2, LAND["head"]))
    if abs(d1 / d2 - 1) > dist_tol:
        why.append(f"subject distance {d1:.2f} m vs {d2:.2f} m")
    if abs(s1["f_mm"] / s2["f_mm"] - 1) > lens_tol:
        why.append(f"lens {s1['f_mm']:.0f} mm vs {s2['f_mm']:.0f} mm")
    f1, f2 = read_framing(s1, p1, aspect), read_framing(s2, p2, aspect)
    if f1 != f2:
        why.append(f"framing {f1} vs {f2}")
    r1, r2 = side_shown(p1, s1)[2], side_shown(p2, s2)[2]
    if abs(abs(r1) - abs(r2)) > sight_tol_deg:
        why.append(f"sight line {abs(r1):.0f} deg vs {abs(r2):.0f} deg off the lens")
    return not why, why

def headroom_ok(rec, code):
    lo, hi = HEADROOM[NAMES.get(code, code)]
    return lo <= rec["headroom"] <= hi

def leadroom_ok(rec):
    """Nose room (Zettl p. 74; Katz p. 124): the head sits off centre away from where the person looks, more as the person turns."""
    need = LEAD_K * abs(math.sin(math.radians(rec["rel_deg"])))
    sign = {"screen-right": 1, "screen-left": -1}.get(rec["looks"], 0)
    actual = (0.5 - rec["head"][0]) * sign if sign else abs(rec["head"][0] - 0.5)
    return abs(actual - (need if sign else 0.0)) <= LEAD_TOL

# ---------------------------------------------------------------- a move
def ease(t, kind="inout"):
    return {"linear": t, "in": t * t, "out": 1 - (1 - t) ** 2,
            "inout": (1 - math.cos(math.pi * t)) / 2}[kind]

def move(a, b, frames, kind="inout"):
    """Per-frame setups from a to b: position and tilt linear, pan by the short way, lens geometric (an even zoom)."""
    out = []
    for i in range(frames):
        t = ease(i / (frames - 1) if frames > 1 else 1.0, kind)
        s = dict(a, **{k: a[k] + (b[k] - a[k]) * t for k in ("x", "y", "z", "tilt")})
        s["pan"] = a["pan"] + wrap(b["pan"] - a["pan"]) * t
        s["f_mm"] = a["f_mm"] * (b["f_mm"] / a["f_mm"]) ** t
        out.append(s)
    return out

def rates(path, fps=FPS):
    """Peak speeds of a move: pan/tilt deg/s, zoom in stops (doublings of f) per s, travel m/s."""
    pairs = list(zip(path, path[1:]))
    return {"pan_deg_s": max((abs(wrap(b["pan"] - a["pan"])) * fps for a, b in pairs), default=0.0),
            "tilt_deg_s": max((abs(b["tilt"] - a["tilt"]) * fps for a, b in pairs), default=0.0),
            "zoom_stops_s": max((abs(math.log2(b["f_mm"] / a["f_mm"])) * fps for a, b in pairs), default=0.0),
            "travel_m_s": max((math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"])) * fps
                               for a, b in pairs), default=0.0)}

def push_in(cam, p, from_code, to_code, frames, aspect=4 / 3, dolly=False, kind="inout"):
    """A push-in on p: a zoom from the camera's place, or (dolly=True) a travel at the start's focal length."""
    a = frame_single(cam, p, from_code, aspect)
    b = frame_single(a if dolly else cam, p, to_code, aspect, f_mm=a["f_mm"] if dolly else None)
    return move(a, b, frames, kind)
