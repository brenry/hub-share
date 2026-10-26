// The Storyboard tab: the stage above the timeline with a figure at each cast
// member's home; the ruler moves the playhead and the stage; a selected box puts the playhead at its start; Play and
// Pause.
import { readFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'
import type { ToolInfo } from '../../src/lib/protocol'
import { FakeHub } from './fixtures/controller'
import { SEQUENCE_TOOL, mockSequence, seqState } from './fixtures/sequence'
import { open } from './helpers'

const example: unknown = JSON.parse(readFileSync(new URL('../../../tests/fixtures/script-1.json', import.meta.url), 'utf8'))
const DIRECTOR_TOOL: ToolInfo = { id: 'director', title: 'Storyboard', tab: { label: 'Storyboard', order: 30 }, sockets: [] }
type File = { script: unknown; problem: string | null; changed: number; seconds?: number }

const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

/** The director routes of the fake hub, over `files` (by name). */
async function mockScripts(page: Page, files: Record<string, File>, calls: string[]): Promise<void> {
  await page.route(/\/api\/director\//, route => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace('/api/director', '')
    const b = (req.postDataBuffer() ? req.postDataJSON() : {}) as { name?: string; to?: string }
    calls.push(`${req.method()} ${p}${b.name ? ` ${b.name}` : ''}${b.to ? ` ${b.to}` : ''}`)
    const seconds = (f: File) => (f.problem ? 0 : f.seconds ?? 24)
    if (p === '/scripts') {
      return json(route, { scripts: Object.keys(files).sort().map(n => ({ name: n, seconds: seconds(files[n]!), scenes: 1, shots: 3, lines: 3, changed: files[n]!.changed, problem: files[n]!.problem })) })
    }
    const name = req.method() === 'GET' ? url.searchParams.get('name') ?? '' : String(b.name ?? '')
    const f = files[name]
    if (!f) return json(route, { code: 'invalid', text: `There is no script named ${name}` }, 400)
    const pictures = f.problem ? {} : Object.fromEntries(((f.script as { context?: { cast: { name: string }[] } }).context?.cast ?? []).map(m => [m.name, `chars/${m.name}.png`]))
    if (p === '/script') return json(route, { name, seconds: seconds(f), problem: f.problem, script: f.problem ? null : f.script, pictures })
    if (p === '/rename') {
      const to = String(b.to ?? '').trim()
      if (files[to]) return json(route, { code: 'invalid', text: `A script named ${to} already exists` }, 400)
      delete files[name]
      files[to] = f
      return json(route, { name: to })
    }
    if (p === '/delete') { delete files[name]; return route.fulfill({ status: 204, body: '' }) }
    return json(route, { text: 'Not found' }, 404)
  })
}

async function scripts(page: Page, files: Record<string, File> = { Example: { script: example, problem: null, changed: 1 } }) {
  const calls: string[] = []
  await page.setViewportSize({ width: 1600, height: 900 })
  await mockScripts(page, files, calls)
  await mockSequence(page, seqState())
  const base = new FakeHub()
  const { hub } = await open(page, '/', new FakeHub({ tools: [...base.tools, SEQUENCE_TOOL, DIRECTOR_TOOL] }))
  await page.getByRole('tab', { name: 'Storyboard' }).click()
  return { files, calls, hub }
}

const stage = (page: Page) => page.locator('canvas[data-region="script-stage"]')
const playhead = async (page: Page) => Number(await page.locator('[data-region="playhead"]').getAttribute('data-ms'))

test('the stage above the timeline shows one figure per cast member at the home place of the member', async ({ page }) => {
  await scripts(page)
  await expect(page.locator('[data-region="timeline"]')).toBeVisible()
  await expect(stage(page)).toHaveCount(0)
  const band = (await page.locator('[data-region="set-panel"]').boundingBox())!
  const timeline = (await page.locator('[data-region="timeline"]').boundingBox())!
  expect(band.y + band.height).toBeLessThanOrEqual(timeline.y + 1)
  await expect(page.locator('svg[data-figure]')).toHaveCount(11)
})

test('a click on the ruler moves the playhead and the stage; selecting a pose puts it at its start', async ({ page }) => {
  await scripts(page)
  await expect(page.locator('[data-region="timeline"]')).toBeVisible()
  expect(await playhead(page)).toBe(0)
  const pps = Number(await page.locator('[data-region="timeline"]').getAttribute('data-pps'))
  await page.locator('[data-region="ruler"]').click({ position: { x: 6 * pps, y: 5 } })
  await expect.poll(() => playhead(page)).toBeGreaterThan(5900)
  expect(await playhead(page)).toBeLessThan(6100)
  await expect(page.locator('[data-region="playhead-time"]')).toHaveText('6.0 s')
  await page.locator('[data-box="p6"]').click()
  await expect.poll(() => playhead(page)).toBe(12642)
  await expect(page.locator('[data-region="playhead-time"]')).toHaveText('12.6 s')
})

test('Play advances the playhead in real time and Pause stops it', async ({ page }) => {
  await scripts(page)
  const play = page.locator('[data-region="script-play"]')
  await expect(play).toHaveAttribute('aria-label', 'Play')
  await play.click()
  await expect(play).toHaveAttribute('aria-label', 'Pause')
  await expect.poll(() => playhead(page)).toBeGreaterThan(300)
  await play.click()
  await expect(play).toHaveAttribute('aria-label', 'Play')
  const stopped = await playhead(page)
  await page.waitForTimeout(400)
  expect(await playhead(page)).toBe(stopped)
  expect(stopped).toBeLessThan(10_000)
})

test('a locked script shows the lock in the bar; a shot camera object shows its framing', async ({ page }) => {
  const shots = (example as { scenes: { shots: { camera?: unknown }[] }[] }).scenes[0]!.shots
  const camera = { framing: 'close shot', move: 'slow push in', on: ['Character 2'] }
  const locked = { ...(example as object), lock: { locked: true, at: '2026-10-20T09:15:02+02:00' },
    scenes: [{ ...(example as { scenes: object[] }).scenes[0], shots: shots.map((s, k) => (k === 1 ? { ...s, camera } : s)) }] }
  await scripts(page, { Example: { script: example, problem: null, changed: 3 }, Locked: { script: locked, problem: null, changed: 2 } })
  await expect(page.locator('[data-region="script-length"]')).toBeVisible()
  await expect(page.locator('[data-region="script-locked"]')).toHaveCount(0)
  await page.locator('[data-region="scripts"]').click()
  await page.getByRole('menuitem', { name: /^Locked/ }).click()
  await expect(page.locator('[data-region="script-locked"]')).toHaveAttribute('title', 'Locked')
  const box = page.locator('[data-box="shot:1.2"]')
  await expect(box).toContainText('1.2 close shot, slow push in · on Character 2')
  await box.click()
  await expect(page.locator('[data-region="event"]')).toHaveText(/^Shot 1\.2 · close shot, slow push in · on Character 2 · /)
})
