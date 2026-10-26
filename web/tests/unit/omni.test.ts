// Stage 7 on Omni: the detail menu (the engine's choices, kept per model in the card), each identity box's cut-out
// (it travels with its picture and reaches the job only on an identity model), and the 1:4 to 4:1 shape pre-check.
import { describe, expect, it } from 'vitest'
import { draft } from '../../src/modules/generate-image/draft'
import { EMPTY_DRAFT, placeRef, removeRef, resetAdvanced, toggleCutout, withAdvanced } from '../../src/modules/generate-image/edits'
import { addMedia, fitsBox, slotNote } from '../../src/modules/generate-image/inputs'
import { buildJob } from '../../src/modules/generate-image/job'
import { modelList } from '../../src/modules/generate-image/modelList'
import type { Draft, Model } from '../../src/modules/generate-image/types'
import { detailOf, detailOptions, inShape, refsOf } from '../../src/modules/generate-image/video'
import { H3_OMNI, H3_VIDEO, OMNI_DETAIL } from '../e2e/fixtures/data'

const START: Model = { id: 'minimax_h3', label: 'MiniMax H3', family: 'MiniMax', modes: ['new', 'refs'], refCap: 2,
  defaults: { steps: 20, guidance: null }, guidanceKey: null, kind: 'video', video: H3_VIDEO }
const OMNI: Model = { ...START, id: 'minimax_h3_ref2va', label: 'H3 Omni — Pruned', modes: ['refs'], refCap: 3, video: H3_OMNI }
const slot = (id: string, w = 10, h = 10) => ({ id, w, h })
const D: Draft = { ...EMPTY_DRAFT, model: OMNI.id, draft: 'Two friends at a table', aspect: '16:9', size: 1 }
const saved = (detail: string): Draft => withAdvanced(D, OMNI, { detail })

describe('detail', () => {
  it('the saved value when the model announces it, else the engine default; none on First / Last', () => {
    expect(detailOf(saved('max'), OMNI)).toBe('max')
    expect(detailOf(saved('huge'), OMNI)).toBe('match')
    expect(detailOf(D, OMNI)).toBe('match')
    expect(detailOf(withAdvanced(D, START, { detail: 'max' }), START)).toBe('')
    expect(refsOf(START)?.detail).toBeUndefined()
  })

  it('the menu keeps the engine order and labels', () => {
    expect(detailOptions(refsOf(OMNI))).toEqual([{ value: 'match', label: 'Match output' }, { value: 'max', label: 'Maximum detail' }])
    const flipped = { ...OMNI_DETAIL, choices: [...OMNI_DETAIL.choices].reverse() }
    expect(detailOptions({ role: 'identity', max: 3, detail: flipped }).map(o => o.value)).toEqual(['max', 'match'])
    expect(detailOptions(refsOf(START))).toEqual([])
  })

  it('Reset keeps the sheet\'s detail, as it keeps the text encoder', () => {
    expect(resetAdvanced(saved('max'), OMNI).advancedByModel[OMNI.id]).toEqual({ steps: 20, guidance: null, seed: { mode: 'random' }, detail: 'max' })
    expect(resetAdvanced(withAdvanced(D, OMNI, { steps: 9 }), OMNI).advancedByModel[OMNI.id]).toBeUndefined()
  })
})

describe('cut-out', () => {
  const three = { ...D, references: [slot('a'), slot('b'), slot('c')] }

  it('toggleCutout flips one box; off drops the flag', () => {
    const on = toggleCutout(three, 1)
    expect(on.references).toEqual([slot('a'), { ...slot('b'), cutout: true }, slot('c')])
    expect(toggleCutout(on, 1).references).toEqual(three.references)
    expect(toggleCutout(three, 5)).toBe(three)
  })

  it('removeRef keeps each flag with its picture; placeRef gives a new picture none', () => {
    const on = toggleCutout(toggleCutout(three, 1), 2)
    expect(removeRef(on, 0).references).toEqual([{ ...slot('b'), cutout: true }, { ...slot('c'), cutout: true }])
    expect(placeRef(on, 1, slot('n')).references[1]).toEqual(slot('n'))
  })

  it('the job: Omni with [off, on] sends [false, true]; all off sends none; First / Last never sends it', () => {
    const two = { ...D, references: [slot('a'), slot('b')] }
    expect(buildJob(toggleCutout(two, 1), OMNI)).toMatchObject({ references: ['a', 'b'], cutout: [false, true] })
    expect('cutout' in buildJob(two, OMNI)).toBe(false)
    const first = { ...toggleCutout(two, 0), model: START.id }
    expect(buildJob(first, START)).toMatchObject({ references: ['a', 'b'] })
    expect('cutout' in buildJob(first, START)).toBe(false)
  })
})

describe('shape', () => {
  it('1:4 and 4:1 pass, 1:4.01 fails; an unknown size is left to the server', () => {
    expect(inShape(100, 400)).toBe(true)
    expect(inShape(400, 100)).toBe(true)
    expect(inShape(100, 401)).toBe(false)
    expect(inShape(401, 100)).toBe(false)
    expect(inShape(0, 0)).toBe(true)
  })

  it('an out-of-shape drop on Omni places nothing and sets the note; First / Last leaves it to the server', async () => {
    modelList.set([START, OMNI])
    draft.set(D)
    await addMedia([{ id: 'out/tall.png', w: 100, h: 500 }], 0, OMNI)
    expect(draft.get().references).toEqual([])
    expect(slotNote.get()).toBe('H3 Omni — Pruned takes pictures between 1:4 and 4:1')
    slotNote.set(null)
    expect(fitsBox(START, { w: 100, h: 500 })).toBe(true)
    expect(fitsBox(OMNI, { w: 100, h: 400 })).toBe(true)
    expect(slotNote.get()).toBeNull()
  })
})
