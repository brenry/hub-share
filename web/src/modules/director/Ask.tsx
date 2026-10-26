import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Field } from '../../ui/Field'
import { Select } from '../../ui/Select'
import s from './Scripts.module.css'

/** One field of an ask: a line of text, or (`options`) a choice. */
export type AskField = { key: string; label: string; value: string; options?: string[] }
export type AskT = { x: number; y: number; label: string; fields: AskField[]; done: (v: Record<string, string>) => void
  /** An empty field is kept as empty (a shot's Edit), not a reason to keep nothing. */
  blank?: boolean }

/** What a timeline edit needs typed (a line's words, its speaker), at the pointer. Enter or a press
 *  elsewhere keeps it, Escape leaves it; an empty text field keeps nothing unless the ask is `blank`. */
export function Ask({ ask, onClose }: { ask: AskT | null; onClose: () => void }) {
  const box = useRef<HTMLFormElement>(null)
  const first = useRef<HTMLInputElement>(null)
  const [v, setV] = useState<Record<string, string>>({})
  const keep = useRef<() => void>(() => {})
  useEffect(() => {
    if (!ask) return
    setV(Object.fromEntries(ask.fields.map(f => [f.key, f.value])))
    requestAnimationFrame(() => { first.current?.focus(); first.current?.select() })
    const down = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) keep.current() }
    window.addEventListener('pointerdown', down, true)
    return () => window.removeEventListener('pointerdown', down, true)
  }, [ask, onClose])
  const commit = () => {
    if (!ask) return
    if (!ask.blank && ask.fields.some(f => !f.options && !(v[f.key] ?? '').trim())) return onClose()
    onClose()
    ask.done(Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x.trim()])))
  }
  keep.current = commit
  if (!ask) return null
  const firstText = ask.fields.findIndex(f => !f.options)
  return createPortal(
    <form ref={box} className={s.askAt} aria-label={ask.label} data-region="timeline-ask"
      style={{ left: Math.max(0, Math.min(ask.x, window.innerWidth - 336)), top: Math.max(0, Math.min(ask.y, window.innerHeight - 160)) }}
      onSubmit={e => { e.preventDefault(); commit() }} onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }}>
      {ask.fields.map((f, i) => f.options
        ? <Select key={f.key} label={f.label} value={v[f.key] ?? f.value} options={f.options.map(o => ({ value: o, label: o }))}
            onChange={x => setV(o => ({ ...o, [f.key]: x }))} />
        : <Field key={f.key} label={f.label} value={v[f.key] ?? ''} placeholder={f.label}
            {...(i === firstText ? { inputRef: first } : {})} onChange={x => setV(o => ({ ...o, [f.key]: x }))} onEnter={commit} onEscape={onClose} />)}
    </form>,
    document.body)
}
