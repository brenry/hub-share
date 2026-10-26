// Pure: Fit, as in any full-screen viewer: the picture's centre on the area's centre, scaled until its height or its
// width meets the edge. The Stage's pictures and its clips both use it.
export function fitBox(W: number, H: number, w: number, h: number): { s: number; x: number; y: number } {
  const s = Math.min(W / w, H / h)
  return { s, x: (W - w * s) / 2, y: (H - h * s) / 2 }
}
