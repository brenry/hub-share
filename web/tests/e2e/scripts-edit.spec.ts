// The Storyboard's Render (one press, one job, its progress as Track's, the cut's player when it lands, a
// refusal as its line) and its timeline by hand: a box dragged moves (into the shot it lands on), a right-click on a
// box edits or deletes it, one on empty timeline adds a line, a cue or a shot; each one `/edit` call.
import { expect, test, type Page, type Route } from '@playwright/test'
import type { Job, JobSummary, ToolInfo } from '../../src/lib/protocol'
import { FakeHub } from './fixtures/controller'
import { job } from './fixtures/data'
import { SEQUENCE_TOOL, mockSequence, seqState } from './fixtures/sequence'
import { open } from './helpers'

const DIRECTOR_TOOL: ToolInfo = { id: 'director', title: 'Storyboard', tab: { label: 'Storyboard', order: 30 }, sockets: [] }
const NAME = 'Script 1'
const CUT = 'clips/Storyboard/Script 1.mp4'
const SCRIPT = { version: 2, context: { cast: [{ name: 'A' }, { name: 'B' }] }, scenes: [{ title: 'Scene 1', cast: ['A', 'B'], shots: [
  { id: 's1', start_ms: 0, end_ms: 4000, camera: { framing: 'Wide' }, events: [
    { id: 'l1', kind: 'line', speaker: 'A', words: 'One', start_ms: 500, end_ms: 1500 },
    { id: 'p1', kind: 'pose', character: 'A', pose: 'stand', start_ms: 0, end_ms: 1 }] },
  { id: 's2', start_ms: 4000, end_ms: 9000, camera: { framing: 'Close' }, events: [
    { id: 'c1', kind: 'cue', cue: 'effect', words: 'Two', start_ms: 5000, end_ms: 6000 }] },
] }] }

type State = { calls: Record<string, unknown>[]; rendering: string | null; cut: string | null; refuse: string | null }
const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

async function board(page: Page, st: State): Promise<FakeHub> {
  const lora = { on: false, strength: 1 }
  await page.setViewportSize({ width: 1600, height: 900 })
  await page.route(/\/api\/director\//, route => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace('/api/director', '')
    if (p === '/scripts') return json(route, { scripts: [{ name: NAME, seconds: 9, scenes: 1, shots: 2, lines: 1, changed: 1, problem: null }] })
    if (p === '/script') {
      return json(route, { name: NAME, seconds: 9, problem: null, script: SCRIPT, pictures: {}, unpictured: [], audio: null,
        rendering_cut: st.rendering, cut: st.cut })
    }
    if (p === '/video-loras') {
      const b = req.method() === 'POST' ? req.postDataJSON() as { on?: boolean; strength?: number } : null
      if (b) { st.calls.push({ ...b, route: p }); Object.assign(lora, b) }
      return json(route, { loras: [{ path: '/v/lora 1.safetensors', name: 'lora 1.safetensors', ...lora }] })
    }
    if (p === '/render' || p === '/edit') {
      st.calls.push({ path: p, ...(req.postDataJSON() as object) })
      if (st.refuse) return json(route, { problem: st.refuse })
      if (p === '/render') { st.rendering = 'r1'; return json(route, { job: 'r1' }) }
      return json(route, { did: 'done' })
    }
    return json(route, {})
  })
  await mockSequence(page, seqState())
  const hub = new FakeHub({ tools: [...new FakeHub().tools, SEQUENCE_TOOL, DIRECTOR_TOOL] })
  await open(page, '/', hub)
  await page.getByRole('tab', { name: 'Storyboard' }).click()
  await expect(page.locator('[data-region="timeline"] [data-box="l1"]')).toBeVisible()
  return hub
}

