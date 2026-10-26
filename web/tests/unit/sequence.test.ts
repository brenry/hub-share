// The sequence's pure helpers (Stage 11): time to item, the tracks' layout, gap index, reorder, trim
// clamps (frames, 10 ms for a sound), edges, splits, track 2's places, the saved length, the seek.
import { describe, expect, it } from 'vitest'
import { bedLine, clock, endOf, gapAt, insert, kept, lefts, length, locate, movedTo, msOf, place, reorder, secs, seekTime, spec, split, starts, step, timeOf, total, trimEdge, trimIn, trimOut, under, whole, widths, withBed, type Item } from '../../src/modules/sequence/seq'

const item = (over: Partial<Item>): Item => ({ kind: 'clip', id: 'clips/x.mp4', in: 0, out: 124, w: 960, h: 544, fps: 24, frames: 124, seconds: 5.17, kept: 5.17, audio: true, url: '/files/x', ...over })
// 24 fps: frames 0–124 whole (5.17 s), 24–72 (2 s); 30 fps: 0–90 (3 s).
const A = item({ id: 'clips/2026-10-14/a.mp4' })
const B = item({ id: 'clips/2026-10-14/b.mp4', in: 24, out: 72 })
const C = item({ id: 'clips/2026-10-14/c.mp4', out: 90, fps: 30, frames: 90 })
/** A 20 s sound kept from 1 s to 16 s: milliseconds as frames. */
const S = item({ kind: 'sound', id: 'sounds/a.wav', in: 1000, out: 16000, fps: 1000, frames: 20000, w: 0, h: 0 })
const LIST = [A, B, C]

describe('time', () => {
  it('kept seconds, starts and the total', () => {
    expect(kept(B)).toBe(2)
    expect(starts(LIST)).toEqual([0, 124 / 24, 124 / 24 + 2])
    expect(total(LIST)).toBeCloseTo(124 / 24 + 5, 9)
    expect(total([])).toBe(0)
  })

  it('a seek to frame n goes to (n + 0.5) / fps', () => {
    expect(seekTime(0, 24)).toBeCloseTo(0.5 / 24, 12)
    expect(seekTime(24, 24)).toBeCloseTo(24.5 / 24, 12)
    expect(seekTime(89, 30)).toBeCloseTo(89.5 / 30, 12)
  })

  it('the item and frame at a sequence time', () => {
    expect(locate([], 1)).toBeNull()
    expect(locate(LIST, 0)).toEqual({ index: 0, frame: 0 })
    expect(locate(LIST, 1)).toEqual({ index: 0, frame: 24 })
    // the joint: the next item's in
    expect(locate(LIST, 124 / 24)).toEqual({ index: 1, frame: 24 })
    expect(locate(LIST, 124 / 24 + 1)).toEqual({ index: 1, frame: 48 })
    expect(locate(LIST, 124 / 24 + 2 + 1.5)).toEqual({ index: 2, frame: 45 })
    // past the end: the last frame of the last item; before the start: the first
    expect(locate(LIST, 1e6)).toEqual({ index: 2, frame: 89 })
    expect(locate(LIST, -3)).toEqual({ index: 0, frame: 0 })
  })

  it('a frame back to its sequence time, and one frame steps crossing the joints', () => {
    expect(timeOf(LIST, 1, 24)).toBeCloseTo(124 / 24, 12)
    expect(timeOf(LIST, 1, 30)).toBeCloseTo(124 / 24 + 6 / 24, 12)
    expect(locate(LIST, step(LIST, 0, 1))).toEqual({ index: 0, frame: 1 })
    expect(locate(LIST, step(LIST, timeOf(LIST, 0, 123), 1))).toEqual({ index: 1, frame: 24 })
    expect(locate(LIST, step(LIST, timeOf(LIST, 1, 24), -1))).toEqual({ index: 0, frame: 123 })
    expect(locate(LIST, step(LIST, timeOf(LIST, 2, 0), -1))).toEqual({ index: 1, frame: 71 })
    expect(step(LIST, 0, -1)).toBe(0)
    expect(step(LIST, timeOf(LIST, 2, 89), 1)).toBeCloseTo(total(LIST), 9)
    expect(step([], 3, 1)).toBe(0)
  })

  it('m:ss.f and seconds to two decimals', () => {
    expect(clock(0)).toBe('0:00.0')
    expect(clock(5.1666)).toBe('0:05.1')
    expect(clock(65.25)).toBe('1:05.2')
    expect(clock(600)).toBe('10:00.0')
    expect(secs(124 / 24)).toBe('5.17')
    expect(secs(3)).toBe('3')
  })
})

