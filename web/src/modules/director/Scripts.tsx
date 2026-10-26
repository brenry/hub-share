import { useEffect, useMemo, useRef, useState } from 'react'
import { jobs } from '../../lib/live'
import type { ToolProps } from '../../lib/module'
import { useStore } from '../../lib/store'
import type { Opened, Take } from './api'
import { Audio } from './Audio'
import { Bar } from './Bar'
import { Context } from './Context'
import { useEdits } from './Edits'
import { ShotList, usePicks } from './Picks'
import { VideoLoras } from './VideoLoras'
import { list, open, useScripts } from './load'
import { Timeline } from './Timeline'
import { boxes, describe, lengthMs, sketchBox, trackProgress, type Box } from './timeline'
import s from './Scripts.module.css'

/** The Storyboard tab: the open script as a timeline, the bar under it; a version-2 script's context above the
 *  timeline. A file that does not read shows its one-line problem where the timeline would be.
 *  The stage above the timeline draws the figures at the playhead's time; Play moves it in real time to the end.
 *  A locked script's audio script at the timeline's right; a row and its box select each other.
 *  The left column is a top band (the stage, then the context beside it) over the timeline; the timeline's rows come
 *  first and the band takes what is left, at least 8rem; the timeline knows whether Play runs. The
 *  audio script's takes by id, shown on the timeline's line boxes and, for a selected line, in the bar.
 *  The selected box kept across a reload of the same script while its id exists; Track's job from the queue
 *  (`/script`'s `rendering` its id), its progress on the bar and the box being spoken marked. The
 *  timeline's drags and right-click edits (`useEdits`). */
export default function Scripts({ visible }: ToolProps) {
  useScripts(visible)
  const opened = useStore(open, x => x)
  const none = useStore(list, l => l !== null && l.length === 0)
  const [selected, setSelected] = useState<Box | null>(null)
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const shown = useRef<string | null>(null)
  useEffect(() => {
    const same = opened !== null && opened.name === shown.current
    shown.current = opened?.name ?? null
    setSelected(b => (b && same && opened ? again(opened, b.id) : null))
  }, [opened])
  const job = useStore(jobs, m => (opened?.rendering ? m.get(opened.rendering) ?? null : null))
  const progress = useMemo(() => (opened?.rendering ? trackProgress(job) : null), [opened?.rendering, job])
  const speaking = progress && 'id' in progress ? progress.id : null
  const script = opened?.script ?? null
  const context = script?.context ?? null
  const length = script ? lengthMs(script) : 0
  const name = opened?.name ?? null
  const audio = script ? opened?.audio ?? null : null
  const takes = useMemo(() => Object.fromEntries((audio ?? []).map(r => [r.id, r.take])) as Record<string, Take>, [audio])
  const take = selected?.ev?.kind === 'line' ? takes[selected.id] : undefined
  const edits = useEdits(name, script)
  const picks = usePicks(name, script)

  useEffect(() => { setPlaying(false); setTime(0) }, [name])               // another script: stopped, at 0
  useEffect(() => setTime(t => Math.min(t, length)), [length])            // a refetch keeps the time, held to the end
  const endRef = useRef(length)
  const timeRef = useRef(time)
  endRef.current = length
  timeRef.current = time
  useEffect(() => {
    if (!playing) return
    let last = performance.now()
    let frame = requestAnimationFrame(function step(now) {
      const next = Math.min(endRef.current, timeRef.current + Math.max(0, now - last))
      last = now
      timeRef.current = next
      setTime(next)
      if (next >= endRef.current) setPlaying(false)
      else frame = requestAnimationFrame(step)
    })
    return () => cancelAnimationFrame(frame)
  }, [playing])

  const toggle = () => {
    if (playing) return setPlaying(false)
    if (time >= length) setTime(0)
    setPlaying(length > 0)
  }
  const select = (b: Box) => { setSelected(b); setTime(b.start) }
  const selectId = (id: string) => {
    const b = script ? boxes(script).find(x => x.id === id) : undefined
    if (b) select(b)
  }

  return (
    <div className={s.tab}>
      <div className={`${s.main} ${s.withAudio}`}>
        {script ? <>
          <div className={s.left}>
            <div className={s.band} data-region="script-band">
              {/* The stage's figures are on hold: its place holds the set, `Stage.tsx` kept. */}
              {context ? <Context context={context} pictures={opened?.pictures ?? {}} unpictured={opened?.unpictured ?? []} name={name} /> : null}
            </div>
            <Timeline script={script} selected={selected?.id ?? null} picked={picks.picked} onPick={(b, e) => { picks.pick(b, e); select(b) }} onSelect={select} time={time} onSeek={setTime} playing={playing} takes={takes} speaking={speaking} edits={edits} />
          </div>
          {audio ? <Audio rows={audio} selected={selected?.id ?? null} onSelect={selectId} />
            : <div className={s.shotSide}><ShotList name={name} script={script} picked={picks.picked} onPick={(b, e) => { picks.pick(b, e); select(b) }} /><VideoLoras /></div>}
        </> : <div className={s.empty} data-region="script-problem">{opened?.problem ?? (none ? 'No scripts' : '')}</div>}
      </div>
      <Bar opened={opened} line={selected && script ? describe(selected, script) : ''}
        play={script ? { playing, time, toggle } : null} take={take && selected ? { take, plannedMs: selected.end - selected.start } : null}
        progress={progress} />
      {edits.view}
    </div>
  )
}

/** The box of `id` in a reloaded script, its times refreshed; null when the id is gone. */
function again(o: Opened, id: string): Box | null {
  if (!o.script) return null
  const panel = o.panels?.find(p => p.id === id)
  return boxes(o.script).find(b => b.id === id) ?? (panel ? sketchBox(panel) : null)
}
