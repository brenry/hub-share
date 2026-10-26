import { jobs } from '../../lib/live'
import { useStore } from '../../lib/store'
import { Button } from '../../ui/Button'
import { Field } from '../../ui/Field'
import { Progress } from '../../ui/Progress'
import { HOUSE_PLATES, PLATE_NAMES, STAGE_PLATES, type Detail, type Draft, type File, type HousePlate, type Mode, type StagePlate } from './api'
import { again, approve, change, discard, form, houseChange, jobLine, pressing, setPrompt, words } from './load'
import s from './Stage.module.css'

/** The stage's plates or the house's: which plates, which drafts are theirs, and their change press. */
export type Which = 'stage' | 'house'
type Plate = StagePlate | HousePlate
const CONF: Record<Which, { plates: readonly Plate[]; modes: readonly Mode[]; change: () => Promise<void>; field: string }> = {
  stage: { plates: STAGE_PLATES, modes: ['build', 'change'], change, field: 'Change' },
  house: { plates: HOUSE_PLATES, modes: ['house', 'house-change'], change: houseChange, field: 'House change' },
}

/** The pan's Prompt box: sent as typed after the fields with that pan's presses; held by the hub in memory
 *  only. */
export function PromptBox({ which }: { which: Which }) {
  const text = useStore(form, f => f?.prompts[which] ?? '')
  return (
    <div className={s.promptBox}>
      <span className={s.lab}>Prompt</span>
      <textarea className={s.prompt} aria-label="Prompt" value={text} rows={4} spellCheck={false}
        data-region={`${which}-prompt`} onChange={e => setPrompt(which, e.target.value)} />
    </div>
  )
}

/** The job's line and bar while it is queued or running: its title, `Step i of 2 · Pan|Plates`, its percentage. */
function JobRow({ which, draft }: { which: Which; draft: Draft }) {
  const job = useStore(jobs, m => (draft.job ? m.get(draft.job) ?? null : null))
  const line = jobLine(draft, job)
  const live = job && (job.state === 'queued' || job.state === 'running') ? job : null
  const p = live?.progress
  if (!line) return null
  return (
    <div className={s.job} data-region={`${which}-job`} data-state={live?.state ?? draft.state}>
      <span className="ell" title={line}>{line}</span>
      {live || draft.state === 'rendering'
        ? <span className={s.jobBar}><Progress value={p && p.pct > 0 ? p.pct / 100 : null} label={which === 'stage' ? 'Stage' : 'House'} /></span>
        : null}
    </div>
  )
}

/** One labelled row of plates; an empty frame where a plate is not there yet. */
function Row({ plates, files, row, label }: {
  plates: readonly Plate[]; files: Partial<Record<Plate, File>> | null; row: 'approved' | 'new'; label: string | null
}) {
  return (
    <div className={s.plateRow} data-row={row}>
      {label ? <span className={s.rowLab}>{label}</span> : null}
      <div className={s.plates} style={{ gridTemplateColumns: `repeat(${plates.length}, minmax(0, 1fr))` }}>
        {plates.map(p => {
          const f = files?.[p]
          return (
            <figure key={p} className={s.plate} data-plate={p}>
              <div className={s.platePic}>{f ? <img src={f.url} alt={PLATE_NAMES[p]} draggable={false} /> : null}</div>
              <figcaption className={s.cap}>{PLATE_NAMES[p]}</figcaption>
            </figure>
          )
        })}
      </div>
    </div>
  )
}

/** The presses for a draft (Approve when ready; Again and Discard when ready or failed), its job, the plates (the
 *  approved row above the new one when a change waits for its Approve), the pan with a player, and on approved plates
 *  the change line. */
export function Plates({ which, d }: { which: Which; d: Detail }) {
  const c = CONF[which]
  const busy = useStore(pressing, x => x)
  const typed = useStore(words, x => (which === 'stage' ? x.change : x.house))
  const draft = d.draft && c.modes.includes(d.draft.mode) ? d.draft : null
  const rendering = d.draft?.state === 'rendering'
  const ready = draft?.state === 'ready'
  const done = ready || draft?.state === 'failed'
  const old = (which === 'stage' ? d.approved?.plates : d.approved?.house) ?? null
  const fresh = ready ? draft?.plates ?? null : null
  const pan = fresh ? draft?.pan?.url ?? null : (which === 'stage' ? d.approved?.pan_url : d.approved?.house_pan_url) ?? null
  const off = busy || rendering
  return (
    <section className={s.section} data-region={`${which}-plates`} data-approved={old && !fresh ? true : undefined}>
      <PromptBox which={which} />
      {done ? <div className={s.presses}>
        {ready ? <Button onClick={() => void approve()} disabled={off} data-region={`${which}-approve`}>Approve</Button> : null}
        <Button onClick={() => void again()} disabled={off} data-region={`${which}-again`}>Again</Button>
        <Button variant="ghost" onClick={() => void discard()} disabled={off} data-region={`${which}-discard`}>Discard</Button>
      </div> : null}
      {draft ? <JobRow which={which} draft={draft} /> : null}
      {old && fresh ? <>
        <Row plates={c.plates} files={old} row="approved" label="Approved" />
        <Row plates={c.plates} files={fresh} row="new" label={draft?.words ? `New · ${draft.words}` : 'New'} />
      </> : <Row plates={c.plates} files={fresh ?? old} row={fresh ? 'new' : 'approved'} label={null} />}
      {pan ? <video key={pan} className={s.pan} src={pan} controls playsInline preload="metadata" data-region={`${which}-pan`} /> : null}
      {old ? <div className={s.row} data-region={`${which}-change`}>
        <Field label={c.field} value={typed} className={s.grow}
          onChange={v => words.set(w => (which === 'stage' ? { ...w, change: v } : { ...w, house: v }))}
          onEnter={() => { if (!off) void c.change() }} />
        <Button onClick={() => void c.change()} disabled={off} data-region={`${which}-change-press`}>Change</Button>
      </div> : null}
    </section>
  )
}
