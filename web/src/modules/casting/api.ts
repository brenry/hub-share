// The Casting routes (`/api/casting`: role, seat and costumes). A refusal is one line: `{problem}` in the answer, or the hub's
// error line; both reach the tab as the same text.
import { getJSON, q, sendJSON } from '../../lib/http'

/** The six views, in the sheet's order (front 2, left 21, back 42, right 63, face-1 84, face-2 113). */
export const VIEWS = ['front', 'left', 'back', 'right', 'face-1', 'face-2'] as const
export type View = (typeof VIEWS)[number]
export const VIEW_LABELS: Record<View, string> = {
  front: 'Front', left: 'Left', back: 'Back', right: 'Right', 'face-1': 'Face', 'face-2': 'Three-quarter face',
}

/** An extra's four views (front 2, left 21, right 63, face-1 84), the 4-panel sheet's. */
export const AUDIENCE_VIEWS = ['front', 'left', 'right', 'face-1'] as const satisfies readonly View[]
export type Role = 'cast' | 'audience'
/** The views a role's sheet holds, in its order. */
export const viewsOf = (role: Role | null | undefined): readonly View[] => (role === 'audience' ? AUDIENCE_VIEWS : VIEWS)

/** House left and right, as the audience sees them facing the stage; row 1 nearest the stage. */
export const SIDES = ['left', 'centre', 'right'] as const
export type Side = (typeof SIDES)[number]
export type Seat = { side: Side; row: number }
export const ROWS = 12
export const SEAT: Seat = { side: 'centre', row: 1 }

export type State = 'none' | 'rendering' | 'ready' | 'failed' | 'approved'
export type Lines = { keep: string; ignore: string }
export type Bit = Lines & { id: string }
export type Facts = { age: string; build: string }
/** A character in Characters: its picture's id; `cast` when it has an approved sheet, `role` its role. */
export type Summary = { name: string; picture: string; cast: boolean; role?: Role | null; costumes?: number }
/** A costume's chip: `earlier` when cast from a face frame of an earlier approve. */
export type CostumeChip = { variant: string; state: State; approved: boolean; earlier: boolean; thumb: string | null }
/** Six frame ids, by view or in the sheet's order. */
export type Views = Partial<Record<View, string>> | string[]
/** The approved record's files: the six views and the bits as media ids; the orbit is no media item and plays
 *  from its own address. */
export type Approved = {
  views?: Views | null; bits?: (string | null)[]; orbit_url?: string | null
  /** Versioned addresses (`?v=`), so a re-approve is never hidden by the browser's cache. */
  view_urls?: Partial<Record<View, string>> | null; view_thumbs?: Partial<Record<View, string>> | null
  bit_urls?: (string | null)[] | null
}

/** The character's draft, plus the approved record and its file ids when the character is cast. */
export type Draft = {
  name: string
  picture?: string
  state: State
  headshot: Lines & { id?: string }
  bits: Bit[]
  facts: Facts
  job: string | null
  /** The orbit clip's media id. */
  orbit: string | null
  views: Views | null
  model?: string | null
  problem?: string | null
  record?: Record<string, unknown> | null
  files?: Approved | null
  role?: Role
  seat?: Seat
  costumes?: CostumeChip[]
  /** The tab's Prompt box: one text for every cast and costume, held by the hub in memory only. */
  prompt?: string
}

/** A costume's approved files: the six views, the orbit and the costume pictures, each at a versioned address. */
export type CostumeFiles = Approved & { pictures?: string[] | null; picture_urls?: (string | null)[] | null }

/** A costume's draft: the character's two face frames (boxes 1-2), the costume pictures (3-9) and its words. */
export type Costume = {
  name: string
  variant: string
  state: State
  faces: string[]
  face_thumbs: string[]
  pictures: Bit[]
  words: string
  job: string | null
  orbit: string | null
  views: Views | null
  model?: string | null
  problem?: string | null
  from?: string | null
  record?: Record<string, unknown> | null
  files?: CostumeFiles | null
  prompt?: string
}

/** What Cast sends. */
export type CastBody = { name: string; headshot: Lines; bits: Bit[]; facts: Facts; role?: Role; seat?: Seat; prompt: string }
/** What a costume's Cast sends. */
export type CostumeBody = { name: string; variant: string; pictures: Bit[]; words: string; prompt: string }
type Answer = { job?: string; problem?: string }
type Pair = { name: string; variant: string }

const BASE = '/api/casting'

const answer = <T extends Answer>(r: T): T => {
  if (r.problem) throw new Error(r.problem)
  return r
}

export const api = {
  list: () => getJSON<Summary[]>(`${BASE}/list`),
  draft: (name: string) => getJSON<Draft>(`${BASE}/draft?${q({ name })}`),
  cast: (body: CastBody) => sendJSON<Answer>('POST', `${BASE}/cast`, body).then(answer),
  again: (name: string) => sendJSON<Answer>('POST', `${BASE}/again`, { name }).then(answer),
  approve: (name: string) => sendJSON<Answer & Record<string, unknown>>('POST', `${BASE}/approve`, { name }).then(answer),
  seat: (name: string, seat: Seat) => sendJSON<Answer & { seat?: Seat }>('POST', `${BASE}/seat`, { name, seat }).then(answer),
  /** A costume's draft; a refusal is `{problem}` alone (a draft carries `problem` too, with its state). */
  costume: (p: Pair) => getJSON<Costume>(`${BASE}/costume?${q(p)}`).then(c => {
    if (!c.state && c.problem) throw new Error(c.problem)
    return c
  }),
  costumeCast: (body: CostumeBody) => sendJSON<Answer>('POST', `${BASE}/costume/cast`, body).then(answer),
  costumeAgain: (p: Pair) => sendJSON<Answer>('POST', `${BASE}/costume/again`, p).then(answer),
  costumeApprove: (p: Pair) => sendJSON<Answer & Record<string, unknown>>('POST', `${BASE}/costume/approve`, p).then(answer),
  costumeRemove: (p: Pair) => sendJSON<Answer & { removed?: string }>('POST', `${BASE}/costume/remove`, p).then(answer),
  /** Media items confirmed as pictures the hub reads (as Generate's boxes take them). */
  check: (items: string[]) => sendJSON<{ placed: { item: string; id: string }[] }>('POST', '/api/media/check', { items }),
}

const itemPath = (id: string): string => id.split('/').map(encodeURIComponent).join('/')
/** A media item's file (the orbit plays from it). */
export const itemFile = (id: string): string => `/files/${itemPath(id)}`
/** A media item's thumbnail. */
export const itemThumb = (id: string, size: 96 | 336 | 1024 = 336): string => `/thumbs/${itemPath(id)}/${size}`
