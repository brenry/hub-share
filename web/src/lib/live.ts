// Mirrors of controller state, fed only by the bus (current state, never deltas to replay).
import type { Bus } from './bus'
import { createStore } from './store'
import { previews } from './stills'
import type { Focus, Job, Presence, ToolInfo, Welcome } from './protocol'

export const presence = createStore<Presence | null>(null)
export const jobs = createStore<ReadonlyMap<string, Job>>(new Map())
export const focus = createStore<Focus | null>(null)
export const tools = createStore<ToolInfo[] | null>(null)
/** Counts `welcome`s: screens refetch their lists once per (re)connect. */
export const connects = createStore(0)

export function feed(b: Bus): void {
  b.on('welcome', d => {
    const w = d as Welcome
    presence.set(w.presence)
    focus.set(w.focus)
    tools.set(w.tools)
    jobs.set(new Map(w.jobs.map(j => [j.id, j])))
    previews.set(clipPreviewsOf(w.settings))
    connects.set(n => n + 1)
  })
  b.on('settings', d => previews.set(clipPreviewsOf(d)))
  b.on('presence', d => presence.set(d as Presence))
  b.on('focus', d => focus.set((d as Focus | null) ?? null))
  b.on('job', d => {
    const j = d as Job
    jobs.set(m => new Map(m).set(j.id, j))
  })
  b.on('job.gone', d => {
    const id = (d as { id: string }).id
    jobs.set(m => {
      if (!m.has(id)) return m
      const n = new Map(m)
      n.delete(id)
      return n
    })
  })
}

/** Settings → Hardware → Clip previews (off unless the hub says on). */
function clipPreviewsOf(settings: unknown): boolean {
  return ((settings as { vram?: { clip_previews?: unknown } } | null)?.vram?.clip_previews) === true
}
