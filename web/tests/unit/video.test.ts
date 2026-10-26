// A video model on the Generate Image screen: the size menu's tiers, seconds ↔ frames on the engine's lattice, the
// job it sends and the job line when its clip is done.
import { describe, expect, it } from 'vitest'
import { EMPTY_DRAFT, isDefault, resetAdvanced, withAdvanced } from '../../src/modules/generate-image/edits'
import { buildJob } from '../../src/modules/generate-image/job'
import { doneLine, planLine, runningText, verdictOf } from '../../src/modules/generate-image/run/jobs'
import type { Draft, Model, VideoFacts } from '../../src/modules/generate-image/types'
import { encoderOf, encoderOptions, framesOf, secondsOf, sizeValue, snapFrames, tierOf, tierOptions, tierSize, toFrames } from '../../src/modules/generate-image/video'
import { job, summary } from '../e2e/fixtures/data'

const FACTS: VideoFacts = {
  fps: 24, frames: { min: 124, step: 17, max: 345, default: 124 }, steps: 20,
  tiers: [
    { name: '540p', sizes: { '16:9': [960, 544], '9:16': [544, 960], '1:1': [736, 736] } },
    { name: '720p', sizes: { '16:9': [1280, 704], '9:16': [704, 1280], '1:1': [960, 960] } },
    { name: '1080p', sizes: { '16:9': [1920, 1088], '9:16': [1088, 1920], '1:1': [1440, 1440] } },
  ],
}
const H3: Model = { id: 'minimax_h3', label: 'MiniMax H3', family: 'MiniMax', modes: ['new'], refCap: 0, defaults: { steps: 20, guidance: null },
  guidanceKey: null, kind: 'video', video: FACTS }
const TWO: VideoFacts = { ...FACTS, tiers: FACTS.tiers.slice(0, 2) }

describe('tiers', () => {
  it('the megapixels value picks the tier: ≤1 the first, 1.5 and 2 the second, 4 the third', () => {
    expect([0.5, 1, 1.5, 2, 4].map(mp => tierOf(FACTS, mp).name)).toEqual(['540p', '540p', '720p', '720p', '1080p'])
  })

  it('4 takes the last tier when only two are offered; the menu lists the offered tiers with values 1, 2, 4', () => {
    expect(tierOf(TWO, 4).name).toBe('720p')
    expect(tierOptions(FACTS)).toEqual([{ value: '1', name: '540p' }, { value: '2', name: '720p' }, { value: '4', name: '1080p' }])
    expect(tierOptions(TWO).map(o => o.value)).toEqual(['1', '2'])
    expect([1, 1.5, 2, 4].map(mp => sizeValue(TWO, mp))).toEqual(['1', '2', '2', '2'])
    expect([1, 1.5, 2, 4].map(mp => sizeValue(FACTS, mp))).toEqual(['1', '2', '2', '4'])
  })

  it('the size is the tier\'s own for the aspect; Auto is square; a missing aspect takes the nearest shape', () => {
    expect(tierSize(FACTS, 1, '16:9')).toEqual({ width: 960, height: 544 })
    expect(tierSize(FACTS, 2, '9:16')).toEqual({ width: 704, height: 1280 })
    expect(tierSize(FACTS, 1, 'auto')).toEqual({ width: 736, height: 736 })
    expect(tierSize(FACTS, 1, '3:2')).toEqual({ width: 960, height: 544 })
    expect(tierSize(FACTS, 4, '2:3')).toEqual({ width: 1088, height: 1920 })
  })
})

describe('seconds and frames', () => {
  it('snaps up to the lattice and stays inside min..max', () => {
    expect([1, 124, 125, 141, 142, 300, 345, 400].map(f => snapFrames(FACTS, f))).toEqual([124, 124, 141, 141, 158, 311, 345, 345])
  })

  it('seconds become frames by fps, snapped up; frames read back as seconds to one decimal', () => {
    expect([1, 5, 5.2, 6, 10, 14, 30].map(s => toFrames(FACTS, s))).toEqual([124, 124, 124, 158, 243, 345, 345])
    expect([124, 158, 243, 345].map(f => secondsOf(FACTS, f))).toEqual([5.2, 6.6, 10.1, 14.4])
  })

  it('the model\'s default frames until the draft sets them; a set value counts against the defaults', () => {
    const d: Draft = { ...EMPTY_DRAFT, model: H3.id }
    expect(framesOf(d, H3)).toBe(124)
    const set = withAdvanced(d, H3, { frames: 243 })
    expect(framesOf(set, H3)).toBe(243)
    expect(isDefault(set.advancedByModel[H3.id]!, H3)).toBe(false)
    expect(isDefault(withAdvanced(d, H3, { frames: 124 }).advancedByModel[H3.id]!, H3)).toBe(true)
  })
})

describe('the job for a video model', () => {
  const d: Draft = { ...EMPTY_DRAFT, model: H3.id, draft: 'A lighthouse at dusk', aspect: '16:9', size: 1.5, images: 4,
    advancedByModel: { [H3.id]: { steps: 20, guidance: null, seed: { mode: 'random' }, frames: 158 } } }

  it('one clip at the tier\'s size with its frames; no guidance, no references', () => {
    const j = buildJob({ ...d, references: [{ id: 'out/a.png', w: 1, h: 1 }] }, H3)
    expect(j).toMatchObject({ model: 'minimax_h3', mode: 'new', width: 1280, height: 704, images: 1, steps: 20, guidance: null, frames: 158 })
    expect('references' in j).toBe(false)
  })

  it('an image model\'s job carries no frames', () => {
    const flux: Model = { ...H3, id: 'flux', kind: 'image', video: null, modes: ['new', 'refs'], refCap: 3 }
    expect('frames' in buildJob({ ...d, model: 'flux' }, flux)).toBe(false)
  })
})

