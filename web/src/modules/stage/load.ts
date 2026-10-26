// The sets and the open set, mirrored from the hub: loaded on every (re)connect while the tab shows, each time it is
// shown, and on each `stage.changed`. The form (boxes, description, pieces, audience, house words) is local until
// a press; it follows the hub's inputs only when the hub took new ones or another set opens. A name typed in New set
// is a local set until Build makes it the hub's. The two Prompt boxes are in the form, follow the
// hub's only when the hub's change, and go with their pan's presses. Nothing is kept in the browser.
import { useEffect } from 'react'
import { errorText } from '../../lib/http'
import { connects } from '../../lib/live'
import type { DraggedMedia, Job } from '../../lib/protocol'
import { createStore, useStore } from '../../lib/store'
import { useBusEvent } from '../../lib/useBus'
import { BOXES, api, type Audience, type BuildBody, type Detail, type Draft, type HouseWords, type Inputs, type Picture, type Prompts, type Summary } from './api'

export type Form = { boxes: Picture[]; description: string; pieces: string; audience: Audience; house: HouseWords; prompts: Prompts }
export const PICTURES_ONLY = 'Only pictures go in a box'
export const TOO_MANY = `At most ${BOXES} pictures`

const NO_HOUSE: HouseWords = { era: '', dress: '', hair: '', size: '' }
const NO_PROMPTS: Prompts = { stage: '', house: '' }

/** The form as the hub's inputs hold them; none: a new set, every box empty. `prompts` the hub's boxes. */
export function formOf(inp: Inputs | null, prompts: Prompts = NO_PROMPTS): Form {
  const boxes = Array.from({ length: BOXES }, (_, i) => {
    const p = inp?.pictures[i]
    return p ? { id: p.id, keep: p.keep ?? '' } : { id: '', keep: '' }
  })
  return {
    boxes, description: inp?.description ?? '', pieces: (inp?.pieces ?? []).join('\n'),
    audience: inp?.audience ?? 'seen', house: { ...NO_HOUSE, ...inp?.house }, prompts: { ...NO_PROMPTS, ...prompts },
  }
}

/** What Build sends: the boxes up to the last filled one (an empty box between is sent, so the hub names it), the
 *  lines trimmed, one piece a line. */
export function buildBody(name: string, f: Form): BuildBody {
  const last = f.boxes.reduce((n, b, i) => (b.id ? i : n), -1)
  return {
    name, pictures: f.boxes.slice(0, last + 1).map(b => ({ id: b.id, keep: b.keep.trim() })),
    description: f.description.trim(), pieces: f.pieces.split('\n').map(l => l.trim()).filter(Boolean), audience: f.audience,
    prompt: f.prompts.stage,
  }
}

/** Items dropped on box `at`: the first takes that box (its line kept), the rest the free boxes in order. Clips,
 *  sounds and pictures past the ninth box are not placed; `problem` says the first reason. */
export function dropBoxes(boxes: readonly Picture[], items: readonly DraggedMedia[], at: number): { boxes: Picture[]; problem: string | null } {
  let problem: string | null = items.some(i => i.kind !== undefined) ? PICTURES_ONLY : null
  const out = boxes.map(b => ({ ...b }))
  const [first, ...rest] = items.filter(i => i.kind === undefined)
  if (first) out[at] = { ...out[at]!, id: first.id }
  for (const p of rest) {
    const free = out.findIndex(b => !b.id)
    if (free < 0) { problem ??= TOO_MANY; break }
    out[free] = { ...out[free]!, id: p.id }
  }
  return { boxes: out, problem }
}

/** The job's line: its title, its step of the plan's steps and its percentage; gone from the queue, the draft's state. */
export function jobLine(d: Draft | null, job: Job | null): string {
  if (job && (job.state === 'queued' || job.state === 'running')) {
    const p = job.progress
    const steps = job.summary?.step_names
    const step = job.state === 'queued' ? 'queued'
      : p && steps?.length && p.index >= 1 ? `Step ${p.index} of ${steps.length} · ${steps[p.index - 1] ?? ''}` : p?.text || 'running'
    const pct = p && p.pct > 0 ? ` · ${Math.round(p.pct)} %` : ''
    return `${job.title} · ${step}${pct}`
  }
  if (job?.state === 'failed') return `${job.title} · failed${job.error ? ` · ${job.error.text}` : ''}`
  if (d?.state === 'rendering') return 'Rendering'
  if (d?.state === 'failed') return d.problem ? `Failed · ${d.problem}` : 'Failed'
  return ''
}

export const sets = createStore<readonly Summary[] | null>(null)
export const detail = createStore<Detail | null>(null)
/** The open set's name: the hub's, or one typed in New set. */
export const current = createStore<string | null>(null)
export const form = createStore<Form | null>(null)
/** The change lines, the stage's and the house's, as typed. */
export const words = createStore({ change: '', house: '' })
/** The last refusal, one line, shown on the tab until the next press or another set. */
export const problem = createStore<string | null>(null)
/** A press waiting for its answer. */
export const pressing = createStore(false)

let synced = ''
let boxed: Prompts = NO_PROMPTS                    // the hub's boxes as the form last took them
let asked = 0                                       // an older answer never covers a newer one
const fold = (n: string): string => n.toLocaleLowerCase()

