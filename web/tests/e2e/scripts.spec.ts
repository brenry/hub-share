// The Storyboard tab: after Edit Video; the example drawn as a timeline (three shots, a lines row per
// character, the cues, a pose row per character with eleven stick figures); a click shows the event in the bar; the
// Scripts menu renames and deletes; a file that does not read shows its problem. The scene context above the
// timeline (the style line, a card per cast member with the picture, the set's card with its places); a version-1
// script shows no band. A `director.changed` the script tools publish redraws the open script, or opens the
// script it names; a version-2 script being written, with no shot yet, shows its scene context and an empty timeline. The
// bar shows the open script's length beside its name, follows a `director.changed`, and shows none for a file that
// does not read. A cast member with no picture in Characters: the timeline drawn, the member's card says so.
import { readFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'
import type { ToolInfo } from '../../src/lib/protocol'
import { FakeHub } from './fixtures/controller'
import { SEQUENCE_TOOL, mockSequence, seqState } from './fixtures/sequence'
import { open } from './helpers'

const example: unknown = JSON.parse(readFileSync(new URL('../../../tests/fixtures/script-1.json', import.meta.url), 'utf8'))
const DIRECTOR_TOOL: ToolInfo = { id: 'director', title: 'Storyboard', tab: { label: 'Storyboard', order: 30 }, sockets: [] }
/** `missing`: cast names the fake hub's Characters lacks. */
type File = { script: unknown; problem: string | null; changed: number; seconds?: number; missing?: string[] }

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
    const cast = f.problem ? [] : ((f.script as { context?: { cast: { name: string }[] } }).context?.cast ?? []).map(m => m.name)
    const unpictured = cast.filter(n => f.missing?.includes(n))
    const pictures = Object.fromEntries(cast.filter(n => !unpictured.includes(n)).map(n => [n, `chars/${n}.png`]))
    if (p === '/script') return json(route, { name, seconds: seconds(f), problem: f.problem, script: f.problem ? null : f.script, pictures, unpictured })
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

const row = (page: Page, key: string) => page.locator(`[data-row="${key}"]`)

test('the Scripts tab comes after Edit Video and draws the example as a timeline', async ({ page }) => {
  await scripts(page)
  await expect(page.getByRole('tab')).toHaveText(['Generate Image', 'Edit Video', 'Storyboard'])
  await expect(page.locator('[data-region="scripts"]')).toHaveText('Example')
  await expect(page.locator('[data-row]')).toHaveCount(7)
  await expect(page.locator('[data-row] > :first-child')).toHaveText(['', 'Shots', 'Character 1', 'Character 2', 'Cues', 'Character 1 pose', 'Character 2 pose'])
  const shots = row(page, 'shots').locator('[data-box]')
  await expect(shots).toHaveCount(3)
  await expect(shots).toHaveText([/^1\.1 Wide shot/, '1.2 Close shot on Character 2', '1.3 Close shot on Character 1'])
  await expect(row(page, 'line:character 1').locator('[data-box]')).toHaveCount(2)
  await expect(row(page, 'line:character 2').locator('[data-box]')).toHaveText(['Word word, Word. Word word word word word word.'])
  await expect(row(page, 'cues').locator('[data-box]')).toHaveCount(4)
  await expect(page.locator('svg[data-figure]')).toHaveCount(11)
  await expect(row(page, 'pose:character 1').locator('svg[data-figure]')).toHaveCount(7)
  for (const pose of ['stand', 'sit', 'walk_step', 'turn', 'point', 'arms_raised', 'hand_to_face']) {
    await expect(page.locator(`svg[data-figure="${pose}"]`).first()).toBeVisible()
  }
  // each figure 4rem square at its pose's start (80 px at a 20 px root), never scaled
  const fig = (await page.locator('[data-box="p3"] svg').boundingBox())!
  const rem = await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize))
  expect(Math.abs(fig.width - 4 * rem)).toBeLessThan(1)
  expect(Math.abs(fig.height - 4 * rem)).toBeLessThan(1)
  // every box as long as its event at the scale: the whole 24 s fits the width (at least 40 px/s)
  const pps = Number(await page.locator('[data-region="timeline"]').getAttribute('data-pps'))
  expect(pps).toBeGreaterThanOrEqual(2 * rem - 0.01)
  const l1 = (await page.locator('[data-box="l1"]').boundingBox())!
  const start = (await row(page, 'line:character 1').locator('> :last-child').boundingBox())!.x
  expect(Math.abs(l1.x - start - 4 * pps)).toBeLessThan(1.5)
  expect(Math.abs(l1.width - 3.642 * pps)).toBeLessThan(1.5)
  const timeline = page.locator('[data-region="timeline"]')
  expect(await timeline.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true)
})

