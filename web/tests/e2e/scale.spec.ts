// The size is fixed per screen: Ctrl+wheel and Ctrl +/−/0 are consumed and change nothing; over the Media Stage they zoom the image only.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { ZERO, open, regionRects, rootScroll, settle } from './helpers'
import { MEDIA_SCALE, expectedRoot, rootPx } from './fit'

test.use({ viewport: { width: 2000, height: 1130 } })
const BASE = expectedRoot(2000, 1130)

const record = (page: Page) => page.evaluate(() => {
  const w = window as unknown as { prevented: boolean[] }
  w.prevented = []
  addEventListener('wheel', e => { if (e.ctrlKey) setTimeout(() => w.prevented.push(e.defaultPrevented)) }, { passive: true })
  addEventListener('keydown', e => { if (e.ctrlKey && e.key !== 'Control') setTimeout(() => w.prevented.push(e.defaultPrevented)) })
})
const prevented = (page: Page) => page.evaluate(() => (window as unknown as { prevented: boolean[] }).prevented)
async function ctrlWheel(page: Page, x: number, y: number, dy: number): Promise<void> {
  await page.mouse.move(x, y)
  await page.keyboard.down('Control')
  await page.mouse.wheel(0, dy)
  await page.keyboard.up('Control')
}
const centre = async (page: Page, sel: string) => {
  const b = (await page.locator(sel).first().boundingBox())!
  return [b.x + b.width / 2, b.y + b.height / 2] as const
}

test('Ctrl+wheel and Ctrl +/−/0 are consumed and change nothing on Generate', async ({ page }) => {
  await open(page, '/')
  await page.locator('[data-region="bar"]').waitFor()
  await settle(page)
  const before = await regionRects(page)
  await record(page)
  for (const sel of ['[data-scroll="chat"]', '[data-region="draft"]', '[data-region="generate"]']) {
    const [x, y] = await centre(page, sel)
    await ctrlWheel(page, x, y, -300)
    await ctrlWheel(page, x, y, 300)
  }
  await page.mouse.click(1000, 600)
  for (const k of ['Control+Equal', 'Control+Minus', 'Control+0']) await page.keyboard.press(k)
  await settle(page)
  expect(await prevented(page)).toEqual(Array(9).fill(true))
  expect(await rootPx(page)).toBeCloseTo(BASE, 1)
  expect(await regionRects(page)).toEqual(before)
  expect(await rootScroll(page)).toEqual(ZERO)
})

test('over the Stage, wheel and Ctrl+wheel zoom the image only; drag pans with a hand; nothing else moves', async ({ page }) => {
  await open(page, '/media', new FakeHub(), apiState())
  const img = page.locator('[data-stage-img]')
  await img.waitFor()
  await expect.poll(() => img.evaluate(el => (el as HTMLImageElement).complete && el.style.opacity === '1')).toBe(true)
  await settle(page)
  const root = BASE * MEDIA_SCALE
  expect(await rootPx(page)).toBeCloseTo(root, 1)
  await record(page)
  const before = await regionRects(page)
  const t0 = await img.evaluate(el => el.style.transform)
  const [x, y] = await centre(page, '[data-region="stage"]')
  await ctrlWheel(page, x, y, -200)
  await settle(page)
  const t1 = await img.evaluate(el => el.style.transform)
  expect(t1).not.toBe(t0)
  expect(await prevented(page)).toEqual([true])
  await page.mouse.wheel(0, -200)
  await expect.poll(() => img.evaluate(el => el.style.transform)).not.toBe(t1)

  const board = page.locator('[data-region="stage"]')
  await expect(board).toHaveCSS('cursor', 'grab')
  const t2 = await img.evaluate(el => el.style.transform)
  await page.mouse.down()
  await expect(board).toHaveCSS('cursor', 'grabbing')
  await page.mouse.move(x + 120, y + 60, { steps: 4 })
  await page.mouse.up()
  expect(await img.evaluate(el => el.style.transform)).not.toBe(t2)

  await page.keyboard.press('Control+0')
  await expect.poll(() => img.evaluate(el => el.style.transform)).toBe(t0)
  await page.keyboard.press('Control+1')
  await expect.poll(() => img.evaluate(el => el.style.transform)).not.toBe(t0)
  await page.mouse.dblclick(x, y)
  await expect.poll(() => img.evaluate(el => el.style.transform)).toBe(t0)

  const [gx, gy] = await centre(page, '[data-scroll="media-grid"]')
  await ctrlWheel(page, gx, gy, -300)
  await page.keyboard.press('Control+Minus')
  await settle(page)
  expect(await rootPx(page)).toBeCloseTo(root, 1)
  expect(await regionRects(page)).toEqual(before)
  expect(await rootScroll(page)).toEqual(ZERO)
})
