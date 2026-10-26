// The Sound box after the picture boxes, only for a model that keeps a sound as its clip's; the
// clip's seconds are the sound's then, not editable; the press sends the sound to that model alone.
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { draft } from '../../src/modules/generate-image/draft'
import { EMPTY_DRAFT, normalizeDraft } from '../../src/modules/generate-image/edits'
import { buildJob } from '../../src/modules/generate-image/job'
import { SoundBox } from '../../src/modules/generate-image/run/SoundBox'
import { Seconds } from '../../src/modules/generate-image/Seconds'
import type { Draft, Model } from '../../src/modules/generate-image/types'
import { soundOf } from '../../src/modules/generate-image/video'
import { H3_OMNI, MODELS } from '../e2e/fixtures/data'

const OMNI = MODELS.find(m => m.id === 'minimax_h3_ref2va')!
const HEARS: Model = { ...OMNI, id: 'minimax_h3_ref2va_pruned', video: { ...H3_OMNI, soundtrack: 'AS' } }
const LINE = { id: 'sounds/2026-10-17/120000-000.wav', seconds: 14 }
const held: Draft = { ...EMPTY_DRAFT, model: HEARS.id, draft: 'Character 7 talks.', sound: LINE }
const box = (model: Model | null) => renderToStaticMarkup(createElement(SoundBox, { model }))

describe('the Sound box', () => {
  it('shows only with a model that keeps a sound', () => {
    draft.set(EMPTY_DRAFT)
    expect(box(OMNI)).toBe('')
    expect(box(null)).toBe('')
    expect(box(HEARS)).toContain('aria-label="Sound, empty"')
  })

  it('a sound in it shows its name and length, and Remove', () => {
    draft.set(held)
    const html = box(HEARS)
    expect(html).toContain('120000-000')
    expect(html).toContain('14.0 s')
    expect(html).toContain('aria-label="Remove sound"')
  })

  it('changing the model to one without soundtrack removes the box and the sound is not sent', () => {
    draft.set({ ...held, model: OMNI.id })
    expect(box(OMNI)).toBe('')
    expect(soundOf(held, OMNI)).toBeNull()
    expect(buildJob({ ...held, model: OMNI.id }, OMNI).sound).toBeUndefined()
  })
})

describe('a clip that follows a sound', () => {
  it('its seconds are the sound\'s and are not editable', () => {
    const sec = soundOf(held, HEARS)?.seconds
    const html = renderToStaticMarkup(createElement(Seconds, { video: HEARS.video!, frames: 124, step: false, put: () => {}, className: undefined, sound: sec }))
    expect(html).toContain('value="14"')
    expect(html).toContain('disabled')
    const free = renderToStaticMarkup(createElement(Seconds, { video: HEARS.video!, frames: 124, step: false, put: () => {}, className: undefined }))
    expect(free).not.toContain('disabled')
  })

  it('the press sends the sound to a model that keeps one, and none without a sound', () => {
    expect(buildJob(held, HEARS).sound).toBe(LINE.id)
    expect(buildJob({ ...held, sound: null }, HEARS).sound).toBeUndefined()
  })

  it('a stored draft without a sound, or with a broken one, holds none', () => {
    expect(normalizeDraft({}).sound).toBeNull()
    expect(normalizeDraft({ sound: { id: 3 } }).sound).toBeNull()
    expect(normalizeDraft({ sound: LINE }).sound).toEqual(LINE)
  })
})
