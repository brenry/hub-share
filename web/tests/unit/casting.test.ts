// The Casting tab: its manifest, the form (drops from Media, refusals, what Cast sends), which sheet
// shows, the job's line, the presses' refusals as one line, and the sheet's six labelled views.
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Job } from '../../src/lib/protocol'
import type { Draft } from '../../src/modules/casting/api'
import { cast, choose, dropOn, form, open, problem, reload, _reset } from '../../src/modules/casting/load'
import manifest from '../../src/modules/casting/manifest'
import { Sheet } from '../../src/modules/casting/Sheet'
import { PICTURES_ONLY, SHAPE, TOO_MANY, castBody, dropBits, formOf, inShape, jobLine, shown, viewIds } from '../../src/modules/casting/form'

const KEEP = 'Take from <Picture 1> the character\'s identity'
const SIX = ['t/f.png', 't/l.png', 't/b.png', 't/r.png', 't/1.png', 't/2.png']
const draft = (over: Partial<Draft> = {}): Draft => ({
  name: 'Character 8', state: 'none', headshot: { id: 'chars/Character 8.png', keep: KEEP, ignore: '' }, bits: [], facts: { age: '', build: '' },
  job: null, orbit: null, views: null, ...over,
})
const pic = (id: string, w = 800, h = 800) => ({ id, w, h })
const bit = (id: string) => ({ id, keep: '', ignore: '' })

type Call = { method: string; path: string; body: unknown }
/** fetch answered by `answer(path, method, body)`; every call recorded. */
function hub(answer: (path: string, method: string, body: unknown) => [number, unknown]): Call[] {
  const calls: Call[] = []
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) as unknown : null
    calls.push({ method, path: url, body })
    const [status, out] = answer(url, method, body)
    return new Response(JSON.stringify(out), { status, headers: { 'content-type': 'application/json' } })
  })
  return calls
}

afterEach(() => { vi.unstubAllGlobals(); _reset() })

describe('manifest', () => {
  it('is the Casting tab after Storyboard', () => {
    expect({ id: manifest.id, label: manifest.label, order: manifest.order }).toEqual({ id: 'casting', label: 'Casting', order: 40 })
  })
})

describe('the form', () => {
  it('drops fill the free boxes in order; a filled box dropped on takes the first picture and keeps its lines', () => {
    const one = dropBits([], [pic('a.png'), pic('b.png')], 3)
    expect(one).toEqual({ bits: [bit('a.png'), bit('b.png')], problem: null })
    const lined = [{ id: 'a.png', keep: 'the headphones', ignore: 'the desk' }, bit('b.png')]
    expect(dropBits(lined, [pic('c.png'), pic('d.png')], 0).bits)
      .toEqual([{ id: 'c.png', keep: 'the headphones', ignore: 'the desk' }, bit('b.png'), bit('d.png')])
  })

  it('refuses clips and sounds, a picture outside 1:4-4:1 and pictures past 9, each in one line', () => {
    expect(dropBits([], [{ ...pic('c.mp4'), kind: 'clip' }], 0)).toEqual({ bits: [], problem: PICTURES_ONLY })
    expect(dropBits([], [pic('tall.png', 100, 401), pic('ok.png', 100, 400)], 0)).toEqual({ bits: [bit('ok.png')], problem: SHAPE })
    const seven = Array.from({ length: 7 }, (_, i) => bit(`${i}.png`))
    const r = dropBits(seven, [pic('x.png'), pic('y.png')], 7)
    expect(r.bits.map(b => b.id)).toEqual([...seven.map(b => b.id), 'x.png'])
    expect(r.problem).toBe(TOO_MANY)
    expect(TOO_MANY).toBe('At most 9 pictures')
    expect([inShape(1, 4), inShape(4, 1), inShape(1, 5), inShape(0, 0)]).toEqual([true, true, false, true])
  })

  it('Cast sends the name, the headshot lines, the bits in box order and the facts, trimmed, and the box as typed', () => {
    const f = { headshot: { keep: ` ${KEEP} `, ignore: '' }, bits: [{ id: 'a.png', keep: 'the shirt ', ignore: ' the logo' }], facts: { age: '50 ', build: 'heavy' }, prompt: ' Prompt 1\n\n[1] ' }
    expect(castBody('Character 8', f)).toEqual({
      name: 'Character 8', headshot: { keep: KEEP, ignore: '' }, bits: [{ id: 'a.png', keep: 'the shirt', ignore: 'the logo' }], facts: { age: '50', build: 'heavy' }, prompt: ' Prompt 1\n\n[1] ',
    })
    expect(formOf(draft()).headshot).toEqual({ keep: KEEP, ignore: '' })
  })
})

