// Pure: canvas size and the job payload.
import type { Aspect, Draft, Mode, Model, Slot } from './types'
import { advancedOf, stackOf } from './edits'
import { clipInBox, clipSize, framesOf, isVideo, refsOf, soundOf, videoOf } from './video'

export const RATIOS: Record<Exclude<Aspect, 'auto'>, number> = {
  '1:1': 1, '4:3': 4 / 3, '3:4': 3 / 4, '3:2': 3 / 2, '2:3': 2 / 3, '16:9': 16 / 9, '9:16': 9 / 16,
}
export const SIZES = [1, 1.5, 2, 4] as const

const round16 = (x: number): number => Math.round(x / 16) * 16
const floor16 = (x: number): number => Math.max(16, Math.floor(x / 16) * 16)

/** The canvas for a shape and megapixels, in multiples of 16; above `budget` pixels, the largest canvas of that shape
 *  within it (the server's `screen.canvas`). */
export function canvasSize(ratio: number, mp: number, budget?: number | null): { width: number; height: number } {
  const p = mp * 1048576
  const width = round16(Math.sqrt(p * ratio)), height = round16(Math.sqrt(p / ratio))
  if (budget && width * height > budget) return { width: floor16(Math.sqrt(budget * ratio)), height: floor16(Math.sqrt(budget / ratio)) }
  return { width, height }
}

/** The sizes the menu offers a picture model: those within its budget (the smallest always). */
export const sizesFor = (budget?: number | null): number[] => SIZES.filter((m, i) => !budget || i === 0 || m * 1048576 <= budget)

const slotRatio = (s: Slot | null | undefined): number | null => (s && s.w > 0 && s.h > 0 ? s.w / s.h : null)

/** One path: references in the slots are used, otherwise it is text to image. The server still names the two. */
export const jobMode = (d: Pick<Draft, 'references'>): Mode => (d.references.length > 0 ? 'refs' : 'new')

/** Auto = reference 1's ratio, clamped to 0.4–2.5; 1:1 without references. */
export function autoRatio(d: Pick<Draft, 'references'>): number {
  const r = slotRatio(d.references[0])
  return r === null ? 1 : Math.min(2.5, Math.max(0.4, r))
}

export function canvasOf(d: Pick<Draft, 'aspect' | 'size' | 'references'>, budget?: number | null): { width: number; height: number } {
  return canvasSize(d.aspect === 'auto' ? autoRatio(d) : RATIOS[d.aspect], d.size, budget)
}

const two = (x: number): number => Math.round(x * 100) / 100

type JobParams = {
  tool: string
  model: string
  mode: Mode
  prompt: string
  loras: { id: string; strength: number }[]
  width: number
  height: number
  images: number
  steps: number
  guidance: number | null
  seed: { mode: 'random' } | { mode: 'fixed'; value: number }
  references?: string[]
  frames?: number
  /** One per reference, in box order: an identity model's "Cut out background"; sent only when one is on. */
  cutout?: boolean[]
  /** The Sound box's item, only to a model that keeps a sound: the clip is its length. */
  sound?: string
  /** The Video box's clip, only to a model that takes a reference video. */
  video?: string
}

/** The exact payload of one press of Generate: the assistant's draft (`text`) with the screen's settings. LoRAs at
 *  0.00 stay in the stack but are not sent. A video model makes one clip at its tier's size, with its frames, and its
 *  boxes' pictures only when it takes references (a start frame or identities), and an identity model each box's cut-out.
 *  A clip in box 1 is continued: its size, its id alone. */
export function buildJob(d: Draft, model: Model, text: string = d.draft): JobParams {
  const adv = advancedOf(d, model)
  const video = isVideo(model)
  const clip = video ? clipInBox(d) : null
  const { width, height } = clip ? { width: clip.w, height: clip.h } : video ? clipSize(d, model) : canvasOf(d, model.budget)
  const refs = clip !== null || !video || refsOf(model) !== null
  const job: JobParams = {
    tool: 'generate-image',
    model: model.id,
    mode: refs ? jobMode(d) : 'new',
    prompt: text,
    loras: stackOf(d).filter(l => two(l.strength) > 0).map(l => ({ id: l.id, strength: two(l.strength) })),
    width,
    height,
    images: video ? 1 : d.images,
    steps: model.lockSteps ? model.defaults.steps : adv.steps,
    guidance: model.guidanceKey === null ? null : adv.guidance,
    seed: adv.seed.mode === 'fixed' ? { mode: 'fixed', value: adv.seed.value } : { mode: 'random' },
  }
  if (model.kind === 'speech') job.loras = []                // a line takes no LoRAs (the hub refuses them)
  if (video) job.frames = framesOf(d, model)
  const heard = video ? soundOf(d, model) : null
  if (heard) job.sound = heard.id
  const shown = video ? videoOf(d, model) : null
  if (shown) job.video = shown.id
  if (refs && d.references.length > 0) job.references = clip ? [clip.id] : d.references.map(r => r.id)
  if (!clip && job.references && refsOf(model)?.role === 'identity' && d.references.some(r => r.cutout)) job.cutout = d.references.map(r => r.cutout === true)
  return job
}
