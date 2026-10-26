import { Icon } from './Icon'
import s from './Stepper.module.css'

import { cx } from './cx'

export function Stepper({ label, value, min, max, small = false, onChange }: { label: string; value: number; min: number; max: number; small?: boolean; onChange: (v: number) => void }) {
  return (
    <div role="group" aria-label={label} className={cx(s.box, small && s.small)}>
      <button type="button" aria-label={`Fewer ${label.toLowerCase()}`} disabled={value <= min} onClick={() => onChange(value - 1)}><Icon name="minus" small /></button>
      <output className="num" aria-live="polite">{value}</output>
      <button type="button" aria-label={`More ${label.toLowerCase()}`} disabled={value >= max} onClick={() => onChange(value + 1)}><Icon name="plus" small /></button>
    </div>
  )
}
