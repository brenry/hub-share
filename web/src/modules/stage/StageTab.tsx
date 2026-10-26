import { useState } from 'react'
import type { ToolProps } from '../../lib/module'
import { useStore } from '../../lib/store'
import { Field } from '../../ui/Field'
import { Live } from '../../ui/Live'
import { Scroll } from '../../ui/Scroll'
import { cx } from '../../ui/cx'
import type { Summary } from './api'
import { AudienceChoice, Build } from './Build'
import { House } from './House'
import { choose, current, detail, form, pressing, problem, sets, useStage } from './load'
import { Plates, PromptBox } from './Plates'
import s from './Stage.module.css'

/** New set, then every set the hub holds, approved or drafted: its wide plate, its name, `approved` or `draft`. */
function Sets({ all, open }: { all: readonly Summary[] | null; open: string | null }) {
  const [name, setName] = useState('')
  const typed = open !== null && !all?.some(x => x.name === open) ? open : null
  return (
    <Scroll name="stage-list" className={s.list} data-region="stage-list">
      <Field label="New set" placeholder="New set" value={name} onChange={setName}
        onEnter={() => { choose(name); setName('') }} />
      <div role="listbox" aria-label="Sets" className={s.sets}>
        {all?.length === 0 && typed === null ? <div className={s.empty}>No set</div> : null}
        {[...(all ?? []), ...(typed ? [{ name: typed, approved: false, thumb: null, state: 'none' } as const] : [])].map(x => (
          <button key={x.name} type="button" role="option" aria-selected={x.name === open} data-set={x.name}
            className={cx(s.set, x.name === open && s.on)} onClick={() => choose(x.name)}>
            <span className={s.thumb}>{x.thumb ? <img src={x.thumb} alt="" draggable={false} /> : null}</span>
            <span className="ell">{x.name}</span>
            {x.approved ? <span className={s.mark} data-mark="approved">approved</span>
              : x.state !== 'none' ? <span className={s.mark} data-mark="draft">draft</span> : null}
          </button>
        ))}
      </div>
    </Scroll>
  )
}

/** The Stage tab: the sets at the left; the open set's inputs (before Approve) or its audience and
 *  house (after), then its plates and pan with their presses; the bar under it. */
export default function StageTab({ visible }: ToolProps) {
  useStage(visible)
  const all = useStore(sets, x => x)
  const open = useStore(current, x => x)
  const d = useStore(detail, x => x)
  const f = useStore(form, x => x)
  const busy = useStore(pressing, x => x)
  const pressed = useStore(problem, x => x)
  const line = pressed ?? (d?.draft && d.draft.state !== 'failed' ? d.draft.problem : null)
  const summary = all?.find(x => x.name === open) ?? null
  const rendering = d?.draft?.state === 'rendering'
  const approved = !!d?.approved
  const audience = summary?.audience ?? f?.audience ?? 'seen'
  const say = line ? <div className={s.problem} role="status" data-region="stage-problem">{line}</div> : null
  return (
    <div className={s.tab} data-region="stage">
      <div className={s.main}>
        <Sets all={all} open={open} />
        {open !== null && f ? <>
          <Scroll name="stage-inputs" className={s.left}>
            <h2 className={s.who}>{open}{approved ? <span className={s.mark}>approved</span> : null}</h2>
            {approved && d ? <>
              <AudienceChoice value={audience} disabled={busy || rendering} />
              {audience === 'seen' ? <House d={d} form={f} /> : null}
            </> : <Build form={f} rendering={rendering} />}
          </Scroll>
          <Scroll name="stage-plates" className={s.right}>
            {d ? <Plates which="stage" d={d} /> : <PromptBox which="stage" />}
            {say}
          </Scroll>
        </> : <div className={s.none}>{say}</div>}
      </div>
      <footer className={s.bar} data-region="stage-bar">
        <span className={cx(s.grow, 'ell')}>{open ?? 'Stage'}</span>
        <Live className={s.liveFlat} />
      </footer>
    </div>
  )
}
