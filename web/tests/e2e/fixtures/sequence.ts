// The sequence routes of the fake hub (Stage 11), behind `fixtures/api.ts`'s fallback: register before
// `open`. Two tracks; refusals carry the hub's lines; every write raises the revision and tells the windows
// `sequence.changed`. A saved item with no `out` (or null) is whole: its frames, or a sound's milliseconds. A WAV posted
// to `/api/sounds/upload` lands as `sounds/2026-10-17/up<n>.wav` with the seconds its header says.
import type { Page, Route } from '@playwright/test'
import type { ToolInfo } from '../../../src/lib/protocol'

export const SEQUENCE_TOOL: ToolInfo = { id: 'sequence', title: 'Edit Video', tab: { label: 'Edit Video', order: 20 }, sockets: [] }

/** An item as the hub stores it: its id under its kind. */
export type Spec = { clip?: string; sound?: string; in: number; out: number; at?: number }
type Put = Omit<Spec, 'out'> & { out?: number | null }
type Facts = { w: number; h: number; fps: number; frames: number; audio: boolean }
export type SeqState = {
  seqs: Record<string, { revision: number; tracks: [Spec[], Spec[]]; changed: number }>
  /** A file's facts by id; any other `clips/` id is 124 frames at 24 fps, 960 × 544; a `sounds/` id 20 s. */
  facts: Record<string, Facts>
  limit: number
  joins: string[]
  uploads: { rate: number; seconds: number }[]
  /** The fake hub's bus (set by the spec once the windows are open). */
  broadcast: ((t: string, d: unknown) => void) | null
}

export const CLIP = (n: number, day = '2026-10-13'): string => `clips/${day}/${String(n).padStart(6, '0')}.mp4`
export const SOUND = (n: number): string => `sounds/2026-10-13/${String(n).padStart(6, '0')}.wav`
/** "Opening": a whole clip (5.17 s), frames 12–60 of another (2 s), frames 0–48 of a third (2 s). */
export const OPENING: Spec[] = [{ clip: CLIP(180000), in: 0, out: 124 }, { clip: CLIP(179900), in: 12, out: 60 }, { clip: CLIP(179800), in: 0, out: 48 }]

export function seqState(over: Partial<SeqState> = {}): SeqState {
  return {
    seqs: { Opening: { revision: 3, tracks: [structuredClone(OPENING), []], changed: 2 }, Trailer: { revision: 1, tracks: [[], []], changed: 1 } },
    facts: {}, limit: 200, joins: [], uploads: [], broadcast: null, ...over,
  }
}

const round2 = (x: number) => Math.round(x * 100) / 100
const idOf = (it: Spec | Put): string => it.clip ?? it.sound ?? ''
const facts = (st: SeqState, id: string): Facts | null =>
  st.facts[id] ?? (id.startsWith('clips/') ? { w: 960, h: 544, fps: 24, frames: 124, audio: true }
    : id.startsWith('sounds/') ? { w: 0, h: 0, fps: 1000, frames: 20000, audio: true } : null)

function view(st: SeqState, name: string) {
  const s = st.seqs[name]!
  const tracks = s.tracks.map(t => t.map(it => {
    const id = idOf(it)
    const f = facts(st, id)!
    return { ...it, kind: it.clip ? 'clip' : 'sound', id, ...f, seconds: round2(f.frames / f.fps), kept: round2((it.out - it.in) / f.fps), url: `/files/${id}` }
  }))
  return { name, revision: s.revision, tracks }
}

const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
const no = (route: Route, text: string) => json(route, { code: 'invalid', text }, 400)

/** The line a save is refused with, or null. */
function refusal(st: SeqState, tracks: Spec[][]): string | null {
  if (tracks.length !== 2) return 'A sequence has two tracks'
  if (tracks.some(t => t.length > st.limit)) return `A track holds at most ${st.limit} items`
  for (const [k, track] of tracks.entries()) {
    for (const it of track) {
      const keys = k === 1 ? ['clip', 'sound', 'in', 'out', 'at', 'level', 'fade_in', 'fade_out', 'duck'] : ['clip', 'sound', 'in', 'out']
      if (Object.keys(it).some(x => !keys.includes(x))) return "A sequence holds item ids, order, in and out points, where track 2's items start and their level, fades and duck only"
      const f = facts(st, idOf(it))
      if (!f || (it.clip && !it.clip.startsWith('clips/')) || (it.sound && !it.sound.startsWith('sounds/'))) return 'Only clips and sounds go in a sequence'
      if (!Number.isInteger(it.in) || !Number.isInteger(it.out) || it.in < 0 || it.out > f.frames) {
        return it.clip ? `In and out are frames of the clip, from 0 to ${f.frames}` : `In and out are milliseconds of the sound, from 0 to ${f.frames}`
      }
      if (it.out <= it.in) return it.clip ? 'A clip keeps at least one frame' : 'A sound keeps at least one millisecond'
    }
  }
  if (new Set(tracks[0]!.map(it => (it.clip ? 'clip' : 'sound'))).size > 1) return 'Track 1 holds clips or sounds, not both'
  return null
}