describe('the job line', () => {
  it('a finished clip says "clip", in seconds under a minute, else minutes', () => {
    const clip = job('j1', { state: 'done', outputs: ['clips/2026-10-13/120000.mp4'], summary: summary('minimax_h3', [7], { kind: 'clip', frames: 124, seconds: 5.2 }) })
    expect(doneLine(clip, 42)).toBe('Done · clip in 42 s')
    expect(doneLine(clip, 250)).toBe('Done · clip in 4 min')
    const pics = job('j2', { state: 'done', outputs: ['a', 'b'], summary: summary('flux2_klein_9b', [1, 2]) })
    expect(doneLine(pics, 38)).toBe('Done · 2 images in 38 s')
  })
  it('the newest finished line\'s verdict from the words judge shows, else nothing', () => {
    const older = job('j3', { state: 'done', created: 1, notes: { verdict: 'Heard 71% of the words' } })
    const newer = job('j4', { state: 'done', created: 2, notes: { verdict: 'Heard 95% of the words' } })
    const other = job('j5', { state: 'done', created: 3, tool: 'sequence', notes: { verdict: 'x' } })
    expect(verdictOf([older, newer, other], 'generate-image')).toBe('Heard 95% of the words')
    expect(verdictOf([job('j6', { state: 'done' })], 'generate-image')).toBeNull()
  })

  it('says the take is being checked while the judges run, not 100 %', () => {
    const checking = job('j11', { state: 'running', progress: { phase: 'checking', index: 1, count: 1, step: 0, steps: 0, pct: 100, eta_s: null, text: 'Checking the take…' } })
    expect(runningText(checking)).toEqual({ left: 'Checking the take…', right: '', value: null })
  })

  it('shows the Director\'s planning line as it is, with no bar until the render', () => {
    const planning = job('j12', { state: 'running', progress: { phase: 'planning', index: 0, count: 0, step: 0, steps: 0, pct: 0, eta_s: null, text: 'Planning · ask 1 of 3 · qwen3.5:9b' } })
    expect(runningText(planning)).toEqual({ left: 'Planning · ask 1 of 3 · qwen3.5:9b', right: '', value: null })
  })

  it('lists the windows the engine planned as the running job\'s tooltip', () => {
    const planned = job('j7', { state: 'running', notes: { plan: { windows: [{ seconds: 5.17 }, { seconds: 5.17 }, { seconds: 4.5 }] } } })
    expect(planLine(planned)).toBe('3 windows: 5.2 s, 5.2 s, 4.5 s')
    expect(planLine(job('j8', { state: 'running', notes: { plan: { windows: [{ seconds: 5 }] } } }))).toBe('1 window: 5 s')
    expect(planLine(job('j9', { state: 'running' }))).toBeNull()
    expect(planLine(job('j10', { state: 'running', notes: { plan: { windows: [] } } }))).toBeNull()
  })
})

describe('the text encoder of a video model', () => {
  const v: VideoFacts = { ...FACTS, text_encoders: ['nvfp4_awq', 'gguf_q2_k', 'int8'], text_encoder_default: 'nvfp4_awq',
    text_encoder_names: { nvfp4_awq: 'NVFP4 AWQ (Recommended)', gguf_q2_k: 'GGUF Q2_K (Lowest RAM)' }, text_encoders_found: ['gguf_q2_k'] }
  const m: Model = { ...H3, video: v }
  const d = (text_encoder?: string): Draft => withAdvanced(EMPTY_DRAFT, m, text_encoder === undefined ? {} : { text_encoder })

  it('is the saved variant the model lists, else the default', () => {
    expect(encoderOf(d(), m)).toBe('nvfp4_awq')
    expect(encoderOf(d('int8'), m)).toBe('int8')
    expect(encoderOf(d('gone'), m)).toBe('nvfp4_awq')
  })

  it('lives on the LoRA sheet: it never shows the card\'s Reset, and Reset keeps it while steps/guidance/seed/frames go back', () => {
    expect(isDefault(d('int8').advancedByModel[m.id]!, m)).toBe(true)
    const set = withAdvanced(d('int8'), m, { steps: 40, seed: { mode: 'fixed', value: 7 }, frames: 243 })
    expect(resetAdvanced(set, m).advancedByModel[m.id]).toEqual({ steps: 20, guidance: null, seed: { mode: 'random' }, text_encoder: 'int8' })
    expect(m.id in resetAdvanced(withAdvanced(EMPTY_DRAFT, m, { steps: 40 }), m).advancedByModel).toBe(false)
  })

  it('lists the engine\'s names; a variant whose file is missing says so, unless the engine could not tell', () => {
    expect(encoderOptions(v)).toEqual([{ value: 'nvfp4_awq', label: 'NVFP4 AWQ (Recommended) · not found' },
      { value: 'gguf_q2_k', label: 'GGUF Q2_K (Lowest RAM)' }, { value: 'int8', label: 'int8 · not found' }])
    expect(encoderOptions({ ...v, text_encoders_found: null }).map(o => o.label)).toEqual(['NVFP4 AWQ (Recommended)', 'GGUF Q2_K (Lowest RAM)', 'int8'])
    expect(encoderOptions(FACTS)).toEqual([])
  })
})
