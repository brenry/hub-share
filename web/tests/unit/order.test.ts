import { describe, expect, it } from 'vitest'
import { NEW_FOR_MS, isNew, others, share, stem } from '../../src/modules/generate-image/library/order'
import type { LoraItem } from '../../src/modules/generate-image/types'

const lora = (id: string, file: string, extra: Partial<LoraItem> = {}): LoraItem => ({
  id, name: id, file, fileTriggers: [], cover: null, strength: null, defaultStrength: 1, addedAt: 0, ...extra,
})

describe('LoRA column order', () => {
  it('shows the file name without its extension', () => {
    expect(stem(lora('a', 'krea2_skin_v3.safetensors'))).toBe('krea2_skin_v3')
    expect(stem(lora('a', 'odd.name.v2.safetensors'))).toBe('odd.name.v2')
    expect(stem(lora('a', 'noext'))).toBe('noext')
  })
  it('lists what is not on the stack, A–Z by file name, numbers in order', () => {
    const items = [lora('k/b', 'b_10.safetensors'), lora('k/a', 'B_2.safetensors'), lora('k/c', 'a.safetensors'), lora('k/on', 'zz.safetensors')]
    expect(others(items, [{ id: 'k/on', strength: 1 }]).map(l => l.id)).toEqual(['k/c', 'k/a', 'k/b'])
  })
  it('marks a recent file as new, and nothing else', () => {
    const now = 1_800_000_000_000
    const fresh = lora('a', 'a.safetensors', { addedAt: now / 1000 - 3600 })
    expect(isNew(fresh, now)).toBe(true)
    expect(isNew({ ...fresh, addedAt: (now - NEW_FOR_MS) / 1000 - 1 }, now)).toBe(false)
  })
  it('draws the strength line to 1.0 and no further', () => {
    expect(share(0)).toBe(0)
    expect(share(0.75)).toBe(0.75)
    expect(share(1)).toBe(1)
    expect(share(1.6)).toBe(1)
  })
})
