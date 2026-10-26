import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { cx } from './cx'
import s from './DragNumber.module.css'

type Props = {
  label: string
  value: number
  min: number
  max: number
  /** The value's resolution; the shown number snaps to it. */
  step: number
  /** Change per pixel of horizontal drag. */
  perPx: number
  reset?: number
  onChange: (v: number) => void
  /** The final value, once the pointer is released or a key is handled. */
  onCommit?: (v: number) => void
  className?: string | undefined
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
const snap = (v: number, step: number) => Math.round(v / step) * step
const decimals = (step: number) => Math.max(0, Math.ceil(-Math.log10(step)))

/** A number set by dragging: press on it and move left or right; the value follows the mouse and snaps to `step`.
 *  Arrow keys step it (Shift: ten steps); double-click or Backspace puts it back to `reset`. */
export function DragNumber({ label, value, min, max, step, perPx, reset, onChange, onCommit, className }: Props) {
  const start = useRef<{ x: number; v: number } | null>(null)
  const [dragging, setDragging] = useState(false)
  const put = (v: number, commit: boolean) => {
    const next = clamp(snap(v, step), min, max)
    if (next !== value) onChange(next)
    if (commit) onCommit?.(next)
  }
  const down = (e: PointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0) return
    start.current = { x: e.clientX, v: value }
    e.currentTarget.setPointerCapture(e.pointerId)
    setDragging(true)
  }
  const move = (e: PointerEvent<HTMLButtonElement>) => {
    if (!start.current) return
    put(start.current.v + (e.clientX - start.current.x) * perPx, false)
  }
  const up = (e: PointerEvent<HTMLButtonElement>) => {
    if (!start.current) return
    const v = start.current.v + (e.clientX - start.current.x) * perPx
    start.current = null
    setDragging(false)
    put(v, true)
  }
  const key = (e: KeyboardEvent<HTMLButtonElement>) => {
    const big = e.shiftKey ? 10 : 1
    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') { e.preventDefault(); put(value + step * big, true) }
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') { e.preventDefault(); put(value - step * big, true) }
    else if ((e.key === 'Backspace' || e.key === 'Delete') && reset !== undefined) { e.preventDefault(); put(reset, true) }
  }
  return (
    <button type="button" className={cx(s.num, 'num', dragging && s.drag, className)} aria-label={label} title={`${label}: drag left or right`}
      onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onKeyDown={key}
      onDoubleClick={() => { if (reset !== undefined) put(reset, true) }}>
      {value.toFixed(decimals(step))}
    </button>
  )
}
