// The Scripts timeline's rows and places: rows in order, characters by first appearance in the
// casts, an event's x at the scale, and the 2rem/s floor (40 px/s at a 20 px root).
import { describe, expect, it } from 'vitest'
import example from '../../../tests/fixtures/script-1.json'
import type { Script } from '../../src/modules/director/api'
import { MIN_REM_PER_S, boxes, cameraText, characters, describe as line, drawable, lengthMs, panelsOf, rowOf, rows, scale, sketchBox, x } from '../../src/modules/director/timeline'

const EXAMPLE = example as Script
const two = (a: string[], b: string[]): Script => ({ version: 1, scenes: [
  { title: 'A', cast: a, shots: [{ start_ms: 0, end_ms: 1000, events: [] }] },
  { title: 'B', cast: b, shots: [{ start_ms: 1000, end_ms: 2000, events: [] }] },
] })

describe('timeline', () => {
  it('rows in order: ruler, shots, a lines row per character, cues, a pose row per character', () => {
    expect(rows(EXAMPLE).map(r => r.head)).toEqual(['', 'Shots', 'Character 1', 'Character 2', 'Cues', 'Character 1 pose', 'Character 2 pose'])
    expect(rows(EXAMPLE).map(r => r.kind)).toEqual(['ruler', 'shots', 'lines', 'lines', 'cues', 'poses', 'poses'])
  })

  it('characters by first appearance in the casts, once in any case', () => {
    expect(characters(two(['Character 6', 'Character 7'], ['character 7', 'Character 4', 'Character 6']))).toEqual(['Character 6', 'Character 7', 'Character 4'])
    expect(rows(two(['Character 6'], ['Character 4'])).map(r => r.key)).toEqual(['ruler', 'shots', 'line:character 6', 'line:character 4', 'cues', 'pose:character 6', 'pose:character 4'])
  })

  it('every event on its row, every shot a box', () => {
    const all = boxes(EXAMPLE)
    expect(all.filter(b => b.row === 'shots').map(b => b.text)).toEqual([
      '1.1 Wide shot of the stage, Character 1 standing left, Character 2 seated right', '1.2 Close shot on Character 2',
      '1.3 Close shot on Character 1'])
    expect(all.filter(b => b.row === 'line:character 1').map(b => b.id)).toEqual(['l1', 'l3'])
    expect(all.filter(b => b.row === 'cues').map(b => b.id)).toEqual(['c1', 'c2', 'c3', 'c4'])
    expect(all.filter(b => b.row === 'pose:character 2').map(b => b.text)).toEqual(['sit', 'sit', 'hand_to_face', 'sit'])
    expect(rowOf({ id: 'p', kind: 'pose', start_ms: 0, end_ms: 1, character: 'CHARACTER 7', pose: 'sit' })).toBe('pose:character 7')
  })

  it('x of an event at the scale; the whole script fits the width at 40 px/s or more', () => {
    expect(lengthMs(EXAMPLE)).toBe(24000)
    // a last scene with no shot yet does not make it 0
    expect(lengthMs({ ...EXAMPLE, scenes: [...EXAMPLE.scenes, { title: 'Next', cast: ['Character 1'], shots: [] }] })).toBe(24000)
    expect(lengthMs({ version: 2, scenes: [{ title: 'A', cast: [], shots: [] }] })).toBe(0)
    expect(scale(24000, 1920, 20)).toBe(80)
    expect(x(7642, 80)).toBeCloseTo(611.36)
    expect(x(0, 80)).toBe(0)
    expect(x(24000, scale(24000, 1920, 20))).toBe(1920)
  })

  it('never below 2rem a second (40 px at a 20 px root): a long script scrolls', () => {
    expect(MIN_REM_PER_S).toBe(2)
    expect(scale(24000, 600, 20)).toBe(40)
    expect(scale(3_600_000, 1920, 20)).toBe(40)
    expect(scale(24000, 0, 20)).toBe(40)
    expect(scale(24000, 600, 25)).toBe(50)
  })

  it('a box in one line', () => {
    const all = boxes(EXAMPLE)
    const of = (id: string) => line(all.find(b => b.id === id)!, EXAMPLE)
    expect(of('l1')).toBe('Character 1 · “Word word, word. Word word word word word word.” · English · Emotion 1 · 2.6 words/s · 4.0–7.6 s')
    expect(of('c3')).toBe('Cue effect · Word word word word word word word word · 13.0–13.8 s')
    expect(of('p6')).toBe('Character 2 · hand_to_face · 12.6–17.0 s')
    expect(of('shot:1.2')).toBe('Shot 1.2 · Close shot on Character 2 · 9.0–17.0 s')
  })

  it('drawable keeps lines, cues and poses and drops a panel', () => {
    const withPanel = structuredClone(EXAMPLE)
    const panel = { id: 'f1', kind: 'panel', at_ms: 9000, picture: null, stale: false }
    withPanel.scenes[0]!.shots[1]!.events.push(panel as unknown as Script['scenes'][0]['shots'][0]['events'][0])
    const kept = drawable(withPanel)
    expect(kept).toEqual(EXAMPLE)
    expect(boxes(kept).map(b => b.id)).toEqual(boxes(EXAMPLE).map(b => b.id))
    expect(boxes(kept).some(b => b.id === 'f1')).toBe(false)
  })

  it('panelsOf: each panel’s time, picture, stale and shot label; none without panels', () => {
    const withPanels = structuredClone(EXAMPLE)
    type E = Script['scenes'][0]['shots'][0]['events'][0]
    const add = (k: number, p: object) => withPanels.scenes[0]!.shots[k]!.events.push(p as unknown as E)
    add(1, { id: 'f3', kind: 'panel', at_ms: 12600, picture: null, stale: false })
    add(1, { id: 'f2', kind: 'panel', at_ms: 9000, picture: 'out/d/b.png', stale: true })
    add(0, { id: 'f1', kind: 'panel', at_ms: 0, picture: 'out/d/a.png', stale: false })
    expect(panelsOf(withPanels)).toEqual([
      { id: 'f1', at: 0, picture: 'out/d/a.png', stale: false, shot: '1.1' },
      { id: 'f2', at: 9000, picture: 'out/d/b.png', stale: true, shot: '1.2' },
      { id: 'f3', at: 12600, picture: null, stale: false, shot: '1.2' },
    ])
    expect(panelsOf(EXAMPLE)).toEqual([])
    const [f1, f2, f3] = panelsOf(withPanels).map(sketchBox)
    expect(line(f1!, EXAMPLE)).toBe('Sketch f1 · shot 1.1 · 0.0 s · drawn')
    expect(line(f2!, EXAMPLE)).toBe('Sketch f2 · shot 1.2 · 9.0 s · stale')
    expect(line(f3!, EXAMPLE)).toBe('Sketch f3 · shot 1.2 · 12.6 s · not drawn')
  })

  it('a camera in words: the text, or framing, move and who is in frame', () => {
    const shot = (camera?: Script['scenes'][number]['shots'][number]['camera']) => ({ start_ms: 0, end_ms: 1000, events: [], ...(camera === undefined ? {} : { camera }) })
    expect(cameraText(shot('Close on Character 6'))).toBe('Close on Character 6')
    expect(cameraText(shot({ framing: 'close shot', move: 'slow push in', on: ['Character 6'] }))).toBe('close shot, slow push in · on Character 6')
    expect(cameraText(shot({ framing: 'wide', on: [] }))).toBe('wide · on nobody')
    expect(cameraText(shot({ framing: 'wide' }))).toBe('wide')
    expect(cameraText(shot())).toBe('')
    const script: Script = { version: 2, scenes: [{ title: 'A', cast: ['Character 6'], shots: [shot({ framing: 'close shot', on: ['Character 6'] }), shot('Wide')] }] }
    const shots = boxes(script).filter(b => b.row === 'shots')
    expect(shots.map(b => b.text)).toEqual(['1.1 close shot · on Character 6', '1.2 Wide'])
    expect(line(shots[0]!, script)).toBe('Shot 1.1 · close shot · on Character 6 · 0.0–1.0 s')
  })
})
