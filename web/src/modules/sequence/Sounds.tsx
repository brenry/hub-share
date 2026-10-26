import { useEffect, useMemo, useRef } from 'react'
import { useStore } from '../../lib/store'
import type { Tracks } from './api'
import { kept, length, starts } from './seq'
import { setPlaying, tick, transport } from './transport'

/** One thing heard: its file, where it starts in the sequence, where in the file, and for how long (seconds). */
type Heard = { key: string; url: string; start: number; from: number; dur: number; level: number }
/** A player off by more than this from where it should be is set again. */
const DRIFT = 0.25

/** What plays besides track 1's clips: track 1's sounds back to back and track 2's items at their
 *  places (a clip there: its sound), each through a hidden player started at its time from the playhead. A preview;
 *  the saved file is exact. With no clip on track 1 there is no picture to keep time, so this keeps it (`clock`):
 *  the playhead runs from where it is to the end of what Save would make. */
export function Sounds({ tracks, clock, visible }: { tracks: Tracks; clock: boolean; visible: boolean }) {
  const [t1, t2] = tracks
  const heard = useMemo<Heard[]>(() => {
    const at = starts(t1)
    const first = t1.flatMap((it, i) => (it.kind === 'sound' ? [{ key: `1:${i}:${it.id}`, url: it.url, start: at[i]!, from: it.in / it.fps, dur: kept(it), level: 1 }] : []))
    const second = t2.flatMap((it, i) => (it.audio ? [{ key: `2:${i}:${it.id}`, url: it.url, start: (it.at ?? 0) / 1000, from: it.in / it.fps, dur: kept(it), level: Math.min(1, it.level ?? 1) }] : []))
    return [...first, ...second]
  }, [t1, t2])
  const end = length(t1, t2)
  const players = useRef(new Map<string, HTMLAudioElement>())
  const playing = useStore(transport, x => x.playing)
  const seek = useStore(transport, x => x.seek)
  const live = useRef({ heard, end, clock })
  live.current = { heard, end, clock }

  /** Every player where the playhead says: playing inside its span, paused outside. */
  const follow = (t: number, run: boolean) => {
    for (const h of live.current.heard) {
      const el = players.current.get(h.key)
      if (!el) continue
      const inside = run && t >= h.start && t < h.start + h.dur
      if (!inside) { if (!el.paused) el.pause(); continue }
      const want = h.from + (t - h.start)
      if (el.paused) { el.currentTime = want; void el.play()?.catch(() => {}) }
      else if (Math.abs(el.currentTime - want) > DRIFT) el.currentTime = want
    }
  }

  useEffect(() => { follow(transport.get().t, transport.get().playing) }, [seek, heard])

  useEffect(() => {
    if (!playing) { follow(transport.get().t, false); return }
    let raf = 0
    let t0 = transport.get().t
    if (live.current.clock && t0 >= live.current.end - 1e-3) { t0 = 0; tick(0) }
    const began = performance.now()
    const loop = () => {
      const L = live.current
      let t = transport.get().t
      if (L.clock) {
        t = t0 + (performance.now() - began) / 1000
        if (t >= L.end) { tick(L.end); setPlaying(false); follow(L.end, false); return }
        tick(t)
      }
      follow(t, true)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [playing, seek])

  useEffect(() => { if (!visible) setPlaying(false) }, [visible])
  useEffect(() => () => { for (const el of players.current.values()) { el.pause(); el.removeAttribute('src'); el.load() } }, [])

  return (
    <div hidden data-region="sounds">
      {heard.map(h => (
        <audio key={h.key} preload="auto" src={h.url} data-heard={h.key} data-level={h.level}
          ref={el => { if (el) { el.volume = h.level; players.current.set(h.key, el) } else players.current.delete(h.key) }} />
      ))}
    </div>
  )
}
