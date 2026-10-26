// The seven named poses of R48 §4 on the engine's 18-point body, and how the engine draws it.
// Points are in OpenPose order (the order `limbSeq` numbers from 1): nose, neck, right shoulder, elbow, wrist, left
// shoulder, elbow, wrist, right hip, knee, ankle, left hip, knee, ankle, right eye, left eye, right ear, left ear.
// Each point is [x, y] from 0 to 1 in the figure's box; the figure faces the viewer, so its right is the box's left.
// null: a point not seen (the engine skips it, `-1` in its subset). R48 does not record the engineer's coordinates;
// these are the build's.

export type Point = readonly [number, number] | null
export type Body = readonly Point[]

/** `upstream preprocessing/dwpose/util.py:78-80`: limbs as pairs of points, 1-based. */
export const LIMBS: readonly (readonly [number, number])[] = [[2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8], [2, 9], [9, 10],
  [10, 11], [2, 12], [12, 13], [13, 14], [2, 1], [1, 15], [15, 17], [1, 16], [16, 18], [3, 17], [6, 18]]

/** `util.py:82-84`: one colour per limb and per point. */
export const COLORS: readonly (readonly [number, number, number])[] = [[255, 0, 0], [255, 85, 0], [255, 170, 0], [255, 255, 0],
  [170, 255, 0], [85, 255, 0], [0, 255, 0], [0, 255, 85], [0, 255, 170], [0, 255, 255], [0, 170, 255], [0, 85, 255], [0, 0, 255],
  [85, 0, 255], [170, 0, 255], [255, 0, 255], [255, 0, 170], [255, 0, 85]]

/** `util.py:86`: only the first 17 limbs are drawn. */
export const DRAWN_LIMBS = 17
/** `util.py:76`: a limb is an ellipse this many pixels from its axis (cv2's half-axis). */
export const STICK = 4
/** `util.py:100`: the limb layer at 60 % before the points go on. */
export const LIMB_DIM = 0.6
/** `util.py:110`: a point is a filled circle of this radius. */
export const JOINT = 4
/** The figure's box, rem (80 px at a 20 px root), read in pixels at draw time. Strokes are fixed pixels:
 *  never scaled (R48 §4). */
export const BOX_REM = 4

/** A face from the nose: eyes and ears, `turned` hides the far ear and draws the face to one side. */
const face = (nx: number, ny: number, turned = false): Point[] => turned
  ? [[nx - 0.02, ny - 0.02], [nx + 0.025, ny - 0.02], [nx - 0.07, ny - 0.01], null]
  : [[nx - 0.025, ny - 0.02], [nx + 0.025, ny - 0.02], [nx - 0.06, ny - 0.01], [nx + 0.06, ny - 0.01]]

/** Legs from the hips down: right knee and ankle, left knee and ankle. */
type Legs = readonly [Point, Point, Point, Point]
const straight: Legs = [[0.44, 0.74], [0.44, 0.93], [0.56, 0.74], [0.56, 0.93]]

const body = (nose: [number, number], neck: [number, number], arms: readonly Point[], hips: readonly Point[], legs: Legs, turned = false): Body =>
  [nose, neck, arms[0]!, arms[1]!, arms[2]!, arms[3]!, arms[4]!, arms[5]!, hips[0]!, legs[0], legs[1], hips[1]!, legs[2], legs[3], ...face(nose[0], nose[1], turned)]

const HIPS = [[0.44, 0.55], [0.56, 0.55]] as const
const DOWN = [[0.4, 0.26], [0.37, 0.41], [0.36, 0.55], [0.6, 0.26], [0.63, 0.41], [0.64, 0.55]] as const

