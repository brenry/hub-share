// The Clips section of the Media window: server items as the window keeps them, where a new file lands, the
// listings asked, the one flat list (no days), the tree's order, /clips opening on the section, and Fit.
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fitBox } from '../../src/screens/media/fit'
import { CLIPS, TEMP, clips, fromGeneration, itemsOf, loadMore, norm, prepend, refresh, startView, temp, verdictFor, type View } from '../../src/screens/media/media'
import { job } from '../e2e/fixtures/data'
import { Tree } from '../../src/screens/media/Tree'

const base = { url: '/files/x', createdAt: 1, group: '', fav: false }
const clipRaw = (id: string) => ({ ...base, id, kind: 'clip', url: `/files/${id}`, thumb: null, w: null, h: null })

describe('clip items', () => {
  it('an item without a kind is a picture; a clip keeps no thumbnail, an unknown size is 0 and its day is no group', () => {
    expect(norm({ ...base, id: 'out/2026-10-13/a.png', thumb: '/thumbs/a/336', w: 10, h: 20 })).toMatchObject({ kind: 'image', thumb: '/thumbs/a/336', w: 10, h: 20, group: '' })
    expect(norm(clipRaw('clips/2026-10-13/120000.mp4'))).toMatchObject({ kind: 'clip', thumb: null, w: 0, h: 0, group: '' })
    expect(norm({ ...base, id: 'out/2026-10-13/Character 17/a.png', kind: 'weird', thumb: 't', w: 1, h: 1, group: 'Character 17' })).toMatchObject({ kind: 'image', group: 'Character 17' })
  })

  it('a new clip lands in the Clips, a new picture in the Temp', () => {
    temp.set(m => ({ ...m, items: [], total: 0 }))
    clips.set(m => ({ ...m, items: [], total: 0 }))
    const clip = fromGeneration({ id: 'clips/2026-10-13/120000.mp4', kind: 'clip', url: '/files/clips/2026-10-13/120000.mp4', thumb: null, w: null, h: null, created: 5, job: 'j1' })
    const pic = fromGeneration({ id: 'out/2026-10-13/a.png', kind: 'image', url: '/files/out/2026-10-13/a.png', thumb: '/thumbs/a', w: 4, h: 3, created: 5, job: 'j2' })
    expect(clip).toMatchObject({ kind: 'clip', group: '', w: 0, createdAt: 5 })
    prepend(clip)
    prepend(pic)
    expect([clips.get().total, temp.get().total]).toEqual([1, 1])
    expect(itemsOf(CLIPS).map(i => i.id)).toEqual([clip.id])
    expect(itemsOf(TEMP).map(i => i.id)).toEqual([pic.id])
  })
})

describe('the listings', () => {
  afterEach(() => { vi.unstubAllGlobals() })
  const page = { items: [clipRaw('clips/2026-10-13/120000.mp4')], more: false, total: 1, groups: [] }

  it('Media asks for the Temp, the clips root and the sounds root; the clips go to their own list', async () => {
    const urls: string[] = []
    vi.stubGlobal('fetch', (url: string) => {
      urls.push(url)
      const body = url === '/api/media?root=clips&limit=200' ? page : url.startsWith('/api/media?') ? { ...page, items: [], total: 0 } : { unset: true, items: [], folders: [] }
      return Promise.resolve(new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } }))
    })
    await refresh()
    expect(urls.filter(u => u.startsWith('/api/media?'))).toEqual(['/api/media?limit=200', '/api/media?root=clips&limit=200', '/api/media?root=sounds&limit=200'])
    expect(clips.get().items).toMatchObject([{ kind: 'clip', group: '', w: 0, h: 0 }])
    expect(temp.get().items).toEqual([])
  })

  it('Clips is one flat list of every day, newest first: a new clip at the top, the next page below', async () => {
    const at = (id: string) => norm(clipRaw(id))
    const listed = ['clips/2026-10-13/120000.mp4', 'clips/2026-10-13/090000.mp4', 'clips/2026-10-12/180000.mp4']
    clips.set(m => ({ ...m, items: listed.map(at), more: true, total: 4 }))
    expect(itemsOf(CLIPS).map(i => i.id)).toEqual(listed)
    prepend(at('clips/2026-10-14/080000.mp4'))
    const older = { ...page, items: [clipRaw('clips/2026-10-11/170000.mp4')] }
    vi.stubGlobal('fetch', (url: string) => Promise.resolve(new Response(JSON.stringify(url.includes('before=') ? older : page), { headers: { 'content-type': 'application/json' } })))
    await loadMore('clips')
    expect(itemsOf(CLIPS).map(i => i.id)).toEqual(['clips/2026-10-14/080000.mp4', ...listed, 'clips/2026-10-11/170000.mp4'])
    expect(clips.get().total).toBe(5)
  })
})

