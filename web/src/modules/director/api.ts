// The Scripts routes (`/api/director`). Every refusal is the hub's one line, shown as it comes back.
import { getJSON, q, sendJSON } from '../../lib/http'
import { inMix } from './mixtime'
import { drawable, lengthMs, panelsOf, type Sketch } from './timeline'

export type Anchor = { line: string; at: 'start' | 'end' }
/** A shot's or event's time in the mixed track; the planned times stay beside it. */
export type Span = { start_ms: number; end_ms: number }
type Timed = { id: string; start_ms: number; end_ms: number; measured?: Span }
export type Line = Timed & { kind: 'line'; speaker: string; words: string; language?: string; emotion?: string; pace?: number }
export type Cue = Timed & { kind: 'cue'; cue: 'effect' | 'music' | 'reaction'; words: string; anchor?: Anchor }
export type Pose = Timed & { kind: 'pose'; character: string; pose: string; anchor?: Anchor }
export type Ev = Line | Cue | Pose
/** A shot's camera as blueprint §2's object; a camera written as text reads as its framing. */
export type Camera = { framing: string; move?: string; on?: string[] }
/** `seconds` the shot's held length; `action` what we see happen in it. */
export type Shot = { id?: string; start_ms: number; end_ms: number; measured?: Span; camera?: string | Camera; seconds?: number; action?: string; events: Ev[] }
export type Scene = { title: string; cast: string[]; shots: Shot[]; seconds?: number }
/** The scene context of a version-2 script: an absent field is not written yet. */
export type Member = { name: string; look?: string; costume?: string; ignore?: string; home?: number }
export type Prop = { name: string; owner?: string | null; description?: string }
export type SetDef = { name: string; description?: string; elements?: string[]; props?: Prop[]; plate?: null }
export type Context = { cast: Member[]; set?: SetDef; style?: string }
export type Script = { version: 1 | 2; context?: Context; scenes: Scene[]; lock?: { locked: boolean; at: string | null } }
/** A sketch panel as the file holds it (blueprint §2); `stale`: its shot changed since it was drawn. */
export type Panel = { id: string; kind: 'panel'; at_ms: number; measured?: { at_ms: number }; picture: string | null; stale: boolean }

export type Summary = { name: string; seconds: number; scenes: number; shots: number; lines: number; changed: number; problem: string | null }
/** One script, or (a file that does not read) none and its one-line problem; `pictures` {cast name: picture id};
 *  `unpictured` the cast names with no picture in Characters; `panels` the script's sketches, read by
 *  `one` before `drawable` drops them. */
export type Opened = { name: string; seconds: number; problem: string | null; script: Script | null; pictures: Record<string, string>; unpictured: string[]; panels?: Sketch[]; audio?: AudioRow[] | null; track?: Track | null
  /** The id of the Track job that holds the script, else null. */
  rendering?: string | null
  /** The id of the Render job that holds the script, else null; the last rendered cut's media id
   *  and its address, else null. */
  rendering_cut?: string | null; cut?: string | null; cut_url?: string | null }
/** The mix's state for a locked script: `url` when its file is in Sounds; `note` the room left out;
 *  `why` a failed mix's one line. */
export type Track = {
  state: 'none' | 'mixing' | 'current' | 'stale' | 'failed'; file?: string; url?: string; length_ms?: number | null
  note?: string | null; why?: string | null
}
/** A take's measured fields: each a number or null (a silent take's `lufs` and `true_peak_dbtp`). */
export type Measured = { speech_start_ms: number | null; speech_end_ms: number | null; length_ms: number | null; lufs: number | null; true_peak_dbtp: number | null; gain_db: number | null }
/** A take's judged fields: `heard` 0..1, `verdict` ok or flagged, `why` its reason; each may be null. */
export type Judge = { heard: number | null; first_miss_ms: number | null; extra_speech: number | null; verdict: 'ok' | 'flagged' | null; why: string | null }
/** The take a row has or would make: its state, its file, and its file's `url`, `measured` and `judge` for a
 *  take whose file is in Sounds. A failed take with no landed file has no `file`. */
export type Take = {
  state: 'none' | 'stale' | 'ok' | 'flagged' | 'rendering' | 'failed'; file?: string; why?: string | null
  url?: string; measured?: Partial<Measured> | null; judge?: Partial<Judge> | null
}
/** One row of a locked script's audio script: a line's block (`text`) or its `problem`, a cue's words;
 *  `seconds` the cap; `hash` its sound fields'; `take` the take it would make. */
