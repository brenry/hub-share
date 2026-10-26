// The Storyboard tab: the selected take kept across a reload, one press one job, a queued job's end reaching the
// screen, `rendering` from `/script`, Track drawn as a button, Track's progress on the bar, the take player's gain
// and a failed take with no file.
import { readFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'
import type { Job, JobSummary, ToolInfo } from '../../src/lib/protocol'
import { gainOf, progressText, trackProgress } from '../../src/modules/director/timeline'
import { FakeHub } from './fixtures/controller'
import { job } from './fixtures/data'
import { SEQUENCE_TOOL, mockSequence, seqState } from './fixtures/sequence'
import { open } from './helpers'

const example: unknown = JSON.parse(readFileSync(new URL('../../../tests/fixtures/script-1.json', import.meta.url), 'utf8'))
const DIRECTOR_TOOL: ToolInfo = { id: 'director', title: 'Storyboard', tab: { label: 'Storyboard', order: 30 }, sockets: [] }
const LOCK = { locked: true, at: '2026-10-20T09:15:02+02:00' }
const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

type Take = Record<string, unknown>
const none = (id: string): Take => ({ state: 'none', file: `Script 1/${id}-1.wav` })
const MEASURED = { speech_start_ms: 120, speech_end_ms: 1940, length_ms: 2100, lufs: -23.4, true_peak_dbtp: -3.1, gain_db: 0.4 }
const ok = (id: string, gain_db: number | null = 0.4): Take => ({
  state: 'ok', file: `Script 1/${id}-1.wav`, url: `/files/sounds/Script 1/${id}-1.wav`, measured: { ...MEASURED, gain_db },
  judge: { heard: 1, first_miss_ms: null, extra_speech: 0, verdict: 'ok', why: null },
})
const TIMES: Record<string, [string, number, number, string]> = {
  c1: ['cue', 0, 2500, 'music'], c2: ['cue', 2500, 3900, 'reaction'], l1: ['line', 4000, 7642, 'Character 1'],
  l2: ['line', 9000, 12642, 'Character 2'], c3: ['cue', 13000, 13800, 'effect'], l3: ['line', 17500, 21911, 'Character 1'],
  c4: ['cue', 22000, 23500, 'reaction'],
}
const audioOf = (takes: Record<string, Take>) => Object.entries(TIMES).map(([id, [kind, start, end, who]]) => ({
  id, kind, shot: '1.1', start_ms: start, end_ms: end, who, text: `${who}: words`, problem: null, sample: null,
  seconds: 8, hash: '3f9c0a1b77e2d415', take: takes[id] ?? none(id),
}))
const ALL_OK = Object.fromEntries(Object.keys(TIMES).map(id => [id, ok(id)]))

type State = { takes: Record<string, Take>; rendering: string | null; calls: string[]; reads: number }
const state = (over: Partial<State> = {}): State => ({ takes: {}, rendering: null, calls: [], reads: 0, ...over })

async function scripts(page: Page, st: State): Promise<FakeHub> {
  await page.setViewportSize({ width: 1600, height: 900 })
  await page.route(/\/api\/director\//, route => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace('/api/director', '')
    const row = (name: string, changed: number) => ({ name, seconds: 24, scenes: 1, shots: 3, lines: 3, changed, problem: null })
    if (p === '/scripts') return json(route, { scripts: [row('Script 1', 2), row('Other', 1)] })
    if (p === '/script' && url.searchParams.get('name') === 'Other') {
      return json(route, { name: 'Other', seconds: 24, problem: null, script: example, pictures: {}, unpictured: [], audio: null, rendering: null })
    }
    if (p === '/script') {
      st.reads += 1
      return json(route, { name: 'Script 1', seconds: 24, problem: null, script: { ...(example as object), lock: LOCK }, pictures: {},
        unpictured: [], audio: audioOf(st.takes), rendering: st.rendering })
    }
    if (p === '/track') {
      st.calls.push(`${req.method()} /track ${(req.postDataJSON() as { name: string }).name}`)
      st.takes = { l1: { state: 'rendering', file: 'Script 1/l1-1.wav' }, l2: { state: 'rendering', file: 'Script 1/l2-1.wav' }, l3: { state: 'rendering', file: 'Script 1/l3-1.wav' } }
      return json(route, { job: 'j1', lines: 3 })
    }
    return json(route, {})
  })
  await mockSequence(page, seqState())
  const base = new FakeHub()
  const hub = new FakeHub({ tools: [...base.tools, SEQUENCE_TOOL, DIRECTOR_TOOL] })
  await open(page, '/', hub)
  await page.getByRole('tab', { name: 'Storyboard' }).click()
  await expect(page.locator('[data-region="timeline"]')).toBeVisible()
  return hub
}

/** `director.changed` of `name`, then the next `/script` read of Script 1 landed and drawn. */
async function changed(page: Page, hub: FakeHub, st: State, name = 'Script 1'): Promise<void> {
  const before = st.reads
  hub.broadcast('director.changed', { name, revision: before + 10 }, 'workspace')
  if (name === 'Script 1') await expect.poll(() => st.reads).toBeGreaterThan(before)
  await page.waitForTimeout(300)
}

