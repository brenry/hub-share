// Media data: the Temp (newest first, paged) and its groups — Favorites is one of them, a folder inside each day —
// the clips and the sounds (each its own root, paged the same way, one flat list newest first, as the Temp), the Drive's folders, and the favorite folders
// (Drive paths pinned under Favorites: a list, nothing moved). A picture is all the hub knows about a picture. Nothing
// polls: a new file prepends on `generation`, everything refetches on (re)connect and on `media.changed` from another
// window.
import { getJSON, q, sendBlob, sendJSON } from '../../lib/http'
import type { DraggedMedia, GenerationItem, Job } from '../../lib/protocol'
import { createStore } from '../../lib/store'
import { toVoiceWav } from '../../lib/wav'

/** A clip has no thumbnail, its length in `seconds` and, when listed, its `frames` and `fps`; a size the server does not know is 0.
 *  A sound has no picture at all: its length in `seconds`. */
export type MediaItem = { id: string; kind: 'image' | 'clip' | 'sound'; url: string; thumb: string | null; w: number; h: number; seconds?: number | null
  frames?: number | null; fps?: number | null; createdAt: number; group: string; fav: boolean }
type Raw = Omit<MediaItem, 'kind' | 'thumb' | 'w' | 'h'> & { kind?: string; thumb?: string | null; w: number | null; h: number | null }
/** What a tile carries when dragged: a picture's address and size, a clip also its kind, length, frames and fps (each
 *  when known). */
export function dragged(i: MediaItem): DraggedMedia {
  const d: DraggedMedia = { id: i.id, w: i.w, h: i.h }
  if (i.kind === 'sound') return { ...d, kind: 'sound', ...(typeof i.seconds === 'number' ? { seconds: i.seconds } : {}) }
  if (i.kind !== 'clip') return d
  const known = (k: 'seconds' | 'frames' | 'fps') => (typeof i[k] === 'number' ? { [k]: i[k] } : {})
  return { ...d, kind: 'clip', ...known('seconds'), ...known('frames'), ...known('fps') }
}
type Group = { name: string; count: number }
/** The Clips section's view: every clip of every day, one flat list newest first, as listed. */
export type View = { kind: 'temp'; group: string } | { kind: 'clips' } | { kind: 'sounds' } | { kind: 'drive'; path: string } | { kind: 'chars'; focus: string }
/** `voice`: the words for its voice; `sample`: it has its voice as a sound beside its picture. */
export type Character = MediaItem & { name: string; notes: string; voice: string; sample: boolean; views?: { id: string; view: string }[] }
type Folder = { path: string; name: string; dirs: string[]; items: MediaItem[]; unset?: boolean }
type Page = { items: Raw[]; more: boolean; total: number; groups: Group[] }
type Listing = { items: MediaItem[]; more: boolean; ready: boolean; total: number; groups: Group[] }
export type FavFolder = { path: string; name: string; ok: boolean }

const PAGE = 200
export const TEMP: View = { kind: 'temp', group: '' }
export const CLIPS: View = { kind: 'clips' }
export const SOUNDS: View = { kind: 'sounds' }
export const FAVORITES = 'Favorites'

const listing = (): Listing => ({ items: [], more: false, ready: false, total: 0, groups: [] })
export const temp = createStore<Listing>(listing())
export const clips = createStore<Listing>(listing())
export const sounds = createStore<Listing>(listing())
export const drive = createStore<Record<string, Folder>>({})
export const favFolders = createStore<FavFolder[]>([])
export const characters = createStore<{ unset: boolean; items: Character[] }>({ unset: true, items: [] })
/** Where the window opens: /clips on the Clips section, /sounds on the Sounds, anything else on the Temp. */
export const startView = (path: string): View => {
  const p = path.replace(/\/+$/, '')
  return p === '/clips' ? CLIPS : p === '/sounds' ? SOUNDS : TEMP
}
export const view = createStore<View>(startView(globalThis.location?.pathname ?? '/'))
/** The Stage's clip player loops (the clip menu's Loop, or L): kept for the window's session, in memory only. */
export const looping = createStore(true)          // Loop on by default
/** A picture waiting for its character name (from a drop on the heading or Add to Characters); the tree asks. */
export const naming = createStore<{ id: string; value: string } | null>(null)

export const isTemp = (id: string): boolean => id.startsWith('out/')

/** A listed root: the Temp (`out`, asked without a root), the clips or the sounds. */
type Root = 'out' | 'clips' | 'sounds'
const lists = { out: temp, clips, sounds }
const rootQuery = (r: Root): { root?: string } => (r === 'out' ? {} : { root: r })

/** A server item as the window keeps it: no kind is a picture; a clip's thumbnail is its first frame, a sound has none. */
export function norm(i: Raw): MediaItem {
  const kind = i.kind === 'clip' || i.kind === 'sound' ? i.kind : 'image'
  return { ...i, kind, thumb: i.thumb ?? null, w: i.w ?? 0, h: i.h ?? 0 }
}
const key = (v: View): string => (v.kind === 'temp' ? v.group : v.kind === 'clips' || v.kind === 'sounds' ? '' : v.kind === 'drive' ? v.path : v.focus)
export const sameView = (a: View, b: View): boolean => a.kind === b.kind && key(a) === key(b)

