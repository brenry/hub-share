import { describe, expect, it } from 'vitest'
import { EMPTY_DRAFT } from '../../src/modules/generate-image/edits'
import { RATIOS, SIZES, autoRatio, buildJob, canvasOf, canvasSize, jobMode, sizesFor } from '../../src/modules/generate-image/job'
import type { Draft, Model } from '../../src/modules/generate-image/types'

const FLUX: Model = { id: 'flux2_klein_9b', label: 'Flux 2 Klein 9B', family: 'Flux 2', modes: ['new', 'refs'], refCap: 3, defaults: { steps: 4, guidance: null }, guidanceKey: null, kind: 'image', video: null }
const QWEN: Model = { ...FLUX, id: 'qwen', guidanceKey: 'guidance_scale', defaults: { steps: 20, guidance: 4 } }

// Every cell of the mode table.
const TABLE: Record<string, [string, string, string, string]> = {
  '1:1': ['1024 × 1024', '1248 × 1248', '1456 × 1456', '2048 × 2048'],
  '4:3': ['1184 × 880', '1456 × 1088', '1680 × 1248', '2368 × 1776'],
  '3:4': ['880 × 1184', '1088 × 1456', '1248 × 1680', '1776 × 2368'],
  '3:2': ['1248 × 832', '1536 × 1024', '1776 × 1184', '2512 × 1680'],
  '2:3': ['832 × 1248', '1024 × 1536', '1184 × 1776', '1680 × 2512'],
  '16:9': ['1360 × 768', '1680 × 944', '1936 × 1088', '2736 × 1536'],
  '9:16': ['768 × 1360', '944 × 1680', '1088 × 1936', '1536 × 2736'],
}

describe('canvas', () => {
  for (const [aspect, row] of Object.entries(TABLE)) {
    it(`matches the table for ${aspect}`, () => {
      const got = [1, 1.5, 2, 4].map(mp => canvasSize(RATIOS[aspect as keyof typeof RATIOS], mp)).map(c => `${c.width} × ${c.height}`)
      expect(got).toEqual(row)
    })
  }

  it('Auto uses reference 1 ratio: 1200 × 800 at 1 MP is 1248 × 832', () => {
    const d: Draft = { ...EMPTY_DRAFT, aspect: 'auto', size: 1, references: [{ id: 'in/a', w: 1200, h: 800 }] }
    expect(canvasOf(d)).toEqual({ width: 1248, height: 832 })
  })

  it('a model\'s budget: the menu hides the sizes above it and the canvas shrinks to fit it (the server\'s canvas)', () => {
    const klein = 1920 * 1088, krea = 2048 * 2048
    expect(sizesFor(klein)).toEqual([1, 1.5])
    expect(sizesFor(krea)).toEqual([1, 1.5, 2, 4])
    expect(sizesFor(null)).toEqual([...SIZES])
    for (const ratio of Object.values(RATIOS)) {
      for (const mp of [2, 4]) {
        const c = canvasSize(ratio, mp, klein)
        expect(c.width * c.height).toBeLessThanOrEqual(klein)
        expect(c.width % 16 + c.height % 16).toBe(0)
        expect(c.width * c.height).toBeGreaterThan(0.97 * klein)
      }
      expect(canvasSize(ratio, 1.5, klein)).toEqual(canvasSize(ratio, 1.5))
      const k = canvasSize(ratio, 4, krea)
      expect(k.width * k.height).toBeLessThanOrEqual(krea)
    }
    expect(canvasSize(1, 4, krea)).toEqual({ width: 2048, height: 2048 })
    expect(canvasSize(1, 2, klein)).toEqual({ width: 1440, height: 1440 })
    const d: Draft = { ...EMPTY_DRAFT, aspect: '1:1', size: 2 }
    expect(buildJob({ ...d, model: 'k' }, { ...FLUX, budget: klein })).toMatchObject({ width: 1440, height: 1440 })
  })

  it('Auto is 1:1 without references, follows reference 1, and clamps to 0.4–2.5', () => {
    expect(autoRatio({ references: [] })).toBe(1)
    expect(autoRatio({ references: [{ id: 'r', w: 2000, h: 1000 }] })).toBe(2)
    expect(autoRatio({ references: [{ id: 'r', w: 5000, h: 1000 }] })).toBe(2.5)
    expect(autoRatio({ references: [{ id: 'e', w: 100, h: 1000 }] })).toBe(0.4)
  })
})

describe('job payload', () => {
  const base: Draft = {
    ...EMPTY_DRAFT, model: 'flux2_klein_9b', prompt: 'make it rainy please', draft: 'A grey cat asleep under an apple tree',
    lorasByModel: { flux2_klein_9b: [{ id: 'flux2_klein_9b/style/comic.safetensors', strength: 0.8 }, { id: 'flux2_klein_9b/off.safetensors', strength: 0 }, { id: 'b', strength: 0.15000000000000002 }] },
    aspect: '16:9', size: 1.5, images: 2, references: [{ id: 'in_9f2c41d0', w: 1, h: 1 }],
  }

  it('equals the §1.12 JSON byte for byte; LoRAs at 0.00 are left out', () => {
    expect(JSON.stringify(buildJob(base, FLUX))).toBe(JSON.stringify({
      tool: 'generate-image', model: 'flux2_klein_9b', mode: 'refs', prompt: 'A grey cat asleep under an apple tree',
      loras: [{ id: 'flux2_klein_9b/style/comic.safetensors', strength: 0.8 }, { id: 'b', strength: 0.15 }],
      width: 1680, height: 944, images: 2, steps: 4, guidance: null, seed: { mode: 'random' }, references: ['in_9f2c41d0'],
    }))
  })

  it('a model that runs its own steps sends them, whatever the card holds', () => {
    const turbo: Model = { ...QWEN, id: 'turbo', defaults: { steps: 8, guidance: 1 }, lockSteps: true }
    const held = { ...base, model: 'turbo', advancedByModel: { turbo: { steps: 30, guidance: 1, seed: { mode: 'random' as const } } } }
    expect(buildJob(held, turbo).steps).toBe(8)
    expect(buildJob(held, { ...turbo, lockSteps: false }).steps).toBe(30)
  })

  it('renders the assistant\'s draft, never the prompt box (the words typed to the assistant)', () => {
    expect(buildJob(base, FLUX).prompt).toBe('A grey cat asleep under an apple tree')
    expect(JSON.stringify(buildJob(base, FLUX))).not.toContain('make it rainy')
  })

  it('one path: references make it refs, none make it new text to image, never edit', () => {
    expect(jobMode(base)).toBe('refs')
    const fresh = buildJob({ ...base, references: [] }, FLUX)
    expect(fresh.mode).toBe('new')
    expect('references' in fresh).toBe(false)
    expect(JSON.stringify(buildJob(base, FLUX))).not.toContain('edit')
  })

  it('uses the model defaults, its guidance only when it has one, and a fixed seed when set', () => {
    expect(buildJob({ ...base, model: 'qwen', lorasByModel: {} }, QWEN)).toMatchObject({ steps: 20, guidance: 4, loras: [] })
    const fixed = { ...base, advancedByModel: { flux2_klein_9b: { steps: 6, guidance: 3, seed: { mode: 'fixed' as const, value: 123456 } } } }
    expect(buildJob(fixed, FLUX)).toMatchObject({ steps: 6, guidance: null, seed: { mode: 'fixed', value: 123456 } })
  })
})
