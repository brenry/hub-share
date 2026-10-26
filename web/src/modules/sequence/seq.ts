// Pure helpers of the sequence: frames and seconds, where a sequence time falls, the tracks' layout, the gap under a
// pointer, reorder, trims, splits and track 2's places. An item keeps frames `in` to `out` of its file (`out`
// exclusive); a sound counts its milliseconds as frames (`fps` 1000), so the same sums serve clips and sounds.
// Track 1 plays back to back; a track-2 item starts at `at` milliseconds of the sequence.

export type Kind = 'clip' | 'sound'
/** What the hub stores for one item (its id key is its kind); `at` on track 2 only, and there the bed's own keys
 * : `level` 0-2, `fade_in` / `fade_out` milliseconds, `duck` under track 1. */
export type Spec = { kind: Kind; id: string; in: number; out: number; at?: number; level?: number; fade_in?: number; fade_out?: number; duck?: boolean }
/** The bed's keys alone. */
export type Bed = Pick<Spec, 'level' | 'fade_in' | 'fade_out' | 'duck'>
export const BED_KEYS = ['level', 'fade_in', 'fade_out', 'duck'] as const
/** What a save sends of an item: `out` left out keeps it whole (the hub reads its frames or length). */
export type Put = Omit<Spec, 'out'> & { out?: number }
/** An item as GET `/one` draws it. */
export type Item = Spec & { w: number; h: number; fps: number; frames: number; seconds: number; kept: number; audio: boolean; url: string }
type Timed = { in: number; out: number; fps: number }
type Placed = Timed & { at?: number }

/** The seconds an item keeps, exactly (the hub's `kept` is rounded). */
export const kept = (it: Timed): number => (it.out - it.in) / it.fps

/** Where each item starts in the sequence, in seconds. */
export function starts(items: readonly Timed[]): number[] {
  const out: number[] = []
  let t = 0
  for (const it of items) { out.push(t); t += kept(it) }
  return out
}

export const total = (items: readonly Timed[]): number => items.reduce((t, it) => t + kept(it), 0)

/** A seek to frame n goes to the middle of the frame, so the decoder never lands on its neighbour. */
export const seekTime = (n: number, fps: number): number => (n + 0.5) / fps

const EPS = 1e-6

/** The item under sequence time `t` and the frame of its clip there. Past the end: the last frame of the last item. */
export function locate(items: readonly Timed[], t: number): { index: number; frame: number } | null {
  if (items.length === 0) return null
  const at = starts(items)
  let i = items.length - 1
  while (i > 0 && at[i]! > t + EPS) i--
  const it = items[i]!
  const f = it.in + Math.floor(Math.max(0, t - at[i]!) * it.fps + EPS)
  return { index: i, frame: Math.min(it.out - 1, Math.max(it.in, f)) }
}

/** The sequence time at which frame `frame` of item `index` shows. */
export function timeOf(items: readonly Timed[], index: number, frame: number): number {
  const it = items[index]
  if (!it) return 0
  return (starts(items)[index] ?? 0) + (frame - it.in) / it.fps
}

/** One frame of the current item later (`by` 1) or earlier (-1), crossing into the neighbour at an edge. */
export function step(items: readonly Timed[], t: number, by: 1 | -1): number {
  const here = locate(items, t)
  if (!here) return 0
  const it = items[here.index]!
  const f = here.frame + by
  if (f >= it.in && f < it.out) return timeOf(items, here.index, f)
  const j = here.index + by
  const nb = items[j]
  if (!nb) return by > 0 ? total(items) : 0
  return timeOf(items, j, by > 0 ? nb.in : nb.out - 1)
}

/** `m:ss.f` */
export function clock(seconds: number): string {
  const tenths = Math.floor(Math.max(0, seconds) * 10 + EPS)
  const m = Math.floor(tenths / 600)
  const s = Math.floor((tenths % 600) / 10)
  return `${m}:${String(s).padStart(2, '0')}.${tenths % 10}`
}

