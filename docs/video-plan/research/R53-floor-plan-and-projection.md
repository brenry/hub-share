# R53 — The set's floor plan, the setup and the projection (blueprint §19.2), 2026-10-20

Research note with a reference prototype, for the picture track (blueprint §19.7: the picture track, the floor plan, setups
and projection). Everything this note describes is in `R53-prototype/`:

- `R53-prototype/projection.py`: the prototype, stdlib `math` only.
- `R53-prototype/test_projection.py`: 27 tests.
- `R53-prototype/three_camera.json`: the worked example's set record.
- `R53-prototype/plan.svg`: the example's plan, drawn from the record.

The tests run with `.venv/bin/python -m pytest -p no:cacheprovider docs/video-plan/research/R53-prototype`.

**What was read.**
- Blueprint §11.5, §14, §16, §17.1, §18, §19.
- R50 §2 (ST-1 to ST-15) and §3 (SW-15 to SW-17).
- R49 §7.1-7.4 and §7.7-7.8.
- Katz and Zettl: the extracted text, plus the PDFs for their figures. These pages were rendered and read: Katz
  fig. 6.1, p. 122; Zettl figs. 10.18-10.20, pp. 272-274; 15.17, p. 423; 15.20a-e, pp. 426-427; 15.35, p. 454.
- `web/src/modules/director/tween.ts`, for how figures are placed today.

**Page offsets** were re-checked against the page headers: Katz PDF page = printed page + 13; Zettl PDF page = printed
page + 13. Every page cited here is the printed page.

---

## 1. Decisions a spec writer must know (the short list)

