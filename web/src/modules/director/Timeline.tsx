import { useEffect, useLayoutEffect, useMemo, useRef, useState, type MouseEvent, type PointerEvent } from 'react'
import { follow } from '../../lib/pointer'
import { useStore } from '../../lib/store'
import { pictureThumb, type Script, type Take } from './api'
import type { Edits } from './Edits'
import { Figure } from './Figure'
import { open } from './load'
import { type Box, boxes, measuredMs, namedMs, rows, scale, secs, type Sketch, sketchBox, SKETCHES, sketchState, x } from './timeline'
import s from './Scripts.module.css'

type Props = {
  script: Script; selected: string | null; onSelect: (b: Box) => void
  /** Boxes picked by hand (`Picks.tsx`) and a click's pick, with its keys. */
  picked?: string[]; onPick?: (b: Box, e: MouseEvent) => void; time: number; onSeek: (ms: number) => void; playing: boolean
  takes: Record<string, Take>; speaking?: string | null; edits?: Pick<Edits, 'onMove' | 'onStretch' | 'onBoxMenu' | 'onEmptyMenu'> | undefined
}

/** A press travels this many px before it is a drag (a click below it still selects). */
const SLOP = 4

const rootPx = () => parseFloat(getComputedStyle(document.documentElement).fontSize) || 16

/** The ruler's marks: a tick each second, its number every 5 s. */
function Ruler({ ms, pps }: { ms: number; pps: number }) {
  const ticks = Array.from({ length: Math.floor(ms / 1000) + 1 }, (_, k) => k)
  return <>{ticks.map(k => (
    <span key={k} className={k % 5 === 0 ? s.tickBig : s.tick} style={{ left: x(k * 1000, pps) }}>{k % 5 === 0 ? k : null}</span>
  ))}</>
}

const NONE: Sketch[] = []

/** A sketch at its time, 16:9; a stale one faded with a dashed outline, one not drawn an empty frame. */
function SketchButton({ p, pps, on, onSelect }: { p: Sketch; pps: number; on: boolean; onSelect: (b: Box) => void }) {
  const state = sketchState(p)
  return (
    <button type="button" className={`${s.sketch} ${on ? s.on : ''}`} style={{ left: x(p.at, pps) }}
      title={`Sketch · ${secs(p.at)} s${state === 'drawn' ? '' : ` · ${state}`}`} aria-pressed={on} data-box={p.id}
      data-stale={p.stale && p.picture !== null ? 'true' : 'false'} data-drawn={p.picture === null ? 'false' : 'true'}
      onClick={() => onSelect(sketchBox(p))}>
      {p.picture === null ? null : <img src={pictureThumb(p.picture)} alt="" />}
    </button>
  )
}

/** The script as a timeline: one scroller; the row heads stay put while it scrolls sideways. One click
 *  selects a box; nothing is edited here. The playhead a line across the rows at `time`; a click on the
 *  ruler puts it there. The Sketches row under Shots, only when the open script has a panel.
 *  Every size follows the root (the row heads observed: a root change measures again; one width, the widest name whole, at least 7rem); while playing, a
 *  playhead past the visible rows' right edge (or before their left) scrolls them so it is a quarter of their width
 *  from the row heads; paused, it never scrolls by itself. A line box with a take carries its state
 *  (`data-take`, a mark) and, measured, ` · <s> s` after its words. A cue box as a line box; every
 *  box at the time of the script it is given, the track's for a mixed one (`mixtime.inMix`). The box
 *  Track's job is rendering (`speaking`) carries `data-speaking` and an outline, its take mark kept. A line,
 *  cue, pose or shot box dragged sideways follows the pointer and, let go, moves there (`edits.onMove`); a right-click
 *  on a box or on empty timeline opens the edits' menu. */
/** Empty timeline past the end, one shot's longest hold (15 s), so the last shot's edge has room to be dragged. */
const ROOM_MS = 15_000

