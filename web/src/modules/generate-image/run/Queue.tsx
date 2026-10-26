import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { bus } from '../../../lib/bus'
import { count } from '../../../lib/format'
import { jobs } from '../../../lib/live'
import type { BusError, Job } from '../../../lib/protocol'
import { useStore } from '../../../lib/store'
import { toast } from '../../../lib/toast'
import { Progress } from '../../../ui/Progress'
import { TOOL } from '../types'
import { continueLabel, doneLine, planLine, queueView, runningText, verdictOf } from './jobs'
import s from './Run.module.css'

const act = (t: string, job: string): void => {
  bus.request(t, { job }).catch((e: BusError) => toast(e.text))
}

/** One line: running job, waiting count, failure or a short "Done"; `fallback` when there is none. */
export function Queue({ fallback = null }: { fallback?: ReactNode }) {
  const all = useStore(jobs, m => m)
  const v = useMemo(() => queueView(all.values()), [all])
  const [done, setDone] = useState<string | null>(null)
  const since = useRef(new Map<string, number>())
  const last = useRef(new Map<string, Job['state']>())
  useEffect(() => {
    const now = Date.now() / 1000
    for (const j of all.values()) {
      if (j.tool !== TOOL) continue
      const before = last.current.get(j.id)
      if (j.state === 'running' && !since.current.has(j.id)) since.current.set(j.id, now)
      const start = since.current.get(j.id)
      if (j.state === 'done' && before && before !== 'done' && start !== undefined) {
        setDone(doneLine(j, now - start))
      }
      last.current.set(j.id, j.state)
    }
  }, [all])
  useEffect(() => {
    if (!done) return
    const t = setTimeout(() => setDone(null), 4000)
    return () => clearTimeout(t)
  }, [done])

  const { running, waiting, failed } = v
  const verdict = useMemo(() => verdictOf(all.values(), TOOL), [all])
  const lane = running?.lane ?? waiting[0]?.lane ?? null
  // Texts shrink with an ellipsis; the action buttons never do, so they stay clickable in a narrow window.
  const waitLine = waiting.length > 0 && <>
    <span className="ell">{count(waiting.length)} waiting in queue ·</span>
    <button type="button" className={s.textBtn} disabled={lane === null}
      onClick={() => { if (lane) bus.request('job.clear', { lane }).catch((e: BusError) => toast(e.text)) }}>Clear</button>
  </>
  if (!running && !waiting.length && !failed && !done && !verdict) return <>{fallback}</>
  const r = running ? runningText(running) : null
  const label = running ? continueLabel(running) : null
  return (
    <div className={s.queue} data-region="queue" aria-live="polite">
      {running && r && <>
        {label && <span className="ell" data-region="continue">{label} ·</span>}
        <b className="ell" title={planLine(running) ?? undefined}>{running.cancel_requested ? 'Cancelling…' : r.left}</b>
        {r.right && <span className="t-meta num ell">{r.right}</span>}
        <span className={s.line}><Progress value={r.value} label="Progress" /></span>
        <button type="button" className={s.textBtn} disabled={running.cancel_requested} onClick={() => act('job.cancel', running.id)}>Cancel</button>
      </>}
      {waitLine}
      {failed && <>
        <span className={s.fail} title={failed.error?.text}>Failed: {failed.error?.text ?? 'unknown error'}</span>
        <button type="button" className={s.textBtn} onClick={() => bus.send('job.dismiss', { job: failed.id })}>Dismiss</button>
      </>}
      {done && !running && <span className={s.done}>{done}</span>}
      {verdict && !running && !done && <span className="t-meta ell" data-region="verdict" title={verdict}>{verdict}</span>}
    </div>
  )
}
