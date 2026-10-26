import { describe, expect, it } from 'vitest'
import { about, plural } from '../../src/lib/format'
import { createStore } from '../../src/lib/store'
import type { Job } from '../../src/lib/protocol'
import { doneText, generateLabel, queueView, runningText } from '../../src/modules/generate-image/run/jobs'
import { readFragment, stateFor } from '../../src/screens/pair/pair'
import { geometry, totalHeight, windowRange } from '../../src/screens/media/gridMath'
import { controllerBlip } from '../../src/lib/blips'

const job = (id: string, patch: Partial<Job>): Job => ({
  id, tool: 'generate-image', kind: 'image', title: '', lane: 'image.gpu0', state: 'queued', created: 1, started: null, position: null,
  cancel_requested: false, progress: null, outputs: [], error: null, ...patch,
})

describe('store', () => {
  it('notifies only on real change and unsubscribes', () => {
    const s = createStore(1)
    let n = 0
    const off = s.subscribe(() => n++)
    s.set(1); s.set(2); s.set(v => v + 1)
    off(); s.set(9)
    expect([n, s.get()]).toEqual([2, 9])
  })
})

describe('format', () => {
  it('sizes, durations, counts', () => {
    expect(about(14.2)).toBe('about 14 s')
    expect(about(185)).toBe('about 3 min')
    expect(plural(1, 'image')).toBe('1 image')
    expect(plural(1234, 'image')).toBe('1,234 images')
  })
})

describe('queue area', () => {
  it('splits running, waiting and the latest failure', () => {
    const v = queueView([
      job('r', { state: 'running', created: 2 }),
      job('w1', { created: 3 }), job('w2', { created: 4 }),
      job('f', { state: 'failed', created: 0, error: { stage: 'generation', text: 'Out of GPU memory' } }), job('other', { tool: 'x' }),
    ])
    expect([v.running?.id, v.waiting.map(j => j.id), v.failed?.id]).toEqual(['r', ['w1', 'w2'], 'f'])
  })
  it('running text: k of N, p% and ETA; loading is indeterminate; a re-take named over the engine\'s text', () => {
    const p = { phase: 'inference', index: 1, count: 2, step: 2, steps: 4, pct: 38, eta_s: 11, text: '' }
    expect(runningText(job('r', { progress: p }))).toEqual({ left: 'Generating 1 of 2', right: '38% · about 11 s', value: 0.38 })
    expect(runningText(job('r', { progress: { ...p, eta_s: null } })).right).toBe('38% · estimating…')
    expect(runningText(job('r', { progress: { ...p, phase: 'loading', text: 'Loading Flux 2 Klein 9B' } }))).toEqual({ left: 'Loading Flux 2 Klein 9B', right: '', value: null })
    const summary = { prompt: '', model: 'H3', loras: [], width: 0, height: 0, count: 1, kind: 'clip' as const, step_names: ['Render', 'Voice'] }
    expect(runningText(job('r', { summary, progress: p })).left).toBe('Generating')
    expect(runningText(job('r', { summary, progress: { ...p, index: 2, text: 'Applying Audio Remuxing - Replace Voice' } })).left)
      .toBe('Applying Audio Remuxing - Replace Voice')
    expect(runningText(job('r', { summary, progress: { ...p, index: 2 } })).left).toBe('Voice')
    const scene = { ...summary, mode: 'scene', shots: 5, step_names: ['Shot 1 · Character 7 · 6.2 s', 'Shot 2 · Character 6 · 7.3 s', 'Shot 2 · voice', 'Cut'] }
    expect([1, 2, 3, 4].map(index => runningText(job('r', { summary: scene, progress: { ...p, index, text: 'x' } })).left))
      .toEqual(['Shot 1 of 5 · Character 7 · 6.2 s', 'Shot 2 of 5 · Character 6 · 7.3 s', 'Shot 2 of 5 · voice', 'Cut'])
    const takes = { ...summary, step_names: ['Render', 'Voice', 'Render · take 2', 'Voice · take 2'] }
    expect([2, 3, 4].map(index => runningText(job('r', { summary: takes, progress: { ...p, index, text: 'Decoding' } })).left))
      .toEqual(['Decoding', 'Render · take 2', 'Voice · take 2'])
    expect(doneText(2, 38)).toBe('Done · 2 images in 38 s')
    expect([generateLabel(1), generateLabel(3)]).toEqual(['Generate image', 'Generate 3 images'])
  })
})

describe('connection light', () => {
  it('says the controller state', () => {
    expect(controllerBlip({ state: 'on', since: 0, nextTry: null, version: '' }, 0).dot).toBe('ok')
    expect(controllerBlip({ state: 'cut', since: 0, nextTry: 8000, version: '' }, 0)).toMatchObject({ dot: 'cut', title: 'Reconnecting, next try in 8 s' })
    expect(controllerBlip({ state: 'off', since: 0, nextTry: null, version: '' }, 0)).toMatchObject({ dot: 'idle', detail: 'off' })
  })
})

describe('pairing fragment', () => {
  it('reads the code and only a same-origin next path', () => {
    const at = 'http://192.168.0.10:42010'
    expect(readFragment('#c=abc&next=/media', at)).toEqual({ code: 'abc', next: '/media' })
    expect(readFragment('#c=abc&next=%2F%3Fscreen%3Dmedia', at)).toEqual({ code: 'abc', next: '/?screen=media' })
    expect(readFragment('#c=abc&next=//evil.example', at)).toEqual({ code: 'abc', next: '/' })
    expect(readFragment('#c=abc&next=https://evil.example', at)).toEqual({ code: 'abc', next: '/' })
    expect(readFragment('#c=abc&next=/%09/evil.example/', at)).toEqual({ code: 'abc', next: '/' })
    expect(readFragment('#c=abc&next=/%5C/evil.example', at)).toEqual({ code: 'abc', next: '/' })
    expect(readFragment('#c=abc&next=http://[', at)).toEqual({ code: 'abc', next: '/' })
    expect(readFragment('', at)).toEqual({ code: null, next: '/' })
    expect([stateFor(403), stateFor(410), stateFor(429), stateFor(500)]).toEqual(['bad', 'bad', 'rate', 'failed'])
  })
})

describe('media grid window', () => {
  it('two square tiles per row and renders visible rows plus overscan', () => {
    const g = geometry(430, 2, 10)
    expect(g).toEqual({ cols: 2, tile: 210, rowH: 220, gap: 10 })
    expect(windowRange(0, 600, 5000, g, 3)[0]).toBe(0)
    const [a, b] = windowRange(10000, 600, 5000, g, 3)
    expect(a % g.cols).toBe(0)
    expect(b - a).toBeLessThan(g.cols * 12)
    expect(totalHeight(5000, g)).toBeCloseTo(Math.ceil(5000 / 2) * g.rowH - 10)
  })
})

