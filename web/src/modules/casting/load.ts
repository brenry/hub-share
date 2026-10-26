// The characters and the open one's draft, mirrored from the hub: loaded on every (re)connect while the tab shows,
// each time it is shown, and on each `casting.changed` (a Cast, Again or Approve, and the end of a cast job). The
// form (lines, bits, facts) is local until Cast; it follows the hub's draft only when the hub took new inputs or
// another character opens. Nothing is kept in the browser.
import { useEffect } from 'react'
import { errorText } from '../../lib/http'
import { connects } from '../../lib/live'
import type { DraggedMedia } from '../../lib/protocol'
import { createStore, useStore } from '../../lib/store'
import { useBusEvent } from '../../lib/useBus'
import { api, type Draft, type Role, type Seat, type Summary } from './api'
import { castBody, dropBits, formKey, formOf, removeBit, type Form } from './form'

export const list = createStore<readonly Summary[] | null>(null)
export const open = createStore<Draft | null>(null)
export const form = createStore<Form | null>(null)
/** The last refusal, one line, shown on the tab until the next press or another character. */
export const problem = createStore<string | null>(null)
/** A press waiting for its answer. */
export const pressing = createStore(false)

let name: string | null = null
let synced = ''
let boxed: string | null = null                    // the box the hub last answered
let asked = 0                                       // an older answer never covers a newer one

export async function reload(): Promise<void> {
  const mine = ++asked
  try {
    const all = await api.list()
    if (mine !== asked) return
    list.set(all)
    if (name !== null && !all.some(c => c.name === name)) name = null
    const d = name === null ? null : await api.draft(name)
    if (mine !== asked) return
    open.set(d)
    const key = d ? formKey(d) : ''
    if (key !== synced) { synced = key; boxed = d?.prompt ?? ''; form.set(d ? formOf(d) : null) }
    else if (d && (d.prompt ?? '') !== boxed) { boxed = d.prompt ?? ''; edit(f => ({ ...f, prompt: boxed ?? '' })) }
  } catch (e) {
    if (mine === asked) problem.set(errorText(e))
  }
}

export function choose(n: string): void {
  if (n === name) return
  name = n
  synced = ''
  open.set(null)
  form.set(null)
  problem.set(null)
  void reload()
}

export const edit = (fn: (f: Form) => Form): void => form.set(f => (f ? fn(f) : f))

/** The open character's name. */
export const current = (): string | null => name

/** Items dragged from Media: the pictures confirmed by the hub (as Generate's boxes take them), clips and sounds as
 *  they came (the form refuses them); one the hub does not confirm is left out. Null when the check failed (its
 *  line is the tab's). */
export async function confirm(items: DraggedMedia[]): Promise<DraggedMedia[] | null> {
  const pics = items.filter(i => i.kind === undefined)
  let ok = new Map<string, string>()
  if (pics.length > 0) {
    try {
      ok = new Map((await api.check(pics.map(p => p.id))).placed.map(p => [p.item, p.id]))
    } catch (e) {
      problem.set(errorText(e))
      return null
    }
  }
  return items.flatMap(i => (i.kind !== undefined ? [i] : ok.has(i.id) ? [{ ...i, id: ok.get(i.id)! }] : []))
}

/** Items dragged from Media onto bit box `at` (0 = box 2), confirmed, then placed in the form as it is then. */
export async function dropOn(at: number, items: DraggedMedia[]): Promise<void> {
  const who = name
  if (!form.get()) return
  const confirmed = await confirm(items)
  const f = form.get()
  if (!confirmed || !f || who !== name) return
  const r = dropBits(f.bits, confirmed, at)
  problem.set(r.problem)
  form.set({ ...f, bits: r.bits })
}

export const dropBit = (i: number): void => edit(f => ({ ...f, bits: removeBit(f.bits, i) }))

/** Cast or Audience: the tab's pick, sent with Cast. */
export const pick = (role: Role): void => edit(f => ({ ...f, role }))

let seated = 0
/** A seat edit: in the form at once, and saved to the hub (its draft, and its record when it is audience). Not
 *  a press: two quick clicks on Row both count; only the last one's refusal is shown. */
export async function sit(seat: Seat): Promise<void> {
  const who = name
  if (who === null || !form.get()) return
  edit(f => ({ ...f, seat }))
  const mine = ++seated
  try {
    await api.seat(who, seat)
    if (mine === seated && who === name) problem.set(null)
  } catch (e) {
    if (mine === seated && who === name) problem.set(errorText(e))
  }
}

/** One press: its refusal (or a failed request) is the tab's one line; done, the draft is fetched again. */
export async function press(run: () => Promise<unknown>): Promise<void> {
  if (pressing.get()) return
  pressing.set(true)
  problem.set(null)
  try {
    await run()
  } catch (e) {
    problem.set(errorText(e))
  } finally {
    pressing.set(false)
  }
  await reload()
}

export const cast = (): Promise<void> => {
  const f = form.get()
  return name === null || !f ? Promise.resolve() : press(() => api.cast(castBody(name!, f)))
}
export const again = (): Promise<void> => (name === null ? Promise.resolve() : press(() => api.again(name!)))
export const approve = (): Promise<void> => (name === null ? Promise.resolve() : press(() => api.approve(name!)))

/** Loads on every (re)connect and each time the tab is shown, and follows `casting.changed`; mounted once, by the
 *  tab. */
export function useCasting(visible: boolean): void {
  const n = useStore(connects, x => x)
  useEffect(() => { if (n > 0 && visible) void reload() }, [n, visible])
  useBusEvent('casting.changed', () => { void reload() })
}

/** Test hook: everything forgotten. */
export function _reset(): void {
  name = null
  synced = ''
  boxed = null
  asked = 0
  seated = 0
  list.set(null)
  open.set(null)
  form.set(null)
  problem.set(null)
  pressing.set(false)
}
