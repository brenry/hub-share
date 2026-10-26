// Generate from another window (Media): one job from the saved screen, the assistant's draft as the prompt — the same
// as the Generate button on the Generate screen, checked the same way.
import { bus } from '../../lib/bus'
import type { BusError } from '../../lib/protocol'
import { api } from './api'
import { EMPTY_DRAFT_TEXT, blockingReason } from './blocking'
import { normalizeDraft } from './edits'
import { buildJob } from './job'
import { TOOL } from './types'

/** Null when queued; otherwise the reason it was not. */
export async function queue(): Promise<string | null> {
  const [raw, models] = await Promise.all([api.draft(), api.models()])
  const d = normalizeDraft(raw)
  if (!d.draft.trim()) return EMPTY_DRAFT_TEXT
  const model = models.find(m => m.id === d.model) ?? null
  const reason = blockingReason({ linkOn: true, engineOffline: false, model, prompt: d.draft, refCount: d.references.length, uploading: 0, waiting: 0, draft: d })
  if (reason || !model) return reason
  return bus.request('job.submit', { tool: TOOL, kind: 'image', params: buildJob(d, model) }).then(() => null, (e: BusError) => e.text)
}