test('a click on a box shows its fields in the bar', async ({ page }) => {
  await scripts(page)
  await page.locator('[data-box="l1"]').click()
  await expect(page.locator('[data-region="event"]')).toHaveText('Character 1 · “Word word, word. Word word word word word word.” · English · Emotion 1 · 2.6 words/s · 4.0–7.6 s')
  await expect(page.locator('[data-box="l1"]')).toHaveAttribute('aria-pressed', 'true')
  await page.locator('[data-box="c1"]').click()
  await expect(page.locator('[data-region="event"]')).toHaveText('Cue music · Word word word word-word word · 0.0–2.5 s')
  await page.locator('[data-box="p6"]').click()
  await expect(page.locator('[data-region="event"]')).toHaveText('Character 2 · hand_to_face · 12.6–17.0 s')
})

test('the Scripts menu lists the script with its length, renames it and deletes it', async ({ page }) => {
  const { files, calls } = await scripts(page)
  await page.locator('[data-region="scripts"]').click()
  await expect(page.getByRole('menuitem')).toHaveText(['Example · 24.0 s', 'Rename…', 'Delete script'])
  await page.getByRole('menuitem', { name: 'Rename…' }).click()
  await page.getByLabel('New name').fill('Scene 1')
  await page.getByLabel('New name').press('Enter')
  await expect(page.locator('[data-region="scripts"]')).toHaveText('Scene 1')
  expect(Object.keys(files)).toEqual(['Scene 1'])
  expect(calls).toContain('POST /rename Example Scene 1')
  await page.locator('[data-region="scripts"]').click()
  await page.getByRole('menuitem', { name: 'Delete script' }).click()
  await expect(page.locator('[data-region="script-problem"]')).toHaveText('No scripts')
  expect(files).toEqual({})
  await expect(page.locator('svg[data-figure]')).toHaveCount(0)
})

test('a file that does not read is listed with its problem, shown where the timeline would be, and deletable', async ({ page }) => {
  const problem = 'Scene 1, shot 2, event l2: the speaker Character 4 is not in the scene\'s cast'
  const { files } = await scripts(page, { Broken: { script: null, problem, changed: 2 }, Example: { script: example, problem: null, changed: 1 } })
  await expect(page.locator('[data-region="scripts"]')).toHaveText('Broken')
  await expect(page.locator('[data-region="script-problem"]')).toHaveText(problem)
  await page.locator('[data-region="scripts"]').click()
  await expect(page.getByRole('menuitem')).toHaveText([`Broken · ${problem}`, 'Example · 24.0 s', 'Rename…', 'Delete script'])
  await page.getByRole('menuitem', { name: 'Delete script' }).click()
  await expect(page.locator('[data-region="scripts"]')).toHaveText('Example')
  expect(Object.keys(files)).toEqual(['Example'])
  await expect(page.locator('svg[data-figure]')).toHaveCount(11)
})

test('the scene context shows above the timeline: the style, a card per cast member with the picture, the set with its places', async ({ page }) => {
  await scripts(page)
  const band = page.locator('[data-region="context"]')
  await expect(band).toBeVisible()
  const bandBox = (await band.boundingBox())!
  const timeline = (await page.locator('[data-region="timeline"]').boundingBox())!
  expect(bandBox.y + bandBox.height).toBeLessThanOrEqual(timeline.y + 1)
  await expect(page.locator('[data-region="style"] input')).toHaveValue('Style 1')
  expect(await page.locator('[data-card]').evaluateAll(els => els.map(e => e.getAttribute('data-card')))).toEqual(['Set 1', 'Character 1', 'Character 2'])
  for (const name of ['Character 1', 'Character 2']) await expect(page.locator(`[data-card="${name}"]`)).toContainText(name)
  await expect(page.locator('[data-card="Set 1"] [data-field="Set"]')).toHaveValue('Set 1')
  await expect(page.locator('[data-card="Character 1"] img')).toHaveAttribute('src', '/thumbs/chars/Character%201.png/96')
  await expect(page.locator('[data-card="Character 2"] img')).toHaveAttribute('src', '/thumbs/chars/Character%202.png/96')
  await expect(page.locator('[data-card="Character 1"] [data-field="Costume"]')).toHaveValue('Costume 1')
  await expect(page.locator('[data-card="Character 2"] [data-field="Home"]')).toHaveValue('70')
  const stage = page.locator('[data-card="Set 1"]')
  await expect(stage.locator('[data-field="Elements"]')).toHaveValue('Element 1, Element 2, Element 3, Element 4, Element 5')
  await expect(stage.locator('[data-field="Props"]')).toHaveValue('Prop 1: Description 2\nProp 2: Description 3')
  const strip = (await stage.locator('[data-region="places"]').boundingBox())!
  const card = (await stage.boundingBox())!
  expect(strip.width).toBeGreaterThan(card.width * 0.8)
  const at = async (name: string) => { const b = (await stage.locator(`[data-place="${name}"]`).boundingBox())!; return (b.x + b.width / 2 - strip.x) / strip.width }
  expect(Math.abs(await at('Character 1') - 0.3)).toBeLessThan(0.02)
  expect(Math.abs(await at('Character 2') - 0.7)).toBeLessThan(0.02)
  await expect(page.locator('[data-row]')).toHaveCount(7)
  await expect(page.locator('svg[data-figure]')).toHaveCount(11)
})

