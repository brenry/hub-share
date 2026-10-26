import { useEffect, useLayoutEffect, useRef, useState, type DragEvent, type MouseEvent } from 'react'
import { MEDIA_DRAG } from '../../lib/protocol'
import { ClipStill } from '../../ui/ClipStill'
import { Icon } from '../../ui/Icon'
import { Scroll } from '../../ui/Scroll'
import { cx } from '../../ui/cx'
import { geometry, totalHeight, windowRange, type Geometry } from './gridMath'
import { dragged, isTemp, type MediaItem } from './media'
import type { Selection } from './selection'
import s from './Media.module.css'

type Props = {
  items: MediaItem[]
  sel: Selection
  /** The next page, while the list has one. */
  more: (() => Promise<void>) | null
  empty: string
  label?: string
  onPick: (id: string, mods: { ctrl: boolean; shift: boolean }) => void
  onMenu: (e: MouseEvent, id: string) => void
}

const COLS = 2
const rem = (): number => parseFloat(getComputedStyle(document.documentElement).fontSize) || 16

/** Two square tiles per row, flowing down; windowed, so a long Temp costs nothing. Prepending keeps the scroll
 *  position's tiles in place. A click selects, Ctrl-click adds or removes, Shift-click takes a range; right-click opens
 *  the menu for the selection (or for the tile under the pointer when it is not selected). */
export function Grid({ items, sel, more, empty, label = 'Images', onPick, onMenu }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const [geo, setGeo] = useState<Geometry>({ cols: COLS, tile: 132, rowH: 142, gap: 10 })
  const [view, setView] = useState({ top: 0, h: 0 })
  const anchor = useRef<{ id: string; row: number } | null>(null)

  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const measure = () => {
      const pad = parseFloat(getComputedStyle(el).paddingLeft) * 2
      setGeo(geometry(el.clientWidth - pad, COLS, 0.625 * rem()))
      setView({ top: el.scrollTop, h: el.clientHeight })
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useLayoutEffect(() => {
    const el = box.current
    const a = anchor.current
    if (!el || !a || el.scrollTop === 0) return
    const i = items.findIndex(it => it.id === a.id)
    if (i < 0) return
    const row = Math.floor(i / geo.cols)
    if (row !== a.row) el.scrollTop += (row - a.row) * geo.rowH
  }, [items, geo])

  const [start, end] = windowRange(view.top, view.h, items.length, geo)
  useEffect(() => {
    const firstRow = Math.floor(view.top / geo.rowH)
    const it = items[firstRow * geo.cols]
    anchor.current = it ? { id: it.id, row: firstRow } : null
  }, [items, view.top, geo])

  // Only a change of the current image reveals it; a new arrival never pulls the view.
  useEffect(() => {
    const el = box.current
    if (!el || sel.current === null) return
    const i = items.findIndex(it => it.id === sel.current)
    if (i < 0) return
    const top = Math.floor(i / geo.cols) * geo.rowH
    if (top < el.scrollTop) el.scrollTop = top
    else if (top + geo.tile > el.scrollTop + el.clientHeight) el.scrollTop = top + geo.tile - el.clientHeight
  }, [sel.current])

  const onScroll = () => {
    const el = box.current
    if (!el) return
    setView({ top: el.scrollTop, h: el.clientHeight })
    if (more && el.scrollTop + el.clientHeight > el.scrollHeight - geo.rowH * 4) more().catch(() => {})
  }
  const onDrag = (e: DragEvent, it: MediaItem) => {
    const group = sel.ids.includes(it.id) ? items.filter(x => sel.ids.includes(x.id)) : [it]
    // Pictures go to reference boxes, favorites, folders and characters; a clip to box 1 (to continue it) and Edit
    // Video; a sound to Edit Video and Generate's Sound box.
    e.dataTransfer.setData(MEDIA_DRAG, JSON.stringify(group.map(dragged)))
    e.dataTransfer.setData('text/uri-list', group.map(x => new URL(x.url, location.href).href).join('\r\n'))
    e.dataTransfer.effectAllowed = 'copyMove'
  }
  const pick = (e: MouseEvent, id: string) => onPick(id, { ctrl: e.ctrlKey || e.metaKey, shift: e.shiftKey })
  const many = sel.ids.length > 1

  return (
    <Scroll name="media-grid" ref={box} className={s.grid} role="listbox" aria-label={label} aria-multiselectable="true"
      tabIndex={0} aria-activedescendant={sel.current ? `m-${sel.current}` : undefined} onScroll={onScroll} data-region="grid"
      onContextMenu={e => e.preventDefault()}>
      {items.length === 0 && <p className={s.empty}>{empty}</p>}
      <div className={s.canvas} style={{ height: totalHeight(items.length, geo) }}>
        {items.slice(start, end).map((it, k) => {
          const i = start + k
          const on = sel.ids.includes(it.id)
          return (
            <div key={it.id} id={`m-${it.id}`} role="option" aria-selected={on} data-item={it.id} title={it.id.split('/').pop()}
              className={cx(s.tile, (on || sel.current === it.id) && s.tileOn, many && on && s.tileMany)}
              style={{ width: geo.tile, height: geo.tile, transform: `translate(${(i % geo.cols) * (geo.tile + geo.gap)}px, ${Math.floor(i / geo.cols) * geo.rowH}px)` }}
              draggable onDragStart={e => onDrag(e, it)} onClick={e => pick(e, it.id)}
              onContextMenu={e => { if (!on) onPick(it.id, { ctrl: false, shift: false }); onMenu(e, it.id) }}>
              {it.kind === 'clip'
                ? it.thumb
                  ? <img src={it.thumb} alt="" loading="lazy" decoding="async" width={264} height={264} draggable={false} data-clip-thumb />
                  : <ClipStill url={it.url} />
                : it.kind === 'sound'
                ? <span className={s.soundTile} data-sound><Icon name="run" /><span className="num">{typeof it.seconds === 'number' ? `${it.seconds.toFixed(1)} s` : ''}</span></span>
                : <img src={it.thumb ?? it.url} alt="" loading="lazy" decoding="async" width={264} height={264} draggable={false} />}
              {isTemp(it.id) && <span className={s.tempDot} aria-hidden="true" />}
              {it.fav && <span className={s.favMark} aria-label="Favorite">★</span>}
            </div>
          )
        })}
      </div>
    </Scroll>
  )
}
