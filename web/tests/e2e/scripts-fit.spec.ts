// The Storyboard tab fits a 2000×1130 window: while Play runs, the stage and every row of the timeline are on
// screen together, the timeline not scrolling, at 2000×1130 and two smaller windows, and after a root change (the one
// scaling the Hub's CSS knows); the canvas drawn at its displayed size, a pose figure 4rem square, the stage 8-16rem
// tall, the scene context above the timeline; with the Audio panel the same; at --ui-scale 1.4 only the timeline scrolls; a
// long script keeps the playhead in view while playing; two members at home 0 both whole on the stage, one
// pointing, its fingertips drawn.
import { readFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'
import type { ToolInfo } from '../../src/lib/protocol'
import { FakeHub } from './fixtures/controller'
import { SEQUENCE_TOOL, mockSequence, seqState } from './fixtures/sequence'
import { fitProblems, fullyVisible, rootPx } from './fit'
import { open } from './helpers'

const read = (path: string): Record<string, unknown> => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'))
const example = read('../../../tests/fixtures/script-1.json')
const round1 = read('./fixtures/script-2.json')
const DIRECTOR_TOOL: ToolInfo = { id: 'director', title: 'Storyboard', tab: { label: 'Storyboard', order: 30 }, sockets: [] }
const TAB = '#panel-director'
const CANVAS = 'canvas[data-region="script-stage"]'
const json = (route: Route, body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

const take = (id: string) => ({ state: 'none', file: `Script 1/${id}-1.wav` })
/** Two rows of the example's audio script, locked. */
const AUDIO = [
  { id: 'c1', kind: 'cue', shot: '1.1', start_ms: 0, end_ms: 2500, who: 'music', text: 'Word word word word-word word', problem: null, sample: null, seconds: 3, hash: '3f9c0a1b77e2d415', take: take('c1') },
  { id: 'l1', kind: 'line', shot: '1.1', start_ms: 4000, end_ms: 7642, who: 'Character 1', text: 'Speaker 1:\n[English, Emotion 1, 2.6 words per second] Word word, word. Word word word word word word.', problem: null, sample: 'Character 1.wav', seconds: 8, hash: '3f9c0a1b77e2d415', take: take('l1') },
]

/** One script served as `Script 1` by the fake hub, the Storyboard tab open on it at `w` × `h`. */
async function storyboard(page: Page, script: unknown, w: number, h: number, audio: unknown[] | null = null) {
  await page.setViewportSize({ width: w, height: h })
  await page.route(/\/api\/director\//, route => {
    const p = new URL(route.request().url()).pathname.replace('/api/director', '')
    if (p === '/scripts') return json(route, { scripts: [{ name: 'Script 1', seconds: 30, scenes: 1, shots: 4, lines: 4, changed: 1, problem: null }] })
    if (p === '/script') return json(route, { name: 'Script 1', seconds: 30, problem: null, script, pictures: {}, unpictured: [], audio })
    return json(route, {})
  })
  await mockSequence(page, seqState())
  const base = new FakeHub()
  await open(page, '/', new FakeHub({ tools: [...base.tools, SEQUENCE_TOOL, DIRECTOR_TOOL] }))
  await page.getByRole('tab', { name: 'Storyboard' }).click()
  await expect(page.locator('[data-region="timeline"]')).toBeVisible()
  await expect(page.locator(CANVAS)).toHaveCount(0)               // the stage's figures on hold
}

const play = async (page: Page) => {
  await page.locator('[data-region="script-play"]').click()
  await expect.poll(async () => Number(await page.locator('[data-region="playhead"]').getAttribute('data-ms'))).toBeGreaterThan(0)
}

/** Everything the tab promises while playing; `scrolls`: the timeline may scroll (only it). */
async function fits(page: Page, tag: string, scrolls = false) {
  const rem = await rootPx(page)
  const timeline = page.locator('[data-region="timeline"]')
  const tl = (await timeline.boundingBox())!
  const context = page.locator('[data-region="context"]')
  if (await context.count()) expect((await context.boundingBox())!.y + (await context.boundingBox())!.height, `${tag} context above`).toBeLessThanOrEqual(tl.y + 1)
  const band = (await page.locator('[data-region="script-band"]').boundingBox())!
  expect(band.y + band.height, `${tag} band above`).toBeLessThanOrEqual(tl.y + 1)
  const fig = (await page.locator('svg[data-figure]').first().boundingBox())!
  expect(Math.abs(fig.width - 4 * rem), `${tag} figure 4rem wide`).toBeLessThan(1)
  expect(Math.abs(fig.height - 4 * rem), `${tag} figure 4rem tall`).toBeLessThan(1)
  const over = await timeline.evaluate(el => el.scrollHeight - el.clientHeight)
  if (!scrolls) {
    expect(over, `${tag} timeline does not scroll`).toBeLessThanOrEqual(1)
    for (const key of await page.locator('[data-row]').evaluateAll(els => els.map(e => e.getAttribute('data-row')!))) {
      const r = (await page.locator(`[data-row="${key}"]`).boundingBox())!   // sideways scroll allowed
      expect(r.y >= tl.y - 0.5 && r.y + r.height <= tl.y + tl.height + 0.5, `${tag} row ${key}`).toBe(true)
    }
  }
  expect(await page.evaluate(() => document.documentElement.scrollHeight - innerHeight), `${tag} page`).toBeLessThanOrEqual(0)
  expect(await fitProblems(page, [TAB]), `${tag} fit`).toEqual([])
}

const setScale = (page: Page, scale: number) => page.evaluate(k => document.documentElement.style.setProperty('--ui-scale', String(k)), scale)

for (const [name, script] of [['round 1', round1], ['example', example]] as const) {
  for (const [w, h] of [[2000, 1130], [1600, 900], [1366, 768]] as const) {
    test(`${name} at ${w}×${h}, playing: the stage and every row on screen together`, async ({ page }) => {
      await storyboard(page, script, w, h)
      await play(page)
      await fits(page, `${name} ${w}×${h}`)
    })
  }
  test(`${name} at 2000×1130 follows a root change (--ui-scale 0.8 and 1.25)`, async ({ page }) => {
    await storyboard(page, script, 2000, 1130)
    await play(page)
    for (const k of [0.8, 1.25]) {
      const before = await rootPx(page)
      await setScale(page, k)
      await expect.poll(() => rootPx(page)).not.toBe(before)
      await fits(page, `${name} --ui-scale ${k}`)
    }
  })
}

test('with the Audio panel (a locked script) the same at 2000×1130', async ({ page }) => {
  await storyboard(page, { ...example, lock: { locked: true, at: '2026-10-20T09:15:02+02:00' } }, 2000, 1130, AUDIO)
  await expect(page.locator('[data-region="audio-script"]')).toBeVisible()
  await play(page)
  await fits(page, 'audio')
})

test('at --ui-scale 1.4 only the timeline scrolls; the stage stays whole and nothing is cut', async ({ page }) => {
  await storyboard(page, round1, 2000, 1130)
  await setScale(page, 1.4)
  await play(page)
  await fits(page, '1.4', true)
})

/** A script longer than the width at the least scale: 12 shots of 10 s, one line each. */
const LONG = { version: 2, context: { cast: [{ name: 'Character 1', home: 30 }, { name: 'Character 2', home: 70 }] }, scenes: [{ title: 'Long', cast: ['Character 1', 'Character 2'],
  shots: Array.from({ length: 12 }, (_, k) => ({ start_ms: k * 10000, end_ms: (k + 1) * 10000, events: [
    { id: `l${k}`, kind: 'line', start_ms: k * 10000 + 1000, end_ms: k * 10000 + 4000, speaker: k % 2 ? 'Character 2' : 'Character 1', words: 'Hello there.' }] })) }] }

test('a long script keeps the playhead inside the visible rows while playing', async ({ page }) => {
  await storyboard(page, LONG, 1600, 900)
  const timeline = page.locator('[data-region="timeline"]')
  const [view, head] = await timeline.evaluate(el => [el.clientWidth, (el.querySelector('[data-row] > :first-child') as HTMLElement).offsetWidth])
  expect(await timeline.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true)
  await page.locator('[data-region="ruler"]').click({ position: { x: view! - head! - 8, y: 5 } })
  await play(page)
  await expect.poll(() => timeline.evaluate(el => el.scrollLeft), { timeout: 5000 }).toBeGreaterThan(0)
  for (let i = 0; i < 4; i++) {
    const [t, ph] = [(await timeline.boundingBox())!, (await page.locator('[data-region="playhead"]').boundingBox())!]
    expect(ph.x, 'playhead right of the row heads').toBeGreaterThanOrEqual(t.x + head! - 1)
    expect(ph.x, 'playhead inside the visible rows').toBeLessThanOrEqual(t.x + t.width)
    await page.waitForTimeout(250)
  }
})

/** The example with Character 1 (first in the cast, so at place 0) pointing from its start: the pose reaching farthest left. */
const pointing = (): Record<string, unknown> => {
  const scenes = structuredClone(example.scenes) as { shots: { events: Record<string, unknown>[] }[] }[]
  for (const e of scenes[0]!.shots[0]!.events) if (e.kind === 'pose' && e.character === 'Character 1' && e.start_ms === 0) e.pose = 'point'
  return { ...example, scenes }
}

test('two members at home 0 stand apart, both whole on the stage, a pointing hand drawn to its tip', async ({ page }) => {
  const context = example.context as { cast: Record<string, unknown>[] }
  await storyboard(page, { ...pointing(), context: { ...context, cast: context.cast.map(m => ({ ...m, home: 0 })) } }, 1600, 900)
  const band = page.locator('[data-region="script-band"]')
  expect(await band.locator('> *').evaluateAll(els => els.map(e => e.getAttribute('data-region')))).toEqual(['set-panel', 'context'])
  expect(await fullyVisible(page, '[data-region="set-panel"]')).toBe(true)
})

test('every row head shows its whole name, a long one too, and every track starts at one x', async ({ page }) => {
  const long = JSON.parse(JSON.stringify(example).replaceAll('Character 2', 'Character 2 Character 2 Character 2'))
  for (const script of [example, long]) {
    await storyboard(page, script, 1366, 768)
    const heads = page.locator('[data-region="timeline"] [data-row-head]')
    await expect.poll(() => heads.evaluateAll(els => els.filter(e => e.scrollWidth > e.clientWidth).map(e => e.textContent))).toEqual([])
    const lefts = await page.locator('[data-region="timeline"] [data-row] > :last-child').evaluateAll(els => els.map(e => Math.round(e.getBoundingClientRect().left)))
    expect(new Set(lefts).size, 'tracks start at one x').toBe(1)
    const head = await heads.first().evaluate(e => e.getBoundingClientRect().right)
    expect(Math.abs(lefts[0]! - head)).toBeLessThanOrEqual(1)
  }
})