/** Seconds shown with two decimals at most: 5.17, 4.5, 3. */
export const secs = (s: number): string => String(Math.round(s * 100) / 100)

/** Rem per second of the tracks' three zoom levels. */
export const ZOOMS = { '1': 1.5, '2': 3, '4': 6 } as const
export type Zoom = keyof typeof ZOOMS

/** Tile widths in rem, as long as the seconds each item keeps (both tracks are drawn on one time line). */
export const widths = (items: readonly Timed[], perSecond: number): number[] => items.map(it => kept(it) * perSecond)

/** Left edge of each track-1 tile in rem: where it starts. */
export const lefts = (items: readonly Timed[], perSecond: number): number[] => starts(items).map(t => t * perSecond)

/** The gap of track 1 a drop at sequence time `t` goes into: the nearer side of the item under it. */
export function gapAt(items: readonly Timed[], t: number): number {
  const at = starts(items)
  for (let i = 0; i < items.length; i++) if (t < at[i]! + kept(items[i]!) / 2) return i
  return items.length
}

/** The place item `from` takes when moved into gap `to` (a gap as `gapAt` counts them, before the move). */
export const movedTo = (from: number, to: number): number => (to > from ? to - 1 : to)

/** The list with item `from` moved into gap `to`. */
export function reorder<T>(list: readonly T[], from: number, to: number): T[] {
  if (from < 0 || from >= list.length) return [...list]
  const out = list.filter((_, i) => i !== from)
  const at = Math.max(0, Math.min(out.length, movedTo(from, to)))
  out.splice(at, 0, list[from]!)
  return out
}

/** `items` put into gap `at`. */
export const insert = <T>(list: readonly T[], at: number, items: readonly T[]): T[] =>
  [...list.slice(0, Math.max(0, at)), ...items, ...list.slice(Math.max(0, at))]

/** The smallest step of an item: one frame of a clip, 10 ms of a sound. */
export const unit = (it: { kind: Kind }): number => (it.kind === 'sound' ? 10 : 1)
const snap = (it: { kind: Kind }, f: number): number => Math.round(f / unit(it)) * unit(it)

/** In at frame `f`: at least one step stays before `out`; on track 2 the sound stays where it was heard (`at` moves
 *  with `in`, never before 0). */
export function trimIn<T extends Spec & { fps: number }>(it: T, f: number): T {
  let lo = Math.max(0, Math.min(it.out - unit(it), snap(it, f)))
  if (it.at === undefined) return { ...it, in: lo }
  lo = Math.max(lo, Math.ceil((it.in - (it.at * it.fps) / 1000) / unit(it)) * unit(it))
  return { ...it, in: lo, at: Math.max(0, Math.round(it.at + ((lo - it.in) / it.fps) * 1000)) }
}

/** Out at frame `f` (exclusive): at least one step after `in`, at most the file's frames. */
export const trimOut = <T extends Spec & { frames: number }>(it: T, f: number): T =>
  ({ ...it, out: Math.min(it.frames, Math.max(it.in + unit(it), snap(it, f))) })

/** One edge of an item dragged by `seconds`: its in (`at` follows on track 2) or its out, snapped. */
export const trimEdge = <T extends Item>(it: T, edge: 'in' | 'out', seconds: number): T =>
  (edge === 'in' ? trimIn(it, it.in + seconds * it.fps) : trimOut(it, it.out + seconds * it.fps))

/** An item cut in two at frame `f` (strictly inside it), the second starting where the first ends; else null. */
export function split<T extends Item>(it: T, f: number): [T, T] | null {
  const at = snap(it, f)
  if (at <= it.in || at >= it.out) return null
  const second = { ...it, in: at, ...(it.at === undefined ? {} : { at: Math.round(it.at + ((at - it.in) / it.fps) * 1000) }) }
  return [{ ...it, out: at }, second]
}

