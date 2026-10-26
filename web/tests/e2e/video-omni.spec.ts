// Stage 7 on Omni: a Detail menu on the video sheet (the engine's choices, saved per model in the card; none on
// First / Last), each identity box's own menu with "Cut out background" (a small mark while on; the job carries it),
// and a picture outside 1:4 to 4:1 kept out of an identity box with one line.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState, type ApiState } from './fixtures/api'
import { open } from './helpers'

const H3 = 'minimax_h3'
const OMNI = 'minimax_h3_ref2va'
type Box = { id: string; w: number; h: number; cutout?: boolean }
const PICS: Box[] = [{ id: 'out/2026-10-09/a.png', w: 1024, h: 1024 }, { id: 'out/2026-10-09/b.png', w: 900, h: 1600 }]
const DRAFT = {
  model: OMNI, prompt: '', lorasByModel: {}, aspect: 'auto', size: 1, images: 1,
  advancedByModel: {}, references: PICS, selected: null, draft: 'Two friends at a table',
}
type Saved = typeof DRAFT & { references: Box[]; advancedByModel: Record<string, { detail?: string }> }
const slot = (page: Page, n: number) => page.locator(`[data-socket="reference_${n}"]`)
const note = (page: Page) => page.locator('[data-region="references"] [role="status"]')
const lib = (page: Page) => page.locator('[data-region="video-sheet"]')
const detail = (page: Page) => lib(page).getByRole('combobox', { name: 'Detail' })
const menu = (page: Page, name: string) => page.getByRole('menu', { name })
const draftOf = (st: ApiState) => st.draft as Saved
const lastPut = (st: ApiState) => st.calls.filter(c => c.method === 'PUT' && c.path === '/api/generate-image/draft').at(-1)?.body as Partial<Saved> | undefined

async function start(page: Page, over: Partial<Saved> = {}, cap = 3): Promise<{ hub: FakeHub; st: ApiState }> {
  const r = await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, ...over } }))
  await expect(page.locator('[data-region="references"]')).toHaveAttribute('data-cap', String(cap))
  return r
}
/** A video model's rows are on the sheet Video raises. */
async function raise(page: Page) {
  await page.locator('[data-region="video-toggle"]').click()
  await expect.poll(() => page.locator('[data-region="library-sheet"]').getAttribute('inert')).toBeNull()
  await expect.poll(() => page.evaluate(() => Math.abs(document.querySelector('[data-region="video-sheet"]')!.getBoundingClientRect().top
    - document.querySelector('[data-region="library-sheet"]')!.getBoundingClientRect().top))).toBeLessThan(1)
}
async function submitted(hub: FakeHub, page: Page): Promise<Record<string, unknown>> {
  const n = hub.sent('job.submit').length
  await page.locator('[data-region="generate"]').click()
  await expect.poll(() => hub.sent('job.submit').length).toBe(n + 1)
  return (hub.sent('job.submit').at(-1)!.d as { params: Record<string, unknown> }).params
}

test('Omni: Detail sits under Text encoder with the engine\'s choices; Maximum detail reaches the draft PUT', async ({ page }) => {
  const { st } = await start(page)
  await raise(page)
  await expect(lib(page).locator('[data-region="detail"] > span')).toHaveText('Detail')
  await expect(detail(page)).toHaveValue('match')
  await expect(detail(page).locator('option')).toHaveText(['Match output', 'Maximum detail'])
  const enc = (await lib(page).locator('[data-region="text-encoder"]').boundingBox())!
  const row = (await lib(page).locator('[data-region="detail"]').boundingBox())!
  expect(row.y).toBeGreaterThanOrEqual(enc.y + enc.height - 1)
  await detail(page).selectOption('max')
  await expect.poll(() => draftOf(st).advancedByModel?.[OMNI]?.detail, { timeout: 4000 }).toBe('max')
  expect(lastPut(st)?.advancedByModel?.[OMNI]?.detail).toBe('max')
  // the card keeps it: a reload shows it again
  await page.reload()
  await raise(page)
  await expect(detail(page)).toHaveValue('max')
})

test('First / Last: no Detail on the sheet (the Text encoder stays)', async ({ page }) => {
  await start(page, { model: H3, references: [] }, 2)
  await raise(page)
  await expect(lib(page).locator('[data-region="text-encoder"]')).toBeVisible()
  await expect(lib(page).locator('[data-region="detail"]')).toHaveCount(0)
  await expect(page.getByRole('combobox', { name: 'Detail' })).toHaveCount(0)
})