1. **Coordinates.**
   - Units are metres.
   - The origin is the centre of the stage's downstage edge, at floor level.
   - `x` runs camera-left to camera-right as seen from the house; `y` runs upstage, away from the house; `z` is up.
   - Plan angles are degrees counter-clockwise from +x, seen from above: 90 faces upstage, -90 faces the house.
   - Tilt is positive up.
   - Screen positions are fractions of the frame: `u` 0-1 from left to right, `v` 0-1 from top to bottom. Pixels are
     taken last, from the canvas, so the projection does not depend on resolution. The sizes are §20.3's: 640×480 for
     the 4:3 control and renders, 512×384 for the 4:3 sketch (§18.1's 448×336 is withdrawn there), and 576×320 for
     the 16:9 sketch.
2. **The lens is a focal length on Zettl's camera.**
   - The camera is a 1-inch Plumbicon with an image 12.8 × 9.6 mm, behind a 10:1 zoom of 17-170 mm (Zettl pp. 34,
     42-43).
   - The 12.8 mm width is derived, not printed: Zettl says the 17 mm end covers 4.5 m wide at 6 m. A test checks
     both ends of the zoom against Zettl's figure 3.9.
   - **The vertical angle is the same in both aspects.** A 16:9 canvas has the same height and sees more at the
     sides. Katz's framing heights are vertical, so a solved lens is the same in 4:3 and 16:9.
   - A camera record may give `horizontal_fov_deg` instead of a lens. It is read at 4:3.
3. **Framings are Katz's lines, measured off Katz's figure.** Fig. 6.1 (p. 122) is a drawing with no numbers. Its nine
   lines were measured as fractions of standing height below the crown (§3).
   - The Hub's six codes map onto five of those lines: XCU, CU, MCU, MS, MLS, LS.
   - ELS is a rule on scale, not a line.
   - The mapping and its reasons are in §3. "Close shot" means MCU, which is Katz's
     own Close Shot.
4. **The set record holds places; the staging holds people.**
   - `set.json`'s `floor_plan` holds the elements, the audience area, the named **marks** and the named **cameras**.
   - A scene's staging is the stager's output. It puts people on marks, or at an explicit `x, y`, with `facing_deg`,
     `height_m`, `posture` and `on` (the chair).
   - So "move the table" changes the set record only, and every scene on that set is re-projected (§14.3's stale
     rule).
5. **A setup is `{camera, f_mm, pan, tilt}`.** The camera's `x, y, height` come from the plan.
   - A shot stores its solved setup (the framing name is kept with it) and, for a move, the start and end setups
     with the ease.
   - Nothing downstream re-solves. The projection is deterministic from those numbers.
6. **Solving.** Each named framing is three equations in three unknowns, solved by Newton's method with a numeric
   Jacobian:
   - the head's `u`;
   - the crown's `v`, at the headroom;
   - the Katz line's `v`, at 1.0, the bottom edge.
   - The unknowns are pan, tilt and focal length. With a **fixed lens** they are pan, tilt and the distance along the
     subject-to-camera line: a dolly instead of a zoom.
7. **The checks need only geometry.**
   - The 180-degree line: the plan sides of the cameras, plus the screen order of two people.
   - Matched pairs: subject distance, lens, read-back framing and sight-line angle.
   - Headroom and lead room: on the layout.
   - Tolerances and headroom bands are **assumptions**, because no book gives a number. They are marked `advise`
     until measured, in R50's way.
8. **Findings from the worked example that change the preset.** Details are in §5.
   - **A standing lead with seated speakers** makes every two-shot uneven. Its MS request widens to MLS or LS, with
     0.36 of headroom over the seated speaker.
   - The same staging makes the "OTS over Character 1's shoulder" an over-the-hip: Character 1's head is above the frame.
   - Zettl's two-person sets seat both speakers (pp. 421-427). The worked example's lead stands.
   - The stager either seats the lead for question-and-answer stretches, or accepts that the outer cameras' singles are the
     coverage and the OTS is an over-the-hip (Katz p. 181: low-angle over-the-hip reverses "tend to put the subjects
     in an adversarial relationship").
9. **The zoom range is a check.** Camera 1's XCU on Character 2 needs 273 mm, and the zoom ends at 170 mm. ELS from
   camera 1 needs 9 mm, and it starts at 17 mm.
   - The prototype reports the focal length. It does not clamp it.
   - The builder adds `zoom_mm: [17, 170]` per camera and refuses with the fix: "dolly in" (the fixed-lens solve), or
     a range extender (Zettl p. 43).

---

## 2. The math, briefly

**Camera basis.** For pan θ and tilt φ:
- forward `f = (cosφ cosθ, cosφ sinθ, sinφ)`;
- right `r = (sinθ, −cosθ, 0)`;
- up `u = r × f`.

**Pinhole projection.** For a world point P, take `d = P − C` (C is the lens) and `z_c = d·f`. A point with
`z_c ≤ 0` is behind the lens. Otherwise:

```
tan_v = (sensor_h / 2) / f_mm            tan_h = tan_v × aspect
u = 0.5 + (d·r) / z_c / tan_h / 2         v = 0.5 − (d·u) / z_c / tan_v / 2
```

**A person** is an upright figure of `height_m` standing on `base_z`. `base_z` is the top of the highest walkable
element under the person; here, the 0.30 m platform. The person's body points are at Katz fractions `f` below the crown:

| point | f |
|---|---|
| crown | 0 |
| head (eye level) | 0.06 |
| chin | 0.112 |
| shoulders | 0.175 |
| waist (belt) | 0.384 |
| hips | 0.468 |
| knees | 0.722 |
| feet | 1.0 |

- **Standing:** `z = base + H(1 − f)`.
- **Sitting** (an assumption, anthropometric): the torso drops onto a 0.45 m seat, so the hips sit at seat + 0.05.
  The knees are 0.45 m forward at seat + 0.08, and the feet 0.50 m forward on the floor.
- The box for in-frame tests is 0.26 H wide. For occlusion, the person's solid is 0.26 H wide, 0.30 m deep and turned to the person's
  facing.

**The frame layout**, per person:
- `in_frame`: the person's box meets the frame.
- `head_in`: the person's eye point is inside the frame.
- `head`, `feet` and `crown` as `(u, v)`.
- `scale`: the box's height as a fraction of the frame. It is above 1 when the person is cropped.
- `side`: front, left, right or back.
- `looks`: camera, screen-left, screen-right or away.
- `framing`: the read-back. It is the Katz line nearest the bottom edge, or LS/ELS when the person's feet are in the frame.
- `headroom`: the crown's `v`.
- `depth`, `depth_rank`, `occluded_by`, `face_hidden` and `hidden_points`.

**Side shown.** Take `rel = wrap(bearing(person → lens) − facing)`:
- `|rel| ≤ 45°` is front;
- `|rel| ≥ 135°` is back;
- otherwise `rel > 0` is the person's left side and `rel < 0` the person's right side.

`looks` is the sign of the person's facing vector against the camera's right vector. "Camera" means `|rel| ≤ 15°`.

**Occlusion is a ray test, not a screen-box overlap.**
- A point is hidden when the segment from the lens to it crosses another item's oriented solid (a slab test in the
  solid's own frame).
- A person's own chair (`on`) is excluded.
- Points tested: head, shoulders, waist, knees and feet.
- Screen-box overlap does not work: the back flats' box spans the frame, so it "hides" Character 2.

**A named framing, solved.** Unknowns x = (pan, tilt, f). Residuals:

```
u(head) − u_target      v(crown) − headroom_target      v(Katz line point) − 1.0
```

- The solver is Newton's method with a forward-difference Jacobian and Gaussian elimination. It starts from the
  bearing to the points, their mean elevation and their angular spread, and converges in at most 5 steps on the example.
- `u_target` is the lead-room target: `0.5 ∓ 0.17·|sin rel|`, the head moved away from where the person looks.
- The **fixed-lens** variant swaps f for the distance d along the subject-to-camera bearing. It moves the camera; the
  camera's height is kept.
- **A group** (two-shot or three-shot) uses these residuals: the mean of the outermost heads' `u` at 0.5; the highest
  crown at the headroom; the lowest framing line at the bottom.
  - If any box crosses a 5 % side margin, the third residual becomes "outer box edges span 0.90" and the solve runs
    again.
  - This is Zettl's warning that people "glued to the edges" of the frame need a wider shot (p. 426).
- **OTS** solves the subject's single with `u_head = 0.64` (or 0.36), away from the foreground person. It then
  verifies three things:
  - the foreground person is in frame on the near edge (box edge before 0.35);
  - the foreground person is nearer the lens;
  - the foreground person does not hide the subject's face.
  - When any fails, the reason names `ots_position()`.
- **`ots_position`** puts a camera on the subject-to-foreground line, 1.0 m beyond the foreground person and shifted
  0.6 m toward the house. That is the line's camera side, so the place stays inside the semicircle. Its height is the
  subject's eye level (Zettl pp. 346-347: shoot "at eye level"). All three numbers are assumptions.

---

## 3. Katz's framing heights, measured, and the Hub's codes

Fig. 6.1, "Basic Framing heights for the human figure" (Katz p. 122), was rendered at 150 dpi.
- Crown (the top of the hair): row 189. Soles: row 1507. Height 1318 px.
- Each line is the frame's **lower edge** (R49 §7.1.1).
- Fraction = (line row − 189) / 1318.

| Katz's name | line row | fraction below crown | body point (read from the figure) | Hub code |
|---|---|---|---|---|
| Extreme Close-up | 344 | 0.118 | just below the chin | **XCU** |
| Medium Close-up | 361 | 0.130 | the neck | — |
| Full Close-up | 420 | 0.175 | the collar, top of the shoulders | — |
| Wide Close-up | 462 | 0.207 | below the shoulders | **CU** |
| Close Shot | 532 | 0.260 | the upper chest | **MCU** ("close shot") |
| Medium Close Shot | 695 | 0.384 | the belt | — |
| Medium Shot | 806 | 0.468 | below the hips | **MS** |
| Medium Full Shot | 1141 | 0.722 | above the knees | **MLS** (Zettl's "knee shot", p. 73) |
| Full Shot | 1520 | 1.010 | below the feet | **LS** |
| — | — | — | the person 25 % of frame height (crown v 0.55, feet v 0.80) | **ELS** (assumption) |

**Why this mapping:**
- Katz says the dialogue framing is "the shoulder-and-head shot" (p. 123), so CU is Katz's Wide Close-up.
- The brief's "close shot on Character 2" is Katz's Close Shot, so MCU = Close Shot.
- **Conflict:** Katz's own "Medium Close-up" is at the neck, which is tighter than television's MCU. The Hub never
  writes "medium close-up" in Katz's sense.
- Zettl's five steps (XLS, LS, MS, CU, XCU, p. 72) are relative and give no lines. Neither book draws ELS.

**The top of the frame.** Neither book gives a number:
- Zettl: "You must leave some headroom" (p. 78).
- Katz: "more space at the bottom of the frame than at the top" (p. 124).

The headroom bands are assumptions, as fractions of frame height from the crown to the top edge. The solver aims at
each band's middle.

| code | headroom band |
|---|---|
| XCU | −0.20 to 0 (the crown is cut) |
| CU | 0.03-0.12 |
| MCU | 0.04-0.14 |
| MS | 0.05-0.15 |
| MLS | 0.05-0.18 |
| LS | 0.05-0.20 |

**Seated people.** Katz's lines are drawn on a standing figure. On a seated one the lines down to the hips keep their
lengths below the crown. MS (the lap) and MLS (the knees, 0.45 m forward) then end only 3 cm apart. The solved lenses
from camera 1 for MS and MLS on Character 2 are 56.4 mm and 54.4 mm. **For a seated subject, MLS and MS read the same.** The
switcher should treat them as one framing for SW-16's no-near-identical-cut rule.

---

## 4. The floor-plan schema (in `set.json`) and the staging (in the scene)

```jsonc
"floor_plan": {
  "version": 1,
  "units": "m",
  "origin": "centre of the stage's downstage edge, at floor level",
  "axes": {"x": "...", "y": "...", "z": "up", "angles": "..."},              // documentation, fixed text
  "sensor": {"height_mm": 9.6, "width_mm_at_4_3": 12.8, "source": "..."},
  "elements": [                                  // every footprint on the plan, props included
    {"name": "low_table", "kind": "platform|flat|chair|table|desk|riser|prop",
     "shape": "rect", "x": 0.85, "y": 1.6, "w": 0.9, "d": 0.45, "rot_deg": 0,   // centre, size along its own axes
     "z0": 0.30, "height": 0.40,                 // base and height of its box (m)
     "walkable": false, "seat_z": 0.45,          // walkable: people stand on its top; seat_z: chairs only
     "source": "Zettl p. ... | assumption"},
    {"name": "plant", "shape": "circle", "x": 3.4, "y": 3.6, "r": 0.3, "z0": 0.3, "height": 1.4}
  ],
  "audience_area": {"shape": "rect", "x": 0, "y": -7.25, "w": 10, "d": 5.5,
                    "rows": 6, "row_depth": 0.9, "riser_step": 0.2, "seat_z": 0.45},
  "marks": [{"name": "lead", "x": -1.3, "y": 1.5, "posture": "stand", "facing_deg": 0},
            {"name": "seat_1", "x": 0.2, "y": 2.3, "posture": "sit", "facing_deg": 200, "on": "chair_1"}],
  "cameras": [
    {"name": "1", "role": "...", "x": -3.2, "y": -2.2, "height": 1.5,
     "default_lens_mm": 102,                     // or "horizontal_fov_deg": 7.2 (read at 4:3)
     "default_aim": {"pan_deg": 53.6, "tilt_deg": -0.5},
     "covers": {"framing": "MCU", "on": ["seat_1"]},   // marks; what the plan says this camera is for
     "source": "..."}
  ]
}
// the scene's staging (the stager's output, Step 14), not the set record:
"staging": {"pattern": "...", "people": [
  {"name": "Character 2", "mark": "seat_1", "x": 0.2, "y": 2.3, "facing_deg": 200, "height_m": 1.85,
   "posture": "sit", "on": "chair_1"}]}
// a shot (blueprint §19.1) gains:
"setup": {"camera": "1", "framing": "MCU", "on": ["Character 2"], "f_mm": 102.4, "pan": 53.59, "tilt": -0.52},
"move": {"kind": "push_in", "to": {"f_mm": 130.8, "pan": 53.45, "tilt": -0.10}, "ease": "inout"}
```

**Rules on the record:**
- `name` is unique across elements, marks and cameras.
- A prop that a line or a shot names must be an element; the Director never invents a prop (§14.2).
- Every camera of the plan is on one side of the scene's stage line (ST-3); the reverse is exempt.
- The cameras are numbered left to right by `x` (ST-5; Zettl p. 454); a test checks this.
- The default lenses lie inside the zoom (17-170 mm).
- Active furniture is at least 2 m from the set wall (Zettl p. 349).

**From `home` to a place.** The context's `home` (0-100, left to right, `tween.ts`) becomes a mark: the stager maps
`home` to the nearest mark of the right posture. Without a plan, `x = −w/2 + w·home/100` on a line at `y = 1.5`.
§16.3's `{where: "house", side, row}` maps to a seat in `audience_area`: `y = y_front − (row − 0.5)·row_depth`,
`base_z = (row − 1)·riser_step`.

---

## 5. The worked example: a three-camera stage with an audience

The plan is `R53-prototype/plan.svg`, drawn from the record. **Sources and numbers:**

| item | value | source |
|---|---|---|
| stage platform | 9.0 × 4.5 m, 0.30 m high | height: Zettl pp. 346-347 (chairs "on a platform (anywhere from 6 to 12 inches high)" so the cameras shoot "at eye level"), 12 in taken; footprint: assumption |
| back flats | at y 4.5-4.7, 3.05 m high | Zettl p. 189 ("the average television scenery is 10 feet high") |
| furniture to the wall | ≥ 2.0 m (the chairs are at y 2.3 and 2.5) | Zettl p. 349 ("at least six feet (roughly two meters) from the set wall") |
| chairs | 0.6 × 0.6 m, seat 0.45 m, close together | assumption; Zettl pp. 353-354 and 427 ("smaller and simpler chairs … closer together") |
| low table | 0.9 × 0.45 m, 0.40 m high, in front of the seated speakers | assumption |
| plant | upstage right, out of every camera's shot | Zettl p. 426 (the rubber plant is "in the way") |
| audience | 10 × 5.5 m, 6 rows, front row at y −4.5 | assumption; front rows draw reactions (Grindstaff p. 127) |
| camera heights | 1.5-1.6 m; rev 2.0 m | Zettl p. 62 (pedestal "about 6½ feet (approximately 2m)" up, "about 4 feet (approximately 1.20m)" down); eye level of the seated speakers (Character 2's eyes at 1.56 m) |
| camera numbering | 1, 2, 3 left to right | Zettl p. 454 (15.35) |
| the plan's logic | the outer cameras cross-shoot, the centre camera holds the group | Zettl pp. 426-427 (15.20c, d: "from the extreme left … over-the-shoulder shot from the host to the guest"; "cross-shoot with the other camera … a reverse-angle shot of the host"); Katz pp. 130-133 (the triangle, "the middle camera always obtains the two-shot", p. 133) |
| the house reverse | its own camera | blueprint §16.4; Zettl p. 470 (a third camera "can get reaction shots from the audience") |
| lead placement | the lead at one side of the seated speakers, screen-left | Zettl p. 271; p. 274 (10.20: "Keep the closeup of the host on the left side of the screen"); R50 ST-2 |
| people | Character 1 1.78 m standing; Character 2 1.85 m seated; Character 3 1.65 m seated | assumption; "Character 3" is a placeholder for the second seated speaker |

What Zettl and Katz provide toward the three-camera plan:
- Zettl's figures give the **two-camera cross-shoot** two-person set (15.20), the numbering (15.35) and the third camera
  for reactions (p. 470).
- Katz gives the three-camera triangle with the centre on the two-shot (figs. 6.7-6.11, pp. 130-133).
- The preset combines them. Zettl has no chapter on such a set (R49 §7.8). R50 ST-15's "figure numbers to be filled in"
  are therefore Zettl 10.18-10.20, 15.17, 15.20a-e and 15.35, plus Katz figs. 6.7-6.11.

**Staging.** All three stand on the platform (`base_z` 0.30).

| person | position | facing | posture | body heights above the floor |
|---|---|---|---|---|
| Character 1 (mark `lead`) | (−1.3, 1.5) | 0°, across to the seated speakers | standing | crown 2.08, eyes 1.97, shoulders 1.77, belt 1.40 |
| Character 2 (`seat_1`) | (0.2, 2.3) | 200°, toward Character 1 | seated | crown 1.67, eyes 1.56, shoulders 1.34, lap 0.80 |
| Character 3 (`seat_2`) | (1.5, 2.5) | 205° | seated | — |

**The cameras' defaults**, solved by the prototype and written into the record, at 4:3:

| cam | position (x, y, h) | lens | hfov / vfov | pan / tilt | what the layout says | the plan says |
|---|---|---|---|---|---|---|
| 1 | (−3.20, −2.20, 1.50) | 102 mm | 7.2° / 5.4° | 53.6° / −0.5° | Character 2 only: MCU, head at (0.594, 0.304), headroom 0.095, **front** (rel 33°), looks screen-left, 5.64 m | Character 2's single (cross from the left) |
| 2 | (0.00, −3.60, 1.60) | 19.7 mm | 36.0° / 27.4° (16:9: 46.8°) | 90.3° / −5.0° | all three, LS; heads at u 0.112, 0.560, 0.888 (16:9: 0.209, 0.545, 0.791); Character 1 shows the right side, the seated speakers their left; depth order Character 1, Character 2, Character 3; Character 3's feet hidden by the low table | the cover shot / three-shot, the lead screen-left |
| 3 | (3.25, −1.50, 1.50) | 103 mm | 7.1° / 5.3° | 145.9° / 3.9° | Character 1 only: MCU, head at (0.402, 0.301), headroom 0.092, **front** (rel −33°), looks screen-right, 5.47 m | the lead's reverse-angle single, looking right (10.20) |
| rev | (3.80, 0.40, 2.00) | 17 mm | 41.3° / 31.5° | −118° / −6° | the audience area's centre in frame; no one on stage in frame | the house reverse |

- Cameras 1 and 3 are a **matched pair**: one framing (MCU); lenses 102 and 103 mm; subject distances 5.64 and
  5.47 m; sight lines 33° off each lens. Camera 3 was placed by solving for this; at its first guess the lenses
  differed by about 14 %.
- All four cameras are on one side of the Character 1-Character 2 line (`line_side` = −1).
- **Named framings solved from camera 1 on Character 2:**

  | XCU | CU | MCU | MS | MLS | LS | ELS |
  |---|---|---|---|---|---|---|
  | 273 mm (beyond the zoom) | 131 | 102 | 56 | 54 | 32.5 | 9 mm (beyond the zoom) |

  With a fixed 50 mm lens, CU puts the camera at (−1.10, 0.58), 2.16 m from Character 2 and on the same side of the line.
- **"Two-shot of Character 1 and Character 2"** from camera 2 at MS: they are 2.2 m apart, so the MS widens to the margins.
  - Result: 31.0 mm, pan 96.2°, tilt −1.8°.
  - Character 1's head is at (0.154, 0.167) and reads MLS. Character 2's head is at (0.846, 0.424) and reads LS, with headroom
    0.36. Character 3 is out of frame.
  - This is the standing-lead finding of §1.8.
- **"OTS on Character 2 over Character 1's shoulder"** fails from camera 1, where Character 1 is 10° off the bearing to Character 2: "Character 1 is not
  a foreground shoulder from camera 1: use ots_position()".
  - `ots_position` gives (−1.90, 0.50, 1.55). The solve there is 50.3 mm, pan 42.6°, tilt −2.2°.
  - Character 2's head is at (0.640, 0.301), MCU, front (rel 21°), face clear.
  - Character 1's body fills the frame's left edge, 1.24 m from the lens, with Character 1's head above the frame: an over-the-hip.
  - Raised to Character 1's shoulder height, the camera keeps Character 1's head out of frame (Character 1's shoulder point is at v −0.11)
    while it looks down at the seated Character 2.
- **Push-in on Character 2**, MS to CU over 72 frames (3 s), from camera 1:
  - As a zoom: 56.4 to 130.8 mm. Peaks: 0.64 stops/s of zoom, 1.1°/s of tilt.
  - As a dolly at 56.4 mm (MS to MCU): it ends 3.1 m from Character 2. Peak travel is 1.35 m/s, which is fast for a pedestal.
  - No book gives a speed limit, so R50's move rules (Katz chs. 17-19) are still pending.

---

## 6. The checks: what each needs

| check | inputs | function | params |
|---|---|---|---|
| 180-degree line, plan (ST-3, SW-15) | the two speakers' places; the previous and next cameras' x, y | `same_side(a, b, prev, next)`, from `line_side` (the sign of the cross product) | none (Katz p. 130; Zettl pp. 270-272) |
| 180-degree line, screen (SW-15) | the two layouts | `screen_order_kept(lay1, lay2, a, b)`: True/False when both people are in both frames, None otherwise (then the plan test decides) | none |
| inside the semicircle (ST-3) | a camera, the line, the house side | `line_side(a, b, cam) == line_side(a, b, house_point)` | none |
| matched pair (ST-6) | both setups, both subjects | `matched_pair()`: the read-back framing equal; the lens within ±10 %; the lens-to-eye distance within ±10 %; the sight-line angle off the lens within 10° | the tolerances are **assumptions** (S&B pp. 33-34 via R49 §2.9; Katz pp. 176, 179 give the rule, not a number) |
| headroom | the layout record, the code | `headroom_ok(rec, code)` against the band (§3) | **assumption** (Zettl p. 78; Katz p. 124) |
| lead room / nose room | the layout record | `leadroom_ok(rec)`: the head off centre away from the person's look by `0.17·|sin rel|` ± 0.08; centred when the person looks into the lens | **assumption** (Zettl p. 74: "The more profile the performer turns, the more space you must leave in front of [the performer]"; a speaker into the camera goes to screen-centre) |
| zoom range (new) | the solved f_mm, the camera's `zoom_mm` | not in the prototype; refuse outside [17, 170] with "dolly in" (the fixed-lens solve) | Zettl p. 34 (17-170 mm); p. 43 (range extenders) |
| face hidden / OTS valid | the layout | `face_hidden`, `occluded_by`; `frame_ots()` returns its reason | `OTS_U` = 0.64, assumption |
| move speed (Katz chs. 17-19) | the per-frame path | `rates(path)`: peak pan and tilt in °/s, zoom in stops/s, travel in m/s | pending (no number found); fps 24 (R48 §7) |

---

## 7. What a builder should copy

- **Copy as-is:** the conventions (§1.1), the Katz table and `point_at` (§2-§3), `project`, `side_shown`, the ray
  occlusion (`_solid`, `_local`, `_blocks`), `_newton`/`_lin`, `frame_single`, `frame_group`, `frame_ots`, the checks,
  `move` (a linear position, the short-way pan, a geometric zoom) and `rates`. They are pure and stdlib-only.
- **Split for the 300-line rule:** `stage/plan.py` (record and validation), `stage/project.py` (basis, project,
  `point_at`, layout), `stage/solve.py`, `stage/checks.py` and `stage/move.py`. The tests copy over unchanged and
  read the example record as a fixture.
- **Keep the solver in Python.** The Hub (switcher, rulebook) solves once per shot and stores the numbers in the
  shot's `setup`.
- **The projection is the sketch's guide.** Blueprint §20.2 makes the sketch
  request's `image_guide` "Step 11b's projection drawn as stick figures". The same layout is the control frame's figure
  placement (§17.1) and the stage view (§19.2).
- **Port only the projection to the web.** The Storyboard stage view and the control frame need per-frame drawing:
  `basis`, `project`, `point_at` and `move`/`ease`, about 60 lines of TS.
  - A shared-fixture contract test runs the same three setups in both languages and compares `(u, v)` to 1e-9.
  - `tween.ts` then places each 2D figure at its projected feet point, scales it by the projected crown-to-feet
    height and mirrors it by `looks`. That replaces `home`'s flat line-up.
  - `tween.ts` already has the same cosine `ease`.
- **Do not copy:**
  - the prototype's lack of a zoom-range refusal;
  - its circle-as-square footprint for props;
  - a seated figure's MS/MLS distinction (§3);
  - the screen-box occlusion idea (§2).

## 8. Not known (recorded)

- Whether a box-figure projection reads well enough in the stage view. §19.7 says the Step 11b run on the server decides.
- The real dimensions of the set. Every footprint marked "assumption" is replaced from the stage picture or
  the chat message's words when the set is built (§14.1). The plan's numbers then come from those inputs, not from this example.
- Speed limits for moves (Katz chs. 17-19 are cited by §17.1 but not read here).
- Measured headroom and lead-room bands: the measurement tool, §11.6, applied to the approved plates.
- Whether the outer cameras' 100 mm singles at 5.5 m match the set's look. Zettl's zoom allows them; the plates
  decide.
