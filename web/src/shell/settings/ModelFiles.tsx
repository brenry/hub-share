import { useCallback, useEffect, useRef, useState } from 'react'
import { errorText, getJSON, sendJSON } from '../../lib/http'
import { useBusEvent } from '../../lib/useBus'
import { loadModels } from '../../modules/generate-image/modelList'
import { Button } from '../../ui/Button'
import { Field, Value } from '../../ui/Field'
import { Select } from '../../ui/Select'
import { Row, Section, Tag } from '../../ui/Sheet'
import ps from '../../ui/PathField.module.css'
import s from './ImageModels.module.css'

export type Part = { part: string; label: string; name: string; path: string | null; chosen: boolean }
export type FileModel = { id: string; name: string; kind: string; parts: Part[] }
export type Listing = { models: FileModel[]; files: string[]; loras: string[] }

export const MODEL_FILES = '/api/generate-image/model-files'
/** A part whose file the engine names but cannot find. */
const lacks = (p: Part) => p.path === null && p.name !== ''
const optionLabel = (m: FileModel) =>
  `${m.name}${m.kind === 'video' ? ' · clip' : ''}${m.parts.some(lacks) ? ' · file not found' : ''}${m.parts.some(p => p.chosen) ? ' · yours' : ''}`
/** The model shown first: one whose main file is here but another part is not found (the one an error names),
 *  else one whose main file is here, else the first. */
const here = (m: FileModel) => m.parts.some(p => p.part === 'URLs' && p.path !== null)
const first = (l: Listing) =>
  (l.models.find(m => here(m) && m.parts.some(lacks)) ?? l.models.find(here) ?? l.models[0])?.id ?? ''
const shown = (p: Part) => p.path ?? (p.name ? `Not found: ${p.name}` : 'The engine picks it')

/** One part's file: shown like a path; click to type or pick one (any file on this computer, offered from the
 *  model and LoRA folders); Enter saves, Esc cancels. */
function FileRow({ part, list, busy, save, reset }: {
  part: Part; list: string; busy: boolean; save: (path: string) => Promise<unknown>; reset: () => void
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const done = useRef(false)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { if (open) { input.current?.focus(); input.current?.select() } }, [open])
  const begin = () => { if (busy) return; done.current = false; setDraft(part.path ?? ''); setError(null); setOpen(true) }
  const close = () => { done.current = true; setOpen(false) }
  const commit = () => {
    if (done.current) return
    const next = draft.trim()
    if (next === '' || next === part.path) { setError(null); close(); return }
    done.current = true
    save(next).then(close, e => { done.current = false; setError(errorText(e)) })
  }
  const tag = part.chosen ? <Tag tone="accent">Yours</Tag> : lacks(part) ? <Tag tone="warn">Missing</Tag> : undefined
  return (
    <>
      <Row label={part.label} trail={part.chosen && !open
        ? <Button variant="ghost" icon="x" disabled={busy} aria-label={`Put back the engine's own ${part.label.toLowerCase()}`} onClick={reset} />
        : undefined}>
        {open
          ? <div className={ps.edit} onBlur={commit} data-part={part.part}>
              <Field label={`${part.label} file`} icon="folder" value={draft} list={list} placeholder="/path/to/file.safetensors"
                onChange={v => { setDraft(v); setError(null) }} onEnter={commit} onEscape={() => { setError(null); close() }} inputRef={input} />
            </div>
          : <div className={ps.path} role="button" tabIndex={0} aria-label={`Choose the ${part.label.toLowerCase()} file`} title={part.path ?? part.name}
              data-part={part.part} onClick={begin} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); begin() } }}>
              <Value icon="folder" trail={tag}>{shown(part)}</Value>
            </div>}
      </Row>
      {error && <p className={ps.rowError} role="alert">{error}</p>}
    </>
  )
}

/** Model files: each model's own files (main weights, text encoder, VAEs, extra files, its LoRAs), pointed at
 *  other files on disk. Nothing is copied, moved or renamed; × puts the engine's own back. */
export function ModelFiles() {
  const [listing, setListing] = useState<Listing | null>(null)
  const [model, setModel] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback((fresh = false) => {
    setBusy(true)
    getJSON<Listing>(`${MODEL_FILES}${fresh ? '?fresh=1' : ''}`)
      .then(l => { setListing(l); setModel(m => (l.models.some(x => x.id === m) ? m : first(l))); setError(null) },
        e => setError(errorText(e)))
      .finally(() => setBusy(false))
  }, [])
  useEffect(() => load(), [load])
  useBusEvent('settings', () => load())

  const models = listing?.models ?? []
  const current = models.find(m => m.id === model) ?? models[0]       // the one open stays
  const choose = (part: string, path: string | null): Promise<unknown> => {
    if (!current) return Promise.resolve()
    setBusy(true)
    return sendJSON<Listing>('PUT', MODEL_FILES, { model: current.id, part, path })
      .then(l => { setListing(l); setError(null); void loadModels() })
      .finally(() => setBusy(false))
  }
  const reset = (part: string) => { choose(part, null).catch(e => setError(errorText(e))) }

  return (
    <Section title="Model files" aside={<Button icon="refresh" small disabled={busy} onClick={() => load(true)}>{busy ? 'Asking…' : 'Look again'}</Button>}>
      {error && <p className={s.error} role="alert">{error}</p>}
      {!listing ? <Row label="Model"><span className="t-cap">{busy ? 'Asking the engine for its models…' : '…'}</span></Row> : !current
        ? <Row label="Model"><span className="t-cap">The engine lists no models</span></Row> : <>
          <Row label="Model">
            <Select label="Model whose files to choose" value={current.id} disabled={busy}
              options={models.map(m => ({ value: m.id, label: optionLabel(m) }))} onChange={setModel} />
          </Row>
          <div data-model-files={current.id}>
            {current.parts.map(p => (
              <FileRow key={`${current.id}/${p.part}`} part={p} busy={busy} list={p.part.startsWith('loras:') ? 'hub-lora-files' : 'hub-weight-files'}
                save={path => choose(p.part, path)} reset={() => reset(p.part)} />
            ))}
          </div>
          <datalist id="hub-weight-files">{listing.files.map(f => <option key={f} value={f} />)}</datalist>
          <datalist id="hub-lora-files">{listing.loras.map(f => <option key={f} value={f} />)}</datalist>
        </>}
    </Section>
  )
}
