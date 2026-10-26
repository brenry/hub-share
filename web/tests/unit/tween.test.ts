// The figures between keyframes: every pose whole (18 body, 2 × 21 hand, 68 face points, each hand on
// its wrist); the sine ease; a keyframe's own pose at its time, the eased mix between two, the last held after; no
// tween across a cut; a point missing in one pose from the nearer keyframe; the mouth open only inside the character's
// own lines, every other 200 ms; places from `home`, else (i + 1) / (n + 1); a speaker still through the speaker's line or run,
// whatever the file holds; every pose whole on the stage at any place (REACH, onStage);
// members with one place or too close kept GAP apart, in order.
import { describe, expect, it } from 'vitest'
import example from '../../../tests/fixtures/script-1.json'
import type { Pose, Script } from '../../src/modules/director/api'
import { FULL, POSES, type Full, type Point } from '../../src/modules/director/poses'
import { paint } from '../../src/modules/director/Stage'
import { MOUTH_MS, REACH, ease, mix, mouthOpen, onStage, places, poseAt, stageAt } from '../../src/modules/director/tween'

const EXAMPLE = example as Script
const SEVEN = ['stand', 'sit', 'walk_step', 'turn', 'point', 'arms_raised', 'hand_to_face']
const kf = (id: string, at: number, pose: string, character = 'Character 7'): Pose =>
  ({ id, kind: 'pose', start_ms: at, end_ms: at + 1, character, pose })

/** One scene, two shots: s1 0-4000 with Character 7 stand at 0 and point at 2000; s2 4000-8000 with Character 7 sit at 4000. */
const SCRIPT: Script = { version: 2, context: { cast: [{ name: 'Character 7', home: 30 }, { name: 'Character 6' }] }, scenes: [{
  title: 'A', cast: ['Character 7', 'Character 6'], shots: [
    { start_ms: 0, end_ms: 4000, events: [kf('p1', 0, 'stand'), kf('p2', 2000, 'point'),
      { id: 'l1', kind: 'line', start_ms: 1000, end_ms: 1900, speaker: 'Character 6', words: 'Hello there.' }] },
    { start_ms: 4000, end_ms: 8000, events: [kf('p3', 5000, 'sit')] },
    { start_ms: 8000, end_ms: 9000, events: [] },
  ] }] }
const scene = SCRIPT.scenes[0]!
const near = (a: Point, b: Point) => {
  expect(a && b).toBeTruthy()
  expect(a![0]).toBeCloseTo(b![0], 9)
  expect(a![1]).toBeCloseTo(b![1], 9)
}
const sameFull = (a: Full, b: Full) => [...a.body, ...a.hands[0], ...a.hands[1], ...a.face].forEach((p, i) => {
  const q = [...b.body, ...b.hands[0], ...b.hands[1], ...b.face][i]!
  if (p === null || q === null) expect(p).toBe(q)
  else near(p, q)
})

