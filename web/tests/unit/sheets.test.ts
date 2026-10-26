// The two raised sheets: the fold's lists only the image models, Video's only the video models with the video rows;
// Settings' default models: image models for text and references, a video model for video (`video_default`). Video and
// the fold from a model of the other kind bring back the last picked of their kind, else its default (`switchKind`).
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import GenerateCard from '../../src/modules/generate-image/Card'
import { draft } from '../../src/modules/generate-image/draft'
import { EMPTY_DRAFT, normalizeDraft, switchKind, withModel } from '../../src/modules/generate-image/edits'
import { LoraLibrary } from '../../src/modules/generate-image/library/LoraLibrary'
import { VideoSheet } from '../../src/modules/generate-image/library/VideoSheet'
import { modelList, sheetModel, sheetModels } from '../../src/modules/generate-image/modelList'
import { MODELS } from '../e2e/fixtures/data'

const by = (id: string) => MODELS.find(m => m.id === id)!
const H3 = by('minimax_h3'), OMNI = by('minimax_h3_ref2va'), QWEN = by('qwen_image_edit_plus')
/** The model names a rendered sheet's picker offers. */
const offered = (html: string) => [...html.matchAll(/role="option"[^>]*><span class="ell">([^<]+)</g)].map(m => m[1])
const regions = (html: string) => [...html.matchAll(/data-region="([^"]+)"/g)].map(m => m[1])

describe('the split', () => {
  it('each sheet lists only its kind, in the catalog order', () => {
    expect(sheetModels(MODELS, 'image').map(m => m.id)).toEqual(['flux2_klein_9b', 'qwen_image_edit_plus', 'z_image_turbo'])
    expect(sheetModels(MODELS, 'video').map(m => m.id)).toEqual(['minimax_h3', 'minimax_h3_ref2va'])
  })

  it('a sheet shows the draft\'s model only when it is of its kind', () => {
    expect(sheetModel(H3, 'video')).toBe(H3)
    expect(sheetModel(H3, 'image')).toBeNull()
    expect(sheetModel(QWEN, 'image')).toBe(QWEN)
    expect(sheetModel(QWEN, 'video')).toBeNull()
    expect(sheetModel(null, 'video')).toBeNull()
  })
})

describe('the sheets', () => {
  const draw = (sheet: typeof LoraLibrary, id: string) => {
    draft.set({ ...EMPTY_DRAFT, model: id })
    return renderToStaticMarkup(createElement(sheet, { models: MODELS, model: by(id) }))
  }

  it('Video on a video model: only video models; size, seconds, text encoder (detail on Omni); its LoRAs', () => {
    const h3 = draw(VideoSheet, H3.id)
    expect(offered(h3)).toEqual(['MiniMax H3', 'H3 Omni — Pruned'])
    expect(regions(h3)).toEqual(['video-sheet', 'model-picker', 'video-size', 'seconds', 'text-encoder'])
    expect(h3).toContain('aria-label="LoRAs"')
    expect(regions(draw(VideoSheet, OMNI.id))).toContain('detail')
  })

  it('the fold on a picture model: only image models; guidance, no video rows', () => {
    const qwen = draw(LoraLibrary, QWEN.id)
    expect(offered(qwen)).toEqual(['Flux 2 Klein 9B', 'Qwen Image Edit Plus', 'Z-Image Turbo'])
    expect(regions(qwen)).toEqual(['library', 'model-picker', 'guidance'])
  })

  it('a sheet of the other kind asks for a model and lists no LoRAs', () => {
    for (const html of [draw(LoraLibrary, H3.id), draw(VideoSheet, QWEN.id)]) {
      expect(html).toContain('Choose a model')
      expect(html).not.toContain('aria-label="LoRAs"')
    }
  })
})

