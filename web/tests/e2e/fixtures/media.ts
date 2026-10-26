// The media routes of the FakeHub: the Temp with its groups (Favorites is a folder a picture moves into), the Drive's
// folders, the favorite folders (a list of Drive paths), move, delete.
import type { Route } from '@playwright/test'
import type { FakeItem } from './data'

export type FakeDrive = { name: string; unset?: boolean; favorites: string[]; folders: Record<string, { dirs: string[]; items: FakeItem[] }> }
/** The Characters folder: `unset` until it is chosen; each picture is named by its file name. */
export type FakeChars = { unset: boolean; items: (FakeItem & { name: string; notes: string; voice: string; sample: boolean })[] }
type St = { media: FakeItem[]; clips: FakeItem[]; sounds: FakeItem[]; drive: FakeDrive; chars: FakeChars }

const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
const bad = (route: Route, field: string, text: string) => json(route, { code: 'invalid', field, text }, 400)

function driveItem(path: string, name: string): FakeItem {
  const id = `drive/${path ? path + '/' : ''}${name}`
  return { id, kind: 'image', url: `/files/${id}`, thumb: `/thumbs/${id}/336`, w: 1024, h: 1024, createdAt: 1791500000, group: '', fav: false }
}

const charItem = (name: string, notes = '', ext = 'png', voice = '', sample = false) => {
  const id = `chars/${name}.${ext}`
  return { ...driveItem('', `${name}.${ext}`), id, url: `/files/${id}`, thumb: `/thumbs/${id}/336`, name, notes, voice, sample }
}
const byName = (a: { name: string }, b: { name: string }) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
/** No folder (the default: the section shows its "choose a folder" line), or a folder with these characters (listed by
 *  name, like the hub). A name may carry its file's extension ("Character 30.jpg"; PNG otherwise); `notes` by name ("" for
 *  the rest). */
export const fakeChars = (names?: string[], notes: Record<string, string> = {}): FakeChars => ({
  unset: !names,
  items: (names ?? []).map(n => {
    const [, name = n, ext = 'png'] = /^(.*)\.(jpe?g|webp|png)$/i.exec(n) ?? []
    return charItem(name, notes[name] ?? '', ext)
  }).sort(byName),
})

/** ComfyUI › image (portraits: 3 files, posters: empty) and video. */
export function fakeDrive(): FakeDrive {
  return { name: 'ComfyUI', favorites: [], folders: {
    '': { dirs: ['image', 'video'], items: [] },
    image: { dirs: ['portraits', 'posters'], items: [driveItem('image', 'cover.png')] },
    'image/portraits': { dirs: [], items: ['p1.png', 'p2.png', 'p3.png'].map(n => driveItem('image/portraits', n)) },
    'image/posters': { dirs: [], items: [] },
    video: { dirs: [], items: [] },
  } }
}

const parent = (p: string) => p.split('/').slice(0, -1).join('/')
const base = (p: string) => p.split('/').pop()!
const join = (a: string, b: string) => (a ? `${a}/${b}` : b)
const everyItem = (st: St) => [...st.media, ...Object.values(st.drive.folders).flatMap(f => f.items)]

function renameTree(st: St, from: string, to: string) {
  const next: FakeDrive['folders'] = {}
  for (const [p, f] of Object.entries(st.drive.folders)) {
    const np = p === from ? to : p.startsWith(from + '/') ? to + p.slice(from.length) : p
    next[np] = { dirs: f.dirs, items: f.items.map(i => (p === np ? i : driveItem(np, base(i.id)))) }
  }
  st.drive.folders = next
}

