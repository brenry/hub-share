import s from './Progress.module.css'

/** `value` 0–1, or null for an indeterminate bar. Moves by transform only. */
export function Progress({ value, label }: { value: number | null; label: string }) {
  const v = value === null ? null : Math.max(0, Math.min(1, value))
  return (
    <div className={s.track} role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100}
      {...(v === null ? {} : { 'aria-valuenow': Math.round(v * 100) })}>
      <span className={v === null ? s.indet : s.fill} style={v === null ? undefined : { transform: `scaleX(${v})` }} />
    </div>
  )
}