export type AudioRow = {
  id: string; kind: 'line' | 'cue'; shot: string; start_ms: number; end_ms: number; who: string; text: string | null
  problem: string | null; sample: string | null; seconds: number; hash: string; take: Take
}

const BASE = '/api/director'

/** One edit of the timeline, as the script tools take it; `start_ms` counts from the shot's start. */
export type EditOp =
  | { op: 'move'; id: string; start_ms: number; shot?: string }
  | { op: 'change'; id: string; fields: Record<string, unknown> }
  | { op: 'add_line'; shot: string; speaker: string; words: string; start_ms?: number }
  | { op: 'add_cue'; shot: string; cue: Cue['cue']; words: string; start_ms?: number }
  | { op: 'add_shot'; scene: number; camera: { framing: string; on?: string[] }; after?: string }
  | { op: 'remove'; id: string }
  | { op: 'member'; member: string; field: 'look' | 'costume' | 'ignore' | 'home'; value: string }
  | { op: 'set'; field: 'name' | 'description' | 'elements' | 'props' | 'style'; value: string }
  | { op: 'length'; seconds: number }
  | { op: 'import'; text: string }
export type Problem = { problem: string }

/** A post whose refusal is its one line, whatever its status. */
async function ask<T>(path: string, body: unknown): Promise<T | Problem> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST', credentials: 'same-origin', headers: { accept: 'application/json', 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  const b = (await res.json().catch(() => ({}))) as { problem?: unknown; text?: unknown }
  if (typeof b.problem === 'string') return { problem: b.problem }
  if (!res.ok) return { problem: typeof b.text === 'string' ? b.text : `Request failed (${res.status})` }
  return b as T
}
export const isProblem = (r: unknown): r is Problem => typeof (r as Problem | null)?.problem === 'string'

/** A Characters picture's 96 px thumbnail (the thumbnail route, as `generate-image/api.ts` `itemThumb`; a module
 *  imports only its own folder, `ui/` and `lib/`). */
export const pictureThumb = (id: string): string => `/thumbs/${id.split('/').map(encodeURIComponent).join('/')}/96`
/** A media item's file (the cut plays from it). */
export const mediaFile = (id: string): string => `/files/${id.split('/').map(encodeURIComponent).join('/')}`

export type VideoLora = { path: string; name: string; on: boolean; strength: number }

export const api = {
  /** The Storyboard's own Video LoRAs (Settings → Video LoRA), each with its toggle and strength. */
  videoLoras: async (): Promise<{ loras: VideoLora[] }> =>
    (await fetch(`${BASE}/video-loras`, { credentials: 'same-origin' })).json() as Promise<{ loras: VideoLora[] }>,
  /** Each shot's own pictures (dragged from Media), by shot id. */
  shotPictures: async (name: string): Promise<{ pictures: Record<string, string[]> }> =>
    (await fetch(`${BASE}/shot-pictures?name=${encodeURIComponent(name)}`, { credentials: 'same-origin' })).json() as Promise<{ pictures: Record<string, string[]> }>,
  setShotPictures: (name: string, shot: string, ids: string[]) =>
    ask<{ pictures: Record<string, string[]> }>('/shot-pictures', { name, shot, ids }),
  videoLora: (path: string, change: { on?: boolean; strength?: number }) =>
    ask<{ loras: VideoLora[] }>('/video-loras', { path, ...change }),
  all: () => getJSON<{ scripts: Summary[] }>(`${BASE}/scripts`).then(r => r.scripts),
  /** A mixed script is drawn in the track's time (`inMix`), its length then the track's. */
  one: (name: string) => getJSON<Opened>(`${BASE}/script?${q({ name })}`).then(o => {
    if (!o.script) return o
    const s = inMix(o.script)
    const seconds = s === o.script ? o.seconds : lengthMs(s) / 1000
    return { ...o, seconds, script: drawable(s), panels: panelsOf(s) }
  }),
  rename: (name: string, to: string) => sendJSON<{ name: string }>('POST', `${BASE}/rename`, { name, to }),
  remove: (name: string) => sendJSON<unknown>('POST', `${BASE}/delete`, { name }),
  /** Renders the takes of a locked script's lines that have none or a stale one; refused in one line. */
  track: (name: string) => sendJSON<{ job: string; lines: number }>('POST', `${BASE}/track`, { name }),
  /** The script rendered as it stands, one job. */
  render: (name: string, shot?: string) => ask<{ job: string }>('/render', shot ? { name, shot } : { name }),
  edit: (name: string, op: EditOp) => ask<unknown>('/edit', { name, ...op }),
}
