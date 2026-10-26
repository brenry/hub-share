import { useId, type CSSProperties, type ReactNode, type Ref } from 'react'
import { cx } from './cx'
import s from './Popover.module.css'

/** A stable anchor name for a trigger and its popover. */
export function useAnchor(): { id: string; anchor: { 'data-anchor': true; style: CSSProperties } } {
  const raw = useId().replace(/[^\w-]/g, '')
  const name = `--a${raw}`
  return { id: `pop${raw}`, anchor: { 'data-anchor': true, style: { '--anchor': name } as CSSProperties } }
}

type Props = {
  id: string
  anchorStyle: CSSProperties
  children: ReactNode
  manual?: boolean
  className?: string | undefined
  onToggle?: (open: boolean) => void
  ref?: Ref<HTMLDivElement>
  label?: string
}

/** Native top-layer popover placed under its anchor; it never adds scroll range to the page. */
export function Popover({ id, anchorStyle, children, manual = false, className, onToggle, ref, label }: Props) {
  return (
    <div id={id} ref={ref} popover={manual ? 'manual' : 'auto'} className={cx(s.pop, className)} style={anchorStyle}
      aria-label={label} onToggle={e => onToggle?.((e as unknown as ToggleEvent).newState === 'open')}>
      {children}
    </div>
  )
}
