import { cx } from './cx'
import s from './Select.module.css'

type Option = { value: string; label: string }

/** A native select, styled as a field. */
export function Select({ label, value, options, onChange, disabled = false, className }: {
  label: string; value: string; options: Option[]; onChange: (v: string) => void; disabled?: boolean; className?: string | undefined
}) {
  return (
    <select className={cx(s.select, className)} aria-label={label} value={value} disabled={disabled} onChange={e => onChange(e.target.value)}>
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}
