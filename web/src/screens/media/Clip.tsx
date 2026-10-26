// A clip on the Stage: the player, fitted like a picture (fit.ts) at its own size, so its controls keep theirs; while
// the thumbnails are up it fits left of them, so none of its controls sit under the column. A clip listed without a
// size fills that fit box until the file says its own. No zoom, no pan. Space plays or pauses while the Stage (or the
// player) has focus. `loop` (Media's Loop, or L) plays it round and round; the player has no control row of its own
// (the browser's controls), so Loop lives in the clip menu. Given `edges` (thumbnails folded), the Stage's two edge zones step as they do for a picture (the
// player's own controls keep their presses); a press in a zone never also plays, pauses or goes full screen.
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type PointerEvent } from 'react'
import { ClipStill } from '../../ui/ClipStill'
import { Icon } from '../../ui/Icon'
import { fitBox } from './fit'
import type { Edges } from './Stage'
import s from './Media.module.css'

type Box = { x: number; y: number; w: number; h: number }

/** Mount with `key={src}`. `w`/`h` from the list (0 = unknown: the fit box, then the file's own size once read). */
export function Clip({ src, w, h, side, loop, edges, verdict }: { src: string; w: number; h: number; side: boolean; loop: boolean; edges?: Edges | undefined; verdict?: string | null }) {
  const board = useRef<HTMLDivElement>(null)
  const video = useRef<HTMLVideoElement>(null)
  const press = useRef<-1 | 1 | null>(null)
  const stepped = useRef(false)
  const [natural, setNatural] = useState(w > 0 && h > 0 ? { w, h } : null)
  const [box, setBox] = useState<Box | null>(null)
  // No player until Play: selecting a clip shows its still and a Play button; the clip is loaded only then.
  const [playing, setPlaying] = useState(false)
  useEffect(() => { if (playing) void video.current?.play()?.catch(() => {}) }, [playing])

  const measure = useCallback(() => {
    const el = board.current
    if (!el) return
    const left = el.getBoundingClientRect().left
    const col = side ? document.querySelector('[data-region="side"]')?.getBoundingClientRect().left : undefined
    const W = col !== undefined && col > left ? Math.min(el.clientWidth, col - left) : el.clientWidth
    const H = el.clientHeight
    if (W <= 0 || H <= 0) return
    const { w: nw, h: nh } = natural ?? { w: W, h: H }
    const f = fitBox(W, H, nw, nh)
    setBox({ x: f.x, y: f.y, w: nw * f.s, h: nh * f.s })
  }, [natural, side])
  useLayoutEffect(() => {
    measure()
    const ro = new ResizeObserver(measure)
    if (board.current) ro.observe(board.current)
    return () => ro.disconnect()
  }, [measure])

  // Leaving the Stage empties the player at once, so its decoder and buffers do not wait for the browser to collect them.
  useEffect(() => {
    const v = video.current
    return () => { if (v && !v.isConnected) { v.removeAttribute('src'); v.load() } }   // gone, not a re-run
  }, [])

  const onKey = (e: KeyboardEvent) => {
    if (e.key !== ' ' || e.ctrlKey || e.metaKey || e.altKey) return
    e.preventDefault()
    const v = video.current
    if (!v) { setPlaying(true); return }
    if (v.paused) v.play().catch(() => {})
    else v.pause()
  }

  // The edge zones, measured at each use as the Stage does.
  const zoneAt = (x: number): -1 | 1 | null => {
    const c = edges?.at()
    const r = board.current?.getBoundingClientRect()
    if (c == null || !r || c <= r.left) return null
    const zw = r.right - c
    return x >= c && x <= r.right ? 1 : x >= r.left && x < r.left + zw ? -1 : null
  }
  const onDown = (e: PointerEvent) => { press.current = e.button === 0 ? zoneAt(e.clientX) : null }
  const onUp = (e: PointerEvent) => {
    const z = press.current
    press.current = null
    stepped.current = !!z && e.button === 0 && zoneAt(e.clientX) === z
    if (stepped.current && z) edges?.step(z)
  }
  // A step is not also the player's own click (play / pause) or double-click (full screen).
  const onClick = (e: MouseEvent) => { if (stepped.current || zoneAt(e.clientX)) e.preventDefault(); stepped.current = false }

  return (
    <div ref={board} className={s.board} tabIndex={0} data-region="stage" data-clip onKeyDown={onKey}
      onPointerDown={onDown} onPointerUp={onUp} onPointerCancel={() => { press.current = null }} onClick={onClick} onDoubleClick={onClick}>
      {playing
        ? <video ref={video} src={src} controls loop={loop} preload="metadata" playsInline className={s.stageClip} data-stage-clip
            onLoadedMetadata={e => { const v = e.currentTarget; if (!natural && v.videoWidth > 0) setNatural({ w: v.videoWidth, h: v.videoHeight }) }}
            style={box ? { width: box.w, height: box.h, transform: `translate(${box.x}px, ${box.y}px)` } : { visibility: 'hidden' }} />
        : <button type="button" className={`${s.stageClip} ${s.clipPoster}`} data-clip-poster aria-label="Play"
            onClick={e => { e.stopPropagation(); if (stepped.current || zoneAt(e.clientX)) { stepped.current = false; return } setPlaying(true) }}
            style={box ? { width: box.w, height: box.h, transform: `translate(${box.x}px, ${box.y}px)` } : { visibility: 'hidden' }}>
            <ClipStill url={src} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
            <span className={s.clipPlay}><Icon name="run" /></span>
          </button>}
      {verdict && <span className={`${s.zoom} ${s.zoomOn} ${s.verdict}`} data-region="verdict" title={verdict}>{verdict}</span>}
    </div>
  )
}
