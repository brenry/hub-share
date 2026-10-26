// Stage 12 on the web: the Sounds section of the Media window (where a new sound lands, the tree's row,
// /sounds opening on it) and the Generate bar's speech mode (the one box, the label, what blocks a press, the payload).
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { SOUNDS, TEMP, clips, fromGeneration, itemsOf, norm, prepend, sounds, startView, temp } from '../../src/screens/media/media'
import { Tree } from '../../src/screens/media/Tree'
import { blockingReason, NO_SPEAKER_TEXT, ONE_SPEAKER_TEXT } from '../../src/modules/generate-image/blocking'
import { EMPTY_DRAFT } from '../../src/modules/generate-image/edits'
import { buildJob } from '../../src/modules/generate-image/job'
import { sheetModel, sheetModels } from '../../src/modules/generate-image/modelList'
import { generateLabel } from '../../src/modules/generate-image/run/jobs'
import { MODELS, SPEECH } from '../e2e/fixtures/data'

const sound = (id: string, seconds: number) => fromGeneration({ id, kind: 'sound', url: `/files/${id}`, thumb: null, w: null, h: null, created: 5, job: 'j1', seconds })

describe('the Sounds section', () => {
  it('a new sound lands in the Sounds, with its length and no picture', () => {
    for (const s of [temp, clips, sounds]) s.set(m => ({ ...m, items: [], total: 0 }))
    const it = sound('sounds/2026-10-17/120000-000.wav', 4.2)
    expect(it).toMatchObject({ kind: 'sound', thumb: null, w: 0, h: 0, seconds: 4.2, group: '' })
    prepend(it)
    expect([sounds.get().total, clips.get().total, temp.get().total]).toEqual([1, 0, 0])
    expect(itemsOf(SOUNDS).map(i => i.id)).toEqual([it.id])
    expect(norm({ id: 'sounds/a.wav', kind: 'sound', url: '', thumb: null, w: null, h: null, createdAt: 1, group: '', fav: false }).kind).toBe('sound')
  })

  it('the tree has a Sounds row under Clips, and /sounds opens on it', () => {
    sounds.set(m => ({ ...m, total: 3 }))
    const html = renderToStaticMarkup(createElement(Tree, { view: SOUNDS, onView: () => {} }))
    const rows = [...html.matchAll(/data-row="([^"]+)"/g)].map(m => m[1])
    expect(rows.indexOf('sounds')).toBe(rows.indexOf('clips') + 1)
    expect(/aria-selected="true" data-row="sounds"/.test(html)).toBe(true)
    expect(startView('/sounds')).toEqual(SOUNDS)
    expect(startView('/media')).toEqual(TEMP)
  })
})

describe("the bar's speech mode", () => {
  const all = [...MODELS, SPEECH]
  const character8 = { id: 'chars/Character 8.png', w: 40, h: 30 }
  const OK = { linkOn: true, engineOffline: false, model: SPEECH, prompt: 'Stay right there!', refCount: 1, uploading: 0, waiting: 0,
    draft: { references: [character8], advancedByModel: {} } }

  it('is picked in the image pulldown, keeps its own one box, and says Generate line', () => {
    expect(sheetModels(all, 'image').map(m => m.id)).toContain(SPEECH.id)
    expect(sheetModels(all, 'video').map(m => m.id)).not.toContain(SPEECH.id)
    expect(sheetModel(SPEECH, 'image')).toBe(SPEECH)
    expect(generateLabel(4, false, true)).toBe('Generate line')
  })

  it('blocks a press without one character from Characters in box 1', () => {
    expect(blockingReason(OK)).toBeNull()
    expect(blockingReason({ ...OK, refCount: 0, draft: { references: [], advancedByModel: {} } })).toBe(NO_SPEAKER_TEXT)
    expect(blockingReason({ ...OK, draft: { references: [{ ...character8, id: 'out/2026-10-17/a.png' }], advancedByModel: {} } })).toBe(NO_SPEAKER_TEXT)
    expect(blockingReason({ ...OK, refCount: 2, draft: { references: [character8, { ...character8, id: 'chars/Character 17.png' }], advancedByModel: {} } })).toBe(ONE_SPEAKER_TEXT)
  })

  it('sends the line, the character and no LoRAs', () => {
    const d = { ...EMPTY_DRAFT, model: SPEECH.id, references: [character8], lorasByModel: { [SPEECH.id]: [{ id: 'x/y.safetensors', strength: 1 }] } }
    const job = buildJob(d, SPEECH, 'Stay right there!')
    expect([job.model, job.mode, job.prompt, job.references, job.loras]).toEqual([SPEECH.id, 'refs', 'Stay right there!', ['chars/Character 8.png'], []])
  })
})