test('an identity box\'s menu: Cut out background on (a mark, the title, the draft, the job), then Keep background', async ({ page }) => {
  const { hub, st } = await start(page)
  expect(await submitted(hub, page)).not.toHaveProperty('cutout')
  await slot(page, 2).click({ button: 'right' })
  await expect(menu(page, 'Identity 2').getByRole('menuitem')).toHaveText(['Cut out background', 'Remove'])
  await menu(page, 'Identity 2').getByRole('menuitem', { name: 'Cut out background' }).click()
  await expect(menu(page, 'Identity 2')).toHaveCount(0)
  await expect(slot(page, 2)).toHaveAttribute('data-cutout', 'true')
  await expect(slot(page, 2).locator('img')).toHaveAttribute('title', 'Identity 2 · background cut out')
  await expect(slot(page, 2).locator('img')).toHaveAttribute('alt', 'Identity 2')
  await expect(slot(page, 1)).not.toHaveAttribute('data-cutout', /.*/)
  const mark = await slot(page, 2).evaluate(el => {
    const m = el.querySelector('span[aria-hidden="true"]:not(.num)')!.getBoundingClientRect(), b = el.getBoundingClientRect()
    return { w: m.width, inside: m.left >= b.left && m.right <= b.right + 0.5 && m.top >= b.top - 0.5 && m.bottom <= b.bottom }
  })
  expect(mark.w).toBeGreaterThan(2)
  expect(mark.inside).toBe(true)
  await expect.poll(() => draftOf(st).references?.map(r => r.cutout === true), { timeout: 4000 }).toEqual([false, true])
  expect(lastPut(st)?.references?.[1]).toEqual({ ...PICS[1], cutout: true })
  expect(await submitted(hub, page)).toMatchObject({ model: OMNI, references: PICS.map(p => p.id), cutout: [false, true] })
  // the keyboard: Shift+F10 (or the menu key) on the box's Remove button opens the same menu, now saying Keep background
  const remove = slot(page, 2).getByRole('button', { name: 'Remove identity 2' })
  await remove.focus()
  await page.keyboard.press('Shift+F10')
  await expect(menu(page, 'Identity 2').getByRole('menuitem')).toHaveText(['Keep background', 'Remove'])
  await page.keyboard.press('Escape')
  await expect(menu(page, 'Identity 2')).toHaveCount(0)
  await remove.focus()
  await page.keyboard.press('ContextMenu')
  await menu(page, 'Identity 2').getByRole('menuitem', { name: 'Keep background' }).click()
  await expect(slot(page, 2)).not.toHaveAttribute('data-cutout', /.*/)
  await expect(slot(page, 2).locator('img')).toHaveAttribute('title', 'Identity 2')
  await expect.poll(() => draftOf(st).references?.[1], { timeout: 4000 }).toEqual(PICS[1])
  expect(await submitted(hub, page)).not.toHaveProperty('cutout')
})

test('the flag travels with its picture: Remove from the menu shifts box 2 (cut out) into box 1', async ({ page }) => {
  const { hub, st } = await start(page, { references: [PICS[0]!, { ...PICS[1]!, cutout: true }] })
  await expect(slot(page, 2)).toHaveAttribute('data-cutout', 'true')
  await slot(page, 1).click({ button: 'right' })
  await menu(page, 'Identity 1').getByRole('menuitem', { name: 'Remove' }).click()
  await expect(slot(page, 1)).toHaveAttribute('data-cutout', 'true')
  await expect(slot(page, 2)).toHaveAttribute('aria-label', 'Identity 2, empty')
  await expect.poll(() => draftOf(st).references, { timeout: 4000 }).toEqual([{ ...PICS[1], cutout: true }])
  expect(await submitted(hub, page)).toMatchObject({ references: [PICS[1]!.id], cutout: [true] })
})

test('First / Last: the box menu has Remove only; a flag left from Omni shows no mark and is not sent', async ({ page }) => {
  const { hub } = await start(page, { model: H3, references: [PICS[0]!, { ...PICS[1]!, cutout: true }] }, 2)
  await slot(page, 1).click({ button: 'right' })
  await expect(menu(page, 'Start frame').getByRole('menuitem')).toHaveText(['Remove'])
  await page.keyboard.press('Escape')
  await expect(menu(page, 'Start frame')).toHaveCount(0)
  await expect(slot(page, 2)).not.toHaveAttribute('data-cutout', /.*/)
  await expect(slot(page, 2).locator('img')).toHaveAttribute('title', 'Last frame')
  const params = await submitted(hub, page)
  expect(params).toMatchObject({ model: H3, references: PICS.map(p => p.id) })
  expect(params).not.toHaveProperty('cutout')
})

test('shape: a 1×4.25 picture Sent to Omni is not placed and the box says why; 1×4 is placed', async ({ page }) => {
  const { hub, st } = await start(page, { references: [] })
  const ws = hub.lines.find(l => l.role === 'workspace')!
  const item = (n: string, w: number, h: number) => ({ id: `out/2026-10-09/${n}.png`, kind: 'image', url: `/files/out/2026-10-09/${n}.png?w=${w}&h=${h}` })
  hub.send(ws, 'deliver', { tool: 'generate-image', socket: 'reference', from: { role: 'media' }, items: [item('tall', 400, 1700)] }, { id: 'snd1' })
  await expect.poll(() => hub.sent('received').length).toBe(1)
  await expect(note(page)).toHaveText('H3 Omni — Pruned takes pictures between 1:4 and 4:1')
  await expect(page.locator('[data-region="references"] img')).toHaveCount(0)
  expect(hub.sent('received')[0]!.d).toMatchObject({ placed: [], refused: [{ item: 'out/2026-10-09/tall.png', reason: 'shape' }] })
  hub.send(ws, 'deliver', { tool: 'generate-image', socket: 'reference', from: { role: 'media' }, items: [item('edge', 400, 1600)] }, { id: 'snd2' })
  await expect.poll(() => hub.sent('received').length).toBe(2)
  await expect(slot(page, 1).locator('img')).toHaveAttribute('alt', 'Identity 1')
  await expect.poll(() => draftOf(st).references, { timeout: 4000 }).toEqual([{ id: 'out/2026-10-09/edge.png', w: 400, h: 1600 }])
})
