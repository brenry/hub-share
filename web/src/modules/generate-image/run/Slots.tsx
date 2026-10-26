import { useState, type DragEvent, type KeyboardEvent, type MouseEvent } from 'react'
import { useStore } from '../../../lib/store'
import { ClipStill } from '../../../ui/ClipStill'
import { Icon } from '../../../ui/Icon'
import { Menu, type MenuAt, type MenuItem } from '../../../ui/Menu'
import { cx } from '../../../ui/cx'
import { draft, edit } from '../draft'
import { removeRef, toggleCutout } from '../edits'
import { MEDIA_DRAG, pictures, type DraggedMedia } from '../../../lib/protocol'
import { itemFile } from '../api'
import { CLIP_ONLY_TEXT } from '../blocking'
import { continueClip } from '../continue'
import { addFiles, addMedia, flashing, note, slotNote, slotThumb, type Target } from '../inputs'
import type { Model, Slot as SlotData } from '../types'
import { BOXES, besideClip, boxLabel, clipInBox, isVideo, refsOf, stemOf } from '../video'
import { SoundBox } from './SoundBox'
import { VideoBox } from './VideoBox'
import s from './Run.module.css'

/** Three boxes, always. Media fills them (Send, or a drag); a box past what the model takes is struck through. A video
 *  model's boxes carry its role: box 1 is the "Start frame" (box 2 the "Last frame" when it takes one), or boxes 1…max
 *  are "Identity n". A clip in box 1 is continued: it plays there and shuts boxes 2–3, except on a model whose boxes
 *  are identities, where boxes 2… take them as "Identity 1"…. A clip dropped on box 1 goes
 *  to the hub (the menu's Continue), which puts it there; on any other box it is refused with one line. A filled box opens its menu on right-click, Shift+F10 or the menu key: "Cut out
 *  background" on an identity box (a small mark while on), and Remove. */
const TILE = { width: '100%', height: '100%', objectFit: 'cover' } as const

/** A clip from Media is continued in box 1 only; pictures and files fill the boxes (`model` null: only a clip is taken). */
function drop(e: DragEvent, target: Target, model: Model | null): void {
  e.preventDefault()
  const media = e.dataTransfer.getData(MEDIA_DRAG)
  const items = media ? JSON.parse(media) as DraggedMedia[] : []
  const clip = items.find(i => i.kind === 'clip')
  if (clip) { if (target === 0) void continueClip(clip.id).then(note); else note(CLIP_ONLY_TEXT) }
  else if (!model) return
  else if (items.length) { if (pictures(items).length) void addMedia(pictures(items), target, model) }
  else if (e.dataTransfer.files.length > 0) void addFiles([...e.dataTransfer.files], target, model)
}

type SlotProps = {
  label: string; badge: number; slot: SlotData | null; socket: string; target: Target; model: Model | null; open: boolean
  shut?: string | undefined; cut: boolean; onRemove: () => void; onMenu: (at: MenuAt) => void
}

/** Under the box, for the keyboard: the menu opens above it, as the bar's own menus do. */
const above = (el: Element): MenuAt => { const r = el.getBoundingClientRect(); return { x: r.left, y: r.top, up: true } }

function Slot({ label, badge, slot, socket, target, model, open, shut, cut, onRemove, onMenu }: SlotProps) {
  const lit = useStore(flashing, f => f.includes(socket))
  const dnd = { onDragOver: (e: DragEvent) => e.preventDefault(), onDrop: (e: DragEvent) => drop(e, target, open || shut ? model : null) }
  if (slot) {
    const hover = slot.kind === 'clip' ? `Continues ${stemOf(slot.id)}` : undefined
    const mouse = (e: MouseEvent) => { e.preventDefault(); onMenu(e.clientX || e.clientY ? { x: e.clientX, y: e.clientY } : above(e.currentTarget)) }
    const key = (e: KeyboardEvent) => {
      if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) { e.preventDefault(); onMenu(above(e.currentTarget)) }
    }
    const on = cut && !hover && slot.cutout === true
    return (
      <div className={cx(s.slot, s.filled, lit && s.flash)} title={hover} data-socket={socket} data-cutout={on || undefined} onContextMenu={mouse} onKeyDown={key} {...dnd}>
        {hover
          ? <ClipStill url={itemFile(slot.id)} label={hover} style={TILE} />
          : <img src={slotThumb(slot)} alt={label} title={on ? `${label} · background cut out` : label} loading="lazy" decoding="async" draggable={false} />}
        <span className={cx(s.badge, 'num')} aria-hidden="true">{badge}</span>
        {on && <span className={s.cut} aria-hidden="true" />}
        <button type="button" className={s.remove} aria-label={`Remove ${hover ? 'clip' : label.toLowerCase()}`} onClick={onRemove}><Icon name="x" small /></button>
      </div>
    )
  }
  if (shut || !open || !model) {
    return <span className={cx(s.slot, s.shut)} title={shut ?? (model ? `${label}: this model takes no reference here` : label)} aria-label={`${label}, not available`} data-socket={socket} data-shut {...dnd} />
  }
  const what = isVideo(model) ? 'a picture' : 'an image'
  return <span className={cx(s.slot, lit && s.flash)} title={`${label}: send ${what} from Media`} aria-label={`${label}, empty`} data-socket={socket} {...dnd} />
}

export function Slots({ model }: { model: Model | null }) {
  const d = useStore(draft, v => v)
  const noteText = useStore(slotNote, v => v)
  const [menu, setMenu] = useState<{ at: MenuAt; i: number } | null>(null)
  const cap = model?.refCap ?? 0
  const clip = clipInBox(d) !== null
  const beside = clip ? besideClip(model) : 0
  const refs = refsOf(model)
  const cuts = (i: number) => refs?.role === 'identity' && (clip ? i > 0 && i <= beside : i < refs.max)
  const label = (i: number) => boxLabel(model, i, clip)
  const items = (i: number): MenuItem[] => [
    ...(cuts(i) ? [{ label: d.references[i]?.cutout ? 'Keep background' : 'Cut out background', run: () => edit(x => toggleCutout(x, i)) }] : []),
    { label: 'Remove', icon: <Icon name="x" />, run: () => edit(x => removeRef(x, i)) },
  ]
  return (
    <div className={s.slots} data-region="references" data-cap={cap}>
      {Array.from({ length: BOXES }, (_, i) => (
        <Slot key={i} label={label(i)} badge={i + 1} slot={d.references[i] ?? null} open={clip ? i <= beside : i < cap} cut={cuts(i)}
          shut={clip && i > beside ? CLIP_ONLY_TEXT : undefined} socket={`reference_${i + 1}`} target={i} model={model}
          onRemove={() => edit(x => removeRef(x, i))} onMenu={at => setMenu({ at, i })} />
      ))}
      <SoundBox model={model} />
      <VideoBox model={model} />
      {noteText && <span className={cx('t-meta', 'ell', s.note)} role="status" title={noteText}>{noteText}</span>}
      <Menu at={menu?.at ?? null} items={menu ? items(menu.i) : []} onClose={() => setMenu(null)} label={menu ? label(menu.i) : 'Box'} />
    </div>
  )
}
