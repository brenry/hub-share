// Pure: a video model on the Generate Image screen. The size menu's megapixels value picks a tier (≤1 the first,
// 1.5 and 2 the second, 4 the third when offered); each tier has its exact size per aspect. Clip length is frames on
// the engine's lattice (min + k·step, up to max), shown and typed as seconds. Reference boxes carry the model's role.
import { RATIOS, autoRatio } from './job'
import type { Aspect, Draft, Model, Slot, SoundSlot, VideoFacts, VideoRefs, VideoSlot } from './types'

const VALUES = [1, 2, 4] as const

export const isVideo = (m: Model | null | undefined): m is Model & { video: VideoFacts } => m?.kind === 'video' && m.video != null

const tierIndex = (v: VideoFacts, mp: number): number => Math.max(0, Math.min(v.tiers.length - 1, mp <= 1 ? 0 : mp <= 2 ? 1 : 2))

export const tierOf = (v: VideoFacts, mp: number): VideoFacts['tiers'][number] => v.tiers[tierIndex(v, mp)]!

/** The menu: the offered tiers (three at most), each stored as its megapixels value. */
export const tierOptions = (v: VideoFacts): { value: string; name: string }[] =>
  v.tiers.slice(0, VALUES.length).map((t, i) => ({ value: String(VALUES[i]), name: t.name }))

/** The menu's value for the draft's size: the value of the tier it picks. */
export const sizeValue = (v: VideoFacts, mp: number): string => String(VALUES[tierIndex(v, mp)])

const ratioOf = (key: string): number => { const [a, b] = key.split(':').map(Number); return a && b ? a / b : 1 }

/** The tier's size for the aspect; Auto is the tier's shape nearest `auto` (square unless a start frame sets it), as
 *  the server's `tier_size`; an aspect the tier lacks takes the nearest shape it has. */
export function tierSize(v: VideoFacts, mp: number, aspect: Aspect, auto = 1): { width: number; height: number } {
  const sizes = tierOf(v, mp).sizes
  const want = aspect === 'auto' ? auto : RATIOS[aspect]
  const hit = (aspect === 'auto' ? undefined : sizes[aspect]) ?? Object.entries(sizes)
    .sort(([a], [b]) => Math.abs(Math.log(ratioOf(a) / want)) - Math.abs(Math.log(ratioOf(b) / want)))[0]?.[1]
  return hit ? { width: hit[0], height: hit[1] } : { width: 0, height: 0 }
}

/** Seconds as shown: one decimal. */
export const secondsOf = (v: VideoFacts, frames: number): number => Math.round((frames / v.fps) * 10) / 10

/** Frames snapped up to the lattice, inside min..max. */
export function snapFrames(v: VideoFacts, frames: number): number {
  const { min, step, max } = v.frames
  if (frames <= min) return min
  return Math.min(max, min + Math.ceil((frames - min) / step - 1e-9) * step)
}

/** Typed seconds → the first frame count on the lattice that shows at least those seconds (so a shown value typed
 *  back keeps its frames). */
export function toFrames(v: VideoFacts, seconds: number): number {
  const { min, step, max } = v.frames
  for (let f = min; f <= max; f += step) if (secondsOf(v, f) >= seconds - 1e-9) return f
  return snapFrames(v, max)
}

/** The draft's frames for the model: the draft's `frames`, else the model's default. */
export const framesOf = (d: Pick<Draft, 'advancedByModel'>, m: Model): number =>
  (m.video ? snapFrames(m.video, d.advancedByModel[m.id]?.frames ?? m.video.frames.default) : 0)

/** The draft's text encoder for the model: the draft's when the model lists it, else the definition's default. */
export const encoderOf = (d: Pick<Draft, 'advancedByModel'>, m: Model): string => {
  const ids = m.video?.text_encoders ?? []
  const saved = d.advancedByModel[m.id]?.text_encoder
  return saved !== undefined && ids.includes(saved) ? saved : m.video?.text_encoder_default ?? ids[0] ?? ''
}

/** The text encoder menu: each variant by the engine's name; one whose file is not in the model folders says so. */
export const encoderOptions = (v: VideoFacts): { value: string; label: string }[] =>
  (v.text_encoders ?? []).map(id => {
    const name = v.text_encoder_names?.[id] ?? id
    return { value: id, label: v.text_encoders_found && !v.text_encoders_found.includes(id) ? `${name} · not found` : name }
  })

/** The reference pictures a video model takes (null: none, or an image model). */
export const refsOf = (m: Model | null | undefined): VideoRefs | null => (isVideo(m) ? m.video.references ?? null : null)