describe('Settings → default models', () => {
  it('text and references pick image models; Default video model lists Not set and the video models', () => {
    modelList.set(MODELS)
    draft.set({ ...EMPTY_DRAFT, model: H3.id })
    const html = renderToStaticMarkup(createElement(GenerateCard, { changed: () => {} }))
    expect(offered(html)).toEqual(['Not set', 'Flux 2 Klein 9B', 'Qwen Image Edit Plus', 'Z-Image Turbo',
      'Not set', 'Flux 2 Klein 9B', 'Qwen Image Edit Plus', 'Z-Image Turbo'])
    const select = /<select[^>]*aria-label="Default video model"[^>]*>(.*?)<\/select>/.exec(html)
    expect([...select![1]!.matchAll(/<option value="([^"]*)"[^>]*>([^<]+)</g)].map(m => [m[1], m[2]]))
      .toEqual([['', 'Not set'], ['minimax_h3', 'MiniMax H3'], ['minimax_h3_ref2va', 'H3 Omni — Pruned']])
  })
})

describe('Video and the fold switch kind', () => {
  const NONE = { text: null, refs: null, video: null }
  const SET = { text: 'z_image_turbo', refs: 'qwen_image_edit_plus', video: 'minimax_h3' }
  const on = (id: string, lastModel = { image: '', video: '' }) => ({ ...EMPTY_DRAFT, model: id, lastModel })

  it('from the other kind: the last picked of the button\'s kind, and the model left stays the last of its own', () => {
    const d = switchKind(on(QWEN.id, { image: '', video: OMNI.id }), MODELS, SET, 'video')!
    expect(d.model).toBe(OMNI.id)
    expect(d.lastModel).toEqual({ image: QWEN.id, video: OMNI.id })
    expect(switchKind(d, MODELS, SET, 'image')!.model).toBe(QWEN.id)
  })

  it('nothing remembered: the video default; the image default for the draft\'s references', () => {
    expect(switchKind(on(QWEN.id), MODELS, SET, 'video')!.model).toBe(H3.id)
    expect(switchKind(on(H3.id), MODELS, SET, 'image')!.model).toBe('z_image_turbo')
    expect(switchKind({ ...on(H3.id), references: [{ id: 'a.png', w: 1, h: 1 }] }, MODELS, SET, 'image')!.model).toBe(QWEN.id)
  })

  it('already on the kind, or nothing known (a stale or wrong-kind id too): no switch', () => {
    expect(switchKind(on(H3.id, { image: QWEN.id, video: OMNI.id }), MODELS, SET, 'video')).toBeNull()
    expect(switchKind(on(QWEN.id, { image: '', video: 'gone' }), MODELS, NONE, 'video')).toBeNull()
    expect(switchKind(on(QWEN.id, { image: '', video: QWEN.id }), MODELS, { ...NONE, video: QWEN.id }, 'video')).toBeNull()
  })

  it('the stacks and Advanced are per model: a switch there and back keeps both', () => {
    const lorasByModel = { [QWEN.id]: [{ id: 'q', strength: 1.4 }], [OMNI.id]: [{ id: 'o', strength: 0.6 }] }
    const advancedByModel = { [OMNI.id]: { steps: 12, guidance: null, seed: { mode: 'random' as const }, frames: 97 } }
    const d = { ...on(QWEN.id, { image: '', video: OMNI.id }), lorasByModel, advancedByModel }
    const back = switchKind(switchKind(d, MODELS, NONE, 'video')!, MODELS, NONE, 'image')!
    expect(back.model).toBe(QWEN.id)
    expect(back.lorasByModel).toEqual(lorasByModel)
    expect(back.advancedByModel).toEqual(advancedByModel)
  })

  it('a pick keeps it; an older or broken draft reads as nothing remembered', () => {
    expect(withModel(EMPTY_DRAFT, H3).lastModel).toEqual({ image: '', video: H3.id })
    expect(normalizeDraft({ model: H3.id }).lastModel).toEqual({ image: '', video: '' })
    expect(normalizeDraft({ lastModel: { image: 3, video: OMNI.id } }).lastModel).toEqual({ image: '', video: OMNI.id })
  })
})
