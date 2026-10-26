// Stage 6, continue a clip: the model facts, the step's length, the job, the refusals, the hook, the greyed menus and
// the clip box, the Seconds row, and the Clips section's days (flat: no group folders).
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { blockingReason, type BlockInput } from '../../src/modules/generate-image/blocking'
import GenerateCard from '../../src/modules/generate-image/Card'
import { planDelivery } from '../../src/modules/generate-image/delivery'
import { draft } from '../../src/modules/generate-image/draft'
import { EMPTY_DRAFT } from '../../src/modules/generate-image/edits'
import { buildJob } from '../../src/modules/generate-image/job'
import manifest from '../../src/modules/generate-image/manifest'
import { modelList } from '../../src/modules/generate-image/modelList'
import { AspectMenu, SizeMenu } from '../../src/modules/generate-image/run/Canvas'
import { Slots } from '../../src/modules/generate-image/run/Slots'
import type { Draft, Model, Slot } from '../../src/modules/generate-image/types'
import { besideClip, boxLabel, clipInBox, continuesOf, stemOf, stepMax, stepSeconds } from '../../src/modules/generate-image/video'
import { pictures } from '../../src/lib/protocol'
import { CLIPS, clips, dragged, itemsOf, norm } from '../../src/screens/media/media'
import { continueLabel } from '../../src/modules/generate-image/run/jobs'
import { MODELS, job, summary } from '../e2e/fixtures/data'

const H3 = MODELS.find(m => m.id === 'minimax_h3')!
const OMNI = MODELS.find(m => m.id === 'minimax_h3_ref2va')!
const FLUX = MODELS.find(m => m.id === 'flux2_klein_9b')!
const CLIP: Slot = { id: 'clips/2026-10-13/101500-123.mp4', w: 960, h: 544, kind: 'clip', seconds: 5.17 }
const D: Draft = { ...EMPTY_DRAFT, model: H3.id, draft: 'The same shot continues.', aspect: '9:16', size: 2, references: [CLIP] }
const at = (frames: number): Draft => ({ ...D, advancedByModel: { [H3.id]: { steps: 20, guidance: null, seed: { mode: 'random' }, frames } } })
const block = (model: Model, d: Draft): string | null => blockingReason({ linkOn: true, engineOffline: false, model, prompt: d.draft,
  refCount: d.references.length, uploading: 0, waiting: 0, draft: d } satisfies BlockInput)

afterEach(() => { vi.unstubAllGlobals(); draft.set(EMPTY_DRAFT); modelList.set(null) })

describe('continue facts', () => {
  it('a model continues when the catalog says so with its overlap; the longest step is max − overlap + 1 frames', () => {
    expect([H3, OMNI, FLUX, null].map(continuesOf)).toEqual([true, false, false, false])
    expect(continuesOf({ ...H3, video: { ...H3.video!, overlap: null } })).toBe(false)
    expect(stepMax(H3.video!)).toBe(328)
    const upstream = { ...H3.video!, frames: { min: 107, step: 17, max: 362, default: 124 }, overlap: 18 }
    expect(stepMax({ ...upstream, window_max: 481 })).toBe(362) // the step is at most the frame maximum
    expect(stepMax({ ...upstream, window_max: 300 })).toBe(283)
    expect([124, 328].map(f => stepSeconds(H3.video!, f))).toEqual([5.1, 13.6])
  })

  it('box 1 holds a clip only when it says so; a stem is its file name', () => {
    expect(clipInBox(D)).toBe(CLIP)
    expect(clipInBox({ references: [{ id: 'out/a.png', w: 1, h: 1 }, CLIP] })).toBeNull()
    expect(stemOf(CLIP.id)).toBe('101500-123')
  })
})

