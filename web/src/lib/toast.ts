import { createStore } from './store'

type Toast = { id: number; text: string; action?: { label: string; run: () => void } }

export const toasts = createStore<readonly Toast[]>([])
let next = 0

/** At most three toasts; each leaves after `ms`. */
export function toast(text: string, ms = 4000, action?: Toast['action']): void {
  const t: Toast = action ? { id: ++next, text, action } : { id: ++next, text }
  toasts.set(list => [...list, t].slice(-3))
  setTimeout(() => dismiss(t.id), ms)
}

export function dismiss(id: number): void {
  toasts.set(list => (list.some(t => t.id === id) ? list.filter(t => t.id !== id) : list))
}
