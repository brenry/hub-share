import { describe, expect, it } from 'vitest'
import { declaration, planDelivery } from '../../src/modules/generate-image/delivery'
import { EMPTY_DRAFT, placeRef, removeRef, toggleLora, withModel } from '../../src/modules/generate-image/edits'
import { dropPlan } from '../../src/modules/generate-image/inputs'
import type { Draft, Model } from '../../src/modules/generate-image/types'

const FLUX: Model = { id: 'flux', label: 'Flux', family: 'F', modes: ['new', 'refs'], refCap: 3, defaults: { steps: 4, guidance: null }, guidanceKey: null, kind: 'image', video: null }
const ZIT: Model = { ...FLUX, id: 'zit', modes: ['new'], refCap: 0 }
const slot = (id: string) => ({ id, w: 10, h: 10 })
const D: Draft = { ...EMPTY_DRAFT, model: 'flux', references: [slot('r1')] }

describe('socket declaration', () => {
  it('lists only reference slots with fill state; the primary is the next free reference', () => {
    const d = declaration(D, FLUX)
    expect(d.primary).toBe('reference')
    expect(d.mode).toBe('refs')
    expect(d.sockets.map(s => `${s.id}:${s.filled}`)).toEqual(['reference_1:true', 'reference_2:false', 'reference_3:false'])
    expect(declaration({ ...D, references: [] }, FLUX)).toMatchObject({ mode: 'new', primary: 'reference' })
    expect(declaration({ ...D, references: [] }, ZIT)).toEqual({ tool: 'generate-image', mode: 'new', primary: null, sockets: [] })
  })
})

describe('placing delivered items', () => {
  it('a group fills free slots in order and refuses the rest', () => {
    const p = planDelivery(D, FLUX, 'reference', ['a', 'b', 'c'])
    expect(p.targets).toEqual([{ item: 'a', socket: 'reference_2', index: 1 }, { item: 'b', socket: 'reference_3', index: 2 }])
    expect(p.refused).toEqual([{ item: 'c', reason: 'full', text: 'references are full' }])
  })
  it('a specific slot replaces exactly that slot and never leaves gaps', () => {
    expect(planDelivery(D, FLUX, 'reference_1', ['a']).targets).toEqual([{ item: 'a', socket: 'reference_1', index: 0 }])
    expect(planDelivery(D, FLUX, 'reference_3', ['a']).targets).toEqual([{ item: 'a', socket: 'reference_2', index: 1 }])
    expect(planDelivery(D, FLUX, 'reference_2', ['a', 'b']).refused[0]!.reason).toBe('one_only')
  })
  it('unknown sockets are refused', () => {
    expect(planDelivery(D, FLUX, 'edit_source', ['a']).refused[0]!.reason).toBe('missing')
    expect(planDelivery(D, ZIT, 'reference', ['a']).refused[0]!.reason).toBe('missing')
  })
  it('dropped files fill from the target slot onward', () => {
    expect(dropPlan(1, 3, 1, 3)).toEqual({ indexes: [1, 2], extra: 1 })
    expect(dropPlan(0, 2, 2, 3)).toEqual({ indexes: [0, 2], extra: 0 })
    expect(dropPlan(2, 1, 3, 3)).toEqual({ indexes: [2], extra: 0 })
  })
})

describe('draft edits', () => {
  it('model switch keeps per-model stacks', () => {
    let d = toggleLora({ ...D }, 'l1', 0.8)
    expect(d.selected).toBe('l1')
    d = withModel(d, ZIT)
    expect(d.model).toBe('zit')
    expect(d.lorasByModel.flux).toEqual([{ id: 'l1', strength: 0.8 }])
    d = withModel(d, FLUX)
    expect(d.lorasByModel.flux).toEqual([{ id: 'l1', strength: 0.8 }])
    expect(toggleLora(d, 'l1', 0.8).lorasByModel.flux).toEqual([])
  })
  it('placing a reference fills the slot', () => {
    expect(placeRef(D, 5, slot('x')).references.map(r => r.id)).toEqual(['r1', 'x'])
  })
  it('removing a reference shifts the later ones left', () => {
    const d = { ...D, references: [slot('a'), slot('b'), slot('c')] }
    expect(removeRef(d, 0).references.map(r => r.id)).toEqual(['b', 'c'])
  })
})