test('a version-1 script shows no scene context and the same timeline', async ({ page }) => {
  const v1 = { version: 1, scenes: (example as { scenes: unknown }).scenes }
  await scripts(page, { Example: { script: v1, problem: null, changed: 1 } })
  await expect(page.locator('[data-row]')).toHaveCount(7)
  await expect(page.locator('[data-region="context"]')).toHaveCount(0)
  await expect(page.locator('[data-row] > :first-child')).toHaveText(['', 'Shots', 'Character 1', 'Character 2', 'Cues', 'Character 1 pose', 'Character 2 pose'])
  await expect(row(page, 'shots').locator('[data-box]')).toHaveCount(3)
  await expect(page.locator('svg[data-figure]')).toHaveCount(11)
})

const context = (example as { context: unknown }).context
const started = { version: 2, context, scenes: [] }

test('a director.changed redraws the open script with the new event', async ({ page }) => {
  const script = structuredClone(example) as { scenes: { shots: { events: unknown[] }[] }[] }
  const { files, hub } = await scripts(page, { Example: { script, problem: null, changed: 1 } })
  await expect(row(page, 'line:character 2').locator('[data-box]')).toHaveCount(1)
  script.scenes[0]!.shots[2]!.events.push({ id: 'l4', kind: 'line', start_ms: 22000, end_ms: 23500, speaker: 'Character 2', words: 'Thank you, Character 1.' })
  files.Example = { script, problem: null, changed: 3 }
  hub.broadcast('director.changed', { name: 'Example', revision: 2 }, 'workspace')
  await expect(page.locator('[data-box="l4"]')).toHaveText('Thank you, Character 1.')
  await expect(row(page, 'line:character 2').locator('[data-box]')).toHaveCount(2)
})

test('a director.changed for another script opens it; with no shot it shows the scene context and an empty timeline', async ({ page }) => {
  const { files, hub } = await scripts(page)
  await expect(page.locator('[data-region="scripts"]')).toHaveText('Example')
  files['Script 2'] = { script: started, problem: null, changed: 0 }
  hub.broadcast('director.changed', { name: 'Script 2', revision: 1 }, 'workspace')
  await expect(page.locator('[data-region="scripts"]')).toHaveText('Script 2')
  await expect(page.locator('[data-region="context"]')).toBeVisible()
  await expect(page.locator('[data-card]')).toHaveCount(3)
  await expect(page.locator('[data-row] > :first-child')).toHaveText(['', 'Shots', 'Cues'])
  await expect(page.locator('[data-box]')).toHaveCount(0)
  await expect(page.locator('svg[data-figure]')).toHaveCount(0)
  await page.locator('[data-region="scripts"]').click()
  await expect(page.getByRole('menuitem')).toHaveText(['Example · 24.0 s', 'Script 2 · 24.0 s', 'Rename…', 'Delete script'])
})

test('the bar shows the open script\'s length and follows a director.changed', async ({ page }) => {
  const script = structuredClone(example) as { scenes: { shots: { end_ms: number }[] }[] }
  const { files, hub } = await scripts(page, { Example: { script, problem: null, changed: 1 } })
  await expect(page.locator('[data-region="script-length"]')).toHaveText('24.0 s')
  files.Example = { script, problem: null, changed: 3, seconds: 27.4 }
  hub.broadcast('director.changed', { name: 'Example', revision: 2 }, 'workspace')
  await expect(page.locator('[data-region="script-length"]')).toHaveText('27.4 s')
})

test('a script that does not read shows no length in the bar', async ({ page }) => {
  await scripts(page, { Broken: { script: null, problem: 'Shot 1: end_ms is missing', changed: 2 } })
  await expect(page.locator('[data-region="scripts"]')).toHaveText('Broken')
  await expect(page.locator('[data-region="script-length"]')).toHaveCount(0)
})

test('a cast member with no picture in Characters: the timeline is drawn and the card of the member says so', async ({ page }) => {
  await scripts(page, { Example: { script: example, problem: null, changed: 1, missing: ['Character 2'] } })
  await expect(page.locator('[data-region="script-problem"]')).toHaveCount(0)
  await expect(row(page, 'shots').locator('[data-box]')).toHaveCount(3)
  await expect(row(page, 'line:character 2').locator('[data-box]')).toHaveText(['Word word, Word. Word word word word word word.'])
  await expect(page.locator('[data-card="Character 2"] img')).toHaveCount(0)
  await expect(page.locator('[data-card="Character 2"] [data-region="member-problem"]')).toHaveText('No picture in Characters')
  await expect(page.locator('[data-card="Character 1"] [data-region="member-problem"]')).toHaveCount(0)
  await expect(page.locator('[data-card="Character 1"] img')).toHaveAttribute('src', '/thumbs/chars/Character%201.png/96')
})
