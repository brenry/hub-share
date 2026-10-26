// Clip stills (lib/stills.ts): one player at a time, newest request first, a forgotten request never drawn,
// a clip that gives no frame in time gets none, at most 400 kept (the oldest freed). The DOM is a stand-in.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { _resetStills, forget, previews, still, stillNow } from '../../src/lib/stills'

type FakeVideo = {
  src: string; currentTime: number; duration: number; videoWidth: number; videoHeight: number
  muted: boolean; playsInline: boolean; preload: string; emptied: boolean
  onloadedmetadata: (() => void) | null; onseeked: (() => void) | null; onerror: (() => void) | null
  removeAttribute: (n: string) => void; load: () => void
}

let drawn: string[] = []
let live = 0
let maxLive = 0
let revoked: string[] = []
let made = 0
let stall = new Set<string>()

function fakeVideo(): FakeVideo {
  const v: FakeVideo = {
    src: '', currentTime: 0, duration: 5, videoWidth: 960, videoHeight: 544, muted: false, playsInline: false,
    preload: '', emptied: false, onloadedmetadata: null, onseeked: null, onerror: null,
    removeAttribute: () => { v.emptied = true; live -= 1 }, load: () => {},
  }
  return new Proxy(v, {
    set(t, k, value) {
      (t as Record<string | symbol, unknown>)[k] = value
      if (k === 'src' && value) {
        drawn.push(String(value))
        live += 1
        maxLive = Math.max(maxLive, live)
        if (!stall.has(String(value))) setTimeout(() => { t.onloadedmetadata?.(); setTimeout(() => t.onseeked?.(), 0) }, 0)
      }
      return true
    },
  })
}

beforeEach(() => {
  drawn = []; live = 0; maxLive = 0; revoked = []; made = 0; stall = new Set()
  vi.useFakeTimers()
  vi.stubGlobal('document', {
    createElement: (tag: string) => tag === 'video' ? fakeVideo()
      : { width: 0, height: 0, getContext: () => ({ drawImage: () => {} }), toBlob: (cb: (b: object) => void) => cb({}) },
  })
  vi.stubGlobal('URL', { createObjectURL: () => `blob:${++made}`, revokeObjectURL: (u: string) => { revoked.push(u) } })
  _resetStills()
  revoked = []
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('clip stills', () => {
  it('draws a clip once for every tile that asks, one player at a time, and empties the player', async () => {
    const a = still('/files/a.mp4')
    const b = still('/files/a.mp4')
    const c = still('/files/c.mp4')
    await vi.runAllTimersAsync()
    expect(await a).toBe(await b)
    expect(await c).toMatch(/^blob:/)
    expect(drawn).toEqual(['/files/a.mp4', '/files/c.mp4'])
    expect(maxLive).toBe(1)
    expect(live).toBe(0)
    expect(stillNow('/files/a.mp4')).toBe(await a)
  })

  it('draws the newest request first and never one no tile wants', async () => {
    void still('/files/1.mp4')
    const two = still('/files/2.mp4')
    void still('/files/3.mp4')
    forget('/files/2.mp4')
    await vi.runAllTimersAsync()
    expect(drawn).toEqual(['/files/1.mp4', '/files/3.mp4'])
    expect(await two).toBeNull()
    expect(stillNow('/files/2.mp4')).toBeNull()
  })

  it('a clip that gives no frame in time gets none, and the queue goes on', async () => {
    stall.add('/files/stuck.mp4')
    const stuck = still('/files/stuck.mp4')
    const next = still('/files/next.mp4')
    await vi.advanceTimersByTimeAsync(10_001)
    await vi.runAllTimersAsync()
    expect(await stuck).toBeNull()
    expect(await next).toMatch(/^blob:/)
    expect(live).toBe(0)
  })

  it('keeps at most 400 stills, freeing the oldest', async () => {
    const all: Promise<string | null>[] = []
    for (let i = 0; i < 401; i++) {
      all.push(still(`/files/${i}.mp4`))
      await vi.runAllTimersAsync()
    }
    const first = await all[0]
    expect(revoked).toEqual([first])
    expect(stillNow('/files/0.mp4')).toBeNull()
    expect(stillNow('/files/400.mp4')).toBe(await all[400])
  })
})

describe('clip previews', () => {
  it('switched off: no player at all', async () => {
    _resetStills(false)
    expect(await still('/files/clips/a.mp4')).toBeNull()
    await vi.runAllTimersAsync()
    expect(drawn).toEqual([])
  })
  it('nothing is drawn before the hub has said; then it is', async () => {
    _resetStills(null)
    const waiting = still('/files/clips/b.mp4')
    await vi.runAllTimersAsync()
    expect(drawn).toEqual([])
    previews.set(true)
    await vi.runAllTimersAsync()
    expect(await waiting).toBe('blob:1')
  })
})