describe('the job and its refusals', () => {
  it('a clip in box 1: the clip\'s size, refs, the clip id alone, the step\'s frames', () => {
    expect(buildJob(at(141), H3)).toMatchObject({ model: H3.id, mode: 'refs', width: 960, height: 544, images: 1, frames: 141, references: [CLIP.id] })
  })

  it('a model that cannot continue, a filled box 2, a clip past box 1, a step over the longest: one line each', () => {
    expect(block(H3, D)).toBeNull()
    expect(block(OMNI, D)).toBe('H3 Omni — Pruned cannot continue a clip')
    expect(block(FLUX, D)).toBe('Flux 2 Klein 9B cannot continue a clip')
    expect(block(H3, { ...D, references: [CLIP, { id: 'out/a.png', w: 1, h: 1 }] })).toBe('A continued clip takes only box 1')
    expect(block(H3, { ...D, references: [{ id: 'out/a.png', w: 1, h: 1 }, CLIP] })).toBe('A continued clip takes only box 1')
    expect(block(H3, at(328))).toBeNull()
    expect(block(H3, at(345))).toBe('Each step is at most 13.7 s')
  })

  it('a picture sent while box 1 holds a clip is refused with the same line', () => {
    expect(planDelivery(D, H3, 'reference', ['out/a.png'])).toEqual({ targets: [], refused: [{ item: 'out/a.png', reason: 'clip', text: 'A continued clip takes only box 1' }] })
  })
})

describe('the continueClip hook', () => {
  it('posts the id to the Continue route: null when placed, else the hub\'s line', async () => {
    const calls: [string, RequestInit][] = []
    const answer = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
    vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
      calls.push([url, init])
      return calls.length === 1 ? answer(200, { id: CLIP.id, model: H3.id, label: H3.label }) : answer(400, { code: 'invalid', field: 'id', text: 'The clip to continue is gone' })
    })
    expect(await manifest.continueClip(CLIP.id)).toBeNull()
    expect(await manifest.continueClip('clips/x.mp4')).toBe('The clip to continue is gone')
    expect(calls.map(([u, i]) => [u, i.method, i.body])).toEqual([
      ['/api/generate-image/continue', 'POST', JSON.stringify({ id: CLIP.id })], ['/api/generate-image/continue', 'POST', '{"id":"clips/x.mp4"}']])
  })
})