const state = (over: Partial<State> = {}): State => ({ calls: [], rendering: null, cut: null, refuse: null, ...over })
const box = (page: Page, id: string) => page.locator(`[data-region="timeline"] [data-box="${id}"]`)
const renderBtn = (page: Page) => page.locator('[data-region="script-render"]')
const pps = async (page: Page) => Number(await page.locator('[data-region="timeline"]').getAttribute('data-pps'))
const card = (patch: Partial<Job>): Job => job('r1', { tool: 'director', kind: 'director.render', title: `Render · ${NAME}`, lane: 'jobs',
  state: 'running', position: null, summary: { step_names: ['Shot 1.1', 'Shot 1.2', 'Join'] } as unknown as JobSummary, ...patch })

/** Drags a box (a pose by its figure) sideways by `ms` of the timeline. */
async function drag(page: Page, id: string, ms: number): Promise<void> {
  const r = (await (id.startsWith('p') ? box(page, id).locator('svg') : box(page, id)).boundingBox())!
  const dx = (ms / 1000) * (await pps(page))
  await page.mouse.move(r.x + 6, r.y + r.height / 2)
  await page.mouse.down()
  await page.mouse.move(r.x + 6 + dx / 2, r.y + r.height / 2, { steps: 4 })
  await page.mouse.move(r.x + 6 + dx, r.y + r.height / 2, { steps: 4 })
  await page.mouse.up()
}

/** A right-click on row `row` at `ms` of the timeline. */
async function rightAt(page: Page, row: string, ms: number): Promise<void> {
  const track = (await page.locator(`[data-row="${row}"] > :last-child`).boundingBox())!
  await page.mouse.click(track.x + (ms / 1000) * (await pps(page)), track.y + track.height / 2, { button: 'right' })
}

const near = (v: unknown, want: number) => expect(Math.abs(Number(v) - want)).toBeLessThan(40)

test('Render: one press posts /render, off while its job runs with its progress, then the cut plays', async ({ page }) => {
  const st = state()
  const hub = await board(page, st)
  await expect(renderBtn(page)).toHaveText('Render')
  await expect(renderBtn(page)).toHaveAttribute('aria-disabled', 'false')
  await renderBtn(page).click()
  await expect(renderBtn(page)).toHaveAttribute('aria-disabled', 'true')
  expect(st.calls).toEqual([{ path: '/render', name: NAME }])
  hub.setJob(card({ progress: { phase: 'clip', index: 2, count: 3, step: 0, steps: 0, pct: 50, eta_s: null, text: '' } }))
  await expect(page.locator('[data-region="render-progress"]')).toHaveText('1 of 3 · Shot 1.2')
  await renderBtn(page).click({ force: true })
  expect(st.calls).toHaveLength(1)
  st.rendering = null
  st.cut = CUT
  hub.setJob(card({ state: 'done' }))
  await expect(page.locator('[data-region="render-progress"]')).toHaveCount(0)
  await expect(renderBtn(page)).toHaveAttribute('aria-disabled', 'false')
  await page.locator('[data-region="script-cut"]').click()
  await expect(page.locator('[data-region="cut-play"]')).toHaveAttribute('src', '/files/clips/Storyboard/Script%201.mp4')
})

test('Render: a refusal shows its one line', async ({ page }) => {
  const st = state({ refuse: 'The video model is not present' })
  await board(page, st)
  await renderBtn(page).click()
  await expect(page.getByRole('status')).toContainText('The video model is not present')
  await expect(renderBtn(page)).toHaveAttribute('aria-disabled', 'false')
})

test('a dragged line moves in its shot; dropped on the next shot it names that shot', async ({ page }) => {
  const st = state()
  await board(page, st)
  await drag(page, 'l1', 1000)
  await expect.poll(() => st.calls.length).toBe(1)
  expect(st.calls[0]).toMatchObject({ path: '/edit', name: NAME, op: 'move', id: 'l1' })
  expect(st.calls[0]).not.toHaveProperty('shot')
  near(st.calls[0]!.start_ms, 1500)
  await drag(page, 'l1', 5000)
  await expect.poll(() => st.calls.length).toBe(2)
  expect(st.calls[1]).toMatchObject({ op: 'move', id: 'l1', shot: 's2' })
  near(st.calls[1]!.start_ms, 1500)
})

