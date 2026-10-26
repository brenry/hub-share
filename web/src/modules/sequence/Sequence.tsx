import { useEffect, useMemo, useRef, useState } from 'react'
import { isTypingTarget } from '../../lib/keys'
import type { ToolProps } from '../../lib/module'
import { useStore } from '../../lib/store'
import type { Tracks } from './api'
import { Bar } from './Bar'
import { edit, open, useSequenceData } from './load'
import { Player } from './Player'
import { Sounds } from './Sounds'
import { Strip, type Sel } from './Strip'
import { endOf, length, locate, split, starts, step, trimIn, trimOut, under, unit, type Item } from './seq'
import { seekTo, setPlaying, transport } from './transport'
import s from './Sequence.module.css'

const NONE: Tracks = [[], []]
/** Controls that answer these keys themselves: the tabs, a radio group, a menu, a popover, the trim numbers. */
const OWN = '[role=tab], [role=radio], [role=menuitem], [role=menu], [popover], [data-keys="own"]'
type Draft = { track: 0 | 1; index: number; item: Item } | null

/** Both tracks with item `index` of `track` replaced (or cut out with `null`, or split in two with a pair). */
const swap = (ts: Tracks, track: 0 | 1, index: number, by: Item | null | [Item, Item]): Tracks => {
  const next = ts[track].flatMap((x, i) => (i !== index ? [x] : by === null ? [] : Array.isArray(by) ? by : [by]))
  return (track === 0 ? [next, ts[1]] : [ts[0], next]) as Tracks
}
/** Where an item starts in the sequence, seconds. */
const startOf = (ts: Tracks, sel: Sel): number =>
  (sel.track === 0 ? starts(ts[0])[sel.index] ?? 0 : (ts[1][sel.index]?.at ?? 0) / 1000)

/** The frame of item `sel` under the playhead, or null when the playhead is not inside it. */
function frameAt(ts: Tracks, sel: Sel): number | null {
  const t = transport.get().t
  if (sel.track === 0) {
    const here = locate(ts[0], t)
    return here && here.index === sel.index && t < length(ts[0], []) ? here.frame : null
  }
  const it = ts[1][sel.index]
  if (!it || under(ts[1], t) !== sel.index) return null
  return it.in + Math.floor((t - (it.at ?? 0) / 1000) * it.fps + 1e-6)
}

/** The Edit Video tab: the player, the two tracks, the bar, top to bottom. Media (the other window) is the bin: its
 *  clips and sounds are dragged onto a track, and so is an mp3 or wav file from the computer. Keys act while the tab
 *  shows and the focus is not in a text field: Space plays or pauses, Left and Right step one frame of track 1 while
 *  paused, Home and End go to the ends, Delete removes the selected item from the sequence (never its file), I and O
 *  set its in and out at the playhead, S splits it there. Hidden, it pauses. */
export default function Sequence({ visible }: ToolProps) {
  useSequenceData()
  const seq = useStore(open, x => x)
  const [draft, setDraft] = useState<Draft>(null)
  const saved = seq?.tracks ?? NONE
  const tracks = useMemo(() => (draft ? swap(saved, draft.track, draft.index, draft.item) : saved), [saved, draft])
  const [selected, setSelected] = useState<Sel | null>(null)
  const name = seq?.name ?? null
  const clips = tracks[0][0]?.kind === 'clip' ? tracks[0] : NONE[0]

  useEffect(() => { setSelected(sel => (sel && sel.index < saved[sel.track].length ? sel : null)); setDraft(null) }, [saved])
  useEffect(() => { setSelected(null); setPlaying(false); seekTo(0) }, [name])

  const now = useRef({ tracks: saved, selected })
  now.current = { tracks: saved, selected }
  const select = (sel: Sel, ts: Tracks = saved) => { setSelected(sel); seekTo(startOf(ts, sel)) }
  const remove = (sel: Sel) => { void edit(ts => swap(ts, sel.track, sel.index, null)).then(r => { if (r) setSelected(null) }) }
  const splitAt = (sel: Sel) => {
    const ts = now.current.tracks
    const f = frameAt(ts, sel)
    const it = ts[sel.track][sel.index]
    const two = it && f !== null ? split(it, f) : null
    if (two) void edit(ts => swap(ts, sel.track, sel.index, two))
  }
  const trimAt = (sel: Sel, end: 'in' | 'out') => {
    const ts = now.current.tracks
    const f = frameAt(ts, sel)
    const it = ts[sel.track][sel.index]
    if (!it || f === null) return
    void edit(ts => swap(ts, sel.track, sel.index, end === 'in' ? trimIn(it, f) : trimOut(it, f + unit(it)))).then(r => {
      if (r && end === 'in') seekTo(startOf(r.tracks, sel))
    })
  }
  const onDraft = (track: 0 | 1, index: number, item: Item | null, edge: 'in' | 'out') => {
    setDraft(item ? { track, index, item } : null)
    if (!item) return
    const start = track === 0 ? starts(now.current.tracks[0])[index] ?? 0 : (item.at ?? 0) / 1000
    seekTo(edge === 'in' ? start : (track === 0 ? start + (item.out - item.in) / item.fps : endOf(item)) - 1 / item.fps)
  }
  const onCommit = (track: 0 | 1, index: number, item: Item) => {
    void edit(ts => swap(ts, track, index, item)).then(r => { if (!r) setDraft(null) })
  }

  useEffect(() => {
    if (!visible) return
    const down = (e: KeyboardEvent) => {
      const target = e.target
      if (e.ctrlKey || e.metaKey || e.altKey || isTypingTarget(target)) return
      if (target instanceof Element && target.closest(OWN)) return
      if (document.querySelector('[data-region="menu"]')) return
      const { tracks: ts, selected: sel } = now.current
      const { t, playing } = transport.get()
      const end = length(ts[0], ts[1])
      const k = e.key.length === 1 ? e.key.toLowerCase() : e.key
      if (k === ' ') {
        if (target instanceof HTMLButtonElement) return
        if (end > 0) setPlaying(!playing)
      } else if (k === 'ArrowLeft' || k === 'ArrowRight') {
        if (!playing && ts[0].length) seekTo(step(ts[0], t, k === 'ArrowRight' ? 1 : -1))
      } else if (k === 'Home') seekTo(0)
      else if (k === 'End') seekTo(end)
      else if (k === 'Delete') { if (sel) remove(sel) }
      else if (k === 'i' || k === 'o') { if (sel) trimAt(sel, k === 'i' ? 'in' : 'out') }
      else if (k === 's') { if (sel) splitAt(sel) }
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', down)
    return () => window.removeEventListener('keydown', down)
  }, [visible])

  return (
    <div className={s.seq} data-region="sequence">
      <Player items={clips} visible={visible} />
      <Sounds tracks={tracks} clock={clips.length === 0} visible={visible} />
      <Strip tracks={tracks} selected={selected} onSelect={(sel, ts) => select(sel, ts)} onRemove={remove} onSplit={splitAt}
        onDraft={onDraft} onCommit={onCommit} />
      <Bar seq={seq} tracks={tracks} selected={selected} />
    </div>
  )
}
