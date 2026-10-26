// Media's sound menu keeps a sound as the scene's audience, one kind at a time, through the Hub's route.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { audienceItem } from '../../src/screens/media/audience'

afterEach(() => { vi.unstubAllGlobals() })

describe('Keep as audience…', () => {
  it('calls the route with the kind and says what it kept', async () => {
    const calls: { url: string; body: unknown }[] = []
    vi.stubGlobal('fetch', (url: string, init: RequestInit) => {
      calls.push({ url, body: JSON.parse(String(init.body)) })
      return Promise.resolve(new Response(JSON.stringify({ id: 'sounds/audience/laughter.wav' }), { headers: { 'content-type': 'application/json' } }))
    })
    const said: string[] = []
    const item = audienceItem(['sounds/2026-10-18/120000-000.wav'], t => said.push(t), () => {})
    expect([item.label, item.off, item.sub.map(s => s.label)]).toEqual(['Keep as audience…', null, ['Applause', 'Laughter', 'Gasps']])
    item.sub[1]?.run()
    await vi.waitFor(() => expect(said).toEqual(['Laughter kept for the audience']))
    expect(calls).toEqual([{ url: '/api/sounds/audience', body: { id: 'sounds/2026-10-18/120000-000.wav', kind: 'laughter' } }])
    expect(audienceItem(['a.wav', 'b.wav'], () => {}, () => {}).off).toBe('One sound at a time')
  })
})
