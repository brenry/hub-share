// Bus messages.
export type Role = 'workspace' | 'media'

export type Envelope = { t: string; id?: string; re?: string; d?: unknown }

export type EngineState = 'none' | 'starting' | 'ready' | 'busy' | 'stopping' | 'down'

export type Presence = {
  screens: { workspace: number; media: number; aux: number }
  labels: { media?: string[] }
  engines: Record<string, EngineState>
}

export type SocketDecl = { id: string; group: string; label: string; accepts: string[]; filled: boolean }
export type Declaration = { tool: string; mode: string; primary: string | null; sockets: SocketDecl[] }
export type Focus = Declaration & { screen: string; label: string }

export type JobState = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
export type JobProgress = {
  phase: string; index: number; count: number; step: number; steps: number
  pct: number; eta_s: number | null; text: string
}
export type JobSummary = {
  prompt: string; model: string; loras: { name: string; strength: number }[]
  width: number; height: number; count: number; model_id?: string; seeds?: number[]
  /** A video model's job: `clip`, with its frames and seconds; a speech model's: `sound`. */
  kind?: 'image' | 'clip' | 'sound'; frames?: number; seconds?: number
  /** A continued clip: `continue`, with the scene's length after it lands. */
  mode?: string; scene_seconds?: number
  /** A job of steps (the render, then the speaker's voice by SeedVC): each step's name. */
  step_names?: string[]
  /** A scene (`mode` "scene"): its shot count. */
  shots?: number
}
export type Job = {
  id: string; tool: string; kind: string; title: string; lane: string | null
  state: JobState; created: number; started: number | null
  position: number | null
  cancel_requested: boolean; progress: JobProgress | null; outputs: string[]
  error: { stage: string; text: string } | null; summary?: JobSummary
  /** What the hub learned after submit (the Director's plan, the judges' verdicts). */
  notes?: Record<string, unknown>
}

export type ToolInfo = {
  id: string; title: string; tab: { label: string; order: number } | null
  sockets: { id: string; label: string; kinds: string[]; max: number }[]
}

/** `session` changes when a new session opens (the last window had been gone for the grace): what a window kept
 *  of the old one is dropped. */
export type Welcome = {
  proto: number; boot: string; version: string; session: string
  you: { screen: string; role: Role; lanes: string[] }
  limits: { max_bytes: number; deliver_timeout_s: number; beat_after_s: number; silence_s: number }
  tools: ToolInfo[]; presence: Presence; focus: Focus | null
  jobs: Job[]; settings: Record<string, unknown>
}

/** A picture that just landed in Temp, a clip in the clips root (no thumbnail; its size may be unknown) or a sound in
 *  the sounds root (no picture; its `seconds`): the file, nothing about how it was made. */
export type GenerationItem = {
  id: string; kind: 'image' | 'clip' | 'sound'; url: string; thumb: string | null; w: number | null; h: number | null
  created: number; job: string; seconds?: number | null
}

export type DeliverItem = { id: string; kind: string; url: string; seconds?: number }
export type Deliver = { tool: string; socket: string; from: { role: string; label?: string }; items: DeliverItem[] }
export type Placed = { item: string; socket: string }
export type Refused = { item: string; reason: string; text: string }
export type Delivery =
  | { status: 'done'; tool: string; toolLabel: string; placed: Placed[]; refused: Refused[] }
  | { status: 'failed'; reason: string; text: string }

/** The assistant's chat: GET/DELETE /api/assistant/chat and the `assistant.chat` event. */
/** A message: a `user` one, a reply (`seconds` is its time), an error line saying why there was no reply, or the Hub's own
 *  line (`hub`, a module's `chat.note`). */
export type Msg = { id: string; role: 'user' | 'assistant' | 'error' | 'hub'; text: string; at: number; seconds: number | null }
export type ChatView = { busy: boolean; messages: Msg[]; model: string | null }

export type GoingOff = { reason: 'restart' | 'shutdown'; back_in_s: number | null }
export type BusError = { code: string; field?: string; text: string }

/** Drag payload of Media tiles: JSON [{id, w, h}], a clip also `kind` and its `seconds`, `frames` and `fps` (when
 *  known; the Edit Video tracks keep a dropped clip whole by its frames), a sound `kind` and its `seconds`.
 *  Generate's slots accept it; only a Generate box takes a clip (to continue it), Edit Video and Generate's Sound box take a sound,
 *  folders, favorites and characters take pictures. */
export const MEDIA_DRAG = 'application/x-hub-media'
export type DraggedMedia = { id: string; w: number; h: number; kind?: 'clip' | 'sound'; seconds?: number; frames?: number; fps?: number }
export const pictures = (items: DraggedMedia[]): DraggedMedia[] => items.filter(x => x.kind === undefined)