export function Timeline({ script, selected, onSelect, picked = [], onPick, time, onSeek, playing, takes, speaking = null, edits }: Props) {
  const scroller = useRef<HTMLDivElement>(null)
  const rowsBox = useRef<HTMLDivElement>(null)
  const head = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const [headW, setHeadW] = useState(0)
  const [rem, setRem] = useState(rootPx)
  /** Every head one width, the widest head's whole text with its padding, never under 7rem; kept in rem
   *  on the rows (`--head`), so a root change scales it and the observer measures again. */
  const measure = useRef(() => {})
  measure.current = () => {
    const el = scroller.current
    const box = rowsBox.current
    if (!el || !box) return
    const r = rootPx()
    box.style.setProperty('--head', 'max-content')
    const widest = Math.max(7 * r, ...[...box.querySelectorAll<HTMLElement>('[data-row-head]')].map(h => h.getBoundingClientRect().width))
    box.style.setProperty('--head', `${Math.ceil(widest) / r}rem`)
    const w = head.current?.offsetWidth ?? 0
    setRem(r)
    setHeadW(w)
    setWidth(el.clientWidth - w)
  }
  useLayoutEffect(() => {
    const el = scroller.current
    if (!el) return
    const ro = new ResizeObserver(() => measure.current())
    ro.observe(el)
    if (head.current) ro.observe(head.current)
    return () => ro.disconnect()
  }, [])
  const ms = namedMs(script)                                  // up to the named length, past the shots
  const room = Math.min(ROOM_MS, Math.max(0, (width / scale(0, width, rem)) * 1000 - ms))   // as much as fits on screen
  const pps = scale(ms + room, width, rem)                     // room past the end to drag a shot's edge into
  const all = useMemo(() => boxes(script), [script])
  const sketches = useStore(open, o => o?.panels ?? NONE)
  const shown = useMemo(() => {
    const out = rows(script)
    return sketches.length ? [...out.slice(0, 2), SKETCHES, ...out.slice(2)] : out
  }, [script, sketches.length])
  useLayoutEffect(() => measure.current(), [shown])
  const span = x(ms + room, pps)
  const seek = (e: MouseEvent<HTMLDivElement>) => {
    const left = e.currentTarget.getBoundingClientRect().left
    onSeek(Math.min(ms, Math.max(0, ((e.clientX - left) / pps) * 1000)))
  }
  const at = Math.min(time, ms)
  const [drag, setDrag] = useState<{ id: string; dx: number } | null>(null)
  const dragged = useRef(false)
  const press = (e: PointerEvent<HTMLButtonElement>, b: Box) => {
    if (e.button !== 0 || !edits) return
    dragged.current = false
    follow(e, dx => {
      if (Math.abs(dx) < SLOP && !dragged.current) return
      dragged.current = true
      setDrag({ id: b.id, dx })
    }, dx => {
      setDrag(null)
      if (dragged.current) edits.onMove(b, b.start + (dx / pps) * 1000)
    })
  }
  const pick = (b: Box, e: MouseEvent) => {
    if (dragged.current) dragged.current = false
    else if (onPick) onPick(b, e)
    else onSelect(b)
  }
  const [grow, setGrow] = useState<{ id: string; dx: number } | null>(null)
  const stretch = (e: PointerEvent<HTMLSpanElement>, b: Box) => {
    e.stopPropagation()
    if (e.button !== 0 || !edits) return
    dragged.current = true
    follow(e, dx => setGrow({ id: b.id, dx }), dx => {
      setGrow(null)
      edits.onStretch(b, Math.max(1, Math.round((b.end - b.start + (dx / pps) * 1000) / 100) / 10))
    })
  }
  const menuAt = (e: MouseEvent<HTMLDivElement>, who: string | null) => {
    if (!edits || (e.target as Element).closest('[data-box]')) return
    const track = e.currentTarget.lastElementChild!.getBoundingClientRect()
    edits.onEmptyMenu(e, Math.max(0, ((e.clientX - track.left) / pps) * 1000), who)
  }
  useEffect(() => {
    const el = scroller.current
    if (!playing || !el || width <= 0) return
    const ph = x(at, pps)
    if (ph > el.scrollLeft + width || ph < el.scrollLeft) el.scrollLeft = Math.max(0, ph - width / 4)
  }, [playing, at, pps, width])

  return (
    <div ref={scroller} className={s.scroll} data-scroll="script-timeline" data-region="timeline" data-pps={pps}>
      <div ref={rowsBox} className={s.rows}>
      <div className={s.playhead} style={{ left: headW + x(at, pps) }} data-region="playhead" data-ms={Math.round(at)} />
      {shown.map((row, i) => (
        <div key={row.key} className={`${s.row} ${s[row.kind]}`} data-row={row.key}
          onContextMenu={row.kind === 'ruler' ? undefined : e => menuAt(e, row.kind === 'lines' ? row.who : null)}>
          <div ref={i === 0 ? head : undefined} className={s.head} data-row-head>{row.head}</div>
          <div className={s.track} style={{ width: span }} onClick={row.kind === 'ruler' ? seek : undefined}
            data-region={row.kind === 'ruler' ? 'ruler' : undefined}>
            {row.kind === 'ruler' ? <Ruler ms={ms} pps={pps} /> : row.kind === 'panels' ? sketches.map(p => (
              <SketchButton key={p.id} p={p} pps={pps} on={p.id === selected} onSelect={onSelect} />
            )) : all.filter(b => b.row === row.key).map(b => {
              const left = x(b.start, pps) + (drag?.id === b.id ? drag.dx : 0)
              const w = Math.max(4, x(b.end, pps) - x(b.start, pps) + (grow?.id === b.id ? grow.dx : 0))
              const on = b.id === selected || picked.includes(b.id)
              const full = b.ev?.kind === 'pose' ? `${b.ev.character} · ${b.text}` : b.text
              if (row.kind === 'poses') {
                return (
                  <button key={b.id} type="button" className={`${s.pose} ${on ? s.on : ''}`} style={{ left, width: w }}
                    title={full} aria-pressed={on} data-box={b.id} data-dragging={drag?.id === b.id || undefined}
                    onPointerDown={e => press(e, b)} onClick={e => pick(b, e)} onContextMenu={e => edits?.onBoxMenu(e, b)}>
                    <span className={s.hold} />
                    <Figure pose={b.text} rem={rem} />
                  </button>
                )
              }
              const take = b.ev?.kind === 'line' || b.ev?.kind === 'cue' ? takes[b.id] : undefined
              const ms = take ? measuredMs(take) : null
              const now = speaking !== null && b.id === speaking
              const text = ms === null ? b.text : `${b.text} · ${secs(ms)} s`
              return (
                <button key={b.id} type="button" className={`${s.box} ${on ? s.on : ''} ${take ? s[`take_${take.state}`] ?? '' : ''} ${now ? s.speaking : ''}`}
                  style={{ left, width: w }} title={take ? `${text} · ${take.state}` : full} aria-pressed={on} data-box={b.id}
                  data-take={take?.state} data-speaking={now ? 'true' : undefined} data-dragging={drag?.id === b.id || undefined}
                  onPointerDown={e => press(e, b)} onClick={e => pick(b, e)} onContextMenu={e => edits?.onBoxMenu(e, b)}>
                  <span className="ell">{text}</span>
                  {b.ev === null && !b.panel && edits
                    ? <span className={s.edge} data-edge={b.id} onPointerDown={e => stretch(e, b)} onClick={e => e.stopPropagation()} />
                    : null}
                </button>
              )
            })}
          </div>
        </div>
      ))}
      </div>
    </div>
  )
}
