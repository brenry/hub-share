import { useRef, useState } from 'react'
import { useStore } from '../../lib/store'
import { Button } from '../../ui/Button'
import { Field } from '../../ui/Field'
import { Icon } from '../../ui/Icon'
import { Live } from '../../ui/Live'
import { Menu, type MenuAt, type MenuItem } from '../../ui/Menu'
import { Popover, useAnchor } from '../../ui/Popover'
import { Progress } from '../../ui/Progress'
import { errorText } from '../../lib/http'
import { toast } from '../../lib/toast'
import { api, isProblem, type Opened, type Take as TakeT } from './api'
import { namedMs } from './timeline'
import { choose, list, reload, removeOpen, rename } from './load'
import { Render } from './Render'
import { Take } from './Take'
import { progressText, type TrackProgress } from './timeline'
import { Track } from './Track'
import s from './Scripts.module.css'

export type Play = { playing: boolean; time: number; toggle: () => void }

/** The tab's bar, as Edit Video's: the Scripts menu (each script with its length, or its problem, then
 *  Rename… and Delete script), the selected event's fields in one line, Live. Rename asks the name in a popover (Enter
 *  keeps it, Escape leaves it); Delete asks nothing. The open script's length beside its name, as the
 *  menu writes it; none when no script is open or its file does not read. Play / Pause and the
 *  playhead's time, for a script that draws. A lock after the length when the open script is locked.
 *  `Track` after the lock for a script with an audio script, off while a take renders; a selected
 *  line's take after the event line. The track's line and player after `Track`. `Track` is the
 *  app's button, off while `/script` names a Track job and from the press until its answer and reload;
 *  the job's progress after it. `Render`, its progress and the cut's player after the lock. */
export function Bar({ opened, line, play, take, progress }: {
  opened: Opened | null; line: string; play: Play | null; take: { take: TakeT; plannedMs: number } | null; progress: TrackProgress | null
}) {
  const [pressing, setPressing] = useState(false)
  const held = useRef(false)
  const all = useStore(list, l => l)
  const [menu, setMenu] = useState<MenuAt | null>(null)
  const [text, setText] = useState('')
  const { id, anchor } = useAnchor()
  const menuBtn = useRef<HTMLButtonElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const pop = () => document.getElementById(id)

  const begin = () => {
    setText(opened?.name ?? '')
    pop()?.showPopover()
    requestAnimationFrame(() => { input.current?.focus(); input.current?.select() })
  }
  const commit = () => { void rename(text.trim()).then(ok => { if (ok) pop()?.hidePopover() }) }
  const none = opened ? null : 'No script open'
  const audio = opened?.script ? opened.audio ?? null : null
  const rendering = (audio?.some(r => r.take.state === 'rendering') ?? false) || Boolean(opened?.rendering)
  const off = rendering || pressing
  const track = () => {
    if (!opened || off || held.current) return
    held.current = true
    setPressing(true)
    void api.track(opened.name).then(() => reload(), e => toast(errorText(e)))
      .finally(() => { held.current = false; setPressing(false) })
  }
  const items: MenuItem[] = [
    ...(all ?? []).map((x): MenuItem => ({
      label: `${x.name} · ${x.problem ?? `${x.seconds.toFixed(1)} s`}`,
      icon: x.name === opened?.name ? <Icon name="right" /> : null, run: () => choose(x.name),
    })),
    ...(all && all.length > 0 ? [{ sep: true } as const] : []),
    { label: 'Rename…', icon: <Icon name="pen" />, off: none, run: begin },
    { label: 'Delete script', icon: <Icon name="trash" />, danger: true, off: none, run: () => { void removeOpen() } },
  ]
  const openMenu = () => {
    const r = menuBtn.current?.getBoundingClientRect()
    const top = menuBtn.current?.closest('footer')?.getBoundingClientRect().top ?? r?.top ?? 0
    setMenu({ x: r?.left ?? 0, y: top, up: true })
  }

  return (
    <footer className={s.bar} data-region="scripts-bar">
      <button ref={menuBtn} type="button" className={s.name} aria-haspopup="menu" aria-label="Storyboard" title="Storyboard"
        onClick={openMenu} data-region="scripts" {...anchor}>
        <span className="ell">{opened?.name ?? 'Storyboard'}</span><Icon name="up" small />
      </button>
      {opened && !opened.problem && <span data-region="script-length">{`${opened.seconds.toFixed(1)} s`}</span>}
      {opened?.script?.lock?.locked && <span data-region="script-locked" title="Locked"><Icon name="lock" label="Locked" /></span>}
      <Render opened={opened} />
      {audio && <Button small className={s.trackBtn} aria-disabled={off} onClick={track} data-region="script-track">Track</Button>}
      {progress && <span className={s.trackProgress} data-region="track-progress">
        {'done' in progress ? <span className={s.trackBar}><Progress value={progress.value} label="Track" /></span> : null}
        <span>{progressText(progress)}</span>
      </span>}
      {opened?.script && opened.track ? <Track track={opened.track} /> : null}
      {play && <>
        <button type="button" className={s.play} aria-label={play.playing ? 'Pause' : 'Play'} title={play.playing ? 'Pause' : 'Play'}
          aria-pressed={play.playing} onClick={play.toggle} data-region="script-play">
          <Icon name={play.playing ? 'pause' : 'run'} />
        </button>
        <span data-region="playhead-time">{`${(play.time / 1000).toFixed(1)} s`}</span>
        {opened?.script ? <Length name={opened.name} seconds={Math.round(namedMs(opened.script) / 1000)} /> : null}
      </>}
      <span className={`${s.grow} ell`} data-region="event" title={line}>{line}</span>
      {take && <Take take={take.take} plannedMs={take.plannedMs} />}
      <Live className={s.liveFlat} />
      <Menu at={menu} items={items} label="Storyboard" onClose={() => setMenu(null)} />
      <Popover id={id} anchorStyle={anchor.style} label="Rename" className={s.ask}>
        <Field label="New name" value={text} onChange={setText}
          inputRef={input} onEnter={commit} onEscape={() => pop()?.hidePopover()} />
      </Popover>
    </footer>
  )
}

/** The video's length, typed (whole seconds): the timeline reaches it, the shots stay as they are. */
function Length({ name, seconds }: { name: string; seconds: number }) {
  const save = (v: string) => {
    const n = Math.round(Number(v))
    if (!Number.isFinite(n) || n < 1 || n === seconds) return
    void api.edit(name, { op: 'length', seconds: n }).then(r => {
      if (isProblem(r)) toast(r.problem)
      return reload()
    })
  }
  return (
    <input key={seconds} className={s.lengthBox} type="number" min={1} step={1} defaultValue={seconds} aria-label="Video length"
      data-region="video-length" onBlur={e => save(e.currentTarget.value)}
      onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur() }} />
  )
}
