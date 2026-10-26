import { useStore } from '../../lib/store'
import { Button } from '../../ui/Button'
import { Field } from '../../ui/Field'
import type { Detail, HouseWords } from './api'
import { buildHouse, edit, pressing, type Form } from './load'
import { Plates } from './Plates'
import s from './Stage.module.css'

const WORDS: { key: keyof HouseWords; label: string }[] = [
  { key: 'era', label: 'Era' }, { key: 'dress', label: 'Dress' }, { key: 'hair', label: 'Hair' }, { key: 'size', label: 'Size' },
]

/** The house of an approved set whose audience is seen: Era, Dress, Hair, Size, Build house; then its plates, its pan
 *  and its change line, as the stage's. */
export function House({ d, form }: { d: Detail; form: Form }) {
  const busy = useStore(pressing, x => x)
  const rendering = d.draft?.state === 'rendering'
  return (
    <section className={s.section} data-region="stage-house">
      <h3 className={s.head}>House</h3>
      <div className={s.facts}>
        {WORDS.map(w => [
          <span key={`${w.key}-l`} className={s.lab}>{w.label}</span>,
          <Field key={w.key} label={w.label} value={form.house[w.key]}
            onChange={v => edit(f => ({ ...f, house: { ...f.house, [w.key]: v } }))} />,
        ])}
      </div>
      <div className={s.presses}>
        <Button onClick={() => void buildHouse()} disabled={busy || rendering} data-region="house-build">Build house</Button>
      </div>
      <Plates which="house" d={d} />
    </section>
  )
}