describe('the tree', () => {
  const draw = (v: View) => renderToStaticMarkup(createElement(Tree, { view: v, onView: () => {} }))
  const rows = (html: string) => [...html.matchAll(/data-row="([^"]+)"/g)].map(m => m[1])

  it('Temp, Favorites, Characters, Clips (one row: no days, no fold), Sounds, Drive', () => {
    clips.set(m => ({ ...m, items: ['clips/2026-10-12/1.mp4', 'clips/2026-10-13/2.mp4'].map(id => norm(clipRaw(id))), total: 2 }))
    const html = draw(TEMP)
    expect(rows(html)).toEqual(['temp', 'fav', 'chars', 'clips', 'sounds', 'drive:'])
    const head = /<div[^>]*data-row="clips"[^>]*>/.exec(html)![0]
    expect(head).not.toContain('aria-expanded')
    expect(html.indexOf('>Clips<')).toBeLessThan(html.indexOf('>Drive<'))
  })

  it('/clips opens on the Clips section, anything else on the Temp', () => {
    expect(startView('/clips')).toEqual(CLIPS)
    expect(startView('/clips/')).toEqual(CLIPS)
    expect(startView('/media')).toEqual(TEMP)
    const selected = (html: string) => [...html.matchAll(/aria-selected="true" data-row="([^"]+)"/g)].map(m => m[1])
    expect(selected(draw(startView('/clips')))).toEqual(['clips'])
  })
})

describe('fit', () => {
  it('centres and scales until the height or the width meets the edge', () => {
    expect(fitBox(1600, 900, 960, 544)).toEqual({ s: 900 / 544, x: (1600 - 960 * (900 / 544)) / 2, y: 0 })
    expect(fitBox(1000, 1000, 2000, 1000)).toEqual({ s: 0.5, x: 0, y: 250 })
  })
})

describe('the judges\' verdict on a clip', () => {
  it('is the newest finished job\'s that made the clip, while the session keeps it', () => {
    const made = job('j1', { state: 'done', created: 1, outputs: ['clips/2026-10-17/a.mp4'], notes: { verdict: "Character 7's face held (0.62)" } })
    const retake = job('j2', { state: 'done', created: 2, outputs: ['clips/2026-10-17/b.mp4'], notes: { verdict: "Character 7's face held (0.71)" } })
    const quiet = job('j3', { state: 'done', created: 3, outputs: ['clips/2026-10-17/c.mp4'] })
    const running = job('j4', { state: 'running', created: 4, outputs: ['clips/2026-10-17/a.mp4'], notes: { verdict: 'x' } })
    const all = [made, retake, quiet, running]
    expect(verdictFor(all, 'clips/2026-10-17/a.mp4')).toBe("Character 7's face held (0.62)")
    expect(verdictFor(all, 'clips/2026-10-17/b.mp4')).toBe("Character 7's face held (0.71)")
    expect(verdictFor(all, 'clips/2026-10-17/c.mp4')).toBeNull()
    expect(verdictFor([], 'clips/2026-10-17/a.mp4')).toBeNull()
  })

  it('prefers a take\'s own line in notes.verdicts, from a failed job too', () => {
    const a = 'clips/2026-10-18/a.mp4', b = 'clips/2026-10-18/b.mp4'
    const scene = job('s1', { state: 'failed', created: 5, outputs: [a, b], notes: { verdict: 'Shot 1 take 2', verdicts: { [a]: 'Take 1 · not used · heard 60% of the words', [b]: 'Take 2 · in the cut · Heard 100% of the words' } } })
    const running = job('s2', { state: 'running', created: 6, outputs: [a], notes: { verdicts: { [a]: 'x' } } })
    expect(verdictFor([scene, running].values(), a)).toBe('Take 1 · not used · heard 60% of the words')
    expect(verdictFor([scene], b)).toBe('Take 2 · in the cut · Heard 100% of the words')
  })
})