test('a cue, a pose and a shot box drag too; a click without travel only selects', async ({ page }) => {
  const st = state()
  await board(page, st)
  await box(page, 'c1').click()
  await expect(box(page, 'c1')).toHaveAttribute('aria-pressed', 'true')
  expect(st.calls).toEqual([])
  await drag(page, 'c1', 1000)
  await drag(page, 'p1', 500)
  await drag(page, 'shot:1.2', -3000)
  await expect.poll(() => st.calls.length).toBe(3)
  expect(st.calls.map(c => [c.op, c.id, c.shot])).toEqual([['move', 'c1', undefined], ['move', 'p1', undefined], ['move', 's2', 's1']])
  near(st.calls[0]!.start_ms, 2000)
})

test('right-click a line: Edit changes its speaker and words; Delete removes it', async ({ page }) => {
  const st = state()
  await board(page, st)
  await box(page, 'l1').click({ button: 'right' })
  await page.getByRole('menuitem', { name: 'Edit' }).click()
  const ask = page.locator('[data-region="timeline-ask"]')
  await ask.getByLabel('Speaker').selectOption('B')
  await ask.getByLabel('Words').fill('Three')
  await ask.getByLabel('Words').press('Enter')
  await expect.poll(() => st.calls.length).toBe(1)
  expect(st.calls[0]).toEqual({ path: '/edit', name: NAME, op: 'change', id: 'l1', fields: { speaker: 'B', words: 'Three' } })
  await expect(ask).toHaveCount(0)
  await box(page, 'c1').click({ button: 'right' })
  await page.getByRole('menuitem', { name: 'Delete' }).click()
  await expect.poll(() => st.calls.length).toBe(2)
  expect(st.calls[1]).toEqual({ path: '/edit', name: NAME, op: 'remove', id: 'c1' })
})

test('right-click empty timeline: Add line on its speaker row, Add cue, Add shot after the shot there', async ({ page }) => {
  const st = state()
  await board(page, st)
  const ask = page.locator('[data-region="timeline-ask"]')
  await rightAt(page, 'line:b', 7000)
  await page.getByRole('menuitem', { name: 'Add line' }).click()
  await expect(ask.getByLabel('Speaker')).toHaveValue('B')
  await ask.getByLabel('Words').fill('Four')
  await ask.getByLabel('Words').press('Enter')
  await expect.poll(() => st.calls.length).toBe(1)
  expect(st.calls[0]).toMatchObject({ path: '/edit', name: NAME, op: 'add_line', shot: 's2', speaker: 'B', words: 'Four' })
  near(st.calls[0]!.start_ms, 3000)
  await rightAt(page, 'cues', 2000)
  await page.getByRole('menuitem', { name: 'Add cue' }).click()
  await ask.getByLabel('Cue').selectOption('music')
  await ask.getByLabel('Words').fill('Five')
  await ask.getByLabel('Words').press('Enter')
  await expect.poll(() => st.calls.length).toBe(2)
  expect(st.calls[1]).toMatchObject({ op: 'add_cue', shot: 's1', cue: 'music', words: 'Five' })
  near(st.calls[1]!.start_ms, 2000)
  await rightAt(page, 'pose:a', 8000)
  await page.getByRole('menuitem', { name: 'Add shot' }).click()
  await ask.getByLabel('Framing').fill('Medium')
  await ask.getByLabel('Framing').press('Enter')
  await expect.poll(() => st.calls.length).toBe(3)
  expect(st.calls[2]).toEqual({ path: '/edit', name: NAME, op: 'add_shot', scene: 1, camera: { framing: 'Medium' }, after: 's2' })
})

test('an edit refused shows its one line', async ({ page }) => {
  const st = state({ refuse: 'Line l1 has events anchored to it' })
  await board(page, st)
  await box(page, 'l1').click({ button: 'right' })
  await page.getByRole('menuitem', { name: 'Delete' }).click()
  await expect(page.getByRole('status')).toContainText('Line l1 has events anchored to it')
})

