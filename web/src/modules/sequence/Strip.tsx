import { useRef, useState, type MouseEvent } from 'react'
import { useStore } from '../../lib/store'
import { Icon } from '../../ui/Icon'
import { Menu, type MenuAt, type MenuItem } from '../../ui/Menu'
import { Scroll } from '../../ui/Scroll'
import { Segmented } from '../../ui/Segmented'
import type { Tracks } from './api'
import { endOf, length, total, withBed, ZOOMS, type Bed, type Item, type Zoom } from './seq'
import { Track } from './Track'
import { transport } from './transport'
import s from './Sequence.module.css'

export { SEQ_DRAG, ONLY_MEDIA } from './Track'
const ZOOM_OPTIONS = (Object.keys(ZOOMS) as Zoom[]).map(z => ({ value: z, label: `${z}×`, name: `Zoom ${z}×` }))
/** Room after the last item, rem: somewhere to drop. */
const ROOM = 12

export type Sel = { track: 0 | 1; index: number }

type Props = {
  tracks: Tracks
  selected: Sel | null
  /** `tracks`: as just saved, when the call follows a save that changed them. */
  onSelect: (sel: Sel, tracks?: Tracks) => void
  onRemove: (sel: Sel) => void
  onSplit: (sel: Sel) => void
  onDraft: (track: 0 | 1, index: number, item: Item | null, edge: 'in' | 'out') => void
  onCommit: (track: 0 | 1, index: number, item: Item) => void
}

const LEVELS = [0.25, 0.5, 0.75, 1, 1.5]
const FADE_MS = 1000

/** A track-2 item's bed menu: its level, a 1 s fade at either end, ducking under track 1; the one set is
 *  marked, and a click on a mark takes it off. */
export function bedItems(it: Item, set: (changes: Bed) => void): MenuItem[] {
  const level = it.level ?? 1
  const on = (yes: boolean) => (yes ? <Icon name="right" /> : null)
  return [
    { label: `Level ${Math.round(level * 100)}%`, icon: <Icon name="sound" />, run: () => {},
      sub: LEVELS.map(v => ({ label: `${Math.round(v * 100)}%${v === level ? ' ·' : ''}`, run: () => set({ level: v }) })) },
    { label: 'Fade in 1 s', icon: on(!!it.fade_in), run: () => set({ fade_in: it.fade_in ? 0 : FADE_MS }) },
    { label: 'Fade out 1 s', icon: on(!!it.fade_out), run: () => set({ fade_out: it.fade_out ? 0 : FADE_MS }) },
    { label: 'Duck under track 1', icon: on(!!it.duck), run: () => set({ duck: !it.duck }) },
    { sep: true },
  ]
}

/** The two tracks on one time line under a playhead line, labelled 1 and 2, and the zoom. Past the end of the file
 *  Save would make (track 1's length), track 2 is shaded: what lies there is cut. */
export function Strip({ tracks, selected, onSelect, onRemove, onSplit, onDraft, onCommit }: Props) {
  const [zoom, setZoom] = useState<Zoom>('2')
  const [menu, setMenu] = useState<{ at: MenuAt; sel: Sel } | null>(null)
  const t = useStore(transport, x => x.t)
  const canvas = useRef<HTMLDivElement>(null)
  const per = ZOOMS[zoom]
  const [t1, t2] = tracks
  const end = length(t1, t2)
  const far = Math.max(total(t1), ...t2.map(endOf), 0)
  const origin = () => canvas.current?.getBoundingClientRect().left ?? 0
  const context = (track: 0 | 1) => (e: MouseEvent, index: number) => {
    e.preventDefault()
    onSelect({ track, index })
    setMenu({ at: { x: e.clientX, y: e.clientY }, sel: { track, index } })
  }
  const row = (track: 0 | 1) => (
    <Track track={track} items={tracks[track]} perSecond={per} origin={origin}
      selected={selected?.track === track ? selected.index : null} onSelect={index => onSelect({ track, index })}
      onMenu={context(track)} onDraft={(i, it, edge) => onDraft(track, i, it, edge)} onCommit={(i, it) => onCommit(track, i, it)}
      onMoved={(index, ts) => { if (index >= 0) onSelect({ track, index }, ts) }} />
  )

  return (
    <div className={s.strip} data-region="strip">
      <span className={s.labels} aria-hidden="true"><span>1</span><span>2</span></span>
      <Scroll name="sequence-strip" className={s.scroll} aria-label="Sequence" onContextMenu={e => e.preventDefault()}>
        <div ref={canvas} className={s.canvas} style={{ width: `${far * per + ROOM}rem` }}>
          {row(0)}
          {row(1)}
          {t1.length > 0 && <span className={s.past} style={{ left: `${end * per}rem` }} aria-hidden="true" data-past />}
          {(t1.length > 0 || t2.length > 0) && <span className={s.head} style={{ left: `${Math.min(t, far) * per}rem` }} aria-hidden="true" data-head />}
        </div>
      </Scroll>
      <Segmented label="Zoom" value={zoom} options={ZOOM_OPTIONS} onChange={setZoom} className={s.zoom} />
      <Menu at={menu?.at ?? null} label="Item" onClose={() => setMenu(null)} items={menu ? [
        ...(menu.sel.track === 1 && tracks[1][menu.sel.index]
          ? bedItems(tracks[1][menu.sel.index]!, changes => onCommit(1, menu.sel.index, withBed(tracks[1][menu.sel.index]!, changes)))
          : []),
        { label: 'Split at playhead', icon: <Icon name="pen" />, key: 'S', run: () => onSplit(menu.sel) },
        { label: 'Remove from sequence', icon: <Icon name="trash" />, key: 'Delete', danger: true, run: () => onRemove(menu.sel) },
      ] : []} />
    </div>
  )
}