export function mediaRoute(route: Route, st: St, m: string, p: string, url: URL, body: unknown): Promise<void> {
  const b = (body ?? {}) as Record<string, unknown>
  if (p === '/api/media') {
    // `root=clips` lists the clips root (same item shape, kind "clip", no thumbnail, no groups), `root=sounds` the
    // sounds root (kind "sound"); `out` by default.
    const root = url.searchParams.get('root') ?? 'out'
    if (root !== 'out' && root !== 'clips' && root !== 'sounds') return bad(route, 'root', 'List out, clips or sounds')
    const all = root === 'clips' ? st.clips : root === 'sounds' ? st.sounds : st.media
    const limit = Number(url.searchParams.get('limit') ?? 200)
    const before = url.searchParams.get('before')
    const start = before ? all.findIndex(i => i.id === before) + 1 : 0
    const counts = new Map<string, number>(root === 'out' ? [['Favorites', 0]] : [])
    for (const i of all) if (i.group) counts.set(i.group, (counts.get(i.group) ?? 0) + 1)
    const groups = [...counts].sort((a, b) => a[0].localeCompare(b[0])).map(([name, count]) => ({ name, count }))
    return json(route, { items: all.slice(start, start + limit), more: start + limit < all.length, total: all.length, groups })
  }
  if (p === '/api/media/characters' && m === 'GET') return json(route, st.chars)
  if (p === '/api/media/characters/rename') {
    const id = String(b.id ?? ''), name = String(b.name ?? '').trim()
    if (!name || name.includes('/')) return bad(route, 'name', 'Use a plain name')
    const was = st.chars.items.find(c => c.id === id)
    if (!was) return bad(route, 'id', 'No such character')
    st.chars.items = [...st.chars.items.filter(c => c.id !== id), charItem(name, was.notes, 'png', was.voice, was.sample)].sort(byName)
    return json(route, { id: `chars/${name}.png` })
  }
  if (p === '/api/media/characters/notes') {
    // Like the hub: the notes go inside the file, which is rewritten as a PNG (a JPEG's id changes).
    const was = st.chars.items.find(c => c.id === b.id)
    if (!was) return bad(route, 'id', 'No such character')
    const notes = String(b.notes ?? '').trim()
    const next = charItem(was.name, notes, 'png', was.voice, was.sample)
    st.chars.items = st.chars.items.map(c => (c === was ? next : c))
    return json(route, { id: next.id })
  }
  if (p === '/api/media/characters/voice') {
    // Like the hub: the voice is a second field inside the file (notes kept), which is rewritten as a PNG.
    const was = st.chars.items.find(c => c.id === b.id)
    if (!was) return bad(route, 'id', 'No such character')
    const next = charItem(was.name, was.notes, 'png', String(b.voice ?? '').trim(), was.sample)
    st.chars.items = st.chars.items.map(c => (c === was ? next : c))
    return json(route, { id: next.id })
  }
  if (p === '/api/media/keep-voice') {
    // A sound kept as `<Name>.wav` beside the character's picture.
    if (!String(b.id ?? '').startsWith('sounds/')) return bad(route, 'id', 'That is not a sound')
    const who = st.chars.items.find(c => c.name.toLowerCase() === String(b.name ?? '').toLowerCase())
    if (!who) return bad(route, 'name', 'No character has that name')
    st.chars.items = st.chars.items.map(c => (c === who ? { ...c, sample: true } : c))
    return json(route, { id: who.id })
  }
  if (p === '/api/media/characters/remove') {
    const gone = st.chars.items.find(c => c.id === b.id)
    if (!gone) return bad(route, 'id', 'No such character')
    st.chars.items = st.chars.items.filter(c => c !== gone)
    return json(route, { name: gone.name })
  }
  if (p === '/api/media/characters') {
    const name = String(b.name ?? '').trim()
    if (String(b.id ?? '').startsWith('clips/')) return bad(route, 'id', 'Only pictures can be characters')
    if (st.chars.unset) return bad(route, 'name', 'Choose your Characters folder first')
    if (!name || name.includes('/')) return bad(route, 'name', 'Use a plain name')
    st.chars.items = [...st.chars.items.filter(c => c.name.toLowerCase() !== name.toLowerCase()), charItem(name)].sort(byName)
    return json(route, { id: `chars/${name}.png` })
  }
  if (p === '/api/media/favorite') {
    const ids = b.ids as string[], on = b.on !== false
    if (ids.some(id => id.startsWith('clips/'))) return bad(route, 'ids', 'Only pictures can be favorites')
    if (ids.some(id => !id.startsWith('out/'))) return bad(route, 'ids', 'Only Temp images can be favorites')
    const moved: { from: string; to: string }[] = []
    st.media = st.media.map(i => {
      if (!ids.includes(i.id) || (i.group === 'Favorites') === on) return i
      const [, day] = i.id.split('/')
      const to = `out/${day}/${on ? 'Favorites/' : ''}${base(i.id)}`
      moved.push({ from: i.id, to })
      return { ...i, id: to, url: `/files/${to}`, thumb: `/thumbs/${to}/336`, group: on ? 'Favorites' : '', fav: on }
    })
    return json(route, { moved, on })
  }
  const favFolders = () => ({ folders: st.drive.favorites.map(path => ({ path, name: base(path), ok: Boolean(st.drive.folders[path]) })) })
  if (p === '/api/media/favorite-folders' && m === 'GET') return json(route, favFolders())
  if (p === '/api/media/favorite-folders') {
    const path = (b.path as string).replace(/^\/+|\/+$/g, ''), on = b.on !== false
    if (on && !path) return bad(route, 'path', 'The Drive itself is always in the tree')
    if (on && !st.drive.folders[path]) return bad(route, 'path', 'That folder is not in the Drive')
    st.drive.favorites = [...st.drive.favorites.filter(f => f !== path), ...(on ? [path] : [])]
    return json(route, favFolders())
  }
  if (p === '/api/media/drive' && m === 'GET') {
    const path = url.searchParams.get('path') ?? ''
    if (st.drive.unset) return json(route, { path: '', name: '', dirs: [], items: [], unset: true })
    const f = st.drive.folders[path]
    if (!f) return bad(route, 'path', 'That folder is not in the Drive')
    return json(route, { path, name: path ? base(path) : st.drive.name, dirs: f.dirs, items: f.items })
  }
  if (p === '/api/media/drive/folder') {
    const path = b.path as string, name = (b.name as string).trim()
    if (!name || name.includes('/')) return bad(route, 'name', 'Use a plain folder name, without slashes')
    if (st.drive.folders[join(path, name)]) return bad(route, 'name', 'A folder with that name is already there')
    st.drive.folders[path]!.dirs = [...st.drive.folders[path]!.dirs, name].sort()
    st.drive.folders[join(path, name)] = { dirs: [], items: [] }
    return json(route, { path: join(path, name) })
  }
  if (p === '/api/media/drive/rename') {
    const path = b.path as string, to = join(parent(path), (b.name as string).trim())
    const par = st.drive.folders[parent(path)]!
    par.dirs = par.dirs.map(d => (d === base(path) ? base(to) : d)).sort()
    renameTree(st, path, to)
    st.drive.favorites = st.drive.favorites.map(f => (f === path ? to : f.startsWith(path + '/') ? to + f.slice(path.length) : f))
    return json(route, { path: to })
  }
  if (p === '/api/media/drive/move') {
    const paths = b.paths as string[], to = b.to as string
    for (const path of paths) {
      const par = st.drive.folders[parent(path)]!
      par.dirs = par.dirs.filter(d => d !== base(path))
      st.drive.folders[to]!.dirs = [...st.drive.folders[to]!.dirs, base(path)].sort()
      renameTree(st, path, join(to, base(path)))
      const np = join(to, base(path))
      st.drive.favorites = st.drive.favorites.map(f => (f === path ? np : f.startsWith(path + '/') ? np + f.slice(path.length) : f))
    }
    return json(route, { paths: paths.map(x => join(to, base(x))) })
  }
  if (p === '/api/media/drive/remove') {
    const path = b.path as string
    const par = st.drive.folders[parent(path)]!
    par.dirs = par.dirs.filter(d => d !== base(path))
    for (const k of Object.keys(st.drive.folders)) if (k === path || k.startsWith(path + '/')) delete st.drive.folders[k]
    st.drive.favorites = st.drive.favorites.filter(f => f !== path && !f.startsWith(path + '/'))
    return json(route, { path })
  }
  if (p === '/api/media/move') {
    const ids = b.ids as string[], to = b.to as string
    if (ids.some(id => id.startsWith('clips/'))) return bad(route, 'ids', 'Only pictures can go to the Drive')
    const dest = st.drive.folders[to]!
    const moved: { from: string; to: string }[] = []
    for (const id of ids) {
      const item = everyItem(st).find(i => i.id === id)
      if (!item || item.id.startsWith(`drive/${to ? to + '/' : ''}`) && parent(item.id.slice(6)) === to) continue
      st.media = st.media.filter(i => i.id !== id)
      for (const f of Object.values(st.drive.folders)) f.items = f.items.filter(i => i.id !== id)
      const next = driveItem(to, base(id))
      dest.items = [...dest.items, next]
      moved.push({ from: id, to: next.id })
    }
    return json(route, { moved })
  }
  if (p === '/api/media/delete') {
    const ids = b.ids as string[]
    st.media = st.media.filter(i => !ids.includes(i.id))
    st.clips = st.clips.filter(i => !ids.includes(i.id))
    st.sounds = st.sounds.filter(i => !ids.includes(i.id))
    for (const f of Object.values(st.drive.folders)) f.items = f.items.filter(i => !ids.includes(i.id))
    return json(route, { ids })
  }
  return json(route, { code: 'not_found', text: 'No such route' }, 404)
}