export async function reload(): Promise<void> {
  const mine = ++asked
  try {
    const { sets: all, prompts: held } = await api.sets()
    if (mine !== asked) return
    sets.set(all)
    const n = current.get()
    const known = n === null ? undefined : all.find(s => fold(s.name) === fold(n))
    const d = known ? await api.set(known.name) : null
    if (mine !== asked) return
    detail.set(d)
    const hub: Prompts = { ...NO_PROMPTS, ...(d?.prompts ?? held) }
    const key = d ? JSON.stringify([d.name, d.inputs]) : null
    // a box follows the hub's only when the hub's changed: the other box's unsent text stays
    const moved = (Object.keys(hub) as (keyof Prompts)[]).filter(k => hub[k] !== boxed[k])
    const take = (f: Form): Form => ({ ...f, prompts: { ...f.prompts, ...Object.fromEntries(moved.map(k => [k, hub[k]])) } })
    boxed = hub
    if (d && key !== synced) { synced = key!; form.set(take(formOf(d.inputs, form.get()?.prompts ?? hub))) }
    else if (!d && n !== null && !form.get()) form.set(formOf(null, hub))
    else if (moved.length) edit(take)
  } catch (e) {
    if (mine === asked) problem.set(errorText(e))
  }
}

/** Opens a set by name: one of the hub's (as it spells it), or a new local one. */
export function choose(n: string): void {
  const name = n.trim()
  if (!name) return
  const known = sets.get()?.find(s => fold(s.name) === fold(name))
  const next = known?.name ?? name
  if (next === current.get()) return
  current.set(next)
  synced = ''
  detail.set(null)
  form.set(null)
  words.set({ change: '', house: '' })
  problem.set(null)
  void reload()
}

export const edit = (fn: (f: Form) => Form): void => form.set(f => (f ? fn(f) : f))

/** Items dragged from Media onto box `at`: the pictures the hub confirms, then placed in the form as it is then. */
export async function dropOn(at: number, items: DraggedMedia[]): Promise<void> {
  const who = current.get()
  if (!form.get()) return
  const pics = items.filter(i => i.kind === undefined)
  let ok = new Map<string, string>()
  if (pics.length > 0) {
    try {
      ok = new Map((await api.check(pics.map(p => p.id))).placed.map(p => [p.item, p.id]))
    } catch (e) {
      problem.set(errorText(e))
      return
    }
  }
  const f = form.get()
  if (!f || who !== current.get()) return
  const confirmed = items.flatMap(i => (i.kind !== undefined ? [i] : ok.has(i.id) ? [{ ...i, id: ok.get(i.id)! }] : []))
  const r = dropBoxes(f.boxes, confirmed, at)
  problem.set(r.problem)
  form.set({ ...f, boxes: r.boxes })
}

/** Box `i` emptied; box 1 keeps its line. */
export const clearBox = (i: number): void =>
  edit(f => ({ ...f, boxes: f.boxes.map((b, k) => (k === i ? { id: '', keep: i === 0 ? b.keep : '' } : b)) }))

/** One press: its refusal (or a failed request) is the tab's one line; done, the set is fetched again. */
async function press(run: (name: string) => Promise<unknown>, after?: () => void): Promise<void> {
  const name = current.get()
  if (name === null || pressing.get()) return
  pressing.set(true)
  problem.set(null)
  try {
    await run(name)
    after?.()
  } catch (e) {
    problem.set(errorText(e))
  } finally {
    pressing.set(false)
  }
  await reload()
}

export const build = (): Promise<void> => {
  const f = form.get()
  return f ? press(n => api.build(buildBody(n, f))) : Promise.resolve()
}
export const again = (): Promise<void> => press(n => api.again(n))
export const approve = (): Promise<void> => press(n => api.approve(n))
export const discard = (): Promise<void> => press(n => api.discard(n))
/** A pan's Prompt box as typed. */
const box = (which: keyof Prompts): string => form.get()?.prompts[which] ?? ''
export const setPrompt = (which: keyof Prompts, text: string): void => edit(f => ({ ...f, prompts: { ...f.prompts, [which]: text } }))
export const change = (): Promise<void> =>
  press(n => api.change(n, words.get().change.trim(), box('stage')), () => words.set(w => ({ ...w, change: '' })))
export const houseChange = (): Promise<void> =>
  press(n => api.houseChange(n, words.get().house.trim(), box('house')), () => words.set(w => ({ ...w, house: '' })))
export const buildHouse = (): Promise<void> => {
  const h = form.get()?.house ?? NO_HOUSE
  return press(n => api.house(n, { era: h.era.trim(), dress: h.dress.trim(), hair: h.hair.trim(), size: h.size.trim() }, box('house')))
}
/** On an approved set the audience is written at once; before, it is part of the form Build sends. */
export const setAudience = (a: Audience): Promise<void> => {
  edit(f => ({ ...f, audience: a }))
  return detail.get()?.approved ? press(n => api.audience(n, a)) : Promise.resolve()
}

/** Loads on every (re)connect and each time the tab is shown, and follows `stage.changed`; mounted once, by the tab. */
export function useStage(visible: boolean): void {
  const n = useStore(connects, x => x)
  useEffect(() => { if (n > 0 && visible) void reload() }, [n, visible])
  useBusEvent('stage.changed', () => { void reload() })
}