export const fromGeneration = (g: GenerationItem): MediaItem => {
  const parts = g.id.split('/')
  const group = parts.length > 3 ? parts.slice(2, -1).join('/') : ''
  return norm({ id: g.id, kind: g.kind, url: g.url, thumb: g.thumb, w: g.w, h: g.h, createdAt: g.created, group, fav: group === FAVORITES,
    ...(g.kind === 'sound' ? { seconds: g.seconds ?? null } : {}) })
}

/** The items a view shows, in its order. */
export function itemsOf(v: View): MediaItem[] {
  if (v.kind === 'drive') return drive.get()[v.path]?.items ?? []
  if (v.kind === 'chars') return characters.get().items
  if (v.kind === 'clips') return clips.get().items
  if (v.kind === 'sounds') return sounds.get().items
  const all = temp.get().items
  return v.group ? all.filter(i => i.group === v.group) : all
}

async function loadRoot(r: Root): Promise<void> {
  const page = await getJSON<Page>(`/api/media?${q({ ...rootQuery(r), limit: PAGE })}`)
  lists[r].set({ items: page.items.map(norm), more: page.more, ready: true, total: page.total, groups: page.groups })
}

const loadingMore = new Set<Root>()
/** The next page of the Temp, the clips or the sounds. */
export async function loadMore(r: Root): Promise<void> {
  const { items, more } = lists[r].get()
  const last = items[items.length - 1]
  if (!more || !last || loadingMore.has(r)) return
  loadingMore.add(r)
  try {
    const page = await getJSON<Page>(`/api/media?${q({ ...rootQuery(r), before: last.id, limit: PAGE })}`)
    lists[r].set(m => {
      const known = new Set(m.items.map(i => i.id))
      return { ...m, items: [...m.items, ...page.items.filter(i => !known.has(i.id)).map(norm)], more: page.more }
    })
  } finally {
    loadingMore.delete(r)
  }
}

/** A new file at the top of its root: a clip in the clips, a sound in the sounds, a picture in the Temp. */
export function prepend(item: MediaItem): void {
  lists[item.kind === 'clip' ? 'clips' : item.kind === 'sound' ? 'sounds' : 'out'].set(m => {
    if (m.items.some(i => i.id === item.id)) return m
    const groups = item.kind === 'image' && item.group && !m.groups.some(g => g.name === item.group)
      ? [...m.groups, { name: item.group, count: 0 }].sort((a, b) => a.name.localeCompare(b.name)) : m.groups
    return { ...m, items: [item, ...m.items], total: m.total + 1, groups: groups.map(g => (g.name === item.group ? { ...g, count: g.count + 1 } : g)) }
  })
}

export async function loadFolder(path: string): Promise<Folder> {
  const raw = await getJSON<Folder>(`/api/media/drive?${q({ path })}`)
  const f = { ...raw, items: raw.items.map(norm) }
  drive.set(d => ({ ...d, [path]: f }))
  return f
}

async function loadFavFolders(): Promise<void> {
  favFolders.set((await getJSON<{ folders: FavFolder[] }>('/api/media/favorite-folders')).folders)
}

/** Pin a Drive folder under Favorites, or take it off. Only the list changes: no folder or file moves. */
export async function favFolder(path: string, on: boolean): Promise<void> {
  favFolders.set((await sendJSON<{ folders: FavFolder[] }>('POST', '/api/media/favorite-folders', { path, on })).folders)
}

/** The Characters folder: each picture with its name (the file name). */
export async function loadCharacters(): Promise<void> {
  const c = await getJSON<{ unset: boolean; items: Character[] }>('/api/media/characters')
  characters.set({ ...c, items: c.items.map(x => ({ ...x, ...norm(x) })) })
}

/** Make a picture the character called `name` — a copy; the picture that had the name is replaced. */
export async function putCharacter(name: string, id: string): Promise<void> {
  await sendJSON<{ id: string }>('POST', '/api/media/characters', { name, id })
  await loadCharacters()
}

/** The character's file takes a new name. -> its new id. */
export async function renameCharacter(id: string, name: string): Promise<string> {
  const r = await sendJSON<{ id: string }>('POST', '/api/media/characters/rename', { id, name })
  await loadCharacters()
  return r.id
}

/** `notes` on a character, saved inside its file ("" clears them). -> its id (the file is now a PNG). */
export async function saveCharacterNotes(id: string, notes: string): Promise<string> {
  const r = await sendJSON<{ id: string }>('POST', '/api/media/characters/notes', { id, notes })
  await loadCharacters()
  return r.id
}