/** What a PUT sends of an item: its id under its kind, in, out, `at` on track 2 and the bed's keys it has. */
export const spec = (it: Put): Record<string, string | number | boolean> => ({
  [it.kind]: it.id, in: it.in, ...(it.out === undefined ? {} : { out: it.out }), ...(it.at === undefined ? {} : { at: it.at }),
  ...Object.fromEntries(BED_KEYS.flatMap(k => (it[k] === undefined ? [] : [[k, it[k]!]]))),
})

/** The item with the bed's keys changed; a default (100 %, no fade, not ducked) is left out, as the hub writes it. */
export function withBed<T extends Spec>(it: T, changes: Bed): T {
  const out: Spec = { ...it, ...changes }
  if (out.level === undefined || out.level === 1) delete out.level
  if (!out.fade_in) delete out.fade_in
  if (!out.fade_out) delete out.fade_out
  if (!out.duck) delete out.duck
  return out as T
}

/** The bed's keys as the tile's title says them: "50% · fade in 1 s · fade out 0.5 s · ducked"; "" when none is set. */
export const bedLine = (it: Bed): string => [
  it.level !== undefined && it.level !== 1 ? `${Math.round(it.level * 100)}%` : '',
  it.fade_in ? `fade in ${secs(it.fade_in / 1000)} s` : '',
  it.fade_out ? `fade out ${secs(it.fade_out / 1000)} s` : '',
  it.duck ? 'ducked' : '',
].filter(Boolean).join(' · ')

/** A clip or sound dropped on a track, whole: `out` at its frames (a sound: its milliseconds) when the drag carried
 *  them, else left to the hub. */
export function whole(d: { id: string; kind?: Kind | undefined; frames?: number | undefined; seconds?: number | undefined }): Put {
  const kind: Kind = d.kind === 'sound' ? 'sound' : 'clip'
  const out = kind === 'sound' ? (typeof d.seconds === 'number' && d.seconds > 0 ? Math.round(d.seconds * 1000) : undefined)
    : (Number.isInteger(d.frames) && d.frames! > 0 ? d.frames : undefined)
  return { kind, id: d.id, in: 0, ...(out === undefined ? {} : { out }) }
}

/** Where a track-2 item ends, in seconds. */
export const endOf = (it: Placed): number => (it.at ?? 0) / 1000 + kept(it)

/** The seconds a saved file has: track 1's, or the end of track 2's last item when track 1 is empty. */
export const length = (t1: readonly Timed[], t2: readonly Placed[]): number =>
  (t1.length ? total(t1) : t2.reduce((m, it) => Math.max(m, endOf(it)), 0))

/** Track 2 with item `it` (`ms` long) placed at `atMs` (index `skip`, the item being moved, left out; `msOf` gives
 *  the others' lengths): one that would overlap another goes right after the item it hits; the track stays in
 *  time order. -> the track and where `it` landed. */
export function place<T extends { at?: number }>(list: readonly T[], it: T, ms: number, atMs: number,
  msOf: (x: T) => number, skip: number | null = null): { list: T[]; at: number } {
  const others = list.filter((_, i) => i !== skip).sort((a, b) => (a.at ?? 0) - (b.at ?? 0))
  let at = Math.max(0, Math.round(atMs))
  for (let moved = true; moved;) {
    moved = false
    for (const o of others) {
      const start = o.at ?? 0
      const end = Math.ceil(start + msOf(o))
      if (at < end && at + ms > start) { at = end; moved = true }
    }
  }
  return { list: [...others, { ...it, at }].sort((a, b) => (a.at ?? 0) - (b.at ?? 0)), at }
}

/** A drawn item's length in milliseconds. */
export const msOf = (it: Timed): number => kept(it) * 1000

/** The track-2 item under sequence time `t`, or -1. */
export const under = (list: readonly Placed[], t: number): number =>
  list.findIndex(it => (it.at ?? 0) / 1000 <= t + 1e-9 && t < endOf(it) - 1e-9)
