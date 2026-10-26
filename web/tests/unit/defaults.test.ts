import { describe, expect, it } from 'vitest'
import { draft, edit } from '../../src/modules/generate-image/draft'
import { EMPTY_DRAFT, defaultModel, placeRef, removeRef, withModel } from '../../src/modules/generate-image/edits'
import { defaults, modelList } from '../../src/modules/generate-image/modelList'
import type { Draft, Model } from '../../src/modules/generate-image/types'

const FLUX: Model = { id: 'flux', label: 'Flux', family: 'F', modes: ['new', 'refs'], refCap: 3, defaults: { steps: 4, guidance: null }, guidanceKey: null, kind: 'image', video: null }
const ZIT: Model = { ...FLUX, id: 'zit', modes: ['new'], refCap: 0 }
const QWEN: Model = { ...FLUX, id: 'qwen', refCap: 2 }
const MODELS = [FLUX, ZIT, QWEN]
const BOTH = { text: 'zit', refs: 'flux', video: null }
const slot = (id: string) => ({ id, w: 10, h: 10 })
const D: Draft = { ...EMPTY_DRAFT, model: 'qwen', selected: 'l1' }

describe('the default model rule', () => {
  it('refs default with references, text default without, nothing when unset or gone', () => {
    expect(defaultModel(MODELS, BOTH, 1)?.id).toBe('flux')
    expect(defaultModel(MODELS, BOTH, 0)?.id).toBe('zit')
    expect(defaultModel(MODELS, { text: 'zit', refs: null, video: null }, 2)).toBeNull()
    expect(defaultModel(MODELS, { text: null, refs: 'flux', video: null }, 0)).toBeNull()
    expect(defaultModel(MODELS, { text: 'gone', refs: 'gone', video: null }, 1)).toBeNull()
  })
})

describe('a box change never changes the model', () => {
  it('placeRef and removeRef through edit() keep the pulldown\'s pick, whatever the defaults', () => {
    modelList.set(MODELS)
    defaults.set(BOTH)
    for (const pick of ['zit', 'qwen', 'flux']) {
      draft.set({ ...D, model: pick })
      edit(d => placeRef(d, 0, slot('a')))
      expect(draft.get().model).toBe(pick)
      edit(d => placeRef(d, 1, slot('b')))
      edit(d => removeRef(d, 0))
      edit(d => removeRef(d, 0))
      expect(draft.get().model).toBe(pick)
    }
    edit(d => withModel(d, QWEN))
    expect(draft.get().model).toBe('qwen')
    defaults.set({ text: null, refs: null, video: null })
  })
})
