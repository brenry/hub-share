// Pure: the form edited on the tab (the headshot's lines, the bits, the facts), what a drop from Media does to it, what Cast
// sends, and which sheet the tab shows.
import type { DraggedMedia, Job } from '../../lib/protocol'
import { SEAT, VIEWS, itemFile, itemThumb, viewsOf, type Approved, type Bit, type CastBody, type Draft, type Facts, type Lines, type Role, type Seat, type State, type View, type Views } from './api'

/** Box 1 (the headshot) and up to 8 bits: Ref2VA's 9 pictures. */
export const MAX_PICTURES = 9
export const MAX_BITS = MAX_PICTURES - 1
export const TOO_MANY = `At most ${MAX_PICTURES} pictures`
export const SHAPE = 'A picture between 1:4 and 4:1'
export const PICTURES_ONLY = 'Only pictures go in a box'

/** `role` and `seat` as picked on the tab; `was` the role the hub's draft holds; `prompt` the tab's Prompt box,
 *  sent as typed with every Cast, a costume's too. */
export type Form = { headshot: Lines; bits: Bit[]; facts: Facts; role?: Role; seat?: Seat; was?: Role; prompt: string }

const bitsOf = (bits: readonly Bit[]): Bit[] => bits.map(b => ({ id: b.id, keep: b.keep ?? '', ignore: b.ignore ?? '' }))

/** The form as the hub's draft holds it. */
export const formOf = (d: Draft): Form => ({
  headshot: { keep: d.headshot.keep ?? '', ignore: d.headshot.ignore ?? '' },
  bits: bitsOf(d.bits),
  facts: { age: d.facts?.age ?? '', build: d.facts?.build ?? '' },
  role: d.role ?? 'cast', seat: d.seat ?? SEAT, was: d.role ?? 'cast', prompt: d.prompt ?? '',
})

/** The draft's inputs as one key: a change means the hub took new inputs (Cast, Again), and the form follows. The
 *  seat and the box are left out: the seat is saved on its own (`/seat`), the box is one for the tab (a costume's Cast
 *  sets it too) and follows on its own (`load.reload`); neither resets the typed lines. */
export const formKey = (d: Draft): string => { const { seat: _, prompt: __, ...f } = formOf(d); return JSON.stringify([d.name, f]) }

const trim = (l: Lines): Lines => ({ keep: l.keep.trim(), ignore: l.ignore.trim() })

/** What Cast sends: the lines as typed, trimmed; the role when it is not the plain cast it had (else the
 *  body holds no role), and the seat with `audience`. */
export const castBody = (name: string, f: Form): CastBody => {
  const role = f.role ?? 'cast'
  return {
    name, headshot: trim(f.headshot), bits: f.bits.map(b => ({ id: b.id, ...trim(b) })),
    facts: { age: f.facts.age.trim(), build: f.facts.build.trim() },
    ...(role === 'audience' || f.was === 'audience' ? { role } : {}),
    ...(role === 'audience' ? { seat: f.seat ?? SEAT } : {}),
    prompt: f.prompt,
  }
}

/** A costume's form: boxes 3-9 and the words. */
export type CostumeForm = { pictures: Bit[]; words: string }
export const COSTUME_PICTURES = 7
export const costumeFormOf = (c: { pictures: readonly Bit[]; words?: string | null }): CostumeForm =>
  ({ pictures: bitsOf(c.pictures), words: c.words ?? '' })
/** What a costume's Cast sends: its pictures in box order with their lines, and the words, trimmed; the tab's Prompt
 *  box as typed. */
export const costumeBody = (name: string, variant: string, f: CostumeForm, prompt: string) =>
  ({ name, variant, pictures: f.pictures.map(b => ({ id: b.id, ...trim(b) })), words: f.words.trim(), prompt })

/** Between 1:4 and 4:1 (an unknown size passes; the hub checks it again). */
export const inShape = (w: number, h: number): boolean => !(w > 0 && h > 0) || Math.max(w, h) <= 4 * Math.min(w, h)

