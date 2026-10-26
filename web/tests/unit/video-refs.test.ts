// A video model's reference boxes (Stage 4): a start frame in box 1 (with `end`, a last frame in box 2), or identities in boxes 1…max. The roles name the
// boxes, refCap (= references.max) caps them, the draft stays on the video model as they fill, and the job sends them.
import { describe, expect, it } from 'vitest'
import { blockingReason } from '../../src/modules/generate-image/blocking'
import { declaration, planDelivery } from '../../src/modules/generate-image/delivery'
import { draft, edit } from '../../src/modules/generate-image/draft'
import { EMPTY_DRAFT, placeRef } from '../../src/modules/generate-image/edits'
import { dropPlan } from '../../src/modules/generate-image/inputs'
import { buildJob } from '../../src/modules/generate-image/job'
import { defaults, modelList } from '../../src/modules/generate-image/modelList'
import type { Draft, Model } from '../../src/modules/generate-image/types'
import { boxLabel, clipSize, tierSize } from '../../src/modules/generate-image/video'
import { H3_VIDEO } from '../e2e/fixtures/data'

const START: Model = { id: 'minimax_h3', label: 'MiniMax H3', family: 'MiniMax', modes: ['new', 'refs'], refCap: 2,
  defaults: { steps: 20, guidance: null }, guidanceKey: null, kind: 'video', video: H3_VIDEO }
/** A start-frame model without a last frame: box 1 only. */
const FIRST: Model = { ...START, refCap: 1, video: { ...H3_VIDEO, references: { role: 'start', max: 1 } } }
const OMNI: Model = { ...START, id: 'minimax_h3_ref2va', label: 'H3 Omni — Pruned', modes: ['refs'], refCap: 3,
  video: { ...H3_VIDEO, references: { role: 'identity', min: 1, max: 3 } } }
const TEXT: Model = { ...START, id: 'turbo', modes: ['new'], refCap: 0, video: { ...H3_VIDEO, references: null } }
const FLUX: Model = { ...START, id: 'flux', label: 'Flux', kind: 'image', video: null, refCap: 3 }
const slot = (id: string, w = 10, h = 10) => ({ id, w, h })
const D: Draft = { ...EMPTY_DRAFT, model: START.id, draft: 'A lighthouse', aspect: '16:9', size: 1 }
const block = (model: Model, refCount: number) =>
  blockingReason({ linkOn: true, engineOffline: false, model, prompt: 'x', refCount, uploading: 0, waiting: 0 })

describe('roles name the boxes', () => {
  it('start: box 1 is "Start frame", box 2 "Last frame" with `end`, the rest "Reference n"; identity: "Identity 1…max"; images unchanged', () => {
    expect(H3_VIDEO.references).toEqual({ role: 'start', max: 2, end: true })
    expect([0, 1, 2].map(i => boxLabel(START, i))).toEqual(['Start frame', 'Last frame', 'Reference 3'])
    expect([0, 1, 2].map(i => boxLabel(FIRST, i))).toEqual(['Start frame', 'Reference 2', 'Reference 3'])
    expect(boxLabel({ ...OMNI, video: { ...H3_VIDEO, references: { role: 'identity', max: 3, end: true } } }, 1)).toBe('Identity 2')
    expect([0, 1, 2].map(i => boxLabel(OMNI, i))).toEqual(['Identity 1', 'Identity 2', 'Identity 3'])
    expect([0, 1, 2].map(i => boxLabel({ ...OMNI, video: { ...H3_VIDEO, references: { role: 'identity', max: 2 } } }, i)))
      .toEqual(['Identity 1', 'Identity 2', 'Reference 3'])
    expect([0, 1, 2].map(i => boxLabel(FLUX, i))).toEqual(['Reference 1', 'Reference 2', 'Reference 3'])
    expect(boxLabel(TEXT, 0)).toBe('Reference 1')
    expect(boxLabel(null, 0)).toBe('Reference 1')
  })

  it('the sockets Media sees carry the role, up to refCap', () => {
    expect(declaration(D, START).sockets.map(s => s.label)).toEqual(['Start frame', 'Last frame'])
    expect(declaration(D, FIRST).sockets.map(s => s.label)).toEqual(['Start frame'])
    expect(declaration(D, OMNI).sockets.map(s => s.label)).toEqual(['Identity 1', 'Identity 2', 'Identity 3'])
    expect(declaration(D, TEXT).sockets).toEqual([])
  })
})

