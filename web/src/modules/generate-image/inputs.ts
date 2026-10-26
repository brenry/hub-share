// Placing images into the reference slots: local files, Media tiles and Media Send.
import { errorText } from '../../lib/http'
import type { DraggedMedia } from '../../lib/protocol'
import { createStore } from '../../lib/store'
import { api, itemThumb } from './api'
import { CLIP_ONLY_TEXT } from './blocking'
import { edit, draft } from './draft'
import { placeRef } from './edits'
import { modelList } from './modelList'
import type { Model, Slot } from './types'
import { besideClip, clipInBox, inShape, refsOf, shapeNote } from './video'

export const uploading = createStore(0)
export const flashing = createStore<readonly string[]>([])
export const slotNote = createStore<string | null>(null)

const TYPES = ['image/png', 'image/jpeg', 'image/webp']
const MAX_BYTES = 25 * 1024 * 1024

let noteTimer: ReturnType<typeof setTimeout> | undefined
export function note(text: string | null): void {
  slotNote.set(text)
  clearTimeout(noteTimer)
  if (text) noteTimer = setTimeout(() => slotNote.set(null), 4000)
}

/** 600 ms brass outline on slots that just received an image. */
export function flash(sockets: string[]): void {
  flashing.set(f => [...f, ...sockets])
  setTimeout(() => flashing.set(f => f.filter(s => !sockets.includes(s))), 600)
}

export async function imageSize(url: string): Promise<{ w: number; h: number }> {
  const img = new Image()
  img.src = url
  await img.decode()
  return { w: img.naturalWidth, h: img.naturalHeight }
}

export type Target = number

/** Slot indexes for n images dropped on `target`: that slot first, then the free ones after it. */
export function dropPlan(target: Target, n: number, filled: number, cap: number): { indexes: number[]; extra: number } {
  const first = Math.min(target, filled)
  const rest: number[] = []
  for (let i = Math.max(filled, first + 1); i < cap && rest.length < n - 1; i++) rest.push(i)
  const indexes = n > 0 && first < cap ? [first, ...rest] : []
  return { indexes, extra: n - indexes.length }
}

function place(index: number, slot: Slot): string {
  edit(d => placeRef(d, Math.min(index, d.references.length), slot))
  return `reference_${Math.min(index, draft.get().references.length - 1) + 1}`
}

/** A clip in box 1 takes nothing beside it, except identities on a model that takes them (`besideClip`): a picture
 *  is refused with one line, as is one dropped on the clip's box. -> whether it was. */
function clipRefuses(model: Model, target: Target): boolean {
  if (!clipInBox(draft.get()) || (besideClip(model) > 0 && target > 0)) return false
  note(CLIP_ONLY_TEXT)
  return true
}

/** The boxes a model fills: beside a clip in box 1, the clip's and the identities after it; else its cap. */
function capOf(model: Model): number {
  return clipInBox(draft.get()) ? besideClip(model) + 1 : model.refCap
}

/** An identity box takes a picture between 1:4 and 4:1: one outside is not placed and the note says so. A start
 *  frame or an image model's reference is left to the server. */
export function fitsBox(model: Model | null, size: { w: number; h: number }): boolean {
  if (!model || refsOf(model)?.role !== 'identity' || inShape(size.w, size.h)) return true
  note(shapeNote(model))
  return false
}

function refusedNote(extra: number): void {
  if (extra === 0) return
  note(`${extra} not added: references are full`)
}

export async function addFiles(files: File[], target: Target, model: Model): Promise<void> {
  if (clipRefuses(model, target)) return
  const ok = files.filter(f => TYPES.includes(f.type) && f.size <= MAX_BYTES)
  if (ok.length < files.length) note('PNG, JPEG or WebP up to 25 MB')
  const d = draft.get()
  const { indexes, extra } = dropPlan(target, ok.length, d.references.length, capOf(model))
  refusedNote(extra)
  const chosen = ok.slice(0, indexes.length)
  uploading.set(n => n + chosen.length)
  const results = await Promise.allSettled(chosen.map(async file => {
    const local = URL.createObjectURL(file)
    try {
      const size = await imageSize(local)
      return fitsBox(model, size) ? { id: (await api.upload(file)).id, ...size } : null
    } finally {
      URL.revokeObjectURL(local)
    }
  }))
  uploading.set(n => n - chosen.length)
  const sockets: string[] = []
  results.forEach((r, i) => {
    if (r.status === 'rejected') note(errorText(r.reason))
    else if (r.value) sockets.push(place(indexes[i]!, r.value))
  })
  flash(sockets)
}

export async function addMedia(items: DraggedMedia[], target: Target, model: Model): Promise<void> {
  if (clipRefuses(model, target)) return
  const d = draft.get()
  const { indexes, extra } = dropPlan(target, items.length, d.references.length, capOf(model))
  refusedNote(extra)
  const chosen = indexes.map((index, i) => ({ index, item: items[i]! })).filter(c => fitsBox(model, c.item))
  if (chosen.length === 0) return
  uploading.set(n => n + 1)
  try {
    const res = await api.check(chosen.map(c => c.item.id))
    const sockets = chosen.flatMap(c => {
      const input = res.placed.find(p => p.item === c.item.id)
      return input ? [place(c.index, { id: input.id, w: c.item.w, h: c.item.h })] : []
    })
    flash(sockets)
  } catch (e) {
    note(errorText(e))
  } finally {
    uploading.set(n => n - 1)
  }
}

export const slotThumb = (s: Slot): string => itemThumb(s.id, 336)

/** A character picked by Tab in the prompt box: its picture goes in the first free reference box, as a drag from
 *  Media would put it. Already in a box: that box flashes and nothing is added. No box free, or a model that takes
 *  no reference pictures: a short note, nothing replaced. */
export async function addCharacter(c: DraggedMedia): Promise<void> {
  const d = draft.get()
  const at = d.references.findIndex(r => r.id === c.id)
  if (at >= 0) { flash([`reference_${at + 1}`]); return }
  const model = modelList.get()?.find(m => m.id === d.model) ?? null
  if (!model) { note('Choose a model first'); return }
  if (model.refCap === 0) { note('This model takes no reference pictures'); return }
  await addMedia([{ id: c.id, w: c.w, h: c.h }], d.references.length, model)
}