/** Media items dropped on bit box `at` (0 = box 2): the first takes that box (its lines kept) when it holds a
 *  picture, the rest go to the free boxes after the filled ones. Clips, sounds, odd shapes and pictures past 9 are
 *  not placed; `problem` says the first reason. */
export function dropBits(bits: readonly Bit[], items: readonly DraggedMedia[], at: number, max = MAX_BITS): { bits: Bit[]; problem: string | null } {
  let problem: string | null = null
  const say = (p: string) => { problem ??= p }
  const pics = items.filter(i => {
    if (i.kind !== undefined) { say(PICTURES_ONLY); return false }
    if (!inShape(i.w, i.h)) { say(SHAPE); return false }
    return true
  })
  const out = bits.map(b => ({ ...b }))
  let rest = pics
  const first = pics[0]
  if (first && at < out.length) {
    out[at] = { ...out[at]!, id: first.id }
    rest = pics.slice(1)
  }
  for (const p of rest) {
    if (out.length >= max) { say(TOO_MANY); break }
    out.push({ id: p.id, keep: '', ignore: '' })
  }
  return { bits: out, problem }
}

/** The bits without box `i` (0 = box 2); the boxes after it move up. */
export const removeBit = (bits: readonly Bit[], i: number): Bit[] => bits.filter((_, k) => k !== i)

/** The frame ids by view, from either shape the hub sends (a list in `names`' order). */
export function viewIds(v: Views | null | undefined, names: readonly View[] = VIEWS): Partial<Record<View, string>> {
  if (!v) return {}
  const at = (name: View, i: number): string | null | undefined => (Array.isArray(v) ? v[i] : v[name])
  return Object.fromEntries(names.flatMap((name, i) => { const id = at(name, i); return id ? [[name, id]] : [] }))
}

/** What a sheet is drawn from: a character's draft or a costume's. */
export type SheetDraft = {
  state: State; job: string | null; orbit: string | null; views: Views | null; problem?: string | null
  files?: Approved | null; record?: Record<string, unknown> | null; role?: Role
}

/** `views` each view's picture address; `orbit` the address the orbit plays from. */
export type Shown = { views: Partial<Record<View, string>>; orbit: string | null; approved: boolean }

/** The sheet on screen: a ready draft's (a new sheet waits for its Approve), else the approved one, else none. */
export function shown(d: SheetDraft | null): Shown | null {
  if (!d) return null
  const names = viewsOf(d.role)
  if (d.state === 'ready') {
    const ids = viewIds(d.views, names)
    const views = Object.fromEntries(Object.entries(ids).map(([v, id]) => [v, itemThumb(id, 1024)]))
    return { views, orbit: d.orbit ? itemFile(d.orbit) : null, approved: false }
  }
  if (d.files) {
    const urls = d.files.view_urls ?? {}
    const views = Object.fromEntries(names.flatMap(v => (urls[v] ? [[v, urls[v] as string]] : [])))
    return { views, orbit: d.files.orbit_url ?? null, approved: true }
  }
  return null
}

/** Whether the character has an approved sheet. */
export const isCast = (d: SheetDraft | null): boolean => !!d && (d.state === 'approved' || !!d.files || !!d.record)

/** The job's state in words: its title, state and progress; or, gone from the queue, the draft's state. */
export function jobLine(d: SheetDraft | null, job: Job | null): string {
  if (job && (job.state === 'queued' || job.state === 'running')) {
    const p = job.progress
    const pct = p && p.pct > 0 ? ` · ${Math.round(p.pct)} %` : ''
    return `${job.title} · ${job.state === 'queued' ? 'queued' : p?.text || 'running'}${pct}`
  }
  if (job?.state === 'failed') return `${job.title} · failed${job.error ? ` · ${job.error.text}` : ''}`
  if (d?.state === 'rendering') return 'Rendering'
  if (d?.state === 'failed') return d.problem ? `Failed · ${d.problem}` : 'Failed'
  return ''
}