describe('the screen with a clip in box 1', () => {
  const html = (el: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(el)

  it('Size and Aspect are greyed with the clip\'s size; without a clip they open', () => {
    draft.set(D)
    for (const M of [SizeMenu, AspectMenu]) expect(html(createElement(M, { model: H3 }))).toMatch(/aria-disabled="true" title="The clip&#x27;s size, 960×544"/)
    draft.set({ ...D, references: [] })
    for (const M of [SizeMenu, AspectMenu]) expect(html(createElement(M, { model: H3 }))).not.toMatch(/aria-disabled/)
  })

  it('box 1 shows the clip\'s still with "Continues <stem>" (no player); boxes 2–3 are shut with one line', () => {
    draft.set(D)
    const out = html(createElement(Slots, { model: H3 }))
    expect(out).toMatch(/title="Continues 101500-123"[^>]*><span aria-label="Continues 101500-123" data-clip-still="\/files\/clips\/2026-10-13\/101500-123\.mp4"/)
    expect(out).not.toMatch(/<video/)
    expect(out.match(/title="A continued clip takes only box 1"/g)).toHaveLength(2)
  })

  it('Settings → Seconds shows the step as "+5.1 s" and caps the box at the longest step', () => {
    modelList.set(MODELS)
    draft.set(D)
    const out = html(createElement(GenerateCard, { changed: () => {} }))
    expect(out).toMatch(/max="13.7"/)
    expect(out).toContain('>+5.1 s</span>')
    draft.set({ ...D, references: [] })
    expect(html(createElement(GenerateCard, { changed: () => {} }))).not.toContain('+5.1 s')
  })
})

describe('the Clips section: one flat list, newest first', () => {
  const raw = (id: string, createdAt: number) => ({ id, kind: 'clip', url: `/files/${id}`, thumb: null, w: 960, h: 544, createdAt, group: '', fav: false })
  const items = [raw('clips/2026-10-13/120000-000.mp4', 4), raw('clips/2026-10-13/102000-000.mp4', 3),
    raw('clips/2026-10-13/101500-123.mp4', 1), raw('clips/2026-10-12/090000-000.mp4', 0)].map(norm)

  it('every clip of every day under Clips, newest first, as the hub lists them; a day is no group', () => {
    clips.set(m => ({ ...m, items }))
    expect(itemsOf(CLIPS).map(i => i.createdAt)).toEqual([4, 3, 1, 0])
    expect(items.map(i => i.group)).toEqual(['', '', '', ''])
  })
})

describe('what a tile carries when dragged', () => {
  const raw = (id: string, extra: object) => norm({ id, url: `/files/${id}`, thumb: null, w: 960, h: 544, createdAt: 1, group: '', fav: false, ...extra })

  it('a clip carries its kind, length, frames and fps; a picture only its address and size; none carried unknown', () => {
    expect(dragged(raw(CLIP.id, { kind: 'clip', seconds: 5.17 }))).toEqual({ id: CLIP.id, w: 960, h: 544, kind: 'clip', seconds: 5.17 })
    expect(dragged(raw(CLIP.id, { kind: 'clip', seconds: 5.17, frames: 124, fps: 24 })))
      .toEqual({ id: CLIP.id, w: 960, h: 544, kind: 'clip', seconds: 5.17, frames: 124, fps: 24 })
    expect(dragged(raw(CLIP.id, { kind: 'clip', seconds: 5.17, frames: null, fps: null }))).toEqual({ id: CLIP.id, w: 960, h: 544, kind: 'clip', seconds: 5.17 })
    expect(dragged(raw(CLIP.id, { kind: 'clip', seconds: null }))).toEqual({ id: CLIP.id, w: 960, h: 544, kind: 'clip' })
    expect(dragged(raw('out/a.png', {}))).toEqual({ id: 'out/a.png', w: 960, h: 544 })
  })

  it('only pictures are left for folders, favorites and characters', () => {
    expect(pictures([dragged(raw(CLIP.id, { kind: 'clip' })), dragged(raw('out/a.png', {}))]).map(d => d.id)).toEqual(['out/a.png'])
  })
})

describe('a continue job in the queue line', () => {
  it('reads the step and the scene; any other job has no label', () => {
    const cont = job('j1', { state: 'running', summary: summary('minimax_h3', [1], { kind: 'clip', mode: 'continue', seconds: 5.04, scene_seconds: 10.08 }) })
    expect(continueLabel(cont)).toBe('Continue · +5 s · scene 10.1 s')
    expect(continueLabel(job('j2', { summary: summary('flux2_klein_9b', [1]) }))).toBeNull()
  })
})

describe('identities beside a clip in box 1', () => {
  const html = (el: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(el)
  const GO: Model = { ...OMNI, video: { ...OMNI.video!, continues: true, overlap: 18 } }
  const CHARACTER_7: Slot = { id: 'chars/Character 7.png', w: 600, h: 900 }
  const on = (d: Draft): Draft => ({ ...d, model: GO.id })

  it('on an identity model that continues, boxes 2–3 are offered as "Identity 1", "Identity 2"', () => {
    expect(besideClip(GO)).toBe(2)
    expect([H3, OMNI, FLUX, null].map(besideClip)).toEqual([0, 0, 0, 0])
    expect([1, 2].map(i => boxLabel(GO, i, true))).toEqual(['Identity 1', 'Identity 2'])
    expect(boxLabel(H3, 1, true)).not.toMatch(/Identity/)
    draft.set(on(D))
    const out = html(createElement(Slots, { model: GO }))
    expect(out).not.toMatch(/title="A continued clip takes only box 1"/)
    expect(out).toMatch(/aria-label="Identity 1, empty"/)
    expect(out).toMatch(/aria-label="Identity 2, empty"/)
  })

  it('any other model: boxes 2–3 stay shut beside the clip', () => {
    draft.set(D)
    expect(html(createElement(Slots, { model: H3 })).match(/title="A continued clip takes only box 1"/g)).toHaveLength(2)
  })

  it('Generate is blocked only past the boxes the hub takes; delivery fills boxes 2–3, never box 1', () => {
    expect(block(GO, on({ ...D, references: [CLIP, CHARACTER_7] }))).toBeNull()
    expect(block(GO, on({ ...D, references: [CLIP, CHARACTER_7, CHARACTER_7] }))).toBeNull()
    expect(block(H3, { ...D, references: [CLIP, CHARACTER_7] })).toBe('A continued clip takes only box 1')
    expect(planDelivery(on(D), GO, 'reference', ['chars/Character 7.png']).targets).toEqual([{ item: 'chars/Character 7.png', socket: 'reference_2', index: 1 }])
    expect(planDelivery(on(D), GO, 'reference_1', ['chars/Character 7.png']).refused[0]?.reason).toBe('clip')
    expect(planDelivery(D, H3, 'reference', ['chars/Character 7.png']).refused[0]?.reason).toBe('clip')
  })
})
