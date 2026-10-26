import { useMemo } from 'react'
import { jobs } from '../../../lib/live'
import { useStore } from '../../../lib/store'
import { cx } from '../../../ui/cx'
import { draft, edit } from '../draft'
import { advancedOf, withAdvanced } from '../edits'
import { modelList } from '../modelList'
import { TOOL } from '../types'
import s from './Run.module.css'

/** The seeds the last render used, picture by picture, on the job line while nothing runs. Click one to keep it: that
 *  model's seed is fixed to it, so the next render starts the same way and only what the draft changes changes. A kept
 *  seed is cyan; Random lets it go. The seeds live in the job record, in memory: nothing is written anywhere. */
export function SeedLine() {
  const all = useStore(jobs, m => m)
  const d = useStore(draft, v => v)
  const models = useStore(modelList, m => m)
  const last = useMemo(() => [...all.values()]
    .filter(j => j.tool === TOOL && (j.summary?.seeds?.length ?? 0) > 0)
    .sort((a, b) => b.created - a.created)[0] ?? null, [all])
  const model = models?.find(m => m.id === last?.summary?.model_id) ?? null
  if (!last || !model) return null
  const seeds = last.summary!.seeds!
  const now = advancedOf(d, model).seed
  const kept = now.mode === 'fixed' ? now.value : null
  const keep = (value: number) => edit(x => withAdvanced(x, model, { seed: { mode: 'fixed', value } }))
  return (
    <span className={s.seed} data-region="seed">
      <span>{seeds.length > 1 ? 'Seeds' : 'Seed'}</span>
      {seeds.map((v, i) => (
        <button key={i} type="button" className={cx(s.seedNum, 'num', kept === v && s.seedKept)} aria-pressed={kept === v}
          title={kept === v ? 'Kept: the next render starts from this seed' : 'Keep this seed'} onClick={() => keep(v)}>{v}</button>
      ))}
      {kept !== null && (
        <button type="button" className={s.textBtn} title="Back to a new seed each render"
          onClick={() => edit(x => withAdvanced(x, model, { seed: { mode: 'random' } }))}>Random</button>
      )}
    </span>
  )
}
