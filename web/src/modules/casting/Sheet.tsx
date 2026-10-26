import { jobs } from '../../lib/live'
import { useStore } from '../../lib/store'
import { Button } from '../../ui/Button'
import { Progress } from '../../ui/Progress'
import { VIEW_LABELS, viewsOf } from './api'
import { again, approve, cast, pressing } from './load'
import { isCast, jobLine, shown, type SheetDraft } from './form'
import s from './Casting.module.css'

/** The cast job's line and bar while it is queued or running. */
function JobState({ draft }: { draft: SheetDraft }) {
  const job = useStore(jobs, m => (draft.job ? m.get(draft.job) ?? null : null))
  const line = jobLine(draft, job)
  const live = job && (job.state === 'queued' || job.state === 'running') ? job : null
  const p = live?.progress
  const value = p ? (p.steps > 0 ? p.step / p.steps : p.pct > 0 ? p.pct / 100 : null) : null
  if (!line) return null
  return (
    <div className={s.job} data-region="casting-job" data-state={live?.state ?? draft.state}>
      <span className="ell" title={line}>{line}</span>
      {live || draft.state === 'rendering' ? <span className={s.jobBar}><Progress value={value} label="Casting" /></span> : null}
    </div>
  )
}

/** What the presses do: the character's own sheet's by default, a costume's when given. */
export type Acts = { cast: () => Promise<void>; again: () => Promise<void>; approve: () => Promise<void> }
const BASE: Acts = { cast, again, approve }

/** The presses first: Cast (Cast again once the character is cast), Again (after a sheet or a failure), Approve for a sheet
 *  waiting for its Approve; the job's state; then the role's views, each labelled, the orbit with a player beside
 *  them: a cast sheet's six in two rows (front, left, back; right, face, three-quarter face), an extra's four 2 × 2
 *  (front, left; right, face). */
export function Sheet({ draft, acts = BASE }: { draft: SheetDraft; acts?: Acts }) {
  const busy = useStore(pressing, x => x)
  const sheet = shown(draft)
  const role = draft.role ?? 'cast'
  const rendering = draft.state === 'rendering'
  const ready = draft.state === 'ready'
  return (
    <section className={s.sheet} data-region="casting-sheet" data-approved={sheet?.approved || undefined}>
      <div className={s.presses}>
        <Button onClick={() => void acts.cast()} disabled={busy || rendering} data-region="casting-cast">
          {isCast(draft) && !ready ? 'Cast again' : 'Cast'}
        </Button>
        {ready || draft.state === 'failed'
          ? <Button onClick={() => void acts.again()} disabled={busy} data-region="casting-again">Again</Button> : null}
        {ready ? <Button onClick={() => void acts.approve()} disabled={busy} data-region="casting-approve">Approve</Button> : null}
      </div>
      <JobState draft={draft} />
      <div className={s.views} data-region="casting-views" data-role={role}>
        {viewsOf(role).map(v => {
          const src = sheet?.views[v]
          return (
            <figure key={v} className={s.view} data-view={v}>
              <div className={s.viewPic}>{src ? <img src={src} alt={VIEW_LABELS[v]} draggable={false} /> : null}</div>
              <figcaption className={s.cap}>{VIEW_LABELS[v]}</figcaption>
            </figure>
          )
        })}
        <div className={s.orbit}>
          {sheet?.orbit ? <video key={sheet.orbit} src={sheet.orbit} controls loop playsInline preload="metadata"
            data-region="casting-orbit" /> : null}
        </div>
      </div>
    </section>
  )
}
