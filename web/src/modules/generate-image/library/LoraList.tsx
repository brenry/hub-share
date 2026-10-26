import { useMemo, type KeyboardEvent, type ReactNode } from 'react'
import { focusInScroller } from '../../../lib/reveal'
import { useStore } from '../../../lib/store'
import { Scroll } from '../../../ui/Scroll'
import { draft, edit } from '../draft'
import { setStrength, stackOf, toggleLora } from '../edits'
import { loras, rememberStrength } from '../loras'
import type { LoraItem } from '../types'
import { OtherRow, SavedRow } from './LoraRow'
import { isNew, others } from './order'
import s from './LoraLibrary.module.css'

/** A saved LoRA whose file is no longer in the folder: shown by its id until it is taken off. */
const gone = (id: string): LoraItem => ({
  id, name: id.split('/').pop() ?? id, file: id.split('/').pop() ?? id, fileTriggers: [],
  cover: null, strength: null, defaultStrength: 1, addedAt: 0,
})

/** A raised sheet: its model and that model's own rows on top, then the model's LoRAs (none while the sheet has no
 *  model). The edges sit on the bar's margin, so the rows line up with the button that raised it. */
export function SheetFrame({ label, region, head, list }: { label: string; region: string; head: ReactNode; list: boolean }) {
  return (
    <section className={s.lib} aria-label={label} data-region={region}>
      <div className={s.head}>{head}</div>
      {list && <LoraList />}
    </section>
  )
}

/** The LoRAs saved for the draft's model (strength on each), a rule, then the rest of its folder. What is on and how
 *  strong is the draft's, kept per model and saved by itself; the folder decides what is listed. */
function LoraList() {
  const d = useStore(draft, v => v)
  const { items, ready } = useStore(loras, v => v)
  const stack = stackOf(d)
  const byId = useMemo(() => new Map(items.map(l => [l.id, l])), [items])
  const saved = useMemo(() => stack.map(a => ({ a, l: byId.get(a.id) ?? gone(a.id) })), [stack, byId])
  const rest = useMemo(() => others(items, stack), [items, stack])
  const order = useMemo(() => [...saved.map(x => x.l), ...rest], [saved, rest])
  const now = Date.now()

  const select = (id: string) => edit(x => ({ ...x, selected: id }))
  const flip = (l: LoraItem, strength: number) => edit(x => toggleLora(x, l.id, strength))
  const strength = (id: string, v: number, done: boolean) => {
    edit(x => setStrength(x, id, v))
    if (done) rememberStrength(id, v)
  }
  const onKey = (e: KeyboardEvent) => {
    if ((e.target as HTMLElement).closest('button')) return
    const at = (e.target as HTMLElement).closest('[data-lora]')?.getAttribute('data-lora') ?? d.selected
    const i = order.findIndex(l => l.id === at)
    const cur = order[i]
    if ((e.key === ' ' || e.key === 'Enter') && cur) { e.preventDefault(); flip(cur, cur.strength ?? cur.defaultStrength); return }
    const step = e.key === 'ArrowDown' ? 1 : e.key === 'ArrowUp' ? -1 : 0
    if (!step) return
    e.preventDefault()
    const next = order[Math.max(0, Math.min(order.length - 1, i + step))]
    if (!next) return
    select(next.id)
    requestAnimationFrame(() => {
      const el = document.getElementById(`lora-${next.id}`)
      if (el) focusInScroller(el)
    })
  }
  const tabbable = order.some(l => l.id === d.selected) ? d.selected : order[0]?.id

  return (
    <Scroll name="lora-list" className={s.list} role="listbox" aria-label="LoRAs" aria-multiselectable="true" onKeyDown={onKey}>
      {saved.map(({ a, l }) => (
        <SavedRow key={l.id} lora={l} strength={a.strength} selected={l.id === d.selected} tabbable={l.id === tabbable}
          onSelect={() => select(l.id)} onStrength={(v, done) => strength(l.id, v, done)} onOff={() => flip(l, a.strength)} />
      ))}
      {saved.length > 0 && rest.length > 0 && <hr className={s.rule} />}
      {rest.map(l => (
        <OtherRow key={l.id} lora={l} fresh={isNew(l, now)} selected={l.id === d.selected} tabbable={l.id === tabbable}
          onSelect={() => select(l.id)} onOn={() => flip(l, l.strength ?? l.defaultStrength)} />
      ))}
      {ready && order.length === 0 && <p className={s.empty}>No LoRAs in this model's folder</p>}
    </Scroll>
  )
}
