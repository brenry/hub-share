// The sequence routes (`/api/sequence`) and the upload of a recording into Sounds (`/api/sounds/upload`). Every
// refusal is the hub's one line, shown as it comes back.
import { getJSON, q, sendBlob, sendJSON } from '../../lib/http'
import { spec, type Item, type Put } from './seq'

export type Summary = { name: string; clips: number; seconds: number; changed: number }
export type Tracks = [Item[], Item[]]
export type Sequence = { name: string; revision: number; tracks: Tracks }

/** The line the hub answers a save drawn from an old revision with. */
export const CHANGED = 'The sequence changed in another window'

const BASE = '/api/sequence'

export const api = {
  all: () => getJSON<{ sequences: Summary[] }>(`${BASE}/all`).then(r => r.sequences),
  one: (name: string) => getJSON<Sequence>(`${BASE}/one?${q({ name })}`),
  create: (name: string) => sendJSON<Sequence>('POST', `${BASE}/new`, { name }),
  save: (name: string, revision: number, tracks: Put[][]) =>
    sendJSON<Sequence>('PUT', `${BASE}/one`, { name, revision, tracks: tracks.map(t => t.map(spec)) }),
  rename: (name: string, to: string) => sendJSON<{ name: string }>('POST', `${BASE}/rename`, { name, to }),
  remove: (name: string) => sendJSON<unknown>('POST', `${BASE}/delete`, { name }),
  join: (name: string) => sendJSON<{ job: string }>('POST', `${BASE}/join`, { name }),
  sound: (wav: Blob) => sendBlob<{ id: string; seconds: number }>('POST', '/api/sounds/upload', wav),
}
