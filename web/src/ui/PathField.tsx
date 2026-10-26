import { useEffect, useRef, useState, type ReactNode } from 'react'
import { errorText } from '../lib/http'
import { Button } from './Button'
import { Field, Value } from './Field'
import type { IconName } from './Icon'
import { Row } from './Sheet'
import s from './PathField.module.css'

/** Saves one value; rejects with the server's one plain line. */
type Save = (value: string) => Promise<unknown>

type Props = {
  label: string
  value: string
  onSave: Save
  icon?: IconName
  trail?: ReactNode
  rowLabel?: string
  remove?: () => Promise<unknown>
  startOpen?: boolean
  onClose?: () => void
}

/** A path shown like a field: click to edit, Enter or leaving saves, Esc cancels. */
export function PathRow({ label, value, onSave, icon = 'folder', trail, rowLabel = label, remove, startOpen = false, onClose }: Props) {
  const [open, setOpen] = useState(startOpen)
  const [draft, setDraft] = useState(value)
  const [error, setError] = useState<string | null>(null)
  const done = useRef(false)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { if (open) { input.current?.focus(); input.current?.select() } }, [open])

  const begin = () => { done.current = false; setDraft(value); setError(null); setOpen(true) }
  const close = () => { done.current = true; setOpen(false); onClose?.() }
  const cancel = () => { setError(null); close() }
  const commit = () => {
    if (done.current) return
    const next = draft.trim()
    if (next === value || next === '') { cancel(); return }
    done.current = true
    onSave(next).then(close, e => { done.current = false; setError(errorText(e)) })
  }
  const drop = remove && (() => { setError(null); remove().catch(e => setError(errorText(e))) })

  return (
    <>
      <Row label={rowLabel} trail={drop && !open ? <Button variant="ghost" icon="x" aria-label={`Remove ${value}`} onClick={drop} /> : undefined}>
        {open
          ? <div className={s.edit} onBlur={commit}>
              <Field label={label} icon={icon} value={draft} onChange={v => { setDraft(v); setError(null) }}
                onEnter={commit} onEscape={cancel} inputRef={input} />
            </div>
          : <div className={s.path} role="button" tabIndex={0} aria-label={`Edit ${label}`} title={value} onClick={begin}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); begin() } }}>
              <Value icon={icon} trail={trail}>{value}</Value>
            </div>}
      </Row>
      {error && <p className={s.rowError} role="alert">{error}</p>}
    </>
  )
}

type ListProps = { label: string; name: string; paths: string[]; onSave: (paths: string[]) => Promise<unknown> }

/** A list of folders: edit in place, remove with ×, "Add folder" opens an empty row. */
export function FolderList({ label, name, paths, onSave }: ListProps) {
  const [adding, setAdding] = useState(false)
  const swap = (i: number) => (v: string) => onSave(paths.map((p, j) => (j === i ? v : p)))
  return (
    <>
      {paths.length === 0 && !adding && <Row label={label}><span className="t-cap">None</span></Row>}
      {paths.map((p, i) => (
        <PathRow key={p} label={`${name} ${i + 1}`} rowLabel={i === 0 ? label : ''} value={p} onSave={swap(i)}
          remove={() => onSave(paths.filter((_, j) => j !== i))} />
      ))}
      {adding
        ? <PathRow label={`New ${name.toLowerCase()}`} rowLabel={paths.length === 0 ? label : ''} value="" startOpen
            onSave={v => onSave([...paths, v])} onClose={() => setAdding(false)} />
        : <Row label=""><Button icon="plus" small onClick={() => setAdding(true)}>Add folder</Button></Row>}
    </>
  )
}
