// LoRA list for the current model.
import { createStore } from '../../lib/store'
import { api } from './api'
import type { LoraItem } from './types'

export const loras = createStore<{ model: string | null; items: LoraItem[]; ready: boolean }>({ model: null, items: [], ready: false })

export async function loadLoras(model: string): Promise<void> {
  if (loras.get().model !== model) loras.set({ model, items: [], ready: false })
  try {
    const items = await api.loras(model)
    if (loras.get().model === model) loras.set({ model, items, ready: true })
  } catch {
    if (loras.get().model === model) loras.set(s => ({ ...s, ready: true }))
  }
}

function patchItem(id: string, patch: Partial<LoraItem>): void {
  loras.set(s => ({ ...s, items: s.items.map(l => (l.id === id ? { ...l, ...patch } : l)) }))
}

const strengthTimers = new Map<string, ReturnType<typeof setTimeout>>()

/** The remembered strength is saved 500 ms after it stops changing. */
export function rememberStrength(id: string, strength: number): void {
  patchItem(id, { strength })
  clearTimeout(strengthTimers.get(id))
  strengthTimers.set(id, setTimeout(() => { void api.patchUser(id, { strength }).catch(() => {}) }, 500))
}
