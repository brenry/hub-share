// Pure: Media selection. `order` is the grid order, newest first.
export type Selection = { ids: readonly string[]; anchor: string | null; current: string | null }

export const EMPTY_SEL: Selection = { ids: [], anchor: null, current: null }

export function click(sel: Selection, order: readonly string[], id: string, mods: { ctrl: boolean; shift: boolean }): Selection {
  if (mods.shift && sel.anchor !== null && order.includes(sel.anchor)) {
    const a = order.indexOf(sel.anchor)
    const b = order.indexOf(id)
    const range = order.slice(Math.min(a, b), Math.max(a, b) + 1)
    return { ids: range, anchor: sel.anchor, current: id }
  }
  if (mods.ctrl) {
    const on = sel.ids.includes(id)
    const ids = on ? sel.ids.filter(x => x !== id) : order.filter(x => x === id || sel.ids.includes(x))
    return { ids, anchor: id, current: id }
  }
  return { ids: [id], anchor: id, current: id }
}

export const selectAll = (order: readonly string[], sel: Selection): Selection =>
  ({ ids: [...order], anchor: sel.anchor ?? order[0] ?? null, current: sel.current ?? order[0] ?? null })

/** Arrows by one or by a real grid row; Home / End. The moved-to image becomes the single selection. */
export function move(sel: Selection, order: readonly string[], key: string, cols: number): Selection {
  if (order.length === 0) return sel
  const i = sel.current === null ? -1 : order.indexOf(sel.current)
  const last = order.length - 1
  const next =
    key === 'ArrowRight' ? Math.min(last, i + 1)
    : key === 'ArrowLeft' ? Math.max(0, i - 1)
    : key === 'ArrowDown' ? Math.min(last, i < 0 ? 0 : i + cols)
    : key === 'ArrowUp' ? Math.max(0, i - cols)
    : key === 'Home' ? 0
    : key === 'End' ? last
    : i
  const id = order[Math.max(0, next)]!
  return { ids: [id], anchor: id, current: id }
}

/** Esc clears the selection; the Stage keeps its image. */
export const clear = (sel: Selection): Selection => ({ ids: [], anchor: null, current: sel.current })

/** What Send and Delete act on: the selection in grid order, else the current image. */
export function targets(sel: Selection, order: readonly string[]): string[] {
  if (sel.ids.length > 0) return order.filter(id => sel.ids.includes(id))
  return sel.current !== null && order.includes(sel.current) ? [sel.current] : []
}

/** After a delete, the Stage moves to the next older image, else the previous one. */
export function afterDelete(order: readonly string[], removed: readonly string[], current: string | null): string | null {
  const gone = new Set(removed)
  const i = current === null ? 0 : Math.max(0, order.indexOf(current))
  for (let k = i; k < order.length; k++) if (!gone.has(order[k]!)) return order[k]!
  for (let k = i - 1; k >= 0; k--) if (!gone.has(order[k]!)) return order[k]!
  return null
}

/** Follow: a new generation becomes the Stage image and the single selection, unless 2+ are selected. */
export function follow(sel: Selection, id: string): { sel: Selection; stole: boolean } {
  if (sel.ids.length >= 2) return { sel, stole: false }
  return { sel: { ids: [id], anchor: id, current: id }, stole: true }
}
