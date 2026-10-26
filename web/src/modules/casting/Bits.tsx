import { useState, type DragEvent } from 'react'
import { MEDIA_DRAG, type DraggedMedia } from '../../lib/protocol'
import { Field } from '../../ui/Field'
import { Icon } from '../../ui/Icon'
import { cx } from '../../ui/cx'
import { itemThumb, type Approved, type Bit, type Lines } from './api'
import { dropBit, dropOn, edit } from './load'
import { MAX_BITS, type Form } from './form'
import s from './Casting.module.css'

/** A box's Keep and Ignore lines. */
function LinePair({ box, lines, onChange }: { box: number; lines: Lines; onChange: (l: Lines) => void }) {
  return (
    <div className={s.lines}>
      <span className={s.lab}>Keep</span>
      <Field label={`Keep ${box}`} value={lines.keep} onChange={keep => onChange({ ...lines, keep })} />
      <span className={s.lab}>Ignore</span>
      <Field label={`Ignore ${box}`} value={lines.ignore} onChange={ignore => onChange({ ...lines, ignore })} />
    </div>
  )
}

/** Media's drag payload, or none. */
function dragged(e: DragEvent): DraggedMedia[] | null {
  const raw = e.dataTransfer.getData(MEDIA_DRAG)
  if (!raw) return null
  try { return JSON.parse(raw) as DraggedMedia[] } catch { return null }
}

/** An approved picture's versioned address when the box still holds it (a re-approve is never hidden by the
 *  browser's cache), else its thumbnail. */
export function picSrc(id: string, ids: readonly (string | null)[] | null | undefined, urls: readonly (string | null)[] | null | undefined): string {
  const k = ids ? ids.indexOf(id) : -1
  return (k >= 0 ? urls?.[k] : null) ?? itemThumb(id)
}

type BoxProps = {
  box: number; bit: Bit | undefined; src: string | null
  onDrop: (items: DraggedMedia[]) => void; onRemove: () => void; onLines: (l: Lines) => void
}

/** A picture box: its picture and lines, or an empty box; either takes pictures dragged from Media. */
export function BitBox({ box, bit, src, onDrop, onRemove, onLines }: BoxProps) {
  const [over, setOver] = useState(false)
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
      onDrop(items)
    },
  }
  return (
    <div className={cx(s.box, over && s.over)} data-box={box} data-filled={bit ? true : undefined} {...dnd}>
      <div className={s.pic}>
        {bit && src ? <img src={src} alt={`Picture ${box}`} draggable={false} /> : null}
        <span className={cx(s.badge, 'num')} aria-hidden="true">{box}</span>
        {bit ? <button type="button" className={s.remove} aria-label={`Remove picture ${box}`} onClick={onRemove}>
          <Icon name="x" small /></button> : null}
      </div>
      {bit ? <LinePair box={box} lines={bit} onChange={onLines} /> : null}
    </div>
  )
}

/** Box 1, the character's picture from Characters with its own lines, then boxes 2-9 for the bits. */
export function Bits({ headshot, form, files }: { headshot: string | null; form: Form; files?: Approved | null | undefined }) {
  return (
    <div className={s.boxes} data-region="casting-boxes">
      <div className={s.box} data-box={1} data-filled>
        <div className={s.pic}>
          {headshot ? <img src={itemThumb(headshot)} alt="Headshot" draggable={false} /> : null}
          <span className={cx(s.badge, 'num')} aria-hidden="true">1</span>
        </div>
        <LinePair box={1} lines={form.headshot} onChange={headshot => edit(f => ({ ...f, headshot }))} />
      </div>
      {Array.from({ length: MAX_BITS }, (_, i) => {
        const bit = form.bits[i]
        return (
          <BitBox key={i} box={i + 2} bit={bit} src={bit ? picSrc(bit.id, files?.bits, files?.bit_urls) : null}
            onDrop={items => void dropOn(i, items)} onRemove={() => dropBit(i)}
            onLines={l => edit(f => ({ ...f, bits: f.bits.map((b, k) => (k === i ? { ...b, ...l } : b)) }))} />
        )
      })}
    </div>
  )
}
