// Shapes for Generate Image: the server routes and the draft.
/** The server's job modes. The UI never asks: references present → 'refs', else 'new' (see job.ts). */
export type Mode = 'new' | 'refs'

export type Model = {
  id: string
  label: string
  family: string
  modes: Mode[]
  refCap: number
  defaults: { steps: number; guidance: number | null }
  guidanceKey: string | null
  /** `speech`: one typed line in the voice of the one character in box 1; no size, steps or LoRAs. */
  kind: 'image' | 'video' | 'speech'
  video: VideoFacts | null
  /** The most pixels a picture may hold on this model (its engine's budget); missing or null: no limit. */
  budget?: number | null
  /** The model runs its own steps (`defaults.steps`): the Steps control is off. */
  lockSteps?: boolean
}

/** A video model's facts from the engine's definition: the frame lattice (min + k·step up to max), per tier the
 *  exact size for each aspect, the reference pictures it takes (`refCap` is their max), and its text encoder variants (ids in the definition's order, the engine's names, the
 *  default, and those whose files are in the model folders; null when the engine could not tell). */
export type VideoFacts = {
  fps: number
  frames: { min: number; step: number; max: number; default: number }
  steps: number
  tiers: { name: string; sizes: Partial<Record<string, [number, number]>> }[]
  text_encoders?: string[]
  text_encoder_default?: string | null
  text_encoder_names?: Record<string, string>
  text_encoders_found?: string[] | null
  /** The reference pictures it takes: null (text only); a start frame in box 1 (with `end`, a last frame in box 2);
   *  identities in boxes 1…max. */
  references?: VideoRefs | null
  /** Whether it continues a clip in box 1, and the frames it carries over (the step's lattice is `overlap − 1` apart). */
  continues?: boolean
  overlap?: number | null
  /** The engine's largest window: one pass of a continue (step plus carried frames) holds at most this many. */
  window_max?: number
  /** The model follows a sound and keeps it as the clip's: the engine's letters for that; missing: it cannot. */
  soundtrack?: string
  /** The model takes one reference video for camera and set: the engine's letters; missing: it takes none. */
  reference_video?: string
  /** How much of that video the engine keeps, in seconds. */
  reference_video_seconds?: number
}

/** `detail` (identity models whose engine announces it): the engine's choices, in its order, by its labels. */
export type VideoRefs = { role: 'start' | 'identity'; min?: number; max: number; end?: boolean; detail?: Detail }
export type Detail = { key: string; choices: { value: string; label: string }[]; default: string }

/** A LoRA as the hub lists it: what the file says, plus the one thing the hub keeps (a strength). */
export type LoraItem = {
  id: string
  name: string
  file: string
  fileTriggers: string[]
  cover: { url: string } | null
  strength: number | null
  defaultStrength: number
  addedAt: number
}

/** A box's picture, or a clip to continue (box 1 only; `seconds` its length). `cutout`: an identity box's "Cut out
 *  background", on; it travels with its picture. */
export type Slot = { id: string; w: number; h: number; kind?: 'clip'; seconds?: number; cutout?: boolean }
/** A sound from Media → Sounds the clip follows: its id and its length. */
export type SoundSlot = { id: string; seconds: number }
/** A clip from Media → Clips as the reference video: its id and its length. */
export type VideoSlot = { id: string; seconds: number }
export type Aspect = 'auto' | '1:1' | '4:3' | '3:4' | '3:2' | '2:3' | '16:9' | '9:16'
export type Seed = { mode: 'random' } | { mode: 'fixed'; value: number }
/** `frames`, `text_encoder` and `detail` only for a video model (frames on its lattice); missing = the model's default. */
export type Advanced = { steps: number; guidance: number | null; seed: Seed; frames?: number; text_encoder?: string; detail?: string }
export type ActiveLora = { id: string; strength: number }
/** The model last picked of each kind ('' none): the bar's Video and fold bring it back. */
export type LastModel = { image: string; video: string }
export type Draft = {
  model: string | null
  lastModel: LastModel
  prompt: string
  draft: string
  /** Director's first cut: the shot the assistant filled, when the draft is the prompt the hub wrote from
   *  it; held by the server for the session, never sent by a window. */
  shot?: unknown
  lorasByModel: Record<string, ActiveLora[]>
  aspect: Aspect
  size: number
  images: number
  advancedByModel: Record<string, Advanced>
  references: Slot[]
  /** The Sound box: held for the session as the boxes are; sent only to a model with `soundtrack`. */
  sound: SoundSlot | null
  /** The Video box: held for the session as the boxes are; sent only to a model with `reference_video`. */
  video: VideoSlot | null
  selected: string | null
  /** The engine line the server's saved ids belong to, as this window loaded it; every save carries it back, so a
   *  window that loaded before the line changed has its old ids brought over (`rename.window`). */
  engine?: string
}

export const TOOL = 'generate-image'
export const QUEUE_MAX = 10
