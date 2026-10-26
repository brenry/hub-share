// The Casting tab's costumes and extras: what a costume's Cast sends, the role and seat in Cast's body,
// the views per role, drops on costume boxes 3-9 capped at 7, the seat saved on its own, a costume opened, refused
// and removed with two presses.
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Costume, Draft } from '../../src/modules/casting/api'
import { AUDIENCE_VIEWS, VIEWS, viewsOf } from '../../src/modules/casting/api'
import { _resetCostume, armed, costume, costumeForm, dropCostume, openCostume, removeCostume, variant } from '../../src/modules/casting/costume'
import { COSTUME_PICTURES, TOO_MANY, castBody, costumeBody, costumeFormOf, dropBits, formKey, formOf, shown, viewIds } from '../../src/modules/casting/form'
import { _reset, choose, form, open, problem, sit } from '../../src/modules/casting/load'
import { Sheet } from '../../src/modules/casting/Sheet'

const draft = (over: Partial<Draft> = {}): Draft => ({
  name: 'Character 14', state: 'none', headshot: { id: 'chars/Character 14.png', keep: 'k', ignore: '' }, bits: [], facts: { age: '30', build: 'slim' },
  job: null, orbit: null, views: null, ...over,
})
const fresh = (variant: string, over: Partial<Costume> = {}): Costume => ({
  name: 'Character 8', variant, state: 'none', faces: ['chars/Character 8/sheet/face-1.png', 'chars/Character 8/sheet/face-2.png'],
  face_thumbs: ['/thumbs/f1?v=1', '/thumbs/f2?v=1'], pictures: [], words: '', job: null, orbit: null, views: null, ...over,
})
const pic = (id: string) => ({ id, w: 800, h: 800 })
const bit = (id: string) => ({ id, keep: '', ignore: '' })

type Call = { method: string; path: string; body: unknown }
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

afterEach(() => { vi.unstubAllGlobals(); _reset(); _resetCostume() })

describe('the bodies', () => {
  it('a costume Cast sends its pictures in box order with their lines and the words, trimmed, and the box as typed', () => {
    const f = costumeFormOf({ pictures: [{ id: 'a.png', keep: ' the jacket ', ignore: 'the figure ' }, bit('b.png')], words: ' a worn black leather jacket ' })
    expect(costumeBody('Character 8', 'Leather jacket', f, ' Prompt 1\n')).toEqual({
      name: 'Character 8', variant: 'Leather jacket', words: 'a worn black leather jacket', prompt: ' Prompt 1\n',
      pictures: [{ id: 'a.png', keep: 'the jacket', ignore: 'the figure' }, bit('b.png')],
    })
  })

  it('Cast sends role and seat for Audience; a plain cast\'s body has no role or seat; back to cast from audience says so', () => {
    const f = formOf(draft())
    expect(f).toMatchObject({ role: 'cast', seat: { side: 'centre', row: 1 }, was: 'cast' })
    expect(Object.keys(castBody('Character 14', f))).toEqual(['name', 'headshot', 'bits', 'facts', 'prompt'])
    expect(castBody('Character 14', { ...f, role: 'audience', seat: { side: 'left', row: 3 } })).toMatchObject({ role: 'audience', seat: { side: 'left', row: 3 } })
    const was = formOf(draft({ role: 'audience', seat: { side: 'right', row: 12 } }))
    expect(was.seat).toEqual({ side: 'right', row: 12 })
    const back = castBody('Character 14', { ...was, role: 'cast' })
    expect(back.role).toBe('cast')
    expect(back).not.toHaveProperty('seat')
  })

  it('a seat the hub saved never resets typed lines', () => {
    expect(formKey(draft({ seat: { side: 'left', row: 3 } }))).toBe(formKey(draft({ seat: { side: 'right', row: 9 } })))
    expect(formKey(draft({ role: 'audience' }))).not.toBe(formKey(draft()))
  })
})

