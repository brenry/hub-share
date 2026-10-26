import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useStore } from '../../lib/store'
import { locate, seekTime, starts, total, type Item } from './seq'
import { setPlaying, tick, transport } from './transport'
import s from './Sequence.module.css'

type Video = HTMLVideoElement
/** The frame callback, where the browser has one. */
const frames = (v: Video): boolean => 'requestVideoFrameCallback' in v
type Live = { items: Item[]; front: 0 | 1; index: number; timer: ReturnType<typeof setTimeout> | undefined; raf: number }

const EPS = 1e-3

/** Two players, one showing the current item and one holding the next, seeked to its `in`. At the current item's
 *  `out` (by the frame callback where the browser has one, else by `timeupdate`) the held one shows and plays, and
 *  the other goes on to hold the item after it. Fitted in its region to the first item's shape by computed size. */
export function Player({ items, visible }: { items: Item[]; visible: boolean }) {
  const box = useRef<HTMLDivElement>(null)
  const a = useRef<HTMLVideoElement>(null)
  const b = useRef<HTMLVideoElement>(null)
  const [area, setArea] = useState({ w: 0, h: 0 })
  const live = useRef<Live>({ items, front: 0, index: -1, timer: undefined, raf: 0 })
  // Leaving the tab for good empties both players at once (decoders and buffers freed, not left to the collector).
  useEffect(() => {
    const players = [a.current, b.current]
    return () => { for (const v of players) if (v && !v.isConnected) { v.removeAttribute('src'); v.load() } }
  }, [])
  live.current.items = items
  const playing = useStore(transport, x => x.playing)
  const seek = useStore(transport, x => x.seek)
  const el = (k: number): Video | null => (k === 0 ? a.current : b.current)

  useLayoutEffect(() => {
    const node = box.current
    if (!node) return
    const measure = () => setArea({ w: node.clientWidth, h: node.clientHeight })
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(node)
    return () => ro.disconnect()
  }, [])

  /** Player `v` on frame `frame` of item `index` (none: emptied). */
  const put = (v: Video | null, index: number, frame: number) => {
    if (!v) return
    const it = live.current.items[index]
    if (!it) { delete v.dataset.place; return }
    if (v.getAttribute('src') !== it.url) v.src = it.url
    v.currentTime = seekTime(frame, it.fps)
    v.dataset.place = String(index + 1)
  }
  const show = () => {
    const L = live.current
    for (const k of [0, 1]) {
      const v = el(k)
      if (!v) continue
      if (k === L.front && L.index >= 0) v.dataset.on = ''
      else delete v.dataset.on
    }
  }
  /** Both players for sequence time `t`. */
  const place = (t: number) => {
    const L = live.current
    clearTimeout(L.timer)
    const here = locate(L.items, t)
    L.index = here?.index ?? -1
    el(1 - L.front)?.pause()
    if (here) {
      put(el(L.front), here.index, here.frame)
      const next = L.items[here.index + 1]
      put(el(1 - L.front), here.index + 1, next?.in ?? 0)
    }
    show()
  }
  const start = (v: Video | null) => { void v?.play()?.catch(() => {}) }

  const handover = () => {
    const L = live.current
    clearTimeout(L.timer)
    if (!transport.get().playing) return
    const cur = el(L.front)
    const next = L.index + 1
    if (next >= L.items.length) {
      cur?.pause()
      tick(total(L.items))
      setPlaying(false)
      return
    }
    L.front = L.front === 0 ? 1 : 0
    L.index = next
    show()
    start(el(L.front))
    cur?.pause()
    put(cur, next + 1, L.items[next + 1]?.in ?? 0)
    watch()
  }

  /** Frame by frame: once the last kept frame shows, the handover waits out that frame. */
  const watch = () => {
    const L = live.current
    const v = el(L.front)
    const index = L.index
    const it = L.items[index]
    if (!v || !it || !frames(v)) return
    v.requestVideoFrameCallback((_, meta) => {
      const now = live.current
      if (!transport.get().playing || now.index !== index || now.items[index] !== it || el(now.front) !== v) return
      const end = it.out / it.fps
      if (meta.mediaTime + 1 / it.fps < end - EPS) { watch(); return }
      clearTimeout(now.timer)
      now.timer = setTimeout(handover, Math.max(0, ((end - meta.mediaTime) * 1000) / (v.playbackRate || 1)))
    })
  }
  const onTime = (k: number) => {
    const L = live.current
    const v = el(k)
    const it = L.items[L.index]
    if (k !== L.front || !v || !it || frames(v) || !transport.get().playing) return
    if (v.currentTime >= it.out / it.fps - EPS) handover()
  }
  const onEnded = (k: number) => { if (k === live.current.front && transport.get().playing) handover() }

  useEffect(() => {
    if (items.length === 0) { place(0); return }        // no clip on track 1: the playhead is `Sounds`' to keep
    const t = transport.get().t
    const end = total(items)
    if (t > end) tick(end)
    place(Math.min(t, end))
    if (transport.get().playing) { start(el(live.current.front)); watch() }
  }, [seek, items])

  useEffect(() => {
    const L = live.current
    if (!playing) {
      clearTimeout(L.timer)
      a.current?.pause()
      b.current?.pause()
      return
    }
    if (L.items.length === 0) return                    // no clip on track 1: `Sounds` keeps the time
    if (transport.get().t >= total(L.items) - EPS) { tick(0); place(0) }
    start(el(L.front))
    watch()
    const loop = () => {
      const v = el(L.front)
      const it = L.items[L.index]
      if (v && it) {
        const f = Math.min(it.out, Math.max(it.in, v.currentTime * it.fps - 0.5))
        tick((starts(L.items)[L.index] ?? 0) + (f - it.in) / it.fps)
      }
      L.raf = requestAnimationFrame(loop)
    }
    L.raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(L.raf)
  }, [playing])

  useEffect(() => { if (!visible) setPlaying(false) }, [visible])
  useEffect(() => () => clearTimeout(live.current.timer), [])

  const first = items[0]
  const ratio = first && first.w > 0 && first.h > 0 ? first.w / first.h : 16 / 9
  const w = Math.min(area.w, area.h * ratio)
  return (
    <div ref={box} className={s.player} data-region="player">
      <div className={s.screen} style={{ width: Math.floor(w), height: Math.floor(w / ratio) }} hidden={!first}>
        {[a, b].map((r, k) => (
          <video key={k} ref={r} className={s.video} playsInline preload="auto" data-player={k}
            onTimeUpdate={() => onTime(k)} onEnded={() => onEnded(k)} />
        ))}
      </div>
    </div>
  )
}