describe('the tracks', () => {
  it('tiles are as long as the seconds they keep, track 1 back to back on one time line', () => {
    expect(widths(LIST, 3)).toEqual([kept(A) * 3, 6, 9])
    expect(lefts(LIST, 3)).toEqual([0, kept(A) * 3, kept(A) * 3 + 6])
  })

  it('the gap under a time: the nearer side of an item', () => {
    expect(gapAt(LIST, -1)).toBe(0)
    expect(gapAt(LIST, 2.5)).toBe(0)
    expect(gapAt(LIST, 2.6)).toBe(1)
    expect(gapAt(LIST, kept(A) + 0.9)).toBe(1)
    expect(gapAt(LIST, kept(A) + 1.1)).toBe(2)
    expect(gapAt(LIST, 100)).toBe(3)
    expect(gapAt([], 3)).toBe(0)
  })

  it('reorder moves one item into a gap; insert puts new ones there', () => {
    const l = ['a', 'b', 'c', 'd']
    expect(reorder(l, 0, 4)).toEqual(['b', 'c', 'd', 'a'])
    expect(reorder(l, 0, 2)).toEqual(['b', 'a', 'c', 'd'])
    expect(reorder(l, 3, 0)).toEqual(['d', 'a', 'b', 'c'])
    expect(reorder(l, 2, 1)).toEqual(['a', 'c', 'b', 'd'])
    expect(reorder(l, 1, 1)).toEqual(l)
    expect(reorder(l, 1, 2)).toEqual(l)
    expect(reorder(l, 9, 0)).toEqual(l)
    expect(insert(l, 2, ['x', 'y'])).toEqual(['a', 'b', 'x', 'y', 'c', 'd'])
    expect(insert(l, 0, ['x'])).toEqual(['x', 'a', 'b', 'c', 'd'])
    expect(insert(l, 4, ['x'])).toEqual([...l, 'x'])
  })

  it('after a move the playhead goes to the moved item\'s start in the saved order', () => {
    // tile 3 to gap 0: the playhead at 0
    expect(movedTo(2, 0)).toBe(0)
    expect(starts(reorder(LIST, 2, 0))[movedTo(2, 0)]).toBe(0)
    // tile 1 to the end: after B (2 s) and C (3 s), not where the third item started before the move
    expect(movedTo(0, 3)).toBe(2)
    expect(starts(reorder(LIST, 0, 3))[movedTo(0, 3)]).toBeCloseTo(5, 9)
    expect(movedTo(2, 1)).toBe(1)
  })
})

describe('trims', () => {
  it('in stays from 0 to one frame before out; out from one after in to the clip\'s frames', () => {
    expect(trimIn(B, 30)).toMatchObject({ in: 30, out: 72 })
    expect(trimIn(B, 72)).toMatchObject({ in: 71 })
    expect(trimIn(B, -5)).toMatchObject({ in: 0 })
    expect(trimIn(B, 30.4)).toMatchObject({ in: 30 })
    expect(trimOut(B, 60)).toMatchObject({ in: 24, out: 60 })
    expect(trimOut(B, 24)).toMatchObject({ out: 25 })
    expect(trimOut(B, 500)).toMatchObject({ out: 124 })
  })

  it('a sound trims by 10 ms', () => {
    expect(trimIn(S, 1234)).toMatchObject({ in: 1230 })
    expect(trimOut(S, 16007)).toMatchObject({ out: 16010 })
    expect(trimIn(S, 16000)).toMatchObject({ in: 15990 })
    expect(trimOut(S, 25000)).toMatchObject({ out: 20000 })
  })

  it('an edge dragged by seconds: in or out, snapped; on track 2 the sound stays where it was heard', () => {
    expect(trimEdge(B, 'in', 0.5)).toMatchObject({ in: 36, out: 72 })
    expect(trimEdge(B, 'out', -1)).toMatchObject({ in: 24, out: 48 })
    expect(trimEdge(S, 'out', -1.003)).toMatchObject({ out: 15000 })
    const placed = { ...S, at: 3000 }
    expect(trimEdge(placed, 'in', 2)).toMatchObject({ in: 3000, at: 5000 })
    // never before the sequence's start
    expect(trimEdge({ ...S, at: 500 }, 'in', -5)).toMatchObject({ in: 500, at: 0 })
  })

  it('a split cuts strictly inside; the second part starts where the first ends', () => {
    expect(split(B, 48)).toEqual([{ ...B, out: 48 }, { ...B, in: 48 }])
    expect(split(B, 24)).toBeNull()
    expect(split(B, 72)).toBeNull()
    expect(split({ ...S, at: 2000 }, 6004)).toEqual([{ ...S, out: 6000, at: 2000 }, { ...S, in: 6000, at: 7000 }])
  })

  it('a save sends the id under its kind, in, out and `at` on track 2', () => {
    expect(spec(B)).toEqual({ clip: B.id, in: 24, out: 72 })
    expect(spec({ kind: 'clip', id: B.id, in: 0 })).toEqual({ clip: B.id, in: 0 })
    expect(spec({ ...S, at: 250 })).toEqual({ sound: S.id, in: 1000, out: 16000, at: 250 })
  })

  it('a dropped item is whole: a clip by the frames the drag carried, a sound by its seconds, else left to the hub', () => {
    expect(whole({ id: A.id, kind: 'clip', frames: 124 })).toEqual({ kind: 'clip', id: A.id, in: 0, out: 124 })
    expect(whole({ id: A.id })).toEqual({ kind: 'clip', id: A.id, in: 0 })
    expect(whole({ id: A.id, frames: 0 })).toEqual({ kind: 'clip', id: A.id, in: 0 })
    expect(whole({ id: S.id, kind: 'sound', seconds: 2.5 })).toEqual({ kind: 'sound', id: S.id, in: 0, out: 2500 })
    expect(whole({ id: S.id, kind: 'sound' })).toEqual({ kind: 'sound', id: S.id, in: 0 })
  })
})