const seconds = (st: SeqState, s: { tracks: [Spec[], Spec[]] }): number => {
  const len = (it: Spec) => (it.out - it.in) / facts(st, idOf(it))!.fps
  return s.tracks[0].length ? s.tracks[0].reduce((t, it) => t + len(it), 0) : s.tracks[1].reduce((m, it) => Math.max(m, (it.at ?? 0) / 1000 + len(it)), 0)
}

export async function mockSequence(page: Page, st: SeqState): Promise<void> {
  let clock = 10
  await page.route(/\/api\/(sequence\/|sounds\/upload)/, route => {
    const req = route.request()
    const url = new URL(req.url())
    if (url.pathname === '/api/sounds/upload') {
      const raw = req.postDataBuffer() ?? Buffer.alloc(0)
      if (raw.length < 44 || raw.subarray(0, 4).toString('latin1') !== 'RIFF') return no(route, 'That sound file could not be read')
      const rate = raw.readUInt32LE(24)
      const secs = round2(raw.readUInt32LE(40) / raw.readUInt32LE(28))
      st.uploads.push({ rate, seconds: secs })
      const id = `sounds/2026-10-17/up${st.uploads.length}.wav`
      st.facts[id] = { w: 0, h: 0, fps: 1000, frames: Math.round(secs * 1000), audio: true }
      return json(route, { id, seconds: secs })
    }
    const p = url.pathname.replace('/api/sequence', '')
    const m = req.method()
    const b = (req.postDataBuffer() ? req.postDataJSON() : {}) as { name?: string; to?: string; revision?: number; tracks?: Put[][] }
    const name = m === 'GET' ? url.searchParams.get('name') ?? '' : String(b.name ?? '')
    const told = (n: string, revision: number) => st.broadcast?.('sequence.changed', { name: n, revision })
    const plain = (n: string) => (n === '' ? 'Name the sequence' : n.includes('/') || new TextEncoder().encode(n).length > 236 ? 'Use a plain sequence name, without slashes' : null)
    if (p === '/all') {
      const sequences = Object.keys(st.seqs).sort().map(n => {
        const s = st.seqs[n]!
        return { name: n, clips: s.tracks[0].length + s.tracks[1].length, seconds: round2(seconds(st, s)), changed: s.changed }
      })
      return json(route, { sequences })
    }
    if (p === '/new') {
      const bad = plain(name) ?? (st.seqs[name] ? `A sequence named ${name} already exists` : null)
      if (bad) return no(route, bad)
      st.seqs[name] = { revision: 0, tracks: [[], []], changed: clock++ }
      told(name, 0)
      return json(route, view(st, name))
    }
    const s = st.seqs[name]
    if (!s) return no(route, plain(name) ?? `There is no sequence named ${name}`)
    if (p === '/one' && m === 'GET') return json(route, view(st, name))
    if (p === '/one' && m === 'PUT') {
      if (b.revision !== s.revision) return no(route, 'The sequence changed in another window')
      const whole = (it: Put) => (it.out == null ? facts(st, idOf(it))?.frames : undefined)
      const tracks = (b.tracks ?? []).map(t => t.map(it => ({ ...it, out: whole(it) ?? it.out }))) as Spec[][]
      const bad = refusal(st, tracks)
      if (bad) return no(route, bad)
      st.seqs[name] = { revision: s.revision + 1, tracks: tracks as [Spec[], Spec[]], changed: clock++ }
      told(name, s.revision + 1)
      return json(route, view(st, name))
    }
    if (p === '/rename') {
      const to = String(b.to ?? '')
      const bad = plain(to) ?? (st.seqs[to] ? `A sequence named ${to} already exists` : null)
      if (bad) return no(route, bad)
      delete st.seqs[name]
      st.seqs[to] = s
      told(to, s.revision)
      return json(route, { name: to })
    }
    if (p === '/delete') {
      delete st.seqs[name]
      told(name, -1)
      return route.fulfill({ status: 204, body: '' })
    }
    if (p === '/join') {
      if (s.tracks[0].length + s.tracks[1].length === 0) return no(route, 'The sequence is empty')
      st.joins.push(name)
      return json(route, { job: `j_join${st.joins.length}` })
    }
    return json(route, { text: 'Not found' }, 404)
  })
}