describe('tween', () => {
  it('every one of the seven poses has 18 body, 2 x 21 hand and 68 face points, each hand on its wrist', () => {
    expect(Object.keys(FULL).sort()).toEqual([...SEVEN].sort())
    for (const name of SEVEN) {
      const f = FULL[name]!
      expect(f.body).toHaveLength(18)
      expect(f.hands.map(h => h.length)).toEqual([21, 21])
      expect(f.face).toHaveLength(68)
      near(f.hands[0][0]!, POSES[name]![4]!)
      near(f.hands[1][0]!, POSES[name]![7]!)
      if (name !== 'turn') near(f.face[30]!, POSES[name]![0]!)          // the nose tip on the nose
      else expect(Math.abs(f.face[30]![0] - POSES.turn![0]![0])).toBeLessThan(0.01)
      expect(f.face.every(p => p !== null)).toBe(true)
    }
  })

  it('eases with e(0) = 0, e(0.5) = 0.5, e(1) = 1', () => {
    expect(ease(0)).toBeCloseTo(0, 12)
    expect(ease(0.5)).toBeCloseTo(0.5, 12)
    expect(ease(1)).toBeCloseTo(1, 12)
    expect(ease(0.25)).toBeLessThan(0.25)
  })

  it('a keyframe at its time is exactly its pose; half-way between two the eased mix; the last held after', () => {
    sameFull(poseAt(scene, 0, 0, 'Character 7'), FULL.stand!)
    sameFull(poseAt(scene, 0, 2000, 'Character 7'), FULL.point!)
    const half = poseAt(scene, 0, 1000, 'Character 7')
    sameFull(half, mix(FULL.stand!, FULL.point!, 0.5))
    const [a, b, m] = [FULL.stand!.body[4]!, FULL.point!.body[4]!, half.body[4]!]
    expect(m[0]).toBeCloseTo((a[0] + b[0]) / 2, 9)
    const quarter = poseAt(scene, 0, 500, 'Character 7').body[4]!
    expect(quarter[0]).toBeCloseTo(a[0] + (b[0] - a[0]) * ease(0.25), 9)
    sameFull(poseAt(scene, 0, 3999, 'Character 7'), FULL.point!)
  })

  it('no tween across a cut: the shot holds its first keyframe from its start, an empty shot the last pose before', () => {
    sameFull(stageAt(SCRIPT, 4000)[0]!.full, FULL.sit!)
    sameFull(stageAt(SCRIPT, 4500)[0]!.full, FULL.sit!)
    sameFull(stageAt(SCRIPT, 8500)[0]!.full, FULL.sit!)
    sameFull(stageAt(SCRIPT, 8500)[1]!.full, FULL.stand!)
  })

  it('a point missing in one pose (turn\'s far ear) is drawn from the nearer keyframe', () => {
    expect(FULL.turn!.body[17]).toBeNull()
    expect(mix(FULL.stand!, FULL.turn!, 0.4).body[17]).toEqual(FULL.stand!.body[17])
    expect(mix(FULL.stand!, FULL.turn!, 0.6).body[17]).toBeNull()
  })

  it('the mouth is open only inside the character\'s own lines, alternating each 200 ms', () => {
    expect(mouthOpen(SCRIPT, 1000, 'Character 6')).toBe(true)
    expect(mouthOpen(SCRIPT, 1000 + MOUTH_MS - 1, 'Character 6')).toBe(true)
    expect(mouthOpen(SCRIPT, 1000 + MOUTH_MS, 'Character 6')).toBe(false)
    expect(mouthOpen(SCRIPT, 1000 + 2 * MOUTH_MS, 'Character 6')).toBe(true)
    expect(mouthOpen(SCRIPT, 1000, 'Character 7')).toBe(false)
    expect(mouthOpen(SCRIPT, 999, 'Character 6')).toBe(false)
    expect(mouthOpen(SCRIPT, 1900, 'Character 6')).toBe(false)
    const [open, shut] = [stageAt(SCRIPT, 1000)[1]!.full, stageAt(SCRIPT, 1200)[1]!.full]
    expect(open.face[66]![1] - open.face[62]![1]).toBeGreaterThan(shut.face[66]![1] - shut.face[62]![1])
    expect(open.face.slice(0, 60)).toEqual(shut.face.slice(0, 60))
  })

  it('a speaker holds the pose across the speaker\'s own line when a pose is asked at its end', () => {
    // As the Hub stores it: arms_raised at l1's start and end, the point asked at l1's end keyed 500 ms after it.
    const line = { id: 'l1', kind: 'line' as const, start_ms: 1000, end_ms: 3000, speaker: 'Character 7', words: 'Hi there.' }
    const one: Script = { version: 2, scenes: [{ title: 'A', cast: ['Character 7'], shots: [{ start_ms: 0, end_ms: 5000,
      events: [kf('p1', 0, 'stand'), kf('p2', 1000, 'arms_raised'), line, kf('p3', 3000, 'arms_raised'),
        kf('p4', 3500, 'point')] }] }] }
    const sc = one.scenes[0]!
    for (let t = 1000; t <= 3000; t += 100) sameFull(poseAt(sc, 0, t, 'Character 7'), FULL.arms_raised!)
    sameFull(poseAt(sc, 0, 3250, 'Character 7'), mix(FULL.arms_raised!, FULL.point!, 0.5))
    sameFull(poseAt(sc, 0, 3500, 'Character 7'), FULL.point!)
  })

  it('a speaker holds the line\'s start pose whatever the file holds inside it or at its end', () => {
    const sc = EXAMPLE.scenes[0]!                      // l1 4000-7642: p3 arms_raised at its start, p4 point at its end
    for (let t = 4000; t <= 7642; t += 91) sameFull(poseAt(sc, 0, t, 'Character 1'), FULL.arms_raised!)
    sameFull(poseAt(sc, 0, 7642, 'Character 1'), FULL.arms_raised!)
    sameFull(poseAt(sc, 0, 7642 + 250, 'Character 1'), mix(FULL.arms_raised!, FULL.point!, 0.5))
    sameFull(poseAt(sc, 0, 7642 + 500, 'Character 1'), FULL.point!)
    // Two lines back to back, one run: a keyframe at the first's end is held off until the run ends.
    const run: Script = { version: 2, scenes: [{ title: 'A', cast: ['Character 7'], shots: [{ start_ms: 0, end_ms: 6000,
      events: [kf('p1', 0, 'stand'), kf('p4', 1000, 'stand'), { id: 'l1', kind: 'line', start_ms: 1000, end_ms: 2000, speaker: 'Character 7', words: 'Hi.' },
        { id: 'l2', kind: 'line', start_ms: 2000, end_ms: 3000, speaker: 'Character 7', words: 'Hi.' }, kf('p2', 2000, 'sit'),
        kf('p3', 3200, 'point')] }] }] }
    const one = run.scenes[0]!
    for (let t = 1000; t <= 3000; t += 100) sameFull(poseAt(one, 0, t, 'Character 7'), FULL.stand!)
    sameFull(poseAt(one, 0, 3100, 'Character 7'), mix(FULL.stand!, FULL.point!, 0.5))   // 200 ms to p3: eased toward it
  })

  it('places from home and, without one, (i + 1) / (n + 1)', () => {
    expect(places(SCRIPT, ['Character 7', 'Character 6'])).toEqual([0.3, 2 / 3])
    expect(places(EXAMPLE, ['Character 1', 'Character 2'])).toEqual([0.3, 0.7])
    expect(places({ version: 1, scenes: [] }, ['A', 'B', 'C'])).toEqual([0.25, 0.5, 0.75])
    expect(stageAt(EXAMPLE, 0).map(f => [f.who, f.x])).toEqual([['Character 1', 0.3], ['Character 2', 0.7]])
  })

  it('at place 0 and 1 paint draws every point of every pose, each disc inside the canvas', () => {
    const all = (f: Full) => [...f.body, ...f.hands[0], ...f.hands[1], ...f.face].filter((p): p is readonly [number, number] => p !== null)
    const widest = Math.max(...Object.values(FULL).flatMap(f => all(f).map(p => Math.abs(p[0] - 0.5))))
    expect(REACH).toBe(widest)
    expect(REACH).toBeCloseTo(0.433, 3)
    for (const w of [320, 400, 597, 1600, 2560]) {
      const h = (w * 9) / 16
      for (const at of [0, 1]) for (const [name, f] of Object.entries(FULL)) {
        const arcs: [number, number, number][] = []
        const ctx = { fillRect() {}, beginPath() {}, fill() {}, ellipse() {}, moveTo() {}, lineTo() {}, stroke() {},
          arc(x: number, y: number, r: number) { arcs.push([x, y, r]) } } as unknown as CanvasRenderingContext2D
        paint(ctx, w, h, [{ who: 'A', x: at, full: f }])
        expect(arcs.length, `${name} at ${at}, ${w} wide: none dropped`).toBe(all(f).length)
        for (const [x, y, r] of arcs) {
          expect(x - r, `${name} at ${at}, ${w}`).toBeGreaterThanOrEqual(-1e-9)
          expect(x + r, `${name} at ${at}, ${w}`).toBeLessThanOrEqual(w + 1e-9)
          expect(y - r, `${name} at ${at}, ${w}`).toBeGreaterThanOrEqual(-1e-9)
          expect(y + r, `${name} at ${at}, ${w}`).toBeLessThanOrEqual(h + 1e-9)
        }
      }
      expect(onStage(0.5, w, h * 0.8)).toBe(w / 2)
    }
  })

  it('members with one place or too close stand GAP apart, in order; homes far enough apart unchanged', () => {
    const homes = (...hs: (number | undefined)[]): Script => ({ version: 2, scenes: [],
      context: { cast: hs.map((home, i) => ({ name: `M${i}`, ...(home === undefined ? {} : { home }) })) } })
    const cast = (n: number) => Array.from({ length: n }, (_, i) => `M${i}`)
    expect(places(homes(0, 0), cast(2))).toEqual([0, 0.25])
    expect(places(homes(100, 100), cast(2))).toEqual([0.75, 1])
    expect(places(homes(50, 50), cast(2))).toEqual([0.375, 0.625])
    expect(places(homes(50, 50, 50), cast(3))).toEqual([0.25, 0.5, 0.75])
    expect(places(homes(0, 2), cast(2))).toEqual([0, 0.25])
    expect(places(homes(2, 0), cast(2))).toEqual([0.25, 0])           // order kept: M1 at 0 stays left of M0
    expect(places(homes(30, 70), cast(2))).toEqual([0.3, 0.7])
    expect(places(EXAMPLE, ['Character 1', 'Character 2'])).toEqual([0.3, 0.7])
    expect(places(homes(50), cast(1))).toEqual([0.5])
    const five = places({ version: 1, scenes: [] }, cast(5))           // five without homes: evenly spread, in order
    expect(five).toEqual([0, 0.25, 0.5, 0.75, 1])
  })
})