describe('the sheet', () => {
  it('a ready draft shows its views and orbit; otherwise the approved sheet; otherwise none', () => {
    expect(viewIds(SIX)).toEqual({ front: 't/f.png', left: 't/l.png', back: 't/b.png', right: 't/r.png', 'face-1': 't/1.png', 'face-2': 't/2.png' })
    expect(viewIds({ front: 'x.png' })).toEqual({ front: 'x.png' })
    expect(viewIds({ front: 'x.png', left: null } as never)).toEqual({ front: 'x.png' })
    const files = { orbit_url: '/api/casting/orbit?name=Character 8&v=7', views: { front: 'chars/Character 8/sheet/front.png' }, bits: [],
      view_urls: { front: '/files/chars/Character 8/sheet/front.png?v=7' } }
    expect(shown(draft({ state: 'ready', orbit: 'clips/o.mp4', views: SIX, files }))).toMatchObject({ orbit: '/files/clips/o.mp4', approved: false })
    expect(shown(draft({ state: 'rendering', files }))).toEqual({ views: files.view_urls, orbit: files.orbit_url, approved: true })
    expect(shown(draft())).toBeNull()
  })

  it('the job line: its title, state and progress; a failure its line; gone, the draft state', () => {
    const j = { id: 'j1', title: 'Cast · Character 8 · 3 pictures', state: 'running', progress: { pct: 40, text: 'step 3/8' }, error: null } as unknown as Job
    expect(jobLine(draft({ state: 'rendering', job: 'j1' }), j)).toBe('Cast · Character 8 · 3 pictures · step 3/8 · 40 %')
    expect(jobLine(draft(), { ...j, state: 'failed', error: { stage: 'run', text: 'the orbit has 113 frames; the views need 114' } }))
      .toBe('Cast · Character 8 · 3 pictures · failed · the orbit has 113 frames; the views need 114')
    expect(jobLine(draft({ state: 'rendering' }), null)).toBe('Rendering')
    expect(jobLine(draft(), null)).toBe('')
  })

  it('draws six labelled views in sheet order and Approve, Again and Cast for a ready sheet', () => {
    const html = renderToStaticMarkup(createElement(Sheet, { draft: draft({ state: 'ready', orbit: 'clips/o.mp4', views: SIX }) }))
    const labels = [...html.matchAll(/<figcaption[^>]*>([^<]+)</g)].map(m => m[1])
    expect(labels).toEqual(['Front', 'Left', 'Back', 'Right', 'Face', 'Three-quarter face'])
    expect([...html.matchAll(/data-view="([^"]+)"/g)].map(m => m[1])).toEqual(['front', 'left', 'back', 'right', 'face-1', 'face-2'])
    expect(html).toContain('/files/clips/o.mp4')
    for (const r of ['casting-approve', 'casting-again', 'casting-cast']) expect(html).toContain(`data-region="${r}"`)
    const cast = renderToStaticMarkup(createElement(Sheet, { draft: draft({ state: 'approved', files: { orbit_url: '/api/casting/orbit?name=Character 8', views: SIX, view_urls: { front: '/files/t/f.png?v=9' } } }) }))
    expect(cast).toContain('src="/files/t/f.png?v=9"')
    expect(cast).toContain('Cast again')
    expect(cast).toContain('src="/api/casting/orbit?name=Character 8"')
    expect(cast).not.toContain('casting-approve')
    expect(cast).not.toContain('casting-again')
    const failed = renderToStaticMarkup(createElement(Sheet, { draft: draft({ state: 'failed', problem: 'The orbit made no views' }) }))
    expect(failed).toContain('casting-again')
    expect(failed).toContain('Failed · The orbit made no views')
  })
})

describe('the presses', () => {
  const list = [{ name: 'Character 8', picture: 'chars/Character 8.png', cast: false }]
  it('opens a character, keeps typed lines across a refetch, and shows a refusal as one line', async () => {
    let d = draft()
    const calls = hub((path, method) => {
      if (path === '/api/casting/list') return [200, list]
      if (path.startsWith('/api/casting/draft')) return [200, d]
      if (path === '/api/casting/cast' && method === 'POST') return [200, { problem: 'The prompt is 212 characters over the 4000' }]
      return [404, { text: 'Not found' }]
    })
    choose('Character 8')
    await vi.waitFor(() => expect(open.get()?.name).toBe('Character 8'))
    form.set(f => (f ? { ...f, facts: { age: '50', build: 'heavy' } } : f))
    await reload()
    expect(form.get()?.facts).toEqual({ age: '50', build: 'heavy' })
    await cast()
    expect(problem.get()).toBe('The prompt is 212 characters over the 4000')
    expect(calls.find(c => c.path === '/api/casting/cast')?.body).toMatchObject({ name: 'Character 8', facts: { age: '50', build: 'heavy' } })
    d = draft({ state: 'rendering', job: 'j1', facts: { age: '50', build: 'heavy' }, bits: [bit('a.png')] })
    await reload()
    expect(form.get()?.bits).toEqual([bit('a.png')])
  })

  it('a drop is confirmed by the hub before it is placed; an error status is the line too', async () => {
    hub((path, method, body) => {
      if (path === '/api/casting/list') return [200, list]
      if (path.startsWith('/api/casting/draft')) return [200, draft()]
      if (path === '/api/media/check') return [200, { placed: (body as { items: string[] }).items.filter(i => i !== 'bad.png').map(item => ({ item, id: item })) }]
      if (path === '/api/casting/cast' && method === 'POST') return [400, { code: 'invalid', text: 'Generate Image is not running' }]
      return [404, { text: 'Not found' }]
    })
    choose('Character 8')
    await vi.waitFor(() => expect(form.get()).not.toBeNull())
    await dropOn(0, [pic('a.png'), pic('bad.png'), pic('c.png')])
    expect(form.get()?.bits.map(b => b.id)).toEqual(['a.png', 'c.png'])
    await cast()
    expect(problem.get()).toBe('Generate Image is not running')
  })
})