/** `POST /api/characters/sample?id=`: the WAV the browser made of the picked file. Like the hub: 2 to 15 s kept as
 *  the character's sample; the call's `body` records what the WAV holds (its tags, channels, rate, seconds). */
export function sampleRoute(route: Route, st: St & { calls: { body: unknown }[] }, url: URL): Promise<void> {
  const raw = route.request().postDataBuffer() ?? Buffer.alloc(0)
  const tag = (at: number) => raw.subarray(at, at + 4).toString('latin1')
  const wav = raw.length >= 44 ? { tags: [tag(0), tag(8), tag(12), tag(36)], channels: raw.readUInt16LE(22), rate: raw.readUInt32LE(24),
    bits: raw.readUInt16LE(34), seconds: raw.readUInt32LE(40) / raw.readUInt32LE(28), type: route.request().headers()['content-type'] } : null
  const last = st.calls[st.calls.length - 1]
  if (last) last.body = wav
  if (!wav || wav.seconds < 2) return bad(route, 'sample', 'A voice sample is at least 2 seconds')
  const who = st.chars.items.find(c => c.id === url.searchParams.get('id'))
  if (!who) return bad(route, 'id', 'That character is not in the Characters folder now')
  st.chars.items = st.chars.items.map(c => (c === who ? { ...c, sample: true } : c))
  return json(route, { id: who.id, seconds: wav.seconds })
}