describe('track 2 and the saved length', () => {
  const fx = (at: number, ms: number) => ({ ...S, in: 0, out: ms, at })
  it('an item placed over another goes right after it; the track stays in time order', () => {
    const list = [fx(1000, 2000), fx(5000, 1000)]
    expect(place(list, fx(0, 500), 500, 0, msOf)).toEqual({ list: [fx(0, 500), ...list], at: 0 })
    expect(place(list, fx(0, 500), 500, 2500, msOf).at).toBe(3000)
    expect(place(list, fx(0, 2500), 2500, 2000, msOf).at).toBe(6000)
    // moving item 0 itself does not collide with itself
    expect(place(list, list[0]!, 2000, 1500, msOf, 0)).toEqual({ list: [fx(1500, 2000), list[1]!], at: 1500 })
  })

  it('the item under a time, its end, and the length a save makes', () => {
    const t2 = [fx(1000, 2000), fx(5000, 1000)]
    expect(under(t2, 1.5)).toBe(0)
    expect(under(t2, 3)).toBe(-1)
    expect(endOf(t2[1]!)).toBe(6)
    expect(length(LIST, t2)).toBeCloseTo(total(LIST), 9)
    expect(length([], t2)).toBe(6)
    expect(length([], [])).toBe(0)
  })
})

describe('a bed under the voice', () => {
  const bed = { ...S, at: 250 }

  it('sets and clears the level, the fades and the duck, never writing a default', () => {
    const set = withBed(bed, { level: 0.5, fade_in: 1000, fade_out: 500, duck: true })
    expect(set).toEqual({ ...bed, level: 0.5, fade_in: 1000, fade_out: 500, duck: true })
    expect(withBed(set, { level: 1, fade_in: 0, fade_out: 0, duck: false })).toEqual(bed)
    expect(withBed(bed, { level: 1.5 })).toEqual({ ...bed, level: 1.5 })
    expect(Object.keys(withBed(bed, { duck: false }))).not.toContain('duck')
  })

  it('sends the keys it has on a save and keeps a split or trimmed bed\'s keys', () => {
    const set = withBed(bed, { level: 0.5, duck: true })
    expect(spec(set)).toEqual({ sound: S.id, in: 1000, out: 16000, at: 250, level: 0.5, duck: true })
    expect(spec(bed)).toEqual({ sound: S.id, in: 1000, out: 16000, at: 250 })
    const [a, b] = split(set, 8000)!
    expect([a.level, a.duck, b.level, b.duck]).toEqual([0.5, true, 0.5, true])
    expect(trimIn(set, 2000).duck).toBe(true)
  })

  it('says what is set in the tile\'s title', () => {
    expect(bedLine(bed)).toBe('')
    expect(bedLine({ level: 0.5, fade_in: 1000, fade_out: 500, duck: true })).toBe('50% · fade in 1 s · fade out 0.5 s · ducked')
    expect(bedLine({ level: 1, duck: true })).toBe('ducked')
    expect(bedLine({ level: 1.5 })).toBe('150%')
  })
})