describe('caps', () => {
  it('with `end` a start-frame model takes two pictures (start, then last): a third is refused, by drop and by Send', () => {
    expect(dropPlan(0, 1, 0, START.refCap)).toEqual({ indexes: [0], extra: 0 })
    expect(dropPlan(1, 1, 1, START.refCap)).toEqual({ indexes: [1], extra: 0 })
    expect(dropPlan(0, 3, 0, START.refCap)).toEqual({ indexes: [0, 1], extra: 1 })
    expect(dropPlan(2, 1, 2, START.refCap)).toEqual({ indexes: [], extra: 1 })
    const one = { ...D, references: [slot('a')] }
    const two = { ...D, references: [slot('a'), slot('b')] }
    expect(planDelivery(one, START, 'reference', ['b']).targets).toEqual([{ item: 'b', socket: 'reference_2', index: 1 }])
    expect(planDelivery(two, START, 'reference', ['c']).refused).toEqual([{ item: 'c', reason: 'full', text: 'references are full' }])
    expect(planDelivery(D, START, 'reference', ['a', 'b', 'c']).targets.map(t => t.socket)).toEqual(['reference_1', 'reference_2'])
    expect(planDelivery(one, START, 'reference_3', ['c']).refused[0]?.reason).toBe('missing')
    // without `end`: one picture
    expect(dropPlan(1, 1, 1, FIRST.refCap)).toEqual({ indexes: [], extra: 1 })
    expect(planDelivery(one, FIRST, 'reference', ['b']).refused).toEqual([{ item: 'b', reason: 'full', text: 'references are full' }])
    expect(planDelivery(D, OMNI, 'reference', ['a', 'b', 'c', 'd']).targets.map(t => t.socket)).toEqual(['reference_1', 'reference_2', 'reference_3'])
  })

  it('Generate: the start model runs with or without its frame; Omni needs one identity; text only takes none', () => {
    expect(block(START, 0)).toBeNull()
    expect(block(START, 1)).toBeNull()
    expect(block(START, 2)).toBeNull()
    expect(block(START, 3)).toBe('Too many references for this model (3 of 2)')
    expect(block(FIRST, 2)).toBe('Too many references for this model (2 of 1)')
    expect(block(OMNI, 0)).toBe('Add a reference image')
    expect(block(OMNI, 3)).toBeNull()
    expect(block(TEXT, 1)).toBe('MiniMax H3 takes no references')
  })

  it('the draft stays on a video model as its boxes fill, whatever the refs default', () => {
    modelList.set([START, FLUX])
    defaults.set({ text: null, refs: 'flux', video: null })
    draft.set(D)
    edit(d => placeRef(d, 0, slot('a')))
    expect(draft.get().model).toBe(START.id)
    defaults.set({ text: null, refs: null, video: null })
  })
})

describe('the job and the Auto shape', () => {
  it('the start frame is sent as a reference (mode refs); a text-only clip model sends none', () => {
    const one = { ...D, references: [slot('chars/Character 11.png')] }
    expect(buildJob(one, START)).toMatchObject({ mode: 'refs', references: ['chars/Character 11.png'], images: 1, frames: 124 })
    expect(buildJob({ ...D, references: [slot('a'), slot('z')] }, START)).toMatchObject({ mode: 'refs', references: ['a', 'z'] })
    expect(buildJob(D, START)).toMatchObject({ mode: 'new' })
    expect('references' in buildJob(D, START)).toBe(false)
    const omni = buildJob({ ...D, model: OMNI.id, references: [slot('a'), slot('b')] }, OMNI)
    expect(omni).toMatchObject({ mode: 'refs', references: ['a', 'b'] })
    const text = buildJob({ ...one, model: TEXT.id }, TEXT)
    expect(text.mode).toBe('new')
    expect('references' in text).toBe(false)
  })

  it('Auto with a start frame is the tier\'s shape nearest the frame (clamped like images); square without one', () => {
    expect(tierSize(H3_VIDEO, 1, 'auto', 16 / 9)).toEqual({ width: 960, height: 544 })
    const auto = { ...D, aspect: 'auto' as const }
    expect(clipSize(auto, START as Model & { video: typeof H3_VIDEO })).toEqual({ width: 736, height: 736 })
    expect(clipSize({ ...auto, references: [slot('a', 900, 1600)] }, START as Model & { video: typeof H3_VIDEO })).toEqual({ width: 544, height: 960 })
    expect(clipSize({ ...auto, size: 2, references: [slot('a', 3000, 1000)] }, START as Model & { video: typeof H3_VIDEO })).toEqual({ width: 1632, height: 704 })
    // an identity is not the frame: Auto stays square
    expect(clipSize({ ...auto, references: [slot('a', 900, 1600)] }, OMNI as Model & { video: typeof H3_VIDEO })).toEqual({ width: 736, height: 736 })
    expect(buildJob({ ...auto, references: [slot('a', 1600, 900)] }, START)).toMatchObject({ width: 960, height: 544 })
  })
})
