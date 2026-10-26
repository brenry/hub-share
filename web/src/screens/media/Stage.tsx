// The Stage viewer, ported: each picture comes up at Fit (centred, filling the window's height or width);
// wheel and Ctrl+wheel zoom at the cursor, drag (any time, so also Space+drag) or middle-drag pans with a hand
// cursor, double-click toggles Fit / 100%, Ctrl+0 fits, Ctrl+1 is 100%. The panel never moves.
// Given `edges` (Media passes them while the thumbnails are folded), the Stage has two invisible edge zones as wide
// as the stretch from the bar's counter to the Stage's right edge, measured at each use: a primary press that goes
// down and comes up in the same zone steps back (left) or forward (right) by one; double-click there does not zoom.
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type MouseEvent, type PointerEvent } from 'react'
import { isTypingTarget } from '../../lib/keys'
import { cx } from '../../ui/cx'
import { fitBox } from './fit'
import s from './Media.module.css'

type View = { s: number; x: number; y: number; fitted: boolean }
/** `at` gives the counter's left edge in client pixels; `step` is the bar's previous / next. */
export type Edges = { at: () => number | null; step: (by: -1 | 1) => void }

/** Mount with `key={src}`: each image starts at Fit. */
export function Stage({ src, edges }: { src: string; edges?: Edges | undefined }) {
  const board = useRef<HTMLDivElement>(null)
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null)
  const [view, setView] = useState<View>({ s: 1, x: 0, y: 0, fitted: true })
  const [hint, setHint] = useState(false)
  const [panning, setPanning] = useState(false)
  const drag = useRef<{ px: number; py: number; x: number; y: number } | null>(null)
  const over = useRef(false)
  const press = useRef<-1 | 1 | null>(null)
  const hintTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const fit = useCallback((): View | null => {
    const el = board.current
    if (!el || !natural) return null
    const { w, h } = natural
    // Fit is the whole window, as in any full-screen viewer: the picture's centre on the window's centre, scaled
    // until its height or its width meets the edge (a 16:9 picture fills a 16:9 window; a square one fills the
    // height with the window's own space left and right). The right column lies over the board and never moves it.
    return { ...fitBox(el.clientWidth, el.clientHeight, w, h), fitted: true }
  }, [natural])
  useLayoutEffect(() => { const f = fit(); if (f) setView(f) }, [fit])
  useEffect(() => {
    const el = board.current
    if (!el) return
    const ro = new ResizeObserver(() => setView(v => (v.fitted ? fit() ?? v : v)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [fit])

  const flash = () => {
    setHint(true)
    clearTimeout(hintTimer.current)
    hintTimer.current = setTimeout(() => setHint(false), 900)
  }
  const zoomAt = useCallback((mx: number, my: number, next: (sc: number) => number) => {
    const f = fit()
    if (!f) return
    setView(v => {
      const sc = Math.min(32, Math.max(f.s * 0.5, next(v.s)))
      if (Math.abs(sc - f.s) < 1e-4) return f
      return { s: sc, x: mx - (mx - v.x) * (sc / v.s), y: my - (my - v.y) * (sc / v.s), fitted: false }
    })
    flash()
  }, [fit])

  useEffect(() => {
    const el = board.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const r = el.getBoundingClientRect()
      zoomAt(e.clientX - r.left, e.clientY - r.top, sc => sc * Math.exp(-e.deltaY * 0.0015))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [zoomAt])
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target)) return
      if (e.code === 'Space' && (over.current || drag.current)) e.preventDefault()
      if ((e.ctrlKey || e.metaKey) && e.key === '0') { e.preventDefault(); const f = fit(); if (f) setView(f); flash() }
      if ((e.ctrlKey || e.metaKey) && e.key === '1' && board.current) {
        e.preventDefault()
        zoomAt(board.current.clientWidth / 2, board.current.clientHeight / 2, () => 1)
      }
    }
    window.addEventListener('keydown', down)
    return () => window.removeEventListener('keydown', down)
  }, [fit, zoomAt])

  // Which edge zone a client x falls in: the right one from the counter's left edge to the Stage's right edge, the left
  // one as wide from the Stage's left edge. None without `edges`.
  const zoneAt = (x: number): -1 | 1 | null => {
    const c = edges?.at()
    const r = board.current?.getBoundingClientRect()
    if (c == null || !r || c <= r.left) return null
    const w = r.right - c
    return x >= c && x <= r.right ? 1 : x >= r.left && x < r.left + w ? -1 : null
  }
  const onDown = (e: PointerEvent) => {
    if (e.button !== 0 && e.button !== 1) return
    press.current = e.button === 0 ? zoneAt(e.clientX) : null
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    drag.current = { px: e.clientX, py: e.clientY, x: view.x, y: view.y }
    setPanning(true)
  }
  const onMove = (e: PointerEvent) => {
    const d = drag.current
    if (d) setView(v => ({ ...v, x: d.x + e.clientX - d.px, y: d.y + e.clientY - d.py, fitted: false }))
  }
  const onUp = (e: PointerEvent) => {
    drag.current = null
    setPanning(false)
    const z = press.current
    press.current = null
    if (z && e.type === 'pointerup' && e.button === 0 && zoneAt(e.clientX) === z) edges?.step(z)
  }
  const onDouble = (e: MouseEvent) => {
    if (zoneAt(e.clientX)) return
    const r = board.current!.getBoundingClientRect()
    if (view.fitted) zoomAt(e.clientX - r.left, e.clientY - r.top, () => 1)
    else { const f = fit(); if (f) setView(f); flash() }
  }

  return (
    <div ref={board} className={cx(s.board, panning ? s.grabbing : s.grab)} data-wheel="stage" data-region="stage"
      onPointerEnter={() => { over.current = true }} onPointerLeave={() => { over.current = false }}
      onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp} onDoubleClick={onDouble}>
      <img src={src} alt="" draggable={false} className={s.stageImg} data-stage-img
        onLoad={e => setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
        style={{ width: natural?.w, height: natural?.h, opacity: natural ? 1 : 0,
          transform: `translate(${view.x}px, ${view.y}px) scale(${view.s})`, imageRendering: view.s >= 2 ? 'pixelated' : 'auto' }} />
      <span className={cx(s.zoom, hint && s.zoomOn, 'num')}>{view.fitted ? 'Fit' : `${Math.round(view.s * 100)}%`}</span>
    </div>
  )
}
