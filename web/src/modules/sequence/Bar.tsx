import { useEffect, useMemo, useRef, useState } from 'react'
import { jobs } from '../../lib/live'
import type { Job, JobState } from '../../lib/protocol'
import { useStore } from '../../lib/store'
import { toast } from '../../lib/toast'
import { DragNumber } from '../../ui/DragNumber'
import { Field } from '../../ui/Field'
import { Icon } from '../../ui/Icon'
import { Live } from '../../ui/Live'
import { Menu, type MenuAt, type MenuItem } from '../../ui/Menu'
import { Popover, useAnchor } from '../../ui/Popover'
import { Progress } from '../../ui/Progress'
import type { Sequence, Tracks } from './api'
import { choose, create, edit, join, list, removeOpen, rename } from './load'
import { clock, length, secs, trimIn, trimOut, unit, type Item } from './seq'
import type { Sel } from './Strip'
import { setPlaying, transport } from './transport'
import s from './Sequence.module.css'

const TOOL = 'sequence'
const EMPTY_TEXT = 'The sequence is empty'

/** The newest job of this tool, a join the assistant asked for included. */
const newest = (all: ReadonlyMap<string, Job>): Job | null =>
  [...all.values()].filter(j => j.tool === TOOL).reduce<Job | null>((a, j) => (!a || j.created >= a.created ? j : a), null)

/** "Saved: <seconds> s" once the job this window saw queued or running is done; a failure says its line. */
function useJoinJob(): Job | null {
  const all = useStore(jobs, m => m)
  const seen = useRef(new Map<string, JobState>())
  useEffect(() => {
    for (const j of all.values()) {
      if (j.tool !== TOOL) continue
      const before = seen.current.get(j.id)
      if (before !== undefined && before !== j.state && j.state === 'done') toast(`Saved: ${secs(j.summary?.seconds ?? 0)} s`)
      if (before !== undefined && before !== j.state && j.state === 'failed' && j.error) toast(j.error.text)
      seen.current.set(j.id, j.state)
    }
  }, [all])
  return useMemo(() => newest(all), [all])
}

/** The item's In and Out in seconds, snapped to its frames (a sound: 10 ms); dragged, then saved once released. */
function Trim({ item, sel }: { item: Item; sel: Sel }) {
  const [draft, setDraft] = useState<{ in: number; out: number } | null>(null)
  useEffect(() => setDraft(null), [item])
  const f = unit(item) / item.fps
  const vIn = draft?.in ?? item.in / item.fps
  const vOut = draft?.out ?? item.out / item.fps
  const save = (cut: (x: Item) => Item) => {
    void edit(ts => ts.map((t, k) => (k !== sel.track ? t : t.map((x, i) => (i === sel.index ? cut(x) : x))))).then(() => setDraft(null))
  }
  return (
    <span className={s.trim} data-region="trim" data-keys="own">
      <span className={s.lab}>In</span>
      <DragNumber label="In" value={vIn} min={0} max={(item.out - unit(item)) / item.fps} step={f} perPx={f / 2} className={s.drag}
        onChange={v => setDraft({ in: v, out: vOut })} onCommit={v => save(x => trimIn(x, v * item.fps))} />
      <span className={s.lab}>Out</span>
      <DragNumber label="Out" value={vOut} min={(item.in + unit(item)) / item.fps} max={item.frames / item.fps} step={f} perPx={f / 2} className={s.drag}
        onChange={v => setDraft({ in: vIn, out: v })} onCommit={v => save(x => trimOut(x, v * item.fps))} />
    </span>
  )
}

type Props = { seq: Sequence | null; tracks: Tracks; selected: Sel | null }

/** The tab's bar: the sequences' menu, play, the time (to the end of what Save makes), In and Out of the selected
 *  item, the save's progress, Save and the light. New and Rename ask for the name in a popover (Enter keeps it, Escape leaves it); Delete asks nothing. */
