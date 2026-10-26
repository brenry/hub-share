// The Storyboard tab, a locked script's bar shows `Track`, which posts `/track` and shows a refusal as it
// comes back, off while a take renders; each line box shows its take's state and measured length; a selected line box
// shows its take's line and a player in the bar; the Audio script panel shows `rendering` and `failed`.
import { readFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'
import type { ToolInfo } from '../../src/lib/protocol'
import { FakeHub } from './fixtures/controller'
import { SEQUENCE_TOOL, mockSequence, seqState } from './fixtures/sequence'
import { open } from './helpers'

const example: unknown = JSON.parse(readFileSync(new URL('../../../tests/fixtures/script-1.json', import.meta.url), 'utf8'))
const DIRECTOR_TOOL: ToolInfo = { id: 'director', title: 'Storyboard', tab: { label: 'Storyboard', order: 30 }, sockets: [] }
const LOCK = { locked: true, at: '2026-10-20T09:15:02+02:00' }
const NOTHING = 'nothing to render: every line has a take'

const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

type Take = Record<string, unknown>
const none = (id: string): Take => ({ state: 'none', file: `Script 1/${id}-1.wav` })
const MEASURED = { speech_start_ms: 120, speech_end_ms: 1940, length_ms: 2100, lufs: -23.4, true_peak_dbtp: -3.1, gain_db: 0.4 }
const ok = (id: string): Take => ({
  state: 'ok', file: `Script 1/${id}-1.wav`, url: `/files/sounds/Script 1/${id}-1.wav`, measured: MEASURED,
  judge: { heard: 1, first_miss_ms: null, extra_speech: 0, verdict: 'ok', why: null },
})
const WHY = 'extra speech after the words'
const flagged = (id: string): Take => ({
  state: 'flagged', file: `Script 1/${id}-1.wav`, why: WHY, url: `/files/sounds/Script 1/${id}-1.wav`,
  measured: { ...MEASURED, speech_end_ms: 3020, lufs: -33.6, gain_db: -1.2 },
  judge: { heard: 0.83, first_miss_ms: 900, extra_speech: 0.6, verdict: 'flagged', why: WHY },
})
const failed = (): Take => ({ state: 'failed', why: 'The speech job failed' })   // no take landed, no file

const TIMES: Record<string, [string, number, number, string]> = {
  c1: ['cue', 0, 2500, 'music'], c2: ['cue', 2500, 3900, 'reaction'], l1: ['line', 4000, 7642, 'Character 1'],
  l2: ['line', 9000, 12642, 'Character 2'], c3: ['cue', 13000, 13800, 'effect'], l3: ['line', 17500, 21911, 'Character 1'],
  c4: ['cue', 22000, 23500, 'reaction'],
}
/** The audio rows for the example, locked, with `takes` by id (the rest none). */
const audioOf = (takes: Record<string, Take>) => Object.entries(TIMES).map(([id, [kind, start, end, who]]) => ({
  id, kind, shot: '1.1', start_ms: start, end_ms: end, who, text: `${who}: words`, problem: null, sample: null,
  seconds: 8, hash: '3f9c0a1b77e2d415', take: takes[id] ?? none(id),
}))

type State = { locked: boolean; takes: Record<string, Take>; refuse: string | null; calls: string[] }

async function scripts(page: Page, st: State): Promise<FakeHub> {
  await page.setViewportSize({ width: 1600, height: 900 })
  await page.route(/\/api\/director\//, route => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace('/api/director', '')
    if (p === '/scripts') return json(route, { scripts: [{ name: 'Script 1', seconds: 24, scenes: 1, shots: 3, lines: 3, changed: 1, problem: null }] })
    if (p === '/script') {
      const script = st.locked ? { ...(example as object), lock: LOCK } : example
      return json(route, { name: 'Script 1', seconds: 24, problem: null, script, pictures: {}, unpictured: [], audio: st.locked ? audioOf(st.takes) : null })
    }
    if (p === '/track') {
      st.calls.push(`${req.method()} /track ${(req.postDataJSON() as { name: string }).name}`)
      if (st.refuse) return json(route, { code: 'invalid', text: st.refuse }, 400)
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

const state = (over: Partial<State> = {}): State => ({ locked: true, takes: {}, refuse: null, calls: [], ...over })
const trackBtn = (page: Page) => page.locator('[data-region="script-track"]')
const box = (page: Page, id: string) => page.locator(`[data-region="timeline"] [data-box="${id}"]`)
const audioRow = (page: Page, id: string) => page.locator(`[data-region="audio-script"] [data-audio="${id}"]`)
const takeLine = (page: Page) => page.locator('[data-region="take"]')

test('a locked script shows Track after the lock and its line boxes their take state', async ({ page }) => {
  await scripts(page, state())
  await expect(trackBtn(page)).toHaveText('Track')
  await expect(trackBtn(page)).toHaveAttribute('aria-disabled', 'false')
  const lock = (await page.locator('[data-region="script-locked"]').boundingBox())!
  expect((await trackBtn(page).boundingBox())!.x).toBeGreaterThan(lock.x)
  await expect(box(page, 'l1')).toHaveAttribute('data-take', 'none')
  await expect(box(page, 'l1')).toHaveText('Word word, word. Word word word word word word.')
})

test('an unlocked script shows no Track and no take mark', async ({ page }) => {
  await scripts(page, state({ locked: false }))
  await expect(page.locator('[data-region="script-play"]')).toBeVisible()
  await expect(trackBtn(page)).toHaveCount(0)
  await expect(page.locator('[data-region="timeline"] [data-take]')).toHaveCount(0)
  await box(page, 'l1').click()
  await expect(takeLine(page)).toHaveCount(0)
})

test('a press posts /track with the name; a refusal is shown as it comes back', async ({ page }) => {
  const st = state({ refuse: NOTHING })
  await scripts(page, st)
  await trackBtn(page).click()
  await expect(page.getByRole('status')).toContainText(NOTHING)
  expect(st.calls).toEqual(['POST /track Script 1'])
})

test('while takes render their boxes are marked rendering and Track is off', async ({ page }) => {
  const st = state()
  await scripts(page, st)
  await trackBtn(page).click()
  for (const id of ['l1', 'l2', 'l3']) await expect(box(page, id)).toHaveAttribute('data-take', 'rendering')
  await expect(trackBtn(page)).toHaveAttribute('aria-disabled', 'true')
  await expect(audioRow(page, 'l2')).toContainText('rendering #3f9c0a1b77e2d415')
  await box(page, 'l2').click()
  await expect(takeLine(page)).toHaveText('rendering')
  await expect(page.locator('[data-region="take-play"]')).toHaveCount(0)
  await trackBtn(page).click({ force: true })
  expect(st.calls).toEqual(['POST /track Script 1'])
})

test('after the job each line box shows its take and length; a click shows its line and a player', async ({ page }) => {
  const st = state()
  const hub = await scripts(page, st)
  st.takes = { l1: ok('l1'), l2: flagged('l2'), l3: failed() }
  hub.broadcast('director.changed', { name: 'Script 1', revision: 2 }, 'workspace')
  await expect(box(page, 'l1')).toHaveAttribute('data-take', 'ok')
  await expect(box(page, 'l2')).toHaveAttribute('data-take', 'flagged')
  await expect(box(page, 'l3')).toHaveAttribute('data-take', 'failed')
  await expect(box(page, 'l1')).toHaveText('Word word, word. Word word word word word word. · 1.8 s')
  await expect(box(page, 'l1')).toHaveAttribute('title', 'Word word, word. Word word word word word word. · 1.8 s · ok')
  await expect(box(page, 'l2')).toHaveText('Word word, Word. Word word word word word word. · 2.9 s')
  await expect(box(page, 'l3')).toHaveText('Word word word, Word, word word word word word word word?')
  for (const id of ['c1', 'c2', 'c3', 'c4']) await expect(box(page, id)).toHaveAttribute('data-take', 'none')
  const l1 = (await box(page, 'l1').boundingBox())!
  const pps = Number(await page.locator('[data-region="timeline"]').getAttribute('data-pps'))
  expect(Math.abs(l1.width - 3.642 * pps)).toBeLessThan(2)

  await box(page, 'l1').click()
  await expect(page.locator('[data-region="event"]')).toContainText('Character 1 · “Word word, word.')
  await expect(takeLine(page)).toHaveText('ok · l1-1.wav · 1.8 s of 3.6 s · heard 100 % · −23.4 LUFS · gain +0.4 dB')
  await expect(page.locator('[data-region="take-play"]')).toHaveAttribute('src', '/files/sounds/Script 1/l1-1.wav')
  await box(page, 'l2').click()
  await expect(takeLine(page)).toHaveText(`flagged · l2-1.wav · 2.9 s of 3.6 s · heard 83 % · −33.6 LUFS · gain −1.2 dB · ${WHY}`)
  await expect(page.locator('[data-region="take-play"]')).toHaveAttribute('src', '/files/sounds/Script 1/l2-1.wav')
  await box(page, 'l3').click()
  await expect(takeLine(page)).toHaveText('failed · The speech job failed')
  await expect(page.locator('[data-region="take-play"]')).toHaveCount(0)
  await box(page, 'c3').click()
  await expect(takeLine(page)).toHaveCount(0)
  await expect(audioRow(page, 'l3')).toContainText('failed · The speech job failed #3f9c0a1b77e2d415')
  await expect(audioRow(page, 'l3')).toHaveAttribute('data-take', 'failed')
  await expect(audioRow(page, 'l2')).toContainText(`flagged Script 1/l2-1.wav · ${WHY}`)
})
