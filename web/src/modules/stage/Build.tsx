import { useState, type DragEvent } from 'react'
import { MEDIA_DRAG, type DraggedMedia } from '../../lib/protocol'
import { useStore } from '../../lib/store'
import { Button } from '../../ui/Button'
import { Field } from '../../ui/Field'
import { Icon } from '../../ui/Icon'
import { Segmented } from '../../ui/Segmented'
import { cx } from '../../ui/cx'
import { AUDIENCES, BOXES, itemThumb, type Audience } from './api'
import { build, clearBox, dropOn, edit, pressing, setAudience, type Form } from './load'
import s from './Stage.module.css'

const AUDIENCE_NAMES: Record<Audience, string> = { none: 'None', heard: 'Heard', seen: 'Seen' }

/** Media's drag payload, or none. */
function dragged(e: DragEvent): DraggedMedia[] | null {
  const raw = e.dataTransfer.getData(MEDIA_DRAG)
  if (!raw) return null
  try { return JSON.parse(raw) as DraggedMedia[] } catch { return null }
}

/** A box: its picture and its Keep line; it takes pictures dragged from Media. */
function Box({ i, form }: { i: number; form: Form }) {
  const [over, setOver] = useState(false)
  const b = form.boxes[i]!
  const src = b.id ? itemThumb(b.id) : null
  const dnd = {
    onDragOver: (e: DragEvent) => {
      if (![...e.dataTransfer.types].includes(MEDIA_DRAG)) return
      e.preventDefault()
      e.dataTransfer.dropEffect = 'copy'
      setOver(true)
    },
    onDragLeave: () => setOver(false),
    onDrop: (e: DragEvent) => {
      setOver(false)
      const items = dragged(e)
      if (!items) return
      e.preventDefault()
      void dropOn(i, items)
    },
  }
  return (
    <div className={cx(s.box, over && s.over)} data-box={i + 1} data-filled={b.id ? true : undefined} {...dnd}>
      <div className={s.pic}>
        {src ? <img src={src} alt={`Picture ${i + 1}`} draggable={false} /> : null}
        <span className={cx(s.badge, 'num')} aria-hidden="true">{i + 1}</span>
        {b.id ? <button type="button" className={s.remove} aria-label={`Remove picture ${i + 1}`} onClick={() => clearBox(i)}>
          <Icon name="x" small /></button> : null}
      </div>
      <div className={s.lines}>
        <span className={s.lab}>Keep</span>
        <Field label={`Keep ${i + 1}`} value={b.keep}
          onChange={keep => edit(f => ({ ...f, boxes: f.boxes.map((x, k) => (k === i ? { ...x, keep } : x)) }))} />
      </div>
    </div>
  )
}

/** Audience: part of the form before Approve; on an approved set, written at once. */
export function AudienceChoice({ value, disabled }: { value: Audience; disabled?: boolean }) {
  return (
    <div className={s.row} data-region="stage-audience">
      <span className={s.lab}>Audience</span>
      <Segmented label="Audience" value={value} onChange={a => { if (!disabled) void setAudience(a) }}
        options={AUDIENCES.map(a => ({ value: a, label: AUDIENCE_NAMES[a] }))} />
    </div>
  )
}

/** A new set's inputs: boxes 1-9, Description, Pieces (one a line), Audience, then Build. */
export function Build({ form, rendering }: { form: Form; rendering: boolean }) {
  const busy = useStore(pressing, x => x)
  return (
    <section className={s.build} data-region="stage-build">
      <div className={s.boxes} data-region="stage-boxes">
        {Array.from({ length: BOXES }, (_, i) => <Box key={i} i={i} form={form} />)}
      </div>
      <div className={s.facts}>
        <span className={s.lab}>Description</span>
        <Field label="Description" value={form.description}
          onChange={description => edit(f => ({ ...f, description }))} />
        <span className={s.lab}>Pieces</span>
        <textarea className={s.area} aria-label="Pieces" rows={4} spellCheck={false} value={form.pieces}
          onChange={e => { const pieces = e.target.value; edit(f => ({ ...f, pieces })) }} />
      </div>
      <AudienceChoice value={form.audience} />
      <div className={s.presses}>
        <Button onClick={() => void build()} disabled={busy || rendering} data-region="stage-build-press">Build</Button>
      </div>
    </section>
  )
}
