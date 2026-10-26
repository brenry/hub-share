// A costume of the open character, mirrored from the hub as the character's own draft is: fetched when opened
// and again each time that draft is (every `casting.changed`, every press). Its form (pictures, lines, words) is local
// until Cast. Nothing is kept in the browser.
import { errorText } from '../../lib/http'
import type { DraggedMedia } from '../../lib/protocol'
import { createStore } from '../../lib/store'
import { api, type Costume } from './api'
import { COSTUME_PICTURES, costumeBody, costumeFormOf, dropBits, removeBit, type CostumeForm } from './form'
import { confirm, current, form, open, press, problem } from './load'

/** The costume open; null shows the character's own sheet. */
export const variant = createStore<string | null>(null)
export const costume = createStore<Costume | null>(null)
export const costumeForm = createStore<CostumeForm | null>(null)
/** Remove pressed once, waiting for the second press. */
export const armed = createStore(false)

let who: string | null = null
let synced = ''
let asked = 0                                       // an older answer never covers a newer one

const keyOf = (c: Costume): string => JSON.stringify([c.name, c.variant, costumeFormOf(c)])

function take(c: Costume): void {
  costume.set(c)
  const k = keyOf(c)
  if (k !== synced) { synced = k; costumeForm.set(costumeFormOf(c)) }
}

/** Back to the character's own sheet. */
export function closeCostume(): void {
  asked++
  who = null
  synced = ''
  variant.set(null)
  costume.set(null)
  costumeForm.set(null)
  armed.set(false)
}

/** Opens costume `v` of the open character (a new name: a fresh draft); a refusal is the tab's one line. */
export async function openCostume(v: string): Promise<void> {
  const n = current()
  const want = v.trim()
  if (n === null || !want) return
  const mine = ++asked
  problem.set(null)
  try {
    const c = await api.costume({ name: n, variant: want })
    if (mine !== asked || n !== current()) return
    who = n
    synced = ''
    armed.set(false)
    variant.set(c.variant || want)
    take(c)
  } catch (e) {
    if (mine === asked) problem.set(errorText(e))
  }
}

async function refetch(): Promise<void> {
  const v = variant.get()
  if (v === null || who === null) return
  const mine = ++asked
  try {
    const c = await api.costume({ name: who, variant: v })
    if (mine === asked && v === variant.get()) take(c)
  } catch (e) {
    if (mine === asked) problem.set(errorText(e))
  }
}

// The character's draft fetched again: the open costume follows; another character (or none) closes it.
open.subscribe(() => {
  if (variant.get() === null) return
  const d = open.get()
  if (!d || d.name !== who) closeCostume()
  else void refetch()
})

export const editCostume = (fn: (f: CostumeForm) => CostumeForm): void => costumeForm.set(f => (f ? fn(f) : f))

/** Items dragged from Media onto costume box `at` (0 = box 3): confirmed, then placed; at most 7. */
export async function dropCostume(at: number, items: DraggedMedia[]): Promise<void> {
  const v = variant.get()
  if (!costumeForm.get()) return
  const confirmed = await confirm(items)
  const f = costumeForm.get()
  if (!confirmed || !f || v !== variant.get()) return
  const r = dropBits(f.pictures, confirmed, at, COSTUME_PICTURES)
  problem.set(r.problem)
  costumeForm.set({ ...f, pictures: r.bits })
}

export const dropCostumePicture = (i: number): void => editCostume(f => ({ ...f, pictures: removeBit(f.pictures, i) }))

const pair = (): { name: string; variant: string } | null => {
  const n = current()
  const v = variant.get()
  return n === null || v === null ? null : { name: n, variant: v }
}

export const castCostume = (): Promise<void> => {
  const p = pair()
  const f = costumeForm.get()
  return !p || !f ? Promise.resolve() : press(() => api.costumeCast(costumeBody(p.name, p.variant, f, form.get()?.prompt ?? '')))
}
export const againCostume = (): Promise<void> => { const p = pair(); return p ? press(() => api.costumeAgain(p)) : Promise.resolve() }
export const approveCostume = (): Promise<void> => { const p = pair(); return p ? press(() => api.costumeApprove(p)) : Promise.resolve() }

/** Remove: the first press arms it, the second removes the costume (its folder and entry) and shows the character's sheet. */
export async function removeCostume(): Promise<void> {
  const p = pair()
  if (!p) return
  if (!armed.get()) { armed.set(true); return }
  armed.set(false)
  await press(async () => { await api.costumeRemove(p); closeCostume() })
}

/** Test hook: everything forgotten. */
export function _resetCostume(): void {
  closeCostume()
  asked = 0
}
