// The timeline's hand edits as `/edit` ops (a drop's time counted from the shot it lands in), and Render's
// progress as Track's.
import { describe, expect, it } from 'vitest'
import type { Job } from '../../src/lib/protocol'
import type { Script } from '../../src/modules/director/api'
import { addAt, moveOf, shotAt, speakers } from '../../src/modules/director/moves'
import { boxes, cutProgress, cutText } from '../../src/modules/director/timeline'

const SCRIPT: Script = { version: 2, context: { cast: [{ name: 'A' }, { name: 'B' }] }, scenes: [
  { title: 'Scene 1', cast: ['A', 'B'], shots: [
    { id: 's1', start_ms: 0, end_ms: 4000, events: [{ id: 'l1', kind: 'line', speaker: 'A', words: 'One', start_ms: 500, end_ms: 1500 }] },
    { id: 's2', start_ms: 4000, end_ms: 9000, events: [{ id: 'c1', kind: 'cue', cue: 'effect', words: 'Two', start_ms: 5000, end_ms: 6000 }] },
  ] },
] }
const box = (id: string) => boxes(SCRIPT).find(b => b.id === id)!

describe('moves', () => {
  it('the shot at a time: its span, else the last before it, else the first', () => {
    expect(shotAt(SCRIPT, 4500)?.id).toBe('s2')
    expect(shotAt(SCRIPT, 12000)?.id).toBe('s2')
    expect(shotAt({ version: 2, scenes: [] }, 0)).toBeNull()
  })

  it('an event dropped in its own shot moves within it; in another it names that shot', () => {
    expect(moveOf(SCRIPT, box('l1'), 2000)).toEqual({ op: 'move', id: 'l1', start_ms: 2000 })
    expect(moveOf(SCRIPT, box('l1'), 6200)).toEqual({ op: 'move', id: 'l1', start_ms: 2200, shot: 's2' })
    expect(moveOf(SCRIPT, box('c1'), -300)).toEqual({ op: 'move', id: 'c1', start_ms: 0, shot: 's1' })
    expect(moveOf(SCRIPT, box('l1'), 500)).toBeNull()
  })

  it('a shot box moves by its id: to the place of the shot it lands on, else to its script time', () => {
    expect(moveOf(SCRIPT, box('shot:1.2'), 1000)).toEqual({ op: 'move', id: 's2', start_ms: 1000, shot: 's1' })
    expect(moveOf(SCRIPT, box('shot:1.1'), 300)).toEqual({ op: 'move', id: 's1', start_ms: 300 })
    expect(moveOf(SCRIPT, box('shot:1.2'), 4600)).toEqual({ op: 'move', id: 's2', start_ms: 4600 })
  })

  it('an add goes to the shot under the pointer, its time from that shot', () => {
    expect(addAt(SCRIPT, 7250)).toEqual({ shot: 's2', start_ms: 3250, scene: 1 })
  })

  it('speakers: the scene context cast, else the scenes casts', () => {
    expect(speakers(SCRIPT)).toEqual(['A', 'B'])
    expect(speakers({ version: 1, scenes: [{ title: 'Scene 1', cast: ['B'], shots: [] }] })).toEqual(['B'])
  })
})

describe('render progress', () => {
  const job = (over: Partial<Job>): Job => ({ id: 'j1', tool: 'director', kind: 'render', title: 'Script 1', lane: null, state: 'running',
    created: 0, started: 0, position: null, cancel_requested: false, progress: null, outputs: [], error: null, ...over })
  it('queued at its place, running its steps done of all, ended none', () => {
    expect(cutText(cutProgress(job({ state: 'queued', position: 2 }))!)).toBe('queued (2)')
    const p = cutProgress(job({ progress: { phase: '', index: 2, count: 4, step: 0, steps: 0, pct: 50, eta_s: null, text: 'Shot 2' } }))!
    expect(p).toMatchObject({ done: 1, count: 4, value: 0.375 })
    expect(cutText(p)).toBe('1 of 4 · Shot 2')
    expect(cutProgress(job({ state: 'done' }))).toBeNull()
  })
})
