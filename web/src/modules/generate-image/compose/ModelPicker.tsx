import { useMemo, type KeyboardEvent } from 'react'
import { useBusEvent } from '../../../lib/useBus'
import { Icon } from '../../../ui/Icon'
import { Popover, useAnchor } from '../../../ui/Popover'
import { Scroll } from '../../../ui/Scroll'
import { cx } from '../../../ui/cx'
import { loadLoras } from '../loras'
import { loadModels } from '../modelList'
import type { Model } from '../types'
import s from './Compose.module.css'


/** Button + popover listbox of the models whose files are in the model folders, grouped by family.
 *  The list is checked again when the picker opens and when Settings change. */
export function ModelPicker({ models, model, onPick }: { models: Model[]; model: Model | null; onPick: (m: Model) => void }) {
  const { id, anchor } = useAnchor()
  useBusEvent('settings', () => { void loadModels(); if (model) void loadLoras(model.id) })
  const families = useMemo(() => {
    const map = new Map<string, Model[]>()
    for (const m of models) map.set(m.family, [...(map.get(m.family) ?? []), m])
    return [...map.entries()]
  }, [models])
  const close = () => document.getElementById(id)?.hidePopover()
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const opts = [...e.currentTarget.querySelectorAll<HTMLButtonElement>('[role=option]:not(:disabled)')]
    const i = opts.indexOf(document.activeElement as HTMLButtonElement)
    const step = e.key === 'ArrowDown' ? 1 : e.key === 'ArrowUp' ? -1 : 0
    if (!step) return
    e.preventDefault()
    opts[(i + step + opts.length) % opts.length]?.focus()
  }
  return (
    <>
      <button type="button" className={cx(s.model, !model && s.modelNone)} popoverTarget={id} aria-haspopup="listbox" {...anchor} data-region="model-picker">
        <span className="ell"><b>{model?.label ?? 'Choose a model'}</b></span>
        <Icon name="down" small />
      </button>
      <Popover id={id} anchorStyle={anchor.style} label="Models" onToggle={open => {
        if (open) void loadModels()
        if (open) requestAnimationFrame(() => document.querySelector<HTMLElement>(`#${id} [aria-selected=true], #${id} [role=option]:not(:disabled)`)?.focus())
      }}>
        <Scroll name="model-list" className={s.menu} role="listbox" aria-label="Models" onKeyDown={onKey}>
          {models.length === 0 && <p className={s.menuEmpty}>No models found</p>}
          {families.map(([family, list]) => (
            <div key={family} role="group" aria-label={family}>
              <div className={cx(s.menuGroup, 't-label')}>{family}</div>
              {list.map(m => (
                <button key={m.id} type="button" role="option" aria-selected={m.id === model?.id}
                  className={s.option} onClick={() => { onPick(m); close() }}>
                  <span className="ell">{m.label}</span>
                </button>
              ))}
            </div>
          ))}
        </Scroll>
      </Popover>
    </>
  )
}
