// The open sequence and the list of sequences, mirrored from the hub. One coalescing loader (one request in flight):
// `sequence.changed` for the open name refetches it unless the revision is the one already drawn, any change refetches
// the list, and so does every (re)connect. Every edit is a PUT drawn from the revision on screen; edits queue, so each
// is drawn from the answer to the one before. Nothing is kept in the browser: the open name is lost with the window;
// a new window opens the most recently changed sequence. With none, the first drop makes "Sequence 1".
import { useEffect } from 'react'
import { errorText } from '../../lib/http'
import { connects } from '../../lib/live'
import { createStore, useStore } from '../../lib/store'
import { toast } from '../../lib/toast'
import { useBusEvent } from '../../lib/useBus'
import { toSequenceWav } from '../../lib/wav'
import { CHANGED, api, type Sequence, type Summary, type Tracks } from './api'
import { gapAt, insert, length, msOf, place, whole, type Put } from './seq'

export const list = createStore<readonly Summary[] | null>(null)
export const open = createStore<Sequence | null>(null)
let name: string | null = null

let busy = false
let want = { list: false, one: false }

/** Refetch the list, and the open sequence unless `one` is false. Calls while a request is out fold into one more pass. */
export function reload(one = true): void {
  want = { list: true, one: want.one || one }
  if (busy) return
  busy = true
  void drain()
}

async function drain(): Promise<void> {
  while (want.list || want.one) {
    const w = want
    want = { list: false, one: false }
    try {
      if (w.list) {
        const all = await api.all()
        list.set(all)
        if (name === null || !all.some(s => s.name === name)) { name = newest(all); w.one = true }
      }
      if (w.one) {
        if (name === null) open.set(null)
        else draw(await api.one(name))
      }
    } catch (e) {
      toast(errorText(e))
    }
  }
  busy = false
}

/** The most recently changed sequence's name. */
const newest = (all: readonly Summary[]): string | null =>
  all.reduce<Summary | null>((a, s) => (!a || s.changed > a.changed ? s : a), null)?.name ?? null

/** An answer for the open name; an older revision never covers a newer one. */
function draw(s: Sequence): void {
  if (s.name !== name) return
  const cur = open.get()
  if (cur && cur.name === s.name && cur.revision > s.revision) return
  open.set(s)
}

type Changed = { name: string; revision: number }

export function changed(d: Changed): void {
  const cur = open.get()
  const drawn = cur !== null && cur.name === d.name && cur.revision === d.revision
  reload(d.name === name && !drawn)
}

/** Loads on every (re)connect and follows `sequence.changed`; mounted once, by the tab. */
export function useSequenceData(): void {
  const n = useStore(connects, x => x)
  useEffect(() => { if (n > 0) reload() }, [n])
  useBusEvent('sequence.changed', d => changed(d as Changed))
}

let chain: Promise<unknown> = Promise.resolve()

/** "Sequence N", the first N not taken. */
export function freeName(all: readonly { name: string }[]): string {
  const taken = new Set(all.map(s => s.name))
  let n = 1
  while (taken.has(`Sequence ${n}`)) n++
  return `Sequence ${n}`
}

/** The open sequence; with none open, "Sequence N" is made first (no New step). */
async function ensure(): Promise<Sequence | null> {
  const s = open.get()
  if (s) return s
  try {
    const made = await api.create(freeName(list.get() ?? []))
    name = made.name
    draw(made)
    reload(false)
    return made
  } catch (e) {
    toast(errorText(e))
    return null
  }
}

/** One edit of the open sequence (made first when none is open): `fn` gets both tracks as drawn and returns them as
 *  they should be saved (null: nothing to send). */
export function edit(fn: (tracks: Tracks) => Put[][] | null): Promise<Sequence | null> {
  const run = chain.then(async () => {
    const s = await ensure()
    const next = s ? fn(s.tracks) : null
    if (!s || !next) return null
    try {
      const r = await api.save(s.name, s.revision, next)
      draw(r)
      return r
    } catch (e) {
      const text = errorText(e)
      toast(text)
      if (text === CHANGED) reload()
      return null
    }
  })
  chain = run
  return run
}

/** An item dropped on a track, with its length in milliseconds when known. */
export type Dropped = { put: Put; ms: number }

/** Items dropped on a track at sequence time `t`, whole, in one save: track 1 into the gap there, track 2 placed one
 *  after the other from `t`, never over another item. */
export const insertAt = (track: 0 | 1, t: number, dropped: readonly Dropped[]): Promise<Sequence | null> =>
  edit(([t1, t2]) => {
    if (track === 0) return [insert<Put>(t1, gapAt(t1, t), dropped.map(d => d.put)), t2]
    const lengths = new Map<Put, number>(t2.map(it => [it, msOf(it)]))
    let out: Put[] = t2
    let at = t * 1000
    for (const d of dropped) {
      lengths.set(d.put, d.ms)
      const r = place<Put>(out, d.put, d.ms, at, x => lengths.get(x) ?? 0)
      out = r.list
      at = r.at + d.ms
    }
    return [t1, out]
  })

/** An mp3 or wav file dropped on a track: made a WAV in the browser, kept in Sounds, then placed at `t`. */
export async function dropFiles(track: 0 | 1, t: number, files: readonly File[]): Promise<void> {
  const made: Dropped[] = []
  for (const f of files) {
    try {
      const { blob } = await toSequenceWav(f)
      const up = await api.sound(blob)
      made.push({ put: whole({ id: up.id, kind: 'sound', seconds: up.seconds }), ms: up.seconds * 1000 })
    } catch (e) {
      toast(errorText(e))
    }
  }
  if (made.length) await insertAt(track, t, made)
}

/** The seconds the open sequence would save as. */
export const seconds = (s: Sequence | null): number => (s ? length(s.tracks[0], s.tracks[1]) : 0)

export function choose(n: string): void {
  name = n
  reload()
}

const fail = (e: unknown): false => { toast(errorText(e)); return false }

/** Resolve to whether it was done (a refusal is toasted as it comes back). */
export const create = (n: string): Promise<boolean> =>
  api.create(n).then(s => { name = s.name; draw(s); reload(false); return true }, fail)

export function rename(to: string): Promise<boolean> {
  const s = open.get()
  if (!s) return Promise.resolve(false)
  return api.rename(s.name, to).then(r => { name = r.name; reload(); return true }, fail)
}

export function removeOpen(): void {
  const s = open.get()
  if (!s) return
  api.remove(s.name).then(() => { name = null; toast('Deleted'); reload() }, fail)
}

export const join = (n: string): Promise<boolean> => api.join(n).then(() => true, fail)
