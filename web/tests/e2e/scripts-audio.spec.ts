// The Storyboard tab, a locked script's `/script` answer carries `audio`, shown as the Audio script panel at
// the timeline's right, one row per line and cue (a line's block with its line break, the times as the bar writes
// them, the take it would make); a row and its box on the timeline select each other; `audio: null` shows no panel.
import { readFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'
import type { ToolInfo } from '../../src/lib/protocol'
import { FakeHub } from './fixtures/controller'
import { SEQUENCE_TOOL, mockSequence, seqState } from './fixtures/sequence'
import { open } from './helpers'

const example: unknown = JSON.parse(readFileSync(new URL('../../../tests/fixtures/script-1.json', import.meta.url), 'utf8'))
const DIRECTOR_TOOL: ToolInfo = { id: 'director', title: 'Storyboard', tab: { label: 'Storyboard', order: 30 }, sockets: [] }
const LOCK = { locked: true, at: '2026-10-20T09:15:02+02:00' }

const json = (route: Route, body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

const BLOCK = 'Speaker 1:\n[English, Emotion 1, 2.6 words per second] Word word, word. Word word word word word word.'
const take = (id: string) => ({ state: 'none', file: `Script 1/${id}-1.wav` })
const row = (id: string, kind: 'line' | 'cue', shot: string, start: number, end: number, who: string, text: string, seconds: number, sample: string | null = null) =>
  ({ id, kind, shot, start_ms: start, end_ms: end, who, text, problem: null, sample, seconds, hash: '3f9c0a1b77e2d415', take: take(id) })
/** The rows `audioscript.plan` gives for the example, locked. */
const AUDIO = [
  row('c1', 'cue', '1.1', 0, 2500, 'music', 'Word word word word-word word', 3),
  row('c2', 'cue', '1.1', 2500, 3900, 'reaction', 'Word word', 2),
  row('l1', 'line', '1.1', 4000, 7642, 'Character 1', BLOCK, 8, 'Character 1.wav'),
  row('l2', 'line', '1.2', 9000, 12642, 'Character 2', 'Speaker 1:\n[English, Emotion 2, 2.6 words per second] Word word, Word. Word word word word word word.', 8),
  row('c3', 'cue', '1.2', 13000, 13800, 'effect', 'Word word word word word word word word', 1),
  row('l3', 'line', '1.3', 17500, 21911, 'Character 1', 'Speaker 1:\n[English, Emotion 3, 2.6 words per second] Word word word, Word, word word word word word word word?', 9, 'Character 1.wav'),
  row('c4', 'cue', '1.3', 22000, 23500, 'reaction', 'Word word', 2),
]

async function scripts(page: Page, audio: unknown[] | null) {
  await page.setViewportSize({ width: 1600, height: 900 })
  const script = audio ? { ...(example as object), lock: LOCK } : example
  await page.route(/\/api\/director\//, route => {
    const p = new URL(route.request().url()).pathname.replace('/api/director', '')
    if (p === '/scripts') return json(route, { scripts: [{ name: 'Script 1', seconds: 24, scenes: 1, shots: 3, lines: 3, changed: 1, problem: null }] })
    if (p === '/script') return json(route, { name: 'Script 1', seconds: 24, problem: null, script, pictures: {}, unpictured: [], audio })
    return json(route, {})
  })
  await mockSequence(page, seqState())
  const base = new FakeHub()
  await open(page, '/', new FakeHub({ tools: [...base.tools, SEQUENCE_TOOL, DIRECTOR_TOOL] }))
  await page.getByRole('tab', { name: 'Storyboard' }).click()
}

const panel = (page: Page) => page.locator('[data-region="audio-script"]')
const rowOf = (page: Page, id: string) => panel(page).locator(`[data-audio="${id}"]`)
const box = (page: Page, id: string) => page.locator(`[data-region="timeline"] [data-box="${id}"]`)

test('a locked script shows its audio script beside the timeline, one row per line and cue', async ({ page }) => {
  await scripts(page, AUDIO)
  await expect(panel(page)).toBeVisible()
  await expect(panel(page).getByRole('heading', { name: 'Audio script' })).toBeVisible()
  await expect(panel(page).locator('[data-audio]')).toHaveCount(7)
  expect(await panel(page).locator('[data-audio]').evaluateAll(els => els.map(e => e.getAttribute('data-audio')))).toEqual(['c1', 'c2', 'l1', 'l2', 'c3', 'l3', 'c4'])
  const timeline = (await page.locator('[data-region="timeline"]').boundingBox())!
  const side = (await panel(page).boundingBox())!
  expect(side.x).toBeGreaterThanOrEqual(timeline.x + timeline.width - 1)
  expect(side.y).toBeLessThanOrEqual(timeline.y + 1)
  const rem = await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize))
  expect(side.width).toBeLessThanOrEqual(26 * rem + 1)
  expect(side.width).toBeGreaterThanOrEqual(18 * rem - 1)
  const l1 = rowOf(page, 'l1')
  expect(await l1.locator('pre').textContent()).toBe(BLOCK)
  await expect(l1).toContainText('1.1 · 4.0–7.6 s · l1 · Character 1 · Character 1.wav · cap 8 s')
  await expect(l1).toContainText('none → Script 1/l1-1.wav #3f9c0a1b77e2d415')
  await expect(rowOf(page, 'l2')).toContainText('1.2 · 9.0–12.6 s · l2 · Character 2 · no voice sample · cap 8 s')
  await expect(rowOf(page, 'c3')).toContainText('1.2 · 13.0–13.8 s · c3 · effect · effect sound · 1 s')
  await expect(rowOf(page, 'c3').locator('pre')).toHaveText('Word word word word word word word word')
  for (const r of await panel(page).locator('[data-audio]').all()) await expect(r).toHaveAttribute('data-take', 'none')
})

test('a row selects its box on the timeline and a box presses its row', async ({ page }) => {
  await scripts(page, AUDIO)
  await rowOf(page, 'l2').click()
  await expect(box(page, 'l2')).toHaveAttribute('aria-pressed', 'true')
  await expect(rowOf(page, 'l2')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('[data-region="event"]')).toHaveText('Character 2 · “Word word, Word. Word word word word word word.” · English · Emotion 2 · 2.6 words/s · 9.0–12.6 s')
  await expect(page.locator('[data-region="playhead"]')).toHaveAttribute('data-ms', '9000')
  await rowOf(page, 'c1').click()
  await expect(box(page, 'c1')).toHaveAttribute('aria-pressed', 'true')
  await expect(box(page, 'l2')).toHaveAttribute('aria-pressed', 'false')
  await box(page, 'c4').click()
  await expect(rowOf(page, 'c4')).toHaveAttribute('aria-pressed', 'true')
  await expect(rowOf(page, 'c1')).toHaveAttribute('aria-pressed', 'false')
  await expect(rowOf(page, 'c4')).toBeInViewport()
})

test('an answer with audio null shows no panel', async ({ page }) => {
  await scripts(page, null)
  await expect(page.locator('[data-region="timeline"]')).toBeVisible()
  await expect(panel(page)).toHaveCount(0)
})
