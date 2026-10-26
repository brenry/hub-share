import { useRef, type KeyboardEvent, type ReactNode } from 'react'
import { cx } from './cx'
import s from './Segmented.module.css'

type SegOption<T extends string> = { value: T; label: ReactNode; name?: string; reason?: string | null; title?: string }

type Props<T extends string> = {
  label: string
  value: T
  options: SegOption<T>[]
  onChange: (v: T) => void
  onReselect?: (v: T) => void
  className?: string | undefined
}

/** A radiogroup. Disabled options stay focusable and say why in their tooltip. */
export function Segmented<T extends string>({ label, value, options, onChange, onReselect, className }: Props<T>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const pick = (o: SegOption<T>) => {
    if (o.reason) return
    if (o.value === value) onReselect?.(o.value)
    else onChange(o.value)
  }
  const onKey = (e: KeyboardEvent, i: number) => {
    const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
    if (!step) return
    e.preventDefault()
    const n = (i + step + options.length) % options.length
    const o = options[n]
    if (!o) return
    refs.current[n]?.focus({ preventScroll: true })
    if (!o.reason) onChange(o.value)
  }
  return (
    <div role="radiogroup" aria-label={label} className={cx(s.seg, className)}>
      {options.map((o, i) => {
        const on = o.value === value
        return (
          <button key={o.value} type="button" role="radio" aria-checked={on} tabIndex={on ? 0 : -1}
            aria-disabled={o.reason ? true : undefined} aria-label={o.name} title={o.reason ?? o.title}
            ref={el => { refs.current[i] = el }} className={cx(s.opt, on && s.on, o.reason && s.off)}
            onClick={() => pick(o)} onKeyDown={e => onKey(e, i)}>
            {typeof o.label === 'string' ? <span className="ell">{o.label}</span> : o.label}
          </button>
        )
      })}
    </div>
  )
}
