// The figures at a moment of the script, pure. A character's keyframes in a shot are its pose
// events there, by start; at a keyframe it is in that pose; between two, every point moves with a sine ease-in-out;
// before its first it holds it, after its last it holds that. A shot never tweens from the shot before (a cut): with
// no keyframe in the shot it holds its last pose earlier in the scene, else stand. Through its own lines it holds the
// pose of their start and eases only after them (`held`). Its mouth opens only inside its own
// lines, every other 200 ms from the line's start. Each cast member stands at its context `home` (0-100, left to
// right), else at (i + 1) / (n + 1) in cast order, members too close kept GAP apart; the place maps into
// an inset range so every pose is whole on the stage (`onStage`). Times are milliseconds from the script's start.
import type { Line, Pose, Scene, Script, Shot } from './api'
import { EPS, FULL, JOINT, LOWER_LIP, UPPER_LIP, type Full, type Point } from './poses'

/** The mouth's beat: open, then closed, each this long. */
export const MOUTH_MS = 200
/** How far the inner lips open, of the mouth's width (points 48 to 54). */
export const MOUTH_OPEN = 0.35
const DEFAULT = 'stand'

/** Sine ease-in-out: e(0) = 0, e(0.5) = 0.5, e(1) = 1. */
export const ease = (u: number): number => (1 - Math.cos(Math.PI * u)) / 2

const same = (a: string, b: string) => a.toLocaleLowerCase() === b.toLocaleLowerCase()
const full = (pose: string): Full => FULL[pose] ?? FULL[DEFAULT]!

function lerp(a: Point, b: Point, e: number, u: number): Point {
  if (!a || !b) return u < 0.5 ? a : b               // a point missing in one: from the nearer keyframe
  return [a[0] + (b[0] - a[0]) * e, a[1] + (b[1] - a[1]) * e]
}

const mixAll = (a: readonly Point[], b: readonly Point[], e: number, u: number) => a.map((p, i) => lerp(p, b[i] ?? null, e, u))

/** Every point of `a` toward `b` by the eased `u`. */
export function mix(a: Full, b: Full, u: number): Full {
  const e = ease(u)
  return { body: mixAll(a.body, b.body, e, u), hands: [mixAll(a.hands[0], b.hands[0], e, u), mixAll(a.hands[1], b.hands[1], e, u)],
    face: mixAll(a.face, b.face, e, u) }
}

/** The character's keyframes in a shot, by time. */
export const keyframes = (shot: Shot, who: string): Pose[] =>
  shot.events.filter((e): e is Pose => e.kind === 'pose' && same(e.character, who)).sort((a, b) => a.start_ms - b.start_ms)

/** The shot holding `t` (a cut's instant belongs to the shot it starts), with its scene; the last shot at the end. */
export function shotAt(script: Script, t: number): { scene: Scene; shot: Shot; k: number } | null {
  let last: { scene: Scene; shot: Shot; k: number } | null = null
  for (const scene of script.scenes) {
    for (const [k, shot] of scene.shots.entries()) {
      last = { scene, shot, k }
      if (t >= shot.start_ms && t < shot.end_ms) return last
    }
  }
  return last
}

/** After the character's line (or run) ends, a keyframe inside it or at its end is eased toward over at most this long. */
export const AFTER_MS = 500
type Key = { t: number; full: Full; name: string | null }

/** The keys at `t`: a key's own pose at its time, the eased mix between two, the first before, the last after. */
function keyAt(keys: readonly Key[], t: number): Key {
  if (t <= keys[0]!.t) return { ...keys[0]!, t }
  for (let i = 0; i + 1 < keys.length; i++) {
    const [a, b] = [keys[i]!, keys[i + 1]!]
    if (t < b.t) {
      if (t === a.t || (a.name !== null && a.name === b.name)) return { ...a, t }
      return { t, full: mix(a.full, b.full, (t - a.t) / (b.t - a.t)), name: null }
    }
  }
  return { ...keys.at(-1)!, t }
}

/** The character's lines in the shot by time, as runs [start, end]: a line starting at the one before's end joins it. */
function runs(shot: Shot, who: string): [number, number][] {
  const out: [number, number][] = []
  const mine = shot.events.filter((e): e is Line => e.kind === 'line' && same(e.speaker, who))
  for (const ln of mine.sort((a, b) => a.start_ms - b.start_ms)) {
    const last = out.at(-1)
    if (last && last[1] === ln.start_ms) last[1] = ln.end_ms
    else out.push([ln.start_ms, ln.end_ms])
  }
  return out
}

/** Inside each of its runs the character holds the pose at its start, whatever the keys inside it or at its end; the
 *  last of those is eased toward from the run's end over the time to the next key or AFTER_MS, whichever is shorter. */