const trackBtn = (page: Page) => page.locator('[data-region="script-track"]')
const box = (page: Page, id: string) => page.locator(`[data-region="timeline"] [data-box="${id}"]`)
const takeLine = (page: Page) => page.locator('[data-region="take"]')
const player = (page: Page) => page.locator('[data-region="take-play"]')
const progressEl = (page: Page) => page.locator('[data-region="track-progress"]')
const speaking = (page: Page) => page.locator('[data-region="timeline"] [data-speaking]')

const NAMES = ['l1', 'l1 · take 2', 'l2', 'l2 · take 2', 'l3', 'l3 · take 2', 'l3 · take 3', 'c1', 'c2', 'c3', 'c4', 'room']
const card = (patch: Partial<Job>): Job => job('j1', {
  tool: 'director', kind: 'director.track', title: 'Track · Script 1', lane: 'jobs', state: 'running', position: null,
  summary: { step_names: NAMES } as unknown as JobSummary, ...patch,
})
const prog = (index: number, pct: number) => ({ phase: 'speech', index, count: 12, step: 0, steps: 0, pct, eta_s: null, text: '' })

test('a director.changed of the open script keeps the selected box, its take line and the same player', async ({ page }) => {
  const st = state({ takes: { l1: ok('l1') } })
  const hub = await scripts(page, st)
  await box(page, 'l1').click()
  await expect(player(page)).toHaveCount(1)
  await player(page).evaluate(el => { (el as unknown as { mark: number }).mark = 7 })
  await changed(page, hub, st)
  await expect(takeLine(page)).toHaveCount(1)
  expect(await player(page).evaluate(el => (el as unknown as { mark?: number }).mark)).toBe(7)
  await expect(box(page, 'l1')).toHaveAttribute('aria-pressed', 'true')
  await changed(page, hub, st, 'Other')
  await expect(page.locator('[data-region="scripts"]')).toContainText('Other')
  await expect(page.locator('[data-region="timeline"] [aria-pressed="true"]')).toHaveCount(0)
  await expect(takeLine(page)).toHaveCount(0)
})

test('two clicks before the reload lands post /track once; Track is off between', async ({ page }) => {
  const st = state()
  await scripts(page, st)
  await page.route(/\/api\/director\/script\?/, async route => { await new Promise(r => setTimeout(r, 600)); await route.fallback() })
  await trackBtn(page).click()
  await expect(trackBtn(page)).toHaveAttribute('aria-disabled', 'true')
  await trackBtn(page).click({ force: true })
  await page.waitForTimeout(1500)
  expect(st.calls).toEqual(['POST /track Script 1'])
  await expect(trackBtn(page)).toHaveAttribute('aria-disabled', 'true')
})

test('the takes back to none and director.changed: the boxes come back and Track presses again', async ({ page }) => {
  const st = state()
  const hub = await scripts(page, st)
  await trackBtn(page).click()
  await expect(box(page, 'l1')).toHaveAttribute('data-take', 'rendering')
  st.takes = {}
  await changed(page, hub, st)
  await expect(box(page, 'l1')).toHaveAttribute('data-take', 'none')
  await expect(trackBtn(page)).toHaveAttribute('aria-disabled', 'false')
  await trackBtn(page).click()
  await expect.poll(() => st.calls.length).toBe(2)
})

test('/script naming a Track job with every row ok: Track is off and a click posts nothing', async ({ page }) => {
  const st = state({ takes: ALL_OK, rendering: 'j9' })
  await scripts(page, st)
  await expect(trackBtn(page)).toHaveAttribute('aria-disabled', 'true')
  await trackBtn(page).click({ force: true })
  await page.waitForTimeout(300)
  expect(st.calls).toEqual([])
})

test('Track is drawn as the app button, a border and a raised face; off it still reads aria-disabled', async ({ page }) => {
  const st = state({ takes: ALL_OK })
  const hub = await scripts(page, st)
  const look = () => trackBtn(page).evaluate(el => {
    const cs = getComputedStyle(el)
    return { tag: el.tagName, border: parseFloat(cs.borderTopWidth), bg: cs.backgroundColor }
  })
  const on = await look()
  expect(on.tag).toBe('BUTTON')
  expect(on.border).toBeGreaterThan(0)
  expect(on.bg).not.toBe('rgba(0, 0, 0, 0)')
  st.rendering = 'j9'
  await changed(page, hub, st)
  await expect(trackBtn(page)).toHaveAttribute('aria-disabled', 'true')
  expect((await look()).border).toBeGreaterThan(0)
})