export const POSES: Record<string, Body> = {
  stand: body([0.5, 0.13], [0.5, 0.25], DOWN, HIPS, straight),
  sit: body([0.5, 0.24], [0.5, 0.36], [[0.4, 0.37], [0.37, 0.5], [0.43, 0.62], [0.6, 0.37], [0.63, 0.5], [0.57, 0.62]],
    [[0.44, 0.64], [0.56, 0.64]], [[0.39, 0.72], [0.39, 0.93], [0.61, 0.72], [0.61, 0.93]]),
  walk_step: body([0.5, 0.13], [0.5, 0.25], [[0.4, 0.26], [0.42, 0.41], [0.47, 0.54], [0.6, 0.26], [0.61, 0.4], [0.62, 0.54]],
    HIPS, [[0.4, 0.73], [0.33, 0.92], [0.59, 0.73], [0.66, 0.9]]),
  turn: body([0.55, 0.13], [0.51, 0.25], [[0.44, 0.26], [0.42, 0.41], [0.42, 0.55], [0.58, 0.26], [0.6, 0.41], [0.61, 0.55]],
    [[0.47, 0.55], [0.55, 0.55]], [[0.47, 0.74], [0.47, 0.93], [0.55, 0.74], [0.56, 0.93]], true),
  point: body([0.5, 0.13], [0.5, 0.25], [[0.4, 0.26], [0.27, 0.26], [0.13, 0.25], [0.6, 0.26], [0.63, 0.41], [0.64, 0.55]], HIPS, straight),
  arms_raised: body([0.5, 0.15], [0.5, 0.27], [[0.4, 0.28], [0.33, 0.16], [0.3, 0.05], [0.6, 0.28], [0.67, 0.16], [0.7, 0.05]], HIPS, straight),
  hand_to_face: body([0.5, 0.13], [0.5, 0.25], [[0.4, 0.26], [0.36, 0.39], [0.47, 0.19], [0.6, 0.26], [0.63, 0.41], [0.64, 0.55]], HIPS, straight),
}

export const rgb = ([r, g, b]: readonly [number, number, number], k = 1): string =>
  `rgb(${Math.round(r * k)}, ${Math.round(g * k)}, ${Math.round(b * k)})`

// ---------------------------------------------------------------- hands and face
// The engine draws, after the body, both hands of 21 points (OpenPose order: wrist 0, thumb 1-4, index 5-8, middle
// 9-12, ring 13-16, little 17-20) and the face's 68 points (iBUG order: jaw 0-16, brows 17-26, nose 27-35, eyes 36-47,
// mouth 48-67). One hand template and one face template, placed on each pose's body; these coordinates are the build's.

export type Full = { body: Body; hands: readonly [readonly Point[], readonly Point[]]; face: readonly Point[] }

/** The hand, wrist at 0, the forearm's direction along x, the middle fingertip (12) at 1; y across the palm. */
const HAND: readonly (readonly [number, number])[] = [[0, 0],
  [0.2, -0.2], [0.38, -0.32], [0.52, -0.42], [0.65, -0.5],
  [0.45, -0.15], [0.65, -0.17], [0.8, -0.18], [0.93, -0.19],
  [0.47, 0], [0.68, 0], [0.85, 0], [1, 0],
  [0.45, 0.13], [0.64, 0.14], [0.79, 0.15], [0.91, 0.16],
  [0.4, 0.25], [0.55, 0.28], [0.67, 0.3], [0.77, 0.32]]
/** The hand's length (wrist to middle fingertip) against the forearm's (elbow to wrist). */
export const HAND_LENGTH = 0.45

/** `upstream util.py:118-119`: a hand's 20 edges. */
export const HAND_EDGES: readonly (readonly [number, number])[] = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8],
  [0, 9], [9, 10], [10, 11], [11, 12], [0, 13], [13, 14], [14, 15], [15, 16], [0, 17], [17, 18], [18, 19], [19, 20]]
/** `util.py:132`, `:139`, `:152`: an edge 2 px thick, a hand point radius 4 in (0, 0, 255), a face point radius 3 white. */
export const HAND_STROKE = 2
export const HAND_POINT = 4
export const HAND_COLOR = [0, 0, 255] as const
export const FACE_POINT = 3
export const FACE_COLOR = [255, 255, 255] as const
/** `util.py:10`: a point at or under this (of the canvas, 0-1) is not drawn. */
export const EPS = 0.01

/** `util.py:132`: edge k in HSV (k / 20, 1, 1), as 0-255 RGB. */
export function edgeColor(k: number): [number, number, number] {
  const h = (k / HAND_EDGES.length) * 6
  const f = h - Math.floor(h)
  const v = [[1, f, 0], [1 - f, 1, 0], [0, 1, f], [0, 1 - f, 1], [f, 0, 1], [1, 0, 1 - f]][Math.floor(h) % 6]!
  return [Math.round(v[0]! * 255), Math.round(v[1]! * 255), Math.round(v[2]! * 255)]
}

