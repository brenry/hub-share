// The Video box (a clip from Media → Clips as the reference video), only on a model that takes one; the
// press sends it; Media's Put in Video through the hub's delivery; a continue refuses it.
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it } from 'vitest'
import { blockingReason, VIDEO_CONTINUE_TEXT } from '../../src/modules/generate-image/blocking'
import { declaration, planDelivery } from '../../src/modules/generate-image/delivery'
import { draft } from '../../src/modules/generate-image/draft'
import { EMPTY_DRAFT, normalizeDraft } from '../../src/modules/generate-image/edits'
import { buildJob } from '../../src/modules/generate-image/job'
import { placeVideo, VideoBox } from '../../src/modules/generate-image/run/VideoBox'
import type { Draft, Model } from '../../src/modules/generate-image/types'
import type { Focus } from '../../src/lib/protocol'
import { deliveryText, videoSend } from '../../src/screens/media/send'
import { MODELS } from '../e2e/fixtures/data'

const H3 = MODELS.find(m => m.id === 'minimax_h3')!
const OMNI = MODELS.find(m => m.id === 'minimax_h3_ref2va')!
const REF: Model = { ...OMNI, video: { ...OMNI.video!, reference_video: 'V-U', reference_video_seconds: 362 / 24 } }
const SHOW = { id: 'clips/2026-10-17/clip1.mp4', seconds: 12 }
const D: Draft = { ...EMPTY_DRAFT, model: REF.id, draft: '<Video 1> is the clip.', references: [{ id: 'chars/Character 7.png', w: 600, h: 900 }] }
const html = (model: Model) => renderToStaticMarkup(createElement(VideoBox, { model }))

afterEach(() => draft.set(EMPTY_DRAFT))

describe('the Video box', () => {
  it('shows only on a model that takes a reference video: empty, then the clip with its length', () => {
    draft.set(D)
    expect(html(H3)).toBe('')
    expect(html(OMNI)).toBe('')
    expect(html(REF)).toMatch(/aria-label="Video, empty" data-socket="video"/)
    draft.set({ ...D, video: SHOW })
    expect(html(REF)).toMatch(/data-video="clips\/2026-10-17\/clip1.mp4"/)
    expect(html(REF)).toContain('12.0 s')
  })

  it('a clip under 2 s, or of no known length, is not placed', () => {
    draft.set(D)
    expect(placeVideo('clips/x/short.mp4', 1.5)).toBe(false)
    expect(placeVideo('clips/x/odd.mp4', undefined)).toBe(false)
    expect(draft.get().video).toBeNull()
    expect(placeVideo(SHOW.id, 12)).toBe(true)
    expect(draft.get().video).toEqual(SHOW)
  })

  it('the press sends it to that model only; a load keeps it', () => {
    expect(buildJob({ ...D, video: SHOW }, REF).video).toBe(SHOW.id)
    expect(buildJob({ ...D, video: SHOW }, OMNI).video).toBeUndefined()
    expect(buildJob(D, REF).video).toBeUndefined()
    expect(normalizeDraft({ video: SHOW }).video).toEqual(SHOW)
    expect(normalizeDraft({ video: { id: 1 } }).video).toBeNull()
  })

  it('a continued clip with a clip in the Video box is blocked in the hub\'s words', () => {
    const clip = { id: 'clips/2026-10-17/a.mp4', w: 960, h: 544, kind: 'clip' as const, seconds: 5 }
    const go: Model = { ...REF, video: { ...REF.video!, continues: true, overlap: 18 } }
    const d = { ...D, references: [clip], video: SHOW }
    expect(blockingReason({ linkOn: true, engineOffline: false, model: go, prompt: d.draft, refCount: 1, uploading: 0, waiting: 0, draft: d })).toBe(VIDEO_CONTINUE_TEXT)
  })
})

describe('Put in Video', () => {
  it('the screen declares a video socket on that model; one clip goes in, never beside a continued clip', () => {
    expect(declaration(D, REF).sockets.find(s => s.id === 'video')).toMatchObject({ accepts: ['video'], filled: false })
    expect(declaration(D, OMNI).sockets.find(s => s.id === 'video')).toBeUndefined()
    expect(planDelivery(D, REF, 'video', [SHOW.id, 'clips/b.mp4'])).toEqual({
      targets: [{ item: SHOW.id, socket: 'video', index: -1 }], refused: [{ item: 'clips/b.mp4', reason: 'one_only', text: 'one video at a time' }] })
    expect(planDelivery(D, OMNI, 'video', [SHOW.id]).refused[0]?.reason).toBe('missing')
  })

  it('Media\'s line and toast', () => {
    const focus = { tool: 'generate-image', label: 'Generate Image', mode: 'refs', primary: 'reference', sockets: declaration(D, REF).sockets } as Focus
    expect(videoSend(true, focus, null, 1)).toEqual({ label: 'Put in Video', off: null })
    expect(videoSend(true, { ...focus, sockets: [] } as Focus, null, 1).off).toBe('This model takes no reference video')
    expect(videoSend(true, focus, null, 2).off).toBe('One clip at a time')
    expect(deliveryText({ status: 'done', toolLabel: 'Generate Image', placed: [{ item: SHOW.id, socket: 'video' }], refused: [] } as never)).toBe('Added to Generate Image · Video')
  })
})
