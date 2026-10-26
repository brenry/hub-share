// The draft store: the server holds the truth (the settings on disk; the prompt, the assistant's draft and the
// references in memory for the session); edits are saved 1 s after the last change.
import { bus } from '../../lib/bus'
import type { Welcome } from '../../lib/protocol'
import { createStore } from '../../lib/store'
import { api } from './api'
import { EMPTY_DRAFT, normalizeDraft } from './edits'
import type { Draft } from './types'

export const draft = createStore<Draft>(EMPTY_DRAFT)
export const draftReady = createStore(false)

const SAVE_MS = 1000
let timer: ReturnType<typeof setTimeout> | undefined
const changed = new Set<keyof Draft>()        // what this window changed and has not saved yet
let saving: Promise<void> = Promise.resolve()
let session: string | null = null
const dirty = (): boolean => changed.size > 0

/** Every edit; a box change never changes the model: the model is the pulldown's pick alone. A model change is saved
 *  at once, so the hub sees every pick and keeps it as the last of its kind (`lastModel`). */
export function edit(fn: (d: Draft) => Draft): void {
  const before = draft.get()
  draft.set(fn)
  const after = draft.get()
  if (after === before) return
  for (const key of Object.keys(after) as (keyof Draft)[]) if (after[key] !== before[key]) changed.add(key)
  clearTimeout(timer)
  if (after.model !== before.model) save()
  else timer = setTimeout(save, SAVE_MS)
}

/** Only the changed fields go to the server, which merges them: a window never writes over what the tool
 *  server (or another window) set meanwhile. */
function save(): void {
  if (!dirty()) return
  if (bus.link.get().state !== 'on') { retry(); return }   // the link is down: wait and try again, do not strand the keys
  const keys = [...changed]
  changed.clear()
  const d = draft.get()
  const part = { ...Object.fromEntries(keys.map(k => [k, d[k]])), ...(d.engine === undefined ? {} : { engine: d.engine }) }
  saving = saving.then(() => api.saveDraft(part)).then(() => {}, () => { for (const k of keys) changed.add(k); retry() })
}

/** A failed or deferred save is retried on the same debounce, so a key is never stranded in `changed`
 *  — a stranded key hides every later value the tool server sets for it (the bar freezes after the first change). */
function retry(): void {
  clearTimeout(timer)
  timer = setTimeout(save, SAVE_MS)
}

/** Resolves once every save sent so far has been answered (a refused save counts as answered). */
export const settled = (): Promise<void> => saving.then(() => {})

/** New chat: the server empties the prompt box and the assistant's draft and tells every window. This window drops
 *  what it was about to save of the two (the last second of typing included) and shows them empty at once, so the
 *  server's clearing is never written over. The references and the settings are not touched. */
export function clearWords(): void {
  changed.delete('prompt')
  changed.delete('draft')
  draft.set(d => (d.prompt === '' && d.draft === '' ? d : { ...d, prompt: '', draft: '' }))
}

/** The server's draft, taken for every field this window has no unsaved change to. */
export async function loadDraft(): Promise<void> {
  try {
    const d = normalizeDraft(await api.draft())
    draft.set(cur => ({ ...d, ...Object.fromEntries([...changed].map(k => [k, cur[k]])) }))
  } catch {
    // A missing draft starts from the defaults.
  }
  draftReady.set(true)
}

/** After a reconnect: into the same session, unsaved edits are flushed and otherwise the draft is read again (another
 *  window may have changed it); into a new session (the link was cut for longer than the grace), what this window
 *  kept of the old one is dropped, so nothing of it is sent back. */
bus.on('welcome', data => {
  const next = (data as Welcome).session
  const fresh = session !== null && next !== session
  session = next
  if (fresh) {
    clearTimeout(timer)
    changed.clear()
    draft.set(d => ({ ...d, prompt: '', draft: '', references: [], selected: null }))
  } else if (dirty()) save()
  void loadDraft()
})
/** Another window saved the draft, the assistant wrote its draft, pushed it into the prompt box or set a setting,
 *  New chat emptied the box and the draft, or Media reset the seed: take it, field by field, except where an edit
 *  here is unsaved. */
bus.on('generate-image.draft', () => {
  void loadDraft()
})