const arc = (n: number, f: (k: number) => readonly [number, number]) => Array.from({ length: n }, (_, k) => f(k))
/** The face: nose tip (30) at 0, the eye centres at (±1, -0.8), y down. */
const FACE: readonly (readonly [number, number])[] = [
  ...arc(17, i => { const t = Math.PI - (i * Math.PI) / 16; return [1.9 * Math.cos(t), -0.9 + 2.8 * Math.sin(t)] }),
  ...arc(5, k => [-1.7 + k * 0.35, -1.5 - 0.25 * Math.sin((Math.PI * k) / 4)]),
  ...arc(5, k => [0.3 + k * 0.35, -1.5 - 0.25 * Math.sin((Math.PI * (4 - k)) / 4)]),
  [0, -0.9], [0, -0.6], [0, -0.3], [0, 0],
  [-0.45, 0.25], [-0.22, 0.32], [0, 0.35], [0.22, 0.32], [0.45, 0.25],
  [-1.45, -0.8], [-1.15, -0.95], [-0.85, -0.95], [-0.55, -0.8], [-0.85, -0.65], [-1.15, -0.65],
  [0.55, -0.8], [0.85, -0.95], [1.15, -0.95], [1.45, -0.8], [1.15, -0.65], [0.85, -0.65],
  [-0.8, 0.9], [-0.5, 0.75], [-0.2, 0.7], [0, 0.73], [0.2, 0.7], [0.5, 0.75], [0.8, 0.9], [0.5, 1.1], [0.2, 1.18], [0, 1.2],
  [-0.2, 1.18], [-0.5, 1.1],
  [-0.65, 0.9], [-0.25, 0.88], [0, 0.88], [0.25, 0.88], [0.65, 0.9], [0.25, 0.92], [0, 0.92], [-0.25, 0.92],
]
/** A turned face is squeezed to this across. */
export const TURN_SQUEEZE = 0.6
/** The inner lips (`FACE` 60-67), the upper ones (61-63) and the lower (65-67). */
export const UPPER_LIP = [61, 62, 63] as const
export const LOWER_LIP = [65, 66, 67] as const

/** One hand on the body: point 0 on the wrist, laid along elbow to wrist; `side` mirrors the palm (the left hand). */
function hand(elbow: Point, wrist: Point, side: 1 | -1): Point[] {
  if (!elbow || !wrist) return HAND.map(() => null)
  const [dx, dy] = [(wrist[0] - elbow[0]) * HAND_LENGTH, (wrist[1] - elbow[1]) * HAND_LENGTH]
  return HAND.map(([u, v]) => [wrist[0] + u * dx - side * v * dy, wrist[1] + u * dy + side * v * dx] as const)
}

/** The face on the body: its nose tip on the nose, its eye centres at the height of the body's eyes (points 15 and 16)
 *  and as far apart; in `turn` squeezed to 60 % across and moved to the eyes' middle, toward the far side. */
function faceOn(b: Body, turned: boolean): Point[] {
  const [nose, re, le] = [b[0], b[14], b[15]]
  if (!nose || !re || !le) return FACE.map(() => null)
  const sy = ((re[1] + le[1]) / 2 - nose[1]) / -0.8
  const sx = turned ? sy * TURN_SQUEEZE : Math.abs(le[0] - re[0]) / 2
  const shift = turned ? (re[0] + le[0]) / 2 - nose[0] : 0
  return FACE.map(([u, v]) => [nose[0] + shift + sx * u, nose[1] + sy * v] as const)
}

/** Each of the seven poses whole: the 18-point body, two hands of 21, the face of 68. */
export const FULL: Record<string, Full> = Object.fromEntries(Object.entries(POSES).map(([name, b]) => [name, {
  body: b,
  hands: [hand(b[3]!, b[4]!, 1), hand(b[6]!, b[7]!, -1)] as const,
  face: faceOn(b, name === 'turn'),
}]))
