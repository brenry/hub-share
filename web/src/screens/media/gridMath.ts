// Pure: the two-per-row tile geometry and the window of rows to render.
export type Geometry = { cols: number; tile: number; rowH: number; gap: number }

/** `cols` square tiles across `width`. */
export function geometry(width: number, cols: number, gap: number): Geometry {
  const tile = Math.max(1, (width - gap * (cols - 1)) / cols)
  return { cols, tile, rowH: tile + gap, gap }
}

/** Visible rows plus `overscan` above and below, as an item index range [start, end). */
export function windowRange(scrollTop: number, viewH: number, count: number, g: Geometry, overscan = 3): [number, number] {
  const rows = Math.ceil(count / g.cols)
  const first = Math.max(0, Math.floor(scrollTop / g.rowH) - overscan)
  const last = Math.min(rows, Math.ceil((scrollTop + viewH) / g.rowH) + overscan)
  return [first * g.cols, Math.min(count, last * g.cols)]
}

export const totalHeight = (count: number, g: Geometry): number => Math.max(0, Math.ceil(count / g.cols) * g.rowH - g.gap)