function held(shot: Shot, who: string, keys: Key[]): Key[] {
  for (const [s, e] of runs(shot, who)) {
    const inside = keys.filter(x => x.t > s && x.t <= e)
    const start = keyAt(inside.length < keys.length ? keys.filter(x => !inside.includes(x)) : keys, s)
    const rest = keys.filter(x => x.t < s || x.t > e)
    const next = rest.find(x => x.t > e)
    const gap = next ? next.t - e : Infinity
    const last = inside.at(-1)
    const tail = last && gap > AFTER_MS && last.name !== start.name ? [{ ...last, t: e + AFTER_MS }] : []
    keys = [...rest, { ...start, t: s }, { ...start, t: e }, ...tail].sort((a, b) => a.t - b.t)
  }
  return keys
}

/** The character's pose at `t` in `shot`, before any mouth. */
export function poseAt(scene: Scene, k: number, t: number, who: string): Full {
  const shot = scene.shots[k]!
  const keys = keyframes(shot, who)
  if (keys.length === 0) {
    for (let j = k - 1; j >= 0; j--) {
      const earlier = keyframes(scene.shots[j]!, who)
      if (earlier.length > 0) return full(earlier.at(-1)!.pose)
    }
    return full(DEFAULT)
  }
  return keyAt(held(shot, who, keys.map(p => ({ t: p.start_ms, full: full(p.pose), name: p.pose }))), t).full
}

/** Whether the character's mouth is open at `t`: inside one of its own lines, on the first 200 ms of every 400 from its start. */
export function mouthOpen(script: Script, t: number, who: string): boolean {
  for (const scene of script.scenes) for (const shot of scene.shots) for (const e of shot.events) {
    if (e.kind === 'line' && same((e as Line).speaker, who) && t >= e.start_ms && t < e.end_ms) {
      return Math.floor((t - e.start_ms) / MOUTH_MS) % 2 === 0
    }
  }
  return false
}

/** The face with its inner lips opened by MOUTH_OPEN of the mouth's width. */
export function opened(f: Full): Full {
  const [l, r] = [f.face[48], f.face[54]]
  if (!l || !r) return f
  const half = (Math.hypot(r[0] - l[0], r[1] - l[1]) * MOUTH_OPEN) / 2
  const face = f.face.map((p, i): Point => {
    if (!p) return p
    if ((UPPER_LIP as readonly number[]).includes(i)) return [p[0], p[1] - half]
    if ((LOWER_LIP as readonly number[]).includes(i)) return [p[0], p[1] + half]
    return p
  })
  return { ...f, face }
}

/** The farthest any point of any pose in FULL lies from its box's centre line, of the box. */
export const REACH: number = Math.max(...Object.values(FULL).flatMap(f => [...f.body, ...f.hands[0], ...f.hands[1], ...f.face])
  .map(p => (p ? Math.abs(p[0] - 0.5) : 0)))

/** A figure's centre in pixels for place `x` (0-1) on a stage `w` wide, its box `box` px: home 0
 *  puts the farthest-reaching point JOINT px past paint's drop line (EPS of the width), so it is drawn and its disc is
 *  inside; home 1 the same from the right; 0.5 the centre. */
export function onStage(x: number, w: number, box: number): number {
  const m = REACH * box + Math.max(JOINT, EPS * w + JOINT)
  return m + x * (w - 2 * m)
}

/** Where each of the scene's cast stands, 0-1 across, in cast order: the context's `home` / 100, else (i + 1) / (n + 1);
 *  members with one place set GAP apart around it, then, left to right (ties in cast order), each at
 *  least GAP right of the one before (from 0) and, if the last passes 1, at least GAP left of the one after (from 1). */
export function places(script: Script, cast: readonly string[]): number[] {
  const members = script.version === 2 ? script.context?.cast ?? [] : []
  const n = cast.length
  const base = cast.map((who, i) => {
    const home = members.find(m => same(m.name, who))?.home
    return home === undefined ? (i + 1) / (n + 1) : home / 100
  })
  if (n < 2) return base
  const gap = Math.min(0.25, 1 / (n - 1))
  const xs = base.map((p, i) => {
    const group = base.flatMap((q, j) => (q === p ? [j] : []))
    return p + (group.indexOf(i) - (group.length - 1) / 2) * gap
  })
  const order = xs.map((_, i) => i).sort((a, b) => xs[a]! - xs[b]! || a - b)
  order.forEach((i, k) => { xs[i] = k === 0 ? Math.max(0, xs[i]!) : Math.max(xs[i]!, xs[order[k - 1]!]! + gap) })
  if (xs[order.at(-1)!]! > 1) {
    for (let k = n - 1; k >= 0; k--) {
      const i = order[k]!
      xs[i] = k === n - 1 ? 1 : Math.min(xs[i]!, xs[order[k + 1]!]! - gap)
    }
  }
  return xs
}

export type Figure = { who: string; x: number; full: Full }

/** The stage at `t`: each cast member of the scene playing then, in cast order, at its place, in its pose. */
export function stageAt(script: Script, t: number): Figure[] {
  const at = shotAt(script, t)
  if (!at) return []
  const xs = places(script, at.scene.cast)
  return at.scene.cast.map((who, i) => {
    const f = poseAt(at.scene, at.k, t, who)
    return { who, x: xs[i]!, full: mouthOpen(script, t, who) ? opened(f) : f }
  })
}
