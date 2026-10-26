import s from './Switch.module.css'
import { cx } from './cx'

export function Switch({ on, label, onChange, disabled = false }: { on: boolean; label: string; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} disabled={disabled}
      className={cx(s.sw, on && s.on)} onClick={() => onChange(!on)} />
  )
}