/** The words for a character's voice, saved inside its file ("" clears them). -> its id (the file is now a PNG). */
export async function saveCharacterVoice(id: string, voice: string): Promise<string> {
  const r = await sendJSON<{ id: string }>('POST', '/api/media/characters/voice', { id, voice })
  await loadCharacters()
  return r.id
}

/** A sound kept as the voice of the character called `name`: `<Name>.wav` beside its picture, replacing its old one. */
export async function keepVoice(id: string, name: string): Promise<void> {
  await sendJSON<{ id: string }>('POST', '/api/media/keep-voice', { id, name })
  await loadCharacters()
}

/** A recording (an mp3 or wav file) as the voice of the character `id`: made a WAV here, whole,
 *  kept as `<Name>.wav` beside its picture, replacing its old one. */
export async function putVoiceSample(id: string, file: File): Promise<void> {
  const { blob } = await toVoiceWav(file)
  await sendBlob<{ id: string; seconds: number }>('POST', `/api/characters/sample?${q({ id })}`, blob)
  await loadCharacters()
}

/** The character's file is erased, no trash. */
export async function removeCharacter(id: string): Promise<void> {
  await sendJSON<{ name: string }>('POST', '/api/media/characters/remove', { id })
  await loadCharacters()
}

/** Refetch what is loaded: the Temp, the clips, the sounds, the favorite folders, the characters and every Drive folder on screen. */
export async function refresh(): Promise<void> {
  const open = Object.keys(drive.get())
  await Promise.all([loadRoot('out'), loadRoot('clips'), loadRoot('sounds'), loadFavFolders(), loadCharacters(), ...open.map(p => loadFolder(p).catch(() => drive.set(d => { const n = { ...d }; delete n[p]; return n })))])
}

const dropIds = (ids: readonly string[]) => {
  const gone = new Set(ids)
  for (const l of Object.values(lists)) l.set(m => ({ ...m, items: m.items.filter(i => !gone.has(i.id)) }))
  drive.set(d => Object.fromEntries(Object.entries(d).map(([p, f]) => [p, { ...f, items: f.items.filter(i => !gone.has(i.id)) }])))
  characters.set(c => ({ ...c, items: c.items.filter(i => !gone.has(i.id)) }))
}

/** Erase for good: the files are gone from the drive at once; no trash, no undo. */
export async function erase(ids: string[]): Promise<number> {
  const r = await sendJSON<{ ids: string[] }>('POST', '/api/media/delete', { ids })
  dropIds(r.ids)
  for (const [k, l] of Object.entries(lists)) l.set(m => ({ ...m, total: Math.max(0, m.total - r.ids.filter(id => id.startsWith(`${k}/`)).length) }))
  return r.ids.length
}

/** Favorite = the file moves into its day's Favorites folder (and back out); the ids change, so the Temp reloads.
 *  -> the new ids, in the order given */
export async function favorite(ids: string[], on: boolean): Promise<string[]> {
  const r = await sendJSON<{ moved: { from: string; to: string }[] }>('POST', '/api/media/favorite', { ids, on })
  await loadRoot('out')
  return r.moved.map(m => m.to)
}

/** Move Temp or Drive files into a Drive folder. -> how many moved */
export async function moveTo(ids: string[], path: string): Promise<number> {
  const r = await sendJSON<{ moved: { from: string; to: string }[] }>('POST', '/api/media/move', { ids, to: path })
  dropIds(r.moved.map(m => m.from))
  await Promise.all([loadRoot('out'), ...(drive.get()[path] ? [loadFolder(path)] : [])])
  return r.moved.length
}

export const folderNew = (path: string, name: string) => sendJSON<{ path: string }>('POST', '/api/media/drive/folder', { path, name })
export const folderRename = (path: string, name: string) => sendJSON<{ path: string }>('POST', '/api/media/drive/rename', { path, name })
export const folderMove = (paths: string[], to: string) => sendJSON<{ paths: string[] }>('POST', '/api/media/drive/move', { paths, to })
export const folderRemove = (path: string) => sendJSON<{ path: string }>('POST', '/api/media/drive/remove', { path })

/** The judges' verdict on a clip: the finished job that made it carries one in `notes.verdict`
 *  for as long as the session keeps its jobs; null when no job in memory made this item or none was judged. A take of
 *  a scene has its own line, `notes.verdicts[item]`, from the newest finished job (any end) that has one. */
export function verdictFor(jobs: Iterable<Job>, itemId: string): string | null {
  let best: Job | null = null, own: Job | null = null
  for (const j of jobs) {
    const line = (j.notes?.verdicts as Record<string, unknown> | undefined)?.[itemId]
    if (j.state !== 'queued' && j.state !== 'running' && typeof line === 'string' && (!own || j.created > own.created)) own = j
    if (j.state !== 'done' || typeof j.notes?.verdict !== 'string' || !j.outputs.includes(itemId)) continue
    if (!best || j.created > best.created) best = j
  }
  if (own) return String((own.notes!.verdicts as Record<string, unknown>)[itemId])
  return best ? String(best.notes!.verdict) : null
}
