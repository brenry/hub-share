import { useMemo } from 'react'
import { bus } from '../../lib/bus'
import { jobs, presence } from '../../lib/live'
import type { BusError } from '../../lib/protocol'
import { useStore } from '../../lib/store'
import { toast } from '../../lib/toast'
import { useLinkState } from '../../lib/useBus'
import { EMPTY_DRAFT_TEXT, blockingReason } from './blocking'
import { draft } from './draft'
import { uploading } from './inputs'
import { buildJob } from './job'
import { queueView } from './run/jobs'
import { TOOL, type Draft, type Model } from './types'

export type Press = { reason: string | null; go: () => void }

/** The Generate press — the bar's button and Ctrl+Enter alike: the assistant's draft with the screen's settings as
 *  one job. The prompt box is the assistant's input only; nothing renders it. A blocked press says why. */
export function useGenerate(d: Draft, model: Model | null): Press {
  const linkOn = useLinkState() === 'on'
  const engines = useStore(presence, p => p?.engines)
  const all = useStore(jobs, m => m)
  const busy = useStore(uploading, n => n)
  const waiting = useMemo(() => queueView(all.values()).waiting.length, [all])
  const states = engines ? Object.values(engines) : []
  const reason = d.draft.trim() ? blockingReason({
    linkOn, engineOffline: states.length > 0 && states.every(s => s === 'down'), model, prompt: d.draft,
    refCount: d.references.length, uploading: busy, waiting, draft: d,
  }) : EMPTY_DRAFT_TEXT
  return {
    reason,
    go: () => {
      if (reason || !model) { toast(reason ?? 'Pick a model'); return }
      bus.request('job.submit', { tool: TOOL, kind: 'image', params: buildJob(draft.get(), model) }).catch((e: BusError) => toast(e.text))
    },
  }
}