export function Bar({ seq, tracks, selected }: Props) {
  const all = useStore(list, l => l)
  const t = useStore(transport, x => x.t)
  const playing = useStore(transport, x => x.playing)
  const job = useJoinJob()
  const [menu, setMenu] = useState<MenuAt | null>(null)
  const [ask, setAsk] = useState<'new' | 'rename'>('new')
  const [text, setText] = useState('')
  const { id, anchor } = useAnchor()
  const menuBtn = useRef<HTMLButtonElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const item = selected === null ? undefined : tracks[selected.track][selected.index]
  const end = length(tracks[0], tracks[1])
  const empty = tracks[0].length === 0 && tracks[1].length === 0
  const pop = () => document.getElementById(id)

  const begin = (kind: 'new' | 'rename') => {
    setAsk(kind)
    setText(kind === 'rename' ? seq?.name ?? '' : '')
    pop()?.showPopover()
    requestAnimationFrame(() => { input.current?.focus(); input.current?.select() })
  }
  const commit = () => {
    const name = text.trim()
    void (ask === 'rename' ? rename(name) : create(name)).then(ok => { if (ok) pop()?.hidePopover() })
  }
  const off = seq ? null : 'No sequence open'
  const items0: MenuItem[] = [
    ...(all ?? []).map((x): MenuItem => ({ label: `${x.name} · ${secs(x.seconds)} s`, icon: x.name === seq?.name ? <Icon name="right" /> : null, run: () => choose(x.name) })),
    ...(all && all.length > 0 ? [{ sep: true } as const] : []),
    { label: 'New sequence…', icon: <Icon name="plus" />, run: () => begin('new') },
    { label: 'Rename…', icon: <Icon name="pen" />, off, run: () => begin('rename') },
    { label: 'Delete sequence', icon: <Icon name="trash" />, danger: true, off, run: removeOpen },
  ]
  const openMenu = () => {
    const r = menuBtn.current?.getBoundingClientRect()
    const top = menuBtn.current?.closest('footer')?.getBoundingClientRect().top ?? r?.top ?? 0
    setMenu({ x: r?.left ?? 0, y: top, up: true })
  }
  const go = () => {
    if (!seq || empty) { toast(EMPTY_TEXT); return }
    void join(seq.name).then(ok => { if (ok) toast('Queued') })
  }
  const busy = job && (job.state === 'queued' || job.state === 'running') ? job : null
  const p = busy?.progress
  const value = p ? (p.steps > 0 ? p.step / p.steps : p.pct > 0 ? p.pct / 100 : null) : null

  return (
    <footer className={s.bar} data-region="sequence-bar">
      <button ref={menuBtn} type="button" className={s.name} aria-haspopup="menu" aria-label="Sequences" title="Sequences"
        onClick={openMenu} data-region="sequences" {...anchor}>
        <span className="ell">{seq?.name ?? 'Sequences'}</span><Icon name="up" small />
      </button>
      <button type="button" className={s.barBtn} aria-label={playing ? 'Pause' : 'Play'} title={playing ? 'Pause' : 'Play'}
        disabled={empty} onClick={() => setPlaying(!playing)} data-region="play"><Icon name={playing ? 'pause' : 'run'} small /></button>
      <span className={s.time} data-region="time">{clock(Math.min(t, end))} / {clock(end)}</span>
      {item && selected !== null && <Trim item={item} sel={selected} />}
      <span className={s.grow}>
        {busy && <span className={s.progress} title={busy.title}><Progress value={value} label="Saving" /></span>}
      </span>
      <button type="button" className={s.go} aria-label="Save" title={empty ? EMPTY_TEXT : 'Save'}
        aria-disabled={empty} onClick={go} data-region="join"><Icon name="link" small /></button>
      <Live className={s.liveFlat} />
      <Menu at={menu} items={items0} label="Sequences" onClose={() => setMenu(null)} />
      <Popover id={id} anchorStyle={anchor.style} label={ask === 'rename' ? 'Rename' : 'New sequence'} className={s.ask}>
        <Field label={ask === 'rename' ? 'New name' : 'Sequence name'} value={text} onChange={setText}
          inputRef={input} onEnter={commit} onEscape={() => pop()?.hidePopover()} />
      </Popover>
    </footer>
  )
}
