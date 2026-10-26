// Pure: the first reason Generate is blocked, or null.
import { QUEUE_MAX, type Draft, type Model } from './types'
import { besideClip, clipInBox, continuesOf, framesOf, isVideo, refsOf, stepMax, videoOf } from './video'

/** The Generate button renders the assistant's draft; with none there is nothing to render. */
export const EMPTY_DRAFT_TEXT = 'The draft is empty'
/** A speech model speaks in the voice of one character: its picture from Characters in box 1 (the hub refuses the same). */
export const NO_SPEAKER_TEXT = "Drop one character's picture"
export const ONE_SPEAKER_TEXT = 'One character speaks at a time'
/** Box 1 holds a clip to continue: nothing goes in boxes 2–3, except identities on a model that takes them. */
export const CLIP_ONLY_TEXT = 'A continued clip takes only box 1'

export type BlockInput = {
  linkOn: boolean
  engineOffline: boolean
  model: Model | null
  prompt: string
  refCount: number
  uploading: number
  waiting: number
  /** The boxes and the frames, for a clip in box 1 (the hub refuses the same lines). */
  draft?: Pick<Draft, 'references' | 'advancedByModel'> & Partial<Pick<Draft, 'video'>>
}

/** A continued clip with a clip in the Video box (the hub refuses the same). */
export const VIDEO_CONTINUE_TEXT = 'A continued clip takes no reference video'

/** The first line a continued clip is refused with: the model, the boxes, the step's length. */
function clipReason(m: Model, d: Pick<Draft, 'references' | 'advancedByModel'> & Partial<Pick<Draft, 'video'>>): string | null {
  if (!clipInBox(d)) return d.references.some(r => r.kind === 'clip') ? CLIP_ONLY_TEXT : null
  if (!continuesOf(m)) return `${m.label} cannot continue a clip`
  if (videoOf({ video: d.video ?? null }, m)) return VIDEO_CONTINUE_TEXT
  if (d.references.length - 1 > besideClip(m)) return CLIP_ONLY_TEXT
  const max = stepMax(m.video)
  return framesOf(d, m) > max ? `Each step is at most ${Math.round((max / m.video.fps) * 10) / 10} s` : null
}

export function blockingReason(i: BlockInput): string | null {
  if (!i.linkOn) return 'Reconnecting…'
  if (i.engineOffline) return 'Engine is offline'
  if (!i.model) return 'Choose a model'
  if (i.prompt.trim() === '') return 'Write a prompt'           // no length cap of the Hub's
  if (i.model.kind === 'speech') {
    if (i.refCount > 1) return ONE_SPEAKER_TEXT
    const who = i.draft?.references[0]
    if (i.refCount === 0 || (who && !/^chars\/[^/]+$/.test(who.id))) return NO_SPEAKER_TEXT
  }
  const clip = i.draft ? clipReason(i.model, i.draft) : null
  if (clip) return clip
  // A video model's references say it all: none (text only), a start frame, or identities (at least `min`).
  const refs = refsOf(i.model)
  const continued = i.draft ? clipInBox(i.draft) !== null : false       // the boxes beside a clip: `clipReason`
  const takesNew = isVideo(i.model) ? (refs?.min ?? 0) === 0 : i.model.modes.includes('new')
  const takesRefs = isVideo(i.model) ? refs !== null : i.model.modes.includes('refs')
  if (!continued && i.refCount === 0 && !takesNew) return 'Add a reference image'
  if (!continued && i.refCount > 0 && !takesRefs) return `${i.model.label} takes no references`
  if (!continued && i.refCount > i.model.refCap) return `Too many references for this model (${i.refCount} of ${i.model.refCap})`
  if (i.uploading > 0) return 'Waiting for the image to upload'
  if (i.waiting >= QUEUE_MAX) return 'Queue is full'
  return null
}
