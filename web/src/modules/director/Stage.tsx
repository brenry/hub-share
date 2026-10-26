import { useLayoutEffect, useRef, useState } from 'react'
import type { Script } from './api'
import {
  COLORS, DRAWN_LIMBS, EPS, FACE_COLOR, FACE_POINT, HAND_COLOR, HAND_EDGES, HAND_POINT, HAND_STROKE, JOINT, LIMBS, LIMB_DIM,
  STICK, edgeColor, rgb, type Point,
} from './poses'
import { onStage, stageAt, type Figure } from './tween'
import s from './Scripts.module.css'

/** The stage's most height, rem; the most of its band's width. */
const MOST_REM = 16
const MOST_OF_WIDTH = 0.5
/** A figure's box against the stage's height, and where its bottom sits. */
const BOX_OF_HEIGHT = 0.8
const FLOOR = 0.95

/** Draws the figures as the engine draws a pose (`upstream preprocessing/dwpose/pose.py:35-42`, `util.py:71-152`) on
 *  a black canvas of `w` × `h` pixels, never scaled: every body's limbs at 60 %, its joints; then the hands' edges and
 *  points; then the faces' points. A point at or under 1 % of the canvas is not drawn. Each figure's box is centred at
 *  `onStage` of its place, so every pose lies whole inside the canvas. */
export function paint(ctx: CanvasRenderingContext2D, w: number, h: number, figures: readonly Figure[]): void {
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, w, h)
  const box = h * BOX_OF_HEIGHT
  const px = (f: Figure, p: Point): [number, number] | null => {
    if (!p) return null
    const [x, y] = [onStage(f.x, w, box) - box / 2 + p[0] * box, h * FLOOR - box + p[1] * box]
    return x / w > EPS && y / h > EPS ? [x, y] : null
  }
  const dot = (at: [number, number] | null, r: number, color: string) => {
    if (!at) return
    ctx.fillStyle = color
    ctx.beginPath()
    ctx.arc(at[0], at[1], r, 0, Math.PI * 2)
    ctx.fill()
  }
  for (const f of figures) {
    LIMBS.slice(0, DRAWN_LIMBS).forEach(([a, b], i) => {
      const [p, q] = [px(f, f.full.body[a - 1] ?? null), px(f, f.full.body[b - 1] ?? null)]
      if (!p || !q) return
      ctx.fillStyle = rgb(COLORS[i]!, LIMB_DIM)
      ctx.beginPath()
      ctx.ellipse((p[0] + q[0]) / 2, (p[1] + q[1]) / 2, Math.hypot(q[0] - p[0], q[1] - p[1]) / 2, STICK, Math.atan2(q[1] - p[1], q[0] - p[0]), 0, Math.PI * 2)
      ctx.fill()
    })
  }
  for (const f of figures) f.full.body.forEach((p, i) => dot(px(f, p), JOINT, rgb(COLORS[i]!)))
  for (const f of figures) {
    for (const hand of f.full.hands) {
      ctx.lineWidth = HAND_STROKE
      HAND_EDGES.forEach(([a, b], k) => {
        const [p, q] = [px(f, hand[a] ?? null), px(f, hand[b] ?? null)]
        if (!p || !q) return
        ctx.strokeStyle = rgb(edgeColor(k))
        ctx.beginPath()
        ctx.moveTo(p[0], p[1])
        ctx.lineTo(q[0], q[1])
        ctx.stroke()
      })
      for (const p of hand) dot(px(f, p), HAND_POINT, rgb(HAND_COLOR))
    }
  }
  for (const f of figures) for (const p of f.full.face) dot(px(f, p), FACE_POINT, rgb(FACE_COLOR))
}

/** The stage: a 16:9 canvas, its pixels its displayed size; black; the scene at `time`, each cast member
 *  at its place. No name, label or box on it. At the left of the top band (its parent, sized by CSS in
 *  rem), as tall as the band, at most 16rem tall and at most half the band wide; measured again whenever the band's box
 *  changes (a root change resizes it), then drawn at its new pixels. */
export function Stage({ script, time }: { script: Script; time: number }) {
  const wrap = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const [size, setSize] = useState<[number, number]>([0, 0])
  useLayoutEffect(() => {
    const el = wrap.current?.parentElement
    if (!el) return
    const measure = () => {
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16
      const h = Math.floor(Math.min(el.clientHeight, (el.clientWidth * MOST_OF_WIDTH * 9) / 16, MOST_REM * rem))
      setSize([Math.floor((h * 16) / 9), h])
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const [w, h] = size
  useLayoutEffect(() => {
    const ctx = canvas.current?.getContext('2d')
    if (ctx && w > 0 && h > 0) paint(ctx, w, h, stageAt(script, time))
  }, [script, time, w, h])
  return (
    <div ref={wrap} className={s.stage}>
      <canvas ref={canvas} width={w} height={h} style={{ width: w, height: h }} data-region="script-stage" data-ms={Math.round(time)} />
    </div>
  )
}