/** The draft's detail for the model: the draft's when the model announces it, else the engine's default ('' when
 *  the model has no detail setting). */
export const detailOf = (d: Pick<Draft, 'advancedByModel'>, m: Model): string => {
  const det = refsOf(m)?.detail
  const saved = d.advancedByModel[m.id]?.detail
  return !det ? '' : saved !== undefined && det.choices.some(c => c.value === saved) ? saved : det.default
}

/** The detail menu: the engine's choices in its order, by its labels. */
export const detailOptions = (r: VideoRefs | null | undefined): { value: string; label: string }[] =>
  (r?.detail?.choices ?? []).map(c => ({ value: c.value, label: c.label }))

/** The identity boxes' shape rule: the long side at most four times the short (an unknown size is left to the server). */
export const inShape = (w: number, h: number): boolean => !(w > 0 && h > 0) || Math.max(w, h) <= 4 * Math.min(w, h)

/** The one line for a picture outside that shape. */
export const shapeNote = (m: Model): string => `${m.label} takes pictures between 1:4 and 4:1`

/** Auto's shape for a video model: box 1's when it holds the start frame, else square. */
export const autoOf = (d: Pick<Draft, 'references'>, m: Model): number =>
  (refsOf(m)?.role === 'start' && d.references.length > 0 ? autoRatio(d) : 1)

/** The clip's canvas: the tier's size for the draft's aspect (Auto follows a start frame). */
export const clipSize = (d: Pick<Draft, 'size' | 'aspect' | 'references'>, m: Model & { video: VideoFacts }): { width: number; height: number } =>
  tierSize(m.video, d.size, d.aspect, autoOf(d, m))

/** Box `i`'s name: "Start frame" (box 1 of a start-frame model), "Last frame" (its box 2 when it takes an end frame),
 *  "Identity n" (an identity model's boxes; beside a clip in box 1 (`clip`), boxes 2… are Identity 1…), else
 *  "Reference n". */
export function boxLabel(m: Model | null, i: number, clip = false): string {
  const r = refsOf(m)
  if (clip && i > 0 && i <= besideClip(m)) return `Identity ${i}`
  if (r?.role === 'start' && i === 0) return 'Start frame'
  if (r?.role === 'start' && r.end && i === 1) return 'Last frame'
  if (r?.role === 'identity' && i < r.max) return `Identity ${i + 1}`
  return `Reference ${i + 1}`
}

/** Whether the model continues a clip: the catalog says so and gives the frames it carries over. */
export const continuesOf = (m: Model | null | undefined): m is Model & { video: VideoFacts } => isVideo(m) && m.video.continues === true && (m.video.overlap ?? 0) > 1

/** The longest step that continues a clip, in frames: one pass is the step plus the carried frames, at most the
 *  engine's largest window (`window_max`, else `max`); the step itself at most `max`. */
export const stepMax = (v: VideoFacts): number => Math.min(v.frames.max, (v.window_max ?? v.frames.max) - (v.overlap ?? 1) + 1)

/** A step's new seconds: the first of its frames is the clip's last. One decimal. */
export const stepSeconds = (v: VideoFacts, frames: number): number => Math.round(((frames - 1) / v.fps) * 10) / 10

/** The bar's boxes: three, always. */
export const BOXES = 3

/** How many boxes after a clip in box 1 take a picture: on a model that continues a clip and whose boxes are
 *  identities, its maximum, within the bar's boxes; else none (the hub refuses the same). */
export function besideClip(m: Model | null | undefined): number {
  const r = refsOf(m)
  return continuesOf(m) && r?.role === 'identity' ? Math.min(r.max, BOXES - 1) : 0
}

/** The clip in box 1, when the draft continues one. */
export const clipInBox = (d: Pick<Draft, 'references'>): Slot | null => (d.references[0]?.kind === 'clip' ? d.references[0] : null)

/** A clip's file name without its folder and suffix: "clips/2026-10-13/101500-123.mp4" -> "101500-123". */
export const stemOf = (id: string): string => (id.split('/').pop() ?? id).replace(/\.[^.]*$/, '')

/** The sound the clip follows: the Sound box's, when the model keeps a sound as its clip's; else null. */
export const soundOf = (d: Pick<Draft, 'sound'>, model: Model | null): SoundSlot | null =>
  (model?.video?.soundtrack ? d.sound ?? null : null)

/** The reference video: the Video box's clip, when the model takes one; else null. */
export const videoOf = (d: Pick<Draft, 'video'>, model: Model | null): VideoSlot | null =>
  (model?.video?.reference_video ? d.video ?? null : null)
