// Pure draft edits. Every change to the draft goes through one of these.
import type { Defaults } from './api'
import type { ActiveLora, Advanced, Draft, Model, Slot } from './types'

export const EMPTY_DRAFT: Draft = {
  model: null, lastModel: { image: '', video: '' }, prompt: '', draft: '', lorasByModel: {}, aspect: 'auto', size: 1, images: 1,
  advancedByModel: {}, references: [], sound: null, video: null, selected: null,
}

/** A stored draft merged over the defaults, so a missing or older file never breaks the page. */
export function normalizeDraft(raw: unknown): Draft {
  if (typeof raw !== 'object' || raw === null) return EMPTY_DRAFT
  const d = { ...EMPTY_DRAFT, ...(raw as Partial<Draft>) }
  const last = (d.lastModel ?? {}) as Partial<Draft['lastModel']>
  return {
    ...d,
    lastModel: { image: typeof last.image === 'string' ? last.image : '', video: typeof last.video === 'string' ? last.video : '' },
    references: Array.isArray(d.references) ? d.references : [],
    sound: d.sound && typeof d.sound.id === 'string' && typeof d.sound.seconds === 'number' ? d.sound : null,
    video: d.video && typeof d.video.id === 'string' && typeof d.video.seconds === 'number' ? d.video : null,
    lorasByModel: d.lorasByModel ?? {},
    advancedByModel: d.advancedByModel ?? {},
    images: Math.min(6, Math.max(1, Math.round(d.images) || 1)),
  }
}

const NONE: ActiveLora[] = []

/** The current model's stack (a stable empty list when there is none). */
export const stackOf = (d: Pick<Draft, 'model' | 'lorasByModel'>): ActiveLora[] => (d.model ? d.lorasByModel[d.model] ?? NONE : NONE)

const defaultsOf = (m: Model): Advanced => ({ steps: m.defaults.steps, guidance: m.defaults.guidance, seed: { mode: 'random' } })

export const advancedOf = (d: Draft, m: Model): Advanced => d.advancedByModel[m.id] ?? defaultsOf(m)

/** The card's own fields at the model's defaults. The text encoder lives on the LoRA sheet, so it does not count. */
export function isDefault(a: Advanced, m: Model): boolean {
  const frames = a.frames === undefined || a.frames === m.video?.frames.default
  return a.steps === m.defaults.steps && a.guidance === m.defaults.guidance && a.seed.mode === 'random' && frames
}

export function withAdvanced(d: Draft, m: Model, patch: Partial<Advanced>): Draft {
  return { ...d, advancedByModel: { ...d.advancedByModel, [m.id]: { ...advancedOf(d, m), ...patch } } }
}

/** Steps, guidance, seed and frames back to the model's; a chosen text encoder and detail (the sheet's) stay. */
export function resetAdvanced(d: Draft, m: Model): Draft {
  const rest = { ...d.advancedByModel }
  const { text_encoder, detail } = rest[m.id] ?? {}
  if (text_encoder === undefined && detail === undefined) delete rest[m.id]
  else rest[m.id] = { ...defaultsOf(m), ...(text_encoder !== undefined && { text_encoder }), ...(detail !== undefined && { detail }) }
  return { ...d, advancedByModel: rest }
}

/** Switch model: its own stack and Advanced come back; it is the last picked of its kind. */
export const withModel = (d: Draft, m: Model): Draft => ({ ...d, model: m.id, selected: null, lastModel: { ...d.lastModel, [m.kind]: m.id } })

function withStack(d: Draft, fn: (s: ActiveLora[]) => ActiveLora[]): Draft {
  if (!d.model) return d
  return { ...d, lorasByModel: { ...d.lorasByModel, [d.model]: fn(stackOf(d)) } }
}

/** On appends in turn-on order and selects it; off removes it. The prompt is never touched. */
export function toggleLora(d: Draft, id: string, strength: number): Draft {
  const on = stackOf(d).some(l => l.id === id)
  const next = withStack(d, s => (on ? s.filter(l => l.id !== id) : [...s, { id, strength }]))
  return on ? next : { ...next, selected: id }
}

export const setStrength = (d: Draft, id: string, strength: number): Draft =>
  withStack(d, s => s.map(l => (l.id === id ? { ...l, strength } : l)))

/** Put an image at reference `index` (replace if filled, else the next free one). */
export function placeRef(d: Draft, index: number, slot: Slot): Draft {
  const refs = [...d.references]
  if (index < refs.length) refs[index] = slot
  else refs.push(slot)
  return { ...d, references: refs }
}

/** Box `i`'s "Cut out background" on or off; off drops the flag, so a box carries it only while on. */
export function toggleCutout(d: Draft, i: number): Draft {
  const r = d.references[i]
  if (!r) return d
  const { cutout, ...plain } = r
  return { ...d, references: d.references.map((x, j) => (j === i ? (cutout ? plain : { ...plain, cutout: true }) : x)) }
}

/** Removing a reference shifts the later ones left, so references stay 1…k. */
export const removeRef = (d: Draft, index: number): Draft => ({ ...d, references: d.references.filter((_, i) => i !== index) })

/** The default model for a job with `refs` references: the refs default with references, the text default without. */
export const defaultModel = (models: readonly Model[], defaults: Defaults, refs: number): Model | null =>
  models.find(m => m.id === (refs > 0 ? defaults.refs : defaults.text)) ?? null

/** The bar's Video (`video`) or fold (`image`) from a model of the other kind: the draft goes onto the last picked of
 *  that kind, else its default (the video default; the image one for the draft's references), and the model it leaves
 *  stays the last of its own kind. Null when the draft is already on that kind or neither is known: the button then
 *  only raises or lowers its sheet. */
export function switchKind(d: Draft, models: readonly Model[], defaults: Defaults, kind: 'image' | 'video'): Draft | null {
  const cur = models.find(m => m.id === d.model) ?? null
  const sheet = (m: Model) => (m.kind === 'video' ? 'video' : 'image')
  if (cur && sheet(cur) === kind) return null
  const of = (id: string | null) => models.find(m => m.id === id && sheet(m) === kind)
  const next = of(d.lastModel[kind]) ?? (kind === 'video' ? of(defaults.video) : of(defaultModel(models, defaults, d.references.length)?.id ?? null))
  return next ? withModel(cur ? withModel(d, cur) : d, next) : null
}