test('the running job shows takes done of all and the step, its box marked; queued its place; gone with the job', async ({ page }) => {
  const st = state({ takes: { l1: { state: 'rendering', file: 'Script 1/l1-1.wav' }, l2: { state: 'rendering', file: 'Script 1/l2-1.wav' } }, rendering: 'j1' })
  const hub = await scripts(page, st)
  hub.setJob(card({ progress: prog(4, 50), started: 1791561700 }))
  await expect(progressEl(page)).toHaveText('3 of 12 takes · l2 · take 2')
  await expect(progressEl(page).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '29')
  await expect(speaking(page)).toHaveCount(1)
  await expect(box(page, 'l2')).toHaveAttribute('data-speaking', 'true')
  await expect(box(page, 'l2')).toHaveAttribute('data-take', 'rendering')
  const btn = (await trackBtn(page).boundingBox())!
  expect((await progressEl(page).boundingBox())!.x).toBeGreaterThan(btn.x)
  hub.setJob(card({ state: 'queued', position: 2, progress: null }))
  await expect(progressEl(page)).toHaveText('queued (2)')
  await expect(speaking(page)).toHaveCount(0)
  hub.setJob(card({ progress: prog(4, 50) }))
  await expect(speaking(page)).toHaveCount(1)
  st.rendering = null
  st.takes = { l1: ok('l1'), l2: ok('l2') }
  await changed(page, hub, st)
  await expect(progressEl(page)).toHaveCount(0)
  await expect(speaking(page)).toHaveCount(0)
})

test('trackProgress and its words', () => {
  expect(trackProgress(null)).toBeNull()
  expect(trackProgress(card({ state: 'done' }))).toBeNull()
  const p = trackProgress(card({ progress: prog(4, 50) }))!
  expect(p).toMatchObject({ done: 3, count: 12, step: 'l2 · take 2', id: 'l2' })
  expect(progressText(p)).toBe('3 of 12 takes · l2 · take 2')
  expect(trackProgress(card({ progress: prog(12, 0) }))).toMatchObject({ step: 'room', id: null })
  expect(trackProgress(card({ progress: prog(1, 0) }))).toMatchObject({ id: 'l1', done: 0 })
  const loading = trackProgress(card({ progress: null }))!
  expect(loading).toMatchObject({ done: 0, count: 12, value: null, id: null })
  expect(progressText(loading)).toBe('0 of 12 takes')
  expect(progressText(trackProgress(card({ state: 'queued', position: 2 }))!)).toBe('queued (2)')
})

/** Records every media source and gain node the page makes. */
const RECORD = () => {
  const w = window as unknown as { sources: number; gains: GainNode[] }
  w.sources = 0
  w.gains = []
  const make = AudioContext.prototype.createMediaElementSource
  AudioContext.prototype.createMediaElementSource = function (this: AudioContext, el: HTMLMediaElement) { w.sources += 1; return make.call(this, el) }
  const gain = AudioContext.prototype.createGain
  AudioContext.prototype.createGain = function (this: AudioContext) { const g = gain.call(this); w.gains.push(g); return g }
}
const heard = (page: Page) => page.evaluate(() => {
  const w = window as unknown as { sources: number; gains: GainNode[] }
  return { sources: w.sources, gain: w.gains.at(-1)?.gain.value ?? null }
})
const playIt = (page: Page) => player(page).evaluate(el => { void (el as HTMLAudioElement).play().catch(() => undefined) })

test('the take plays through one gain node at its measured gain; a new gain reaches the same element', async ({ page }) => {
  await page.addInitScript(RECORD)
  const st = state({ takes: { l1: ok('l1', 6), l2: ok('l2', null) } })
  const hub = await scripts(page, st)
  await box(page, 'l1').click()
  await playIt(page)
  await expect.poll(async () => (await heard(page)).sources).toBe(1)
  expect((await heard(page)).gain).toBeCloseTo(1.995, 3)
  st.takes = { ...st.takes, l1: ok('l1', -6) }
  await changed(page, hub, st)
  await expect.poll(async () => (await heard(page)).gain ?? 0).toBeCloseTo(0.501, 3)
  expect((await heard(page)).sources).toBe(1)
  await box(page, 'l2').click()
  await playIt(page)
  await expect.poll(async () => (await heard(page)).sources).toBe(2)
  expect((await heard(page)).gain).toBe(1)
})

test('gainOf', () => {
  const t = (gain_db: unknown) => ({ state: 'ok', file: 'a.wav', measured: { gain_db } }) as Parameters<typeof gainOf>[0]
  expect(gainOf(t(6))).toBeCloseTo(1.995, 3)
  expect(gainOf(t(-6))).toBeCloseTo(0.501, 3)
  for (const g of [0, null, Number.NaN]) expect(gainOf(t(g))).toBe(1)
  expect(gainOf({ state: 'ok', file: 'a.wav' })).toBe(1)
})

test('a failed take with no file: the take line and the row read failed · <why>', async ({ page }) => {
  await scripts(page, state({ takes: { l3: { state: 'failed', why: 'The speech job failed' } } }))
  await box(page, 'l3').click()
  await expect(takeLine(page)).toHaveText('failed · The speech job failed')
  await expect(page.locator('[data-region="audio-script"] [data-audio="l3"]')).toContainText('failed · The speech job failed #3f9c0a1b77e2d415')
})
