import type { KeyboardEvent, ReactNode } from 'react'
import { Popover, useAnchor } from '../../../ui/Popover'
import { cx } from '../../../ui/cx'
import s from './Run.module.css'

/** `hint`: the option's own hover text (a tier's size). */
export type BarOption<T extends string> = { value: T; label: ReactNode; name: string; hint?: string }

/** A small button in the bar that opens a list; the button shows the current choice. */
export function BarMenu<T extends string>({ label, value, options, onPick, button, square = false, hint }: { label: string; value: T; options: BarOption<T>[]; onPick: (v: T) => void; button?: ReactNode; square?: boolean; hint?: string }) {
  const { id, anchor } = useAnchor()
  const current = options.find(o => o.value === value)
  const close = () => document.getElementById(id)?.hidePopover()
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const opts = [...e.currentTarget.querySelectorAll<HTMLButtonElement>('[role=option]')]
    const i = opts.indexOf(document.activeElement as HTMLButtonElement)
    const step = e.key === 'ArrowDown' ? 1 : e.key === 'ArrowUp' ? -1 : 0
    if (!step) return
    e.preventDefault()
    opts[(i + step + opts.length) % opts.length]?.focus()
  }
  return (
    <>
      <button type="button" className={cx(s.barBtn, square && s.square)} popoverTarget={id} aria-haspopup="listbox" aria-label={label} title={current ? `${label}: ${current.name}${hint ? ` · ${hint}` : ''}` : label} {...anchor}>
        {button ?? current?.label}
      </button>
      <Popover id={id} anchorStyle={anchor.style} label={label} className={s.menuPop} onToggle={open => {
        if (open) requestAnimationFrame(() => document.querySelector<HTMLElement>(`#${id} [aria-selected=true]`)?.focus())
      }}>
        <div role="listbox" aria-label={label} className={s.menu} onKeyDown={onKey}>
          {options.map(o => (
            <button key={o.value} type="button" role="option" aria-selected={o.value === value} aria-label={o.name} title={o.hint}
              className={cx(s.option, o.value === value && s.optionOn)} onClick={() => { onPick(o.value); close() }}>{o.label}</button>
          ))}
        </div>
      </Popover>
    </>
  )
}
