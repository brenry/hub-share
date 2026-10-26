// Pure: how the LoRA column is ordered and labelled.
import type { ActiveLora, LoraItem } from '../types'

/** How long a file counts as new: two weeks from its file time. */
export const NEW_FOR_MS = 14 * 24 * 60 * 60 * 1000

const collator = new Intl.Collator('en', { sensitivity: 'base', numeric: true })

/** The file name without its extension: the name shown in the folder and looked up by. */
export const stem = (l: Pick<LoraItem, 'file'>): string => l.file.replace(/\.[^.]+$/, '')

/** The LoRAs not on the model's stack, A–Z by file name. */
export function others(items: LoraItem[], stack: ActiveLora[]): LoraItem[] {
  const on = new Set(stack.map(l => l.id))
  return items.filter(l => !on.has(l.id)).sort((a, b) => collator.compare(stem(a), stem(b)))
}

/** A file is marked new while it is recent and has never been used in a job. */
export const isNew = (l: Pick<LoraItem, 'addedAt'>, now: number): boolean => now - l.addedAt * 1000 < NEW_FOR_MS

/** The strength line's share of the row: full at 1.0; over 1.0 stays full (the number says the rest). */
export const share = (strength: number): number => Math.max(0, Math.min(1, strength))
