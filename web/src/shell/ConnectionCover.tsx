import { useEffect, useState } from 'react'
import { bus } from '../lib/bus'
import { useStore } from '../lib/store'
import s from './ConnectionCover.module.css'

type Cover = 'none' | 'cut' | 'off' | 'unpaired'

const GRACE_MS = 1500

/** Power cut shows only after a 1.5 s grace, so a quick restart never flickers. */
export function useCover(): Cover {
  const state = useStore(bus.link, l => l.state)
  const since = useStore(bus.link, l => l.since)
  const waiting = state === 'cut' || state === 'connecting'
  const [late, setLate] = useState(false)
  useEffect(() => {
    setLate(false)
    if (!waiting) return
    const t = setTimeout(() => setLate(true), Math.max(0, GRACE_MS - (Date.now() - since)))
    return () => clearTimeout(t)
  }, [waiting, since])
  if (state === 'off') return 'off'
  if (state === 'unpaired') return 'unpaired'
  return waiting && late ? 'cut' : 'none'
}

export function ConnectionCover({ cover }: { cover: Cover }) {
  if (cover === 'none') return null
  return (
    <div className={s.cover} data-cover={cover} role="status">
      <div className={s.card}>
        <span className={s.light} data-tone={cover} aria-hidden="true" />
        {cover === 'cut' && <span>Server offline — reconnecting…</span>}
        {cover === 'off' && <>
          <span>Switched off</span>
          <button type="button" className={s.check} onClick={() => bus.nudge()}>Check now</button>
        </>}
        {cover === 'unpaired' && <>
          <span>Not paired</span>
          <code className={s.code}>hub pair --name &lt;device&gt;</code>
        </>}
      </div>
    </div>
  )
}
