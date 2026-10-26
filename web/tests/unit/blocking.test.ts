import { describe, expect, it } from 'vitest'
import { blockingReason, type BlockInput } from '../../src/modules/generate-image/blocking'
import type { Model } from '../../src/modules/generate-image/types'

const M: Model = { id: 'm', label: 'M', family: 'F', modes: ['new', 'refs'], refCap: 3, defaults: { steps: 4, guidance: null }, guidanceKey: null, kind: 'image', video: null }
const OK: BlockInput = { linkOn: true, engineOffline: false, model: M, prompt: 'cat', refCount: 0, uploading: 0, waiting: 0 }

describe('blocking reasons', () => {
  const cases: [Partial<BlockInput>, string][] = [
    [{ linkOn: false }, 'Reconnecting…'],
    [{ engineOffline: true }, 'Engine is offline'],
    [{ model: null }, 'Choose a model'],
    [{ prompt: '   ' }, 'Write a prompt'],
    [{ model: { ...M, modes: ['refs'] } }, 'Add a reference image'],
    [{ model: { ...M, modes: ['new'] }, refCount: 1 }, 'M takes no references'],
    [{ refCount: 4 }, 'Too many references for this model (4 of 3)'],
    [{ uploading: 1 }, 'Waiting for the image to upload'],
    [{ waiting: 10 }, 'Queue is full'],
  ]
  for (const [patch, text] of cases) {
    it(text, () => expect(blockingReason({ ...OK, ...patch })).toBe(text))
  }

  it('is null when nothing blocks; a prompt of any length is allowed', () => {
    expect(blockingReason(OK)).toBeNull()
    expect(blockingReason({ ...OK, prompt: 'x'.repeat(5000) })).toBeNull()
    expect(blockingReason({ ...OK, refCount: 3 })).toBeNull()
  })

  it('reports only the first matching reason', () => {
    expect(blockingReason({ ...OK, linkOn: false, prompt: '' })).toBe('Reconnecting…')
    expect(blockingReason({ ...OK, prompt: '', refCount: 9 })).toBe('Write a prompt')
  })
})
