// The Storyboard tab, a version-2 script's sketch panels on a Sketches row right under Shots, each at its
// time; a stale one marked, one not drawn an empty frame; a click shows it in the bar; a script without panels (the
// example) shows no Sketches row.
import { readFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'
import type { ToolInfo } from '../../src/lib/protocol'
import { FakeHub } from './fixtures/controller'
import { SEQUENCE_TOOL, mockSequence, seqState } from './fixtures/sequence'
import { open } from './helpers'

type Shot = { start_ms: number; events: unknown[] }
type Doc = { version: number; context: { cast: { name: string }[] }; scenes: { shots: Shot[] }[] }
const example = JSON.parse(readFileSync(new URL('../../../tests/fixtures/script-1.json', import.meta.url), 'utf8')) as Doc
const DIRECTOR_TOOL: ToolInfo = { id: 'director', title: 'Storyboard', tab: { label: 'Storyboard', order: 30 }, sockets: [] }
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64')

const json = (route: Route, body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

/** The example with three panels: f1 drawn at 0, f2 stale at 9 s, f3 not drawn at 17 s. */
function sketched(): Doc {
  const doc = structuredClone(example)
  const [s1, s2, s3] = doc.scenes[0]!.shots
  s1!.events.push({ id: 'f1', kind: 'panel', at_ms: 0, picture: 'out/d/f1.png', stale: false })
  s2!.events.push({ id: 'f2', kind: 'panel', at_ms: 9000, picture: 'out/d/f2.png', stale: true })
  s3!.events.push({ id: 'f3', kind: 'panel', at_ms: 17000, picture: null, stale: false })
  return doc
}

/** The fake hub's director routes over one script, and the thumbnails. */
async function storyboard(page: Page, script: Doc) {
  await page.setViewportSize({ width: 1600, height: 900 })
  await page.route(/\/thumbs\//, route => route.fulfill({ status: 200, contentType: 'image/png', body: PNG }))
  await page.route(/\/api\/director\//, route => {
    const p = new URL(route.request().url()).pathname.replace('/api/director', '')
    if (p === '/scripts') return json(route, { scripts: [{ name: 'Script 1', seconds: 24, scenes: 1, shots: 3, lines: 3, changed: 1, problem: null }] })
    const pictures = Object.fromEntries(script.context.cast.map(m => [m.name, `chars/${m.name}.png`]))
    if (p === '/script') return json(route, { name: 'Script 1', seconds: 24, problem: null, script, pictures, unpictured: [] })
    return route.fulfill({ status: 404, body: '' })
  })
  await mockSequence(page, seqState())
  const base = new FakeHub()
  await open(page, '/', new FakeHub({ tools: [...base.tools, SEQUENCE_TOOL, DIRECTOR_TOOL] }))
  await page.getByRole('tab', { name: 'Storyboard' }).click()
}

const row = (page: Page, key: string) => page.locator(`[data-row="${key}"]`)

test('the Sketches row under Shots, each sketch at its time, stale and not drawn marked', async ({ page }) => {
  await storyboard(page, sketched())
  await expect(row(page, 'panels')).toBeVisible()
  const keys = await page.locator('[data-row]').evaluateAll(els => els.map(e => e.getAttribute('data-row')))
  expect(keys.slice(0, 3)).toEqual(['ruler', 'shots', 'panels'])
  await expect(row(page, 'panels').locator('div').first()).toHaveText('Sketches')
  const buttons = row(page, 'panels').locator('button')
  await expect(buttons).toHaveCount(3)
  const pps = Number(await page.locator('[data-region="timeline"]').getAttribute('data-pps'))
  const track = (await row(page, 'panels').locator('button').first().evaluate(el => el.parentElement!.getBoundingClientRect().left))
  for (const [id, at] of [['f1', 0], ['f2', 9], ['f3', 17]] as const) {
    const box = (await page.locator(`[data-box="${id}"]`).boundingBox())!
    expect(Math.abs(box.x - track - at * pps)).toBeLessThan(2)
    expect(Math.round(box.width / box.height * 9)).toBe(16)
  }
  await expect(page.locator('[data-box="f1"]')).toHaveAttribute('data-stale', 'false')
  await expect(page.locator('[data-box="f1"] img')).toHaveCount(1)
  await expect(page.locator('[data-box="f2"]')).toHaveAttribute('data-stale', 'true')
  await expect(page.locator('[data-box="f2"]')).toHaveAttribute('title', 'Sketch · 9.0 s · stale')
  await expect(page.locator('[data-box="f3"]')).toHaveAttribute('data-drawn', 'false')
  await expect(page.locator('[data-box="f3"] img')).toHaveCount(0)
  await page.locator('[data-box="f2"]').click()
  await expect(page.locator('[data-region="event"]')).toHaveText('Sketch f2 · shot 1.2 · 9.0 s · stale')
  await expect.poll(async () => Number(await page.locator('[data-region="playhead"]').getAttribute('data-ms'))).toBe(9000)
})

test('a script without panels (the example) shows no Sketches row', async ({ page }) => {
  await storyboard(page, example)
  await expect(row(page, 'shots')).toBeVisible()
  await expect(row(page, 'panels')).toHaveCount(0)
})
