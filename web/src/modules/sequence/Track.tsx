import { useState, type DragEvent, type MouseEvent, type PointerEvent } from 'react'
import { follow } from '../../lib/pointer'
import { MEDIA_DRAG, type DraggedMedia } from '../../lib/protocol'
import { toast } from '../../lib/toast'
import { ClipStill } from '../../ui/ClipStill'
import { Icon } from '../../ui/Icon'
import { cx } from '../../ui/cx'
import type { Tracks } from './api'
import { dropFiles, edit, insertAt, type Dropped } from './load'
import { bedLine, gapAt, kept, lefts, movedTo, msOf, place, reorder, secs, trimEdge, whole, widths, type Item } from './seq'
import s from './Sequence.module.css'

/** A tile's own drag: `<track>:<index>:<seconds from its left where it was grabbed>`. */
export const SEQ_DRAG = 'application/x-hub-sequence'
export const ONLY_MEDIA = 'Only clips and sounds go in a sequence'
export const rem = (): number => parseFloat(getComputedStyle(document.documentElement).fontSize) || 16

type Props = {
  track: 0 | 1
  /** The track as drawn (an edge being dragged already applied). */
  items: Item[]
  perSecond: number
  /** The canvas's left edge on screen, px. */
  origin: () => number
  selected: number | null
  onSelect: (index: number) => void
  onMenu: (e: MouseEvent, index: number) => void
  /** An edge moved (`item` null: back as it was); `edge` says which, for the player. */
  onDraft: (index: number, item: Item | null, edge: 'in' | 'out') => void
  onCommit: (index: number, item: Item) => void
  /** After a move: the moved item's place in the saved track, and the tracks as saved. */
  onMoved: (index: number, tracks: Tracks) => void
}

/** One track: its tiles as long as the seconds they keep, at their time (track 1 back to back, track 2 at `at`).
 *  Clips and sounds dragged from Media, and an mp3 or wav file from the computer, drop at the time under the pointer; a
 *  tile dragged along its track moves; a tile's edge dragged trims it (one save when let go). */
export function Track({ track, items, perSecond, origin, selected, onSelect, onMenu, onDraft, onCommit, onMoved }: Props) {
  const [mark, setMark] = useState<number | null>(null)
  const ws = widths(items, perSecond)
  const ls = track === 0 ? lefts(items, perSecond) : items.map(it => ((it.at ?? 0) / 1000) * perSecond)
  /** The sequence time under the pointer, to 10 ms. */
  const tOf = (e: { clientX: number }) => Math.max(0, Math.round(((e.clientX - origin()) / rem() / perSecond) * 100) / 100)

  const over = (e: DragEvent) => {
    const types = [...e.dataTransfer.types]
    if (!types.includes(MEDIA_DRAG) && !types.includes(SEQ_DRAG) && !types.includes('Files')) return
    e.preventDefault()
    e.dataTransfer.dropEffect = types.includes(SEQ_DRAG) ? 'move' : 'copy'
    const t = tOf(e)
    setMark(track === 0 ? (lefts(items, perSecond)[gapAt(items, t)] ?? items.reduce((x, it) => x + kept(it), 0) * perSecond) : t * perSecond)
  }
  const drop = (e: DragEvent) => {
    setMark(null)
    const t = tOf(e)
    const own = e.dataTransfer.getData(SEQ_DRAG)
    if (own !== '') {
      e.preventDefault()
      const [from, index, grab] = own.split(':').map(Number) as [number, number, number]
      if (from !== track || !Number.isInteger(index) || index < 0 || index >= items.length) return
      if (track === 0) {
        const at = gapAt(items, t)
        void edit(([t1, t2]) => (at === index || at === index + 1 ? null : [reorder(t1, index, at), t2]))
          .then(r => { if (r) onMoved(movedTo(index, at), r.tracks) })
      } else {
        void edit(([t1, t2]) => [t1, place(t2, t2[index]!, msOf(t2[index]!), Math.round((t - grab) * 100) * 10, msOf, index).list])
          .then(r => { if (r) onMoved(r.tracks[1].findIndex(x => x.id === items[index]!.id && x.in === items[index]!.in), r.tracks) })
      }
      return
    }
    const raw = e.dataTransfer.getData(MEDIA_DRAG)
    if (raw) {
      e.preventDefault()
      let dragged: DraggedMedia[] = []
      try { dragged = JSON.parse(raw) as DraggedMedia[] } catch { return }
      const media = dragged.filter(d => d.kind === 'clip' || d.kind === 'sound')
      if (media.length < dragged.length) toast(ONLY_MEDIA)
      if (media.length) void insertAt(track, t, media.map((d): Dropped => ({ put: whole(d), ms: (d.seconds ?? 0) * 1000 })))
      return
    }
    if (e.dataTransfer.files.length > 0) {
      e.preventDefault()
      void dropFiles(track, t, [...e.dataTransfer.files])
    }
  }

  /** An edge pressed: followed by the pointer until let go, then saved once. */
  const grab = (e: PointerEvent<HTMLSpanElement>, i: number, edge: 'in' | 'out') => {
    e.preventDefault()
    e.stopPropagation()
    const from = items[i]!
    let last = from
    follow(e, dx => {
      last = trimEdge(from, edge, dx / rem() / perSecond)
      onDraft(i, last, edge)
    }, () => {
      if (last.in !== from.in || last.out !== from.out) onCommit(i, last)
      else onDraft(i, null, edge)
    })
  }

  return (
    <div className={s.row} role="listbox" aria-label={`Track ${track + 1}`} data-track={track + 1}
      onDragOver={over} onDragLeave={() => setMark(null)} onDrop={drop}>
      {items.map((it, i) => (
        <div key={`${i}:${it.id}`} role="option" aria-selected={i === selected} data-tile={i + 1} data-kind={it.kind}
          title={[it.id.split('/').pop(), bedLine(it)].filter(Boolean).join(' · ')} className={cx(s.tile, i === selected && s.tileOn)}
          style={{ left: `${ls[i]}rem`, width: `${ws[i]}rem` }} draggable
          onDragStart={e => {
            const r = e.currentTarget.getBoundingClientRect()
            e.dataTransfer.setData(SEQ_DRAG, `${track}:${i}:${(e.clientX - r.left) / rem() / perSecond}`)
            e.dataTransfer.effectAllowed = 'move'
          }}
          onClick={() => onSelect(i)} onContextMenu={e => onMenu(e, i)}>
          {it.kind === 'clip'
            ? <ClipStill url={it.url} at={Math.round((it.in / it.fps) * 1000) / 1000} />
            : <span className={s.soundTile} data-sound><Icon name="run" small /></span>}
          <span className={cx(s.cap, 'num')}>{i + 1} · {secs(kept(it))} s</span>
          <span className={cx(s.edge, s.edgeIn)} data-edge="in" aria-hidden="true" onPointerDown={e => grab(e, i, 'in')}
            onMouseDown={e => e.preventDefault()} onClick={e => e.stopPropagation()} />
          <span className={cx(s.edge, s.edgeOut)} data-edge="out" aria-hidden="true" onPointerDown={e => grab(e, i, 'out')}
            onMouseDown={e => e.preventDefault()} onClick={e => e.stopPropagation()} />
        </div>
      ))}
      {mark !== null && <span className={s.mark} style={{ left: `${mark}rem` }} aria-hidden="true" />}
    </div>
  )
}