describe('views per role', () => {
  it('cast six, audience four (front, left, right, face) in the 4-panel order', () => {
    expect(viewsOf('cast')).toEqual(VIEWS)
    expect(viewsOf(undefined)).toEqual(VIEWS)
    expect(viewsOf('audience')).toEqual(['front', 'left', 'right', 'face-1'])
    expect(viewIds(['a', 'b', 'c', 'd'], AUDIENCE_VIEWS)).toEqual({ front: 'a', left: 'b', right: 'c', 'face-1': 'd' })
    const ready = shown(draft({ role: 'audience', state: 'ready', orbit: 'o.mp4', views: ['a', 'b', 'c', 'd'] }))
    expect(Object.keys(ready!.views)).toEqual(['front', 'left', 'right', 'face-1'])
  })

  it('draws an extra\'s four views 2 x 2 and labels them', () => {
    const html = renderToStaticMarkup(createElement(Sheet, { draft: draft({ role: 'audience', state: 'ready', orbit: 'o.mp4', views: ['a', 'b', 'c', 'd'] }) }))
    expect([...html.matchAll(/data-view="([^"]+)"/g)].map(m => m[1])).toEqual(['front', 'left', 'right', 'face-1'])
    expect([...html.matchAll(/<figcaption[^>]*>([^<]+)</g)].map(m => m[1])).toEqual(['Front', 'Left', 'Right', 'Face'])
    expect(html).toContain('data-role="audience"')
  })
})

describe('costume drops', () => {
  it('boxes 3-9 take at most 7 pictures', () => {
    const six = Array.from({ length: 6 }, (_, i) => bit(`${i}.png`))
    const r = dropBits(six, [pic('x.png'), pic('y.png')], 6, COSTUME_PICTURES)
    expect(r.bits.map(b => b.id)).toEqual([...six.map(b => b.id), 'x.png'])
    expect(r.problem).toBe(TOO_MANY)
  })
})

describe('the presses', () => {
  const list = [{ name: 'Character 8', picture: 'chars/Character 8.png', cast: true, role: 'cast', costumes: 0 }]
  const base = draft({ name: 'Character 8', state: 'approved', role: 'cast', record: { role: 'cast' }, costumes: [] })

  it('opens a costume, drops on its boxes, refuses a reserved name in one line, removes with two presses', async () => {
    let removed = false
    const calls = hub((path, method, body) => {
      if (path === '/api/casting/list') return [200, list]
      if (path.startsWith('/api/casting/draft')) return [200, base]
      if (path.startsWith('/api/casting/costume?') && path.includes('variant=Sheet')) return [200, { problem: 'Sheet is a name Casting uses; choose another' }]
      if (path.startsWith('/api/casting/costume?')) return [200, removed ? fresh('Leather jacket') : fresh('Leather jacket', { state: 'approved', record: {} })]
      if (path === '/api/media/check') return [200, { placed: (body as { items: string[] }).items.map(item => ({ item, id: item })) }]
      if (path === '/api/casting/costume/remove' && method === 'POST') { removed = true; return [200, { removed: 'Leather jacket' }] }
      return [404, { text: 'Not found' }]
    })
    choose('Character 8')
    await vi.waitFor(() => expect(open.get()?.name).toBe('Character 8'))
    await openCostume('Sheet')
    expect(problem.get()).toBe('Sheet is a name Casting uses; choose another')
    expect(variant.get()).toBeNull()

    await openCostume(' Leather jacket ')
    expect(variant.get()).toBe('Leather jacket')
    expect(calls.at(-1)?.path).toBe('/api/casting/costume?name=Character%208&variant=Leather%20jacket')
    await dropCostume(0, Array.from({ length: 8 }, (_, i) => pic(`${i}.png`)))
    expect(costumeForm.get()?.pictures).toHaveLength(7)
    expect(problem.get()).toBe(TOO_MANY)

    await removeCostume()
    expect(armed.get()).toBe(true)
    expect(calls.some(c => c.path === '/api/casting/costume/remove')).toBe(false)
    await removeCostume()
    expect(calls.find(c => c.path === '/api/casting/costume/remove')?.body).toEqual({ name: 'Character 8', variant: 'Leather jacket' })
    expect(variant.get()).toBeNull()
    expect(costume.get()).toBeNull()
  })

  it('another character closes the costume; a seat edit is saved at once, its refusal one line', async () => {
    hub((path, method) => {
      if (path === '/api/casting/list') return [200, [...list, { name: 'Character 14', picture: 'chars/Character 14.png', cast: false, role: null, costumes: 0 }]]
      if (path.startsWith('/api/casting/draft?name=Character%208')) return [200, base]
      if (path.startsWith('/api/casting/draft')) return [200, draft()]
      if (path.startsWith('/api/casting/costume?')) return [200, fresh('Coat')]
      if (path === '/api/casting/seat' && method === 'POST') return [200, { problem: 'A seat is a side (left, centre or right) and a row from 1 to 12' }]
      return [404, { text: 'Not found' }]
    })
    choose('Character 8')
    await vi.waitFor(() => expect(open.get()?.name).toBe('Character 8'))
    await openCostume('Coat')
    expect(variant.get()).toBe('Coat')
    choose('Character 14')
    expect(variant.get()).toBeNull()
    await vi.waitFor(() => expect(form.get()).not.toBeNull())
    await sit({ side: 'left', row: 3 })
    expect(form.get()?.seat).toEqual({ side: 'left', row: 3 })
    expect(problem.get()).toBe('A seat is a side (left, centre or right) and a row from 1 to 12')
  })
})