test('timeline edits: shots picked by click, Shift-click and Alt-click, deleted by the key; a shot stretched by its edge, rendered alone', async ({ page }) => {
  const st = state()
  await board(page, st)
  await box(page, 'shot:1.1').click(); await box(page, 'shot:1.2').click({ modifiers: ['Shift'] })
  await expect(box(page, 'shot:1.1')).toHaveAttribute('aria-pressed', 'true')
  await expect(box(page, 'shot:1.2')).toHaveAttribute('aria-pressed', 'true')
  await page.keyboard.press('Delete')
  await expect.poll(() => st.calls.filter(c => c.op === 'remove').map(c => c.id)).toEqual(['s1', 's2'])
  st.calls.length = 0
  await box(page, 'shot:1.2').click(); await box(page, 'shot:1.1').click({ modifiers: ['Alt'] })
  await page.keyboard.press('Delete')
  await expect.poll(() => st.calls.filter(c => c.op === 'remove').map(c => c.id)).toEqual(['s2', 's1'])
  st.calls.length = 0
  const item = page.locator('[data-region="shot-list"] [data-shot="shot:1.2"]')
  await expect(item.locator('[data-field="Framing"]')).toHaveValue('Close')
  await item.locator('[data-field="Action"]').fill('action 1'); await item.locator('[data-field="Framing"]').click()
  await expect.poll(() => st.calls.find(c => c.op === 'change')).toMatchObject({ id: 's2', fields: { action: 'action 1' } })
  st.calls.length = 0
  const edge = (await page.locator('[data-edge="shot:1.1"]').boundingBox())!
  const per = await pps(page)
  const [ex, ey] = [edge.x + edge.width / 2, edge.y + edge.height / 2]
  await page.mouse.move(ex, ey); await page.mouse.down(); await page.mouse.move(ex + per * 3, ey, { steps: 5 }); await page.mouse.up()
  await expect.poll(() => st.calls.find(c => c.op === 'change')).toMatchObject({ id: 's1', fields: { seconds: 7 } })
  await box(page, 'shot:1.2').click({ button: 'right' })
  await page.getByRole('menuitem', { name: 'Render this shot' }).click()
  await expect.poll(() => st.calls.find(c => c.path === '/render')).toMatchObject({ name: NAME, shot: 's2' })
})

test('a shot\'s Edit saves with empty fields, by Enter or by a click elsewhere', async ({ page }) => {
  const st = state()
  await board(page, st)
  await box(page, 'shot:1.1').click({ button: 'right' })
  await page.getByRole('menuitem', { name: 'Edit' }).click()
  const ask = page.locator('[data-region="timeline-ask"]')
  await expect(ask.getByPlaceholder('Framing')).toBeFocused()
  await ask.getByPlaceholder('Seconds').fill('9'); await ask.getByPlaceholder('Seconds').press('Enter')
  await expect.poll(() => st.calls.find(c => c.op === 'change')).toMatchObject({ id: 's1', fields: { seconds: 9 } })
  st.calls.length = 0
  await box(page, 'shot:1.2').click({ button: 'right' })
  await page.getByRole('menuitem', { name: 'Edit' }).click()
  await expect(ask.getByPlaceholder('Framing')).toBeFocused()             // the box is open and settled
  await ask.getByPlaceholder('Action').fill('action 1')
  await page.locator('[data-region="context"]').click({ position: { x: 5, y: 5 } })
  await expect.poll(() => st.calls.find(c => c.op === 'change')).toMatchObject({ id: 's2', fields: { action: 'action 1' } })
})

test('the Video LoRAs under the shot list: a toggle and a strength, each saved at once', async ({ page }) => {
  const st = state()
  await board(page, st)
  const row = page.locator('[data-region="video-loras"] [data-lora="lora 1.safetensors"]')
  await row.locator('input[type="checkbox"]').check()
  await expect.poll(() => st.calls.find(c => c.route === '/video-loras')).toMatchObject({ path: '/v/lora 1.safetensors', on: true })
  st.calls.length = 0
  await row.locator('input[type="number"]').fill('0.6'); await row.locator('input[type="number"]').press('Enter')
  await expect.poll(() => st.calls.find(c => c.route === '/video-loras')).toMatchObject({ strength: 0.6 })
})
