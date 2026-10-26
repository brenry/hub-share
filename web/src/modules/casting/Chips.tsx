import { useCallback, useState } from 'react'
import { Field } from '../../ui/Field'
import { cx } from '../../ui/cx'
import type { CostumeChip } from './api'
import { closeCostume, openCostume } from './costume'
import s from './Casting.module.css'

/** The chips over the character's boxes: its own sheet, one chip per costume (the hub's, then the one open if it is
 *  not among them yet), and `+ Costume` (a name; Enter opens it). */
export function Chips({ name, chips, open }: { name: string; chips: readonly CostumeChip[]; open: string | null }) {
  const [adding, setAdding] = useState<string | null>(null)
  const focus = useCallback((el: HTMLInputElement | null) => el?.focus(), [])
  const all = open !== null && !chips.some(c => c.variant === open)
    ? [...chips, { variant: open, state: 'none', approved: false, earlier: false, thumb: null } satisfies CostumeChip]
    : chips
  const add = () => {
    const v = (adding ?? '').trim()
    if (!v) return
    setAdding(null)
    void openCostume(v)
  }
  return (
    <div className={s.chips} data-region="casting-chips" role="tablist" aria-label="Costumes">
      <button type="button" role="tab" aria-selected={open === null} className={cx(s.chip, open === null && s.on)}
        data-chip="" onClick={closeCostume}>
        <span className="ell">{name}</span>
      </button>
      {all.map(c => (
        <button key={c.variant} type="button" role="tab" aria-selected={open === c.variant} data-chip={c.variant}
          data-approved={c.approved || undefined} className={cx(s.chip, open === c.variant && s.on)}
          onClick={() => void openCostume(c.variant)}>
          {c.thumb ? <img src={c.thumb} alt="" draggable={false} /> : null}
          <span className="ell">{c.variant}</span>
          {c.earlier ? <span className={s.cast} data-earlier>earlier face</span> : null}
        </button>
      ))}
      {adding === null
        ? <button type="button" className={s.chip} data-region="casting-add" onClick={() => setAdding('')}>+ Costume</button>
        : <Field label="Costume name" value={adding} className={s.chipName} inputRef={focus}
            onChange={setAdding} onEnter={add} onEscape={() => setAdding(null)} />}
    </div>
  )
}
