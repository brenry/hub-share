import { useEffect, useMemo, useRef, useState } from 'react'
import { jobs } from '../../lib/live'
import { useStore } from '../../lib/store'
import { toast } from '../../lib/toast'
import { Button } from '../../ui/Button'
import { Icon } from '../../ui/Icon'
import { Popover, useAnchor } from '../../ui/Popover'
import { Progress } from '../../ui/Progress'
import { api, isProblem, mediaFile, type Opened } from './api'
import { reload } from './load'
import { cutProgress, cutText } from './timeline'
import s from './Scripts.module.css'

const ENDED = new Set(['done', 'failed', 'cancelled'])

/** `Render` for an open script with a shot, off while its job runs (`rendering_cut`) and from the press
 *  until its answer; the job's progress after it, as Track's; the last cut's player beside it. A refusal is its line. */
export function Render({ opened }: { opened: Opened | null }) {
  const [pressing, setPressing] = useState(false)
  const held = useRef(false)
  const running = opened?.rendering_cut ?? null
  const job = useStore(jobs, m => (running ? m.get(running) ?? null : null))
  const progress = useMemo(() => (running ? cutProgress(job) : null), [running, job])
  const ended = useRef<string | null>(null)
  useEffect(() => {
    if (!running || !job || !ENDED.has(job.state) || ended.current === running) return
    ended.current = running
    if (job.state === 'failed' && job.error) toast(job.error.text)
    void reload()
  }, [running, job])
  const { id, anchor } = useAnchor()
  const shots = opened?.script?.scenes.some(sc => sc.shots.length > 0) ?? false
  if (!opened?.script || !shots) return null
  const off = Boolean(running) || pressing
  const render = () => {
    if (off || held.current) return
    held.current = true
    setPressing(true)
    void api.render(opened.name).then(r => {
      if (isProblem(r)) toast(r.problem)
      return reload()
    }).finally(() => { held.current = false; setPressing(false) })
  }
  return <>
    <Button small className={s.trackBtn} aria-disabled={off} onClick={render} data-region="script-render">Render</Button>
    {progress && <span className={s.trackProgress} data-region="render-progress">
      {'done' in progress ? <span className={s.trackBar}><Progress value={progress.value} label="Render" /></span> : null}
      <span>{cutText(progress)}</span>
    </span>}
    {opened.cut ? <>
      <button type="button" className={s.play} aria-label="Cut" title="Cut" data-region="script-cut"
        onClick={() => document.getElementById(id)?.togglePopover()} {...anchor}>
        <Icon name="video" />
      </button>
      <Popover id={id} anchorStyle={anchor.style} label="Cut" className={s.cutPop}>
        <video key={opened.cut} className={s.cutPlay} controls preload="metadata" src={opened.cut_url ?? mediaFile(opened.cut)} data-region="cut-play" />
      </Popover>
    </> : null}
  </>
}
