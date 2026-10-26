// The Stage routes (`/api/stage`), their types exactly as the contract writes them. A refusal of a press
// is one line: `{problem}` in the answer, or the hub's error line; both reach the tab as the same text.
import { getJSON, q, sendJSON } from '../../lib/http'

export type Audience = 'none' | 'heard' | 'seen'
export type Mode = 'build' | 'change' | 'house' | 'house-change'
export type State = 'none' | 'rendering' | 'ready' | 'failed'
export type StagePlate = 'wide' | 'left' | 'centre' | 'right' | 'audience'
export type HousePlate = 'wide' | 'left' | 'right' | 'row'
export type File = { id: string; url: string; thumb: string | null }
export type Picture = { id: string; keep: string }
export type HouseWords = { era: string; dress: string; hair: string; size: string }
export type Summary = {
  name: string; approved: boolean; revision: number | null; audience: Audience
  house: boolean; thumb: string | null; state: State
}
export type Draft = {
  mode: Mode; state: State; job: string | null; problem: string | null; model: string | null
  words: string | null; pan: File | null
  plates: Partial<Record<StagePlate | HousePlate, File>> | null
}
export type Approved = {
  record: Record<string, unknown>; plates: Record<StagePlate, File>
  house: Record<HousePlate, File> | null; pan_url: string; house_pan_url: string | null
  pictures: File[]
}
export type Inputs = { pictures: Picture[]; description: string; pieces: string[]; audience: Audience; house: HouseWords }
/** The two Prompt boxes, the stage pan's and the house pan's, held by the hub in memory only. */
export type Prompts = { stage: string; house: string }
export type Detail = { name: string; inputs: Inputs; approved: Approved | null; draft: Draft | null; prompts: Prompts }

/** What Build sends; `prompt` the stage's box. */
export type BuildBody = {
  name: string; pictures: Picture[]; description: string; pieces: string[]; audience: Audience; prompt: string
}

/** The five stage plates and the four house plates, in their row's order, with their labels. */
export const STAGE_PLATES: readonly StagePlate[] = ['wide', 'left', 'centre', 'right', 'audience']
export const HOUSE_PLATES: readonly HousePlate[] = ['wide', 'left', 'right', 'row']
export const PLATE_NAMES: Record<StagePlate | HousePlate, string> = {
  wide: 'Wide', left: 'Left', centre: 'Centre', right: 'Right', audience: 'Audience', row: 'Rows',
}
export const AUDIENCES: readonly Audience[] = ['none', 'heard', 'seen']

/** Boxes 1-9: Ref2VA's nine pictures. */
export const BOXES = 9

type Answer = { job?: string; problem?: string }
const BASE = '/api/stage'

const answer = <T extends Answer>(r: T): T => {
  if (r.problem) throw new Error(r.problem)
  return r
}
const post = <T extends Answer>(path: string, body: unknown): Promise<T> => sendJSON<T>('POST', `${BASE}${path}`, body).then(answer)

export const api = {
  sets: () => getJSON<{ sets: Summary[]; prompts: Prompts }>(`${BASE}/sets`),
  set: (name: string) => getJSON<Detail>(`${BASE}/set?${q({ name })}`),
  build: (body: BuildBody) => post('/build', body),
  again: (name: string) => post('/again', { name }),
  change: (name: string, words: string, prompt: string) => post('/change', { name, words, prompt }),
  house: (name: string, h: HouseWords, prompt: string) => post('/house', { name, ...h, prompt }),
  houseChange: (name: string, words: string, prompt: string) => post('/house-change', { name, words, prompt }),
  approve: (name: string) => post<Answer & { record?: unknown }>('/approve', { name }),
  discard: (name: string) => post('/discard', { name }),
  audience: (name: string, audience: Audience) => post<Answer & { record?: unknown }>('/audience', { name, audience }),
  remove: (name: string) => post('/delete', { name }),
  /** Media items confirmed as pictures the hub reads (as Casting's boxes take them). */
  check: (items: string[]) => sendJSON<{ placed: { item: string; id: string }[] }>('POST', '/api/media/check', { items }),
}

const itemPath = (id: string): string => id.split('/').map(encodeURIComponent).join('/')
/** A media item's thumbnail (a dropped picture, not yet in a record). */
export const itemThumb = (id: string, size: 96 | 336 | 1024 = 336): string => `/thumbs/${itemPath(id)}/${size}`
