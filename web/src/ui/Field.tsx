import type { ReactNode, Ref } from 'react'
import { Icon, type IconName } from './Icon'
import { cx } from './cx'
import s from './Field.module.css'

type Props = {
  label: string
  value: string
  onChange?: (v: string) => void
  icon?: IconName
  placeholder?: string
  onEnter?: () => void
  onEscape?: () => void
  clearable?: boolean
  readOnly?: boolean
  type?: 'text' | 'password'
  trail?: ReactNode
  inputRef?: Ref<HTMLInputElement>
  className?: string | undefined
  list?: string
}

/** A one-line input in a well. Esc clears a clearable field. */
export function Field(p: Props) {
  const clear = p.clearable && p.value !== '' && p.onChange
  return (
    <label className={cx(s.field, p.readOnly && s.ro, p.className)}>
      {p.icon && <Icon name={p.icon} />}
      <input aria-label={p.label} value={p.value} placeholder={p.placeholder} readOnly={p.readOnly} ref={p.inputRef} type={p.type ?? 'text'}
        spellCheck={false} {...(p.list ? { list: p.list } : {})}
        onChange={e => p.onChange?.(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && !e.ctrlKey && p.onEnter) { e.preventDefault(); p.onEnter() }
          if (e.key === 'Escape') {
            if (p.onEscape) p.onEscape()
            else if (p.clearable) p.onChange?.('')
          }
        }} />
      {clear && <button type="button" className={s.clear} aria-label={`Clear ${p.label.toLowerCase()}`} onClick={() => p.onChange?.('')}><Icon name="x" small /></button>}
      {p.trail}
    </label>
  )
}

/** A read-only value shown like a field: paths, addresses. */
export function Value({ icon, children, trail }: { icon?: IconName; children: ReactNode; trail?: ReactNode }) {
  return (
    <div className={cx(s.field, s.ro)}>
      {icon && <Icon name={icon} />}
      <span className={cx(s.v, 'ell')}>{children}</span>
      {trail}
    </div>
  )
}
