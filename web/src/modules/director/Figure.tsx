import { BOX_REM, COLORS, DRAWN_LIMBS, JOINT, LIMBS, LIMB_DIM, POSES, STICK, rgb } from './poses'

/** One pose as the engine draws a body (`upstream preprocessing/dwpose/util.py:71-112`), in pixels, BOX_REM square at
 *  the root's `rem` pixels, never scaled: the first 17 limbs as ellipses STICK px from their axis, coloured at 60 %, then the 18 points at full colour.
 *  The engine dims its whole limb layer on black, so a limb's colour is multiplied, not made see-through. */
export function Figure({ pose, rem }: { pose: string; rem: number }) {
  const body = POSES[pose]
  if (!body) return null
  const box = BOX_REM * rem
  const at = (i: number) => body[i]
  const limbs = LIMBS.slice(0, DRAWN_LIMBS).flatMap(([a, b], i) => {
    const p = at(a - 1)
    const q = at(b - 1)
    if (!p || !q) return []
    const [x1, y1, x2, y2] = [p[0] * box, p[1] * box, q[0] * box, q[1] * box]
    const angle = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI
    return [<ellipse key={i} cx={(x1 + x2) / 2} cy={(y1 + y2) / 2} rx={Math.hypot(x2 - x1, y2 - y1) / 2} ry={STICK}
      transform={`rotate(${angle} ${(x1 + x2) / 2} ${(y1 + y2) / 2})`} fill={rgb(COLORS[i]!, LIMB_DIM)} />]
  })
  const joints = body.flatMap((p, i) => (p ? [<circle key={i} cx={p[0] * box} cy={p[1] * box} r={JOINT} fill={rgb(COLORS[i]!)} />] : []))
  return (
    <svg width={box} height={box} data-figure={pose} aria-hidden="true">
      <rect width={box} height={box} fill="#000" />
      {limbs}
      {joints}
    </svg>
  )
}
