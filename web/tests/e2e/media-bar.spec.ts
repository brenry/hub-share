// Media's bar in the bottom right: the two folds (tree out over the Stage, thumbnails down into the bar) and the fold-up.
import { expect, test } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { MEDIA_DRAFT, row, tiles, twoWindows } from './fixtures/mediaPage'
import { open } from './helpers'

test('the folds: the tree rolls out over the Stage, the thumbnails roll down into the bar; the Stage never moves', async ({ page }) => {
  await open(page, '/media', new FakeHub(), apiState())
  await tiles(page).first().waitFor()
  const stage = (await page.locator('[data-region="stage"]').boundingBox())!
  const fold = page.locator('[data-region="fold"]')
  const tree = page.locator('[data-region="tree-col"]')
  const tile = (await tiles(page).first().boundingBox())!
  const t = (await tree.boundingBox())!
  expect(Math.abs(t.x + t.width - (tile.x - 20))).toBeLessThan(24)
  expect(t.x).toBeGreaterThan(stage.x)
  await fold.click()
  await expect(fold).toHaveAttribute('aria-expanded', 'false')
  await expect.poll(() => tree.boundingBox().then(b => b?.width ?? 0)).toBeLessThan(2)
  expect(await tiles(page).first().boundingBox()).toEqual(tile)
  expect(await page.locator('[data-region="stage"]').boundingBox()).toEqual(stage)
  await fold.click()
  await expect.poll(() => tree.boundingBox().then(b => Math.round(b!.width))).toBe(Math.round(t.width))
  const thumbs = page.locator('[data-region="thumbs"]')
  const bar = (await page.locator('[data-region="bar"]').boundingBox())!
  await thumbs.click()
  await expect(thumbs).toHaveAttribute('aria-expanded', 'false')
  await expect(fold).toHaveAttribute('aria-expanded', 'false')
  await expect.poll(() => tiles(page).first().boundingBox().then(b => Math.round(b!.y))).toBeGreaterThanOrEqual(Math.round(bar.y))
  expect(await page.locator('[data-region="bar"]').boundingBox()).toEqual(bar)
  expect(await page.locator('[data-region="stage"]').boundingBox()).toEqual(stage)
  await thumbs.click()
  await expect(thumbs).toHaveAttribute('aria-expanded', 'true')
  await expect(fold).toHaveAttribute('aria-expanded', 'false')
  await expect.poll(() => tiles(page).first().boundingBox().then(b => Math.round(b!.y))).toBe(Math.round(tile.y))
  expect(bar.height).toBeLessThan(32)
})

test('Generate is its own button in the corner; cache and seed fold up as icons', async ({ page }) => {
  const { media, hub, st } = await twoWindows(page)
  const go = media.locator('[data-region="generate"]')
  const bar = (await media.locator('[data-region="bar"]').boundingBox())!
  const g = (await go.boundingBox())!
  expect(bar.x + bar.width - (g.x + g.width)).toBeLessThan(20)
  await go.click()
  await expect(media.getByText('Queued')).toBeVisible()
  // Media's Generate renders the saved draft's `draft` (the assistant's), not the prompt box
  expect(hub.got.filter(e => e.t === 'job.submit').map(e => (e.d as { params: { prompt: string } }).params.prompt)).toEqual(['A grey cat in the rain'])
  await media.locator('[data-region="utilities"]').click()
  const strip = media.getByRole('menu', { name: 'Cache and seed' })
  await expect(strip.getByRole('menuitem')).toHaveCount(2)
  await expect(strip).not.toContainText(/\w/)
  expect((await strip.boundingBox())!.y + (await strip.boundingBox())!.height).toBeLessThan(bar.y)
  await strip.getByRole('menuitem', { name: 'Seed back to random' }).click()
  await expect(media.getByText('Seed: random')).toBeVisible()
  expect(st.calls.some(c => c.path === '/api/generate-image/seed/random')).toBe(true)
  await media.locator('[data-region="utilities"]').click()
  await strip.getByRole('menuitem', { name: 'Clear the GPU cache' }).click()
  await expect.poll(() => hub.got.some(e => e.t === 'gpu.release')).toBe(true)
})

test("Media's Generate with no draft sends nothing and says The draft is empty", async ({ page }) => {
  const { media, hub } = await twoWindows(page, { ...MEDIA_DRAFT, draft: '' })
  await media.locator('[data-region="generate"]').click()
  await expect(media.getByText('The draft is empty')).toBeVisible()
  expect(hub.got.some(e => e.t === 'job.submit')).toBe(false)
})

test('thumbnails down folds both; the column is see-through, the Stage pans there; the tree opens both, never alone', async ({ page }) => {
  await open(page, '/media', new FakeHub(), apiState())
  await page.locator('[data-stage-img]').waitFor()
  const img = page.locator('[data-stage-img]')
  const fitted = await img.evaluate(el => el.style.transform)
  const tree = page.locator('[data-region="tree-col"]')
  const fold = page.locator('[data-region="fold"]')
  const thumbs = page.locator('[data-region="thumbs"]')
  await thumbs.click()
  await expect(thumbs).toHaveAttribute('aria-expanded', 'false')
  expect(await img.evaluate(el => el.style.transform)).toBe(fitted)
  const side = (await page.locator('[data-region="side"]').boundingBox())!
  await page.waitForTimeout(300)
  await page.mouse.move(side.x + side.width / 2, side.y + side.height / 2)
  await page.mouse.wheel(0, -400)
  await expect.poll(() => img.evaluate(el => el.style.transform)).not.toBe(fitted)
  await expect(fold).toHaveAttribute('aria-expanded', 'false')
  await fold.click()
  await expect(fold).toHaveAttribute('aria-expanded', 'true')
  await expect(thumbs).toHaveAttribute('aria-expanded', 'true')
  await fold.click()
  await expect(fold).toHaveAttribute('aria-expanded', 'false')
  await expect(thumbs).toHaveAttribute('aria-expanded', 'true')
  await expect.poll(() => tree.boundingBox().then(b => b?.width ?? 0)).toBeLessThan(2)
})

test.describe('inside HocusPocus Desktop', () => {
  test.use({ userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Electron/44.7.0 Safari/537.36 HocusPocusDesktop/1.2.1 tags=2,3' })

  test('the launch fold-up lists the client\'s tags; one opens hpd:instance/<tag>', async ({ page }) => {
    await page.addInitScript(() => {
      const w = window as unknown as { opened: string[]; open: (url?: string | URL) => null }
      w.opened = []
      w.open = url => { w.opened.push(String(url)); return null }
    })
    await open(page, '/media', new FakeHub(), apiState())
    await tiles(page).first().waitFor()
    await page.locator('[data-region="bar"] [data-region="launch"]').click()
    const menu = page.getByRole('menu', { name: 'Open an instance' })
    await expect(menu.getByRole('menuitem')).toHaveText(['2', '3'])
    await menu.getByRole('menuitem', { name: '2' }).click()
    await expect(menu).toHaveCount(0)
    expect(await page.evaluate(() => (window as unknown as { opened: string[] }).opened)).toEqual(['hpd:instance/2'])
  })

  test('a fold-up opened by keyboard focuses its first item; ArrowDown and ArrowUp walk the items; Enter picks', async ({ page }) => {
    await page.addInitScript(() => {
      const w = window as unknown as { opened: string[]; open: (url?: string | URL) => null }
      w.opened = []
      w.open = url => { w.opened.push(String(url)); return null }
    })
    await open(page, '/media', new FakeHub(), apiState())
    await tiles(page).first().waitFor()
    await page.locator('[data-region="bar"] [data-region="launch"]').focus()
    await page.keyboard.press('Enter')
    const items = page.getByRole('menu', { name: 'Open an instance' }).getByRole('menuitem')
    await expect(items.nth(0)).toBeFocused()
    await page.keyboard.press('ArrowDown')
    await expect(items.nth(1)).toBeFocused()
    await page.keyboard.press('ArrowDown')
    await expect(items.nth(0)).toBeFocused()
    await page.keyboard.press('ArrowUp')
    await expect(items.nth(1)).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(items).toHaveCount(0)
    expect(await page.evaluate(() => (window as unknown as { opened: string[] }).opened)).toEqual(['hpd:instance/3'])
  })
})

test('previous and next step through the images; the position is small and grey', async ({ page }) => {
  const st = apiState()
  await open(page, '/media', new FakeHub(), st)
  await tiles(page).first().waitFor()
  const prev = page.locator('[data-region="prev"]'), next = page.locator('[data-region="next"]')
  await expect(page.locator('[data-region="count"]')).toHaveText('1 / 60')
  await expect(prev).toBeDisabled()
  await next.click()
  await next.click()
  await expect(page.locator(`[data-item="${st.media[2]!.id}"]`)).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('[data-region="count"]')).toHaveText('3 / 60')
  await prev.click()
  await expect(page.locator('[data-region="count"]')).toHaveText('2 / 60')
  expect(await page.locator('[data-region="count"]').evaluate(el => getComputedStyle(el).fontWeight)).toBe('400')
})


test('whatever fold opens again comes up on Temp, however deep the window was', async ({ page }) => {
  await open(page, '/media', new FakeHub(), apiState())
  await tiles(page).first().waitFor()
  const fold = page.locator('[data-region="fold"]')
  const thumbs = page.locator('[data-region="thumbs"]')
  await row(page, 'drive:image').click()
  await row(page, 'drive:image/portraits').click()
  await expect(tiles(page)).toHaveCount(3)
  await thumbs.click()
  await expect(thumbs).toHaveAttribute('aria-expanded', 'false')
  await thumbs.click()
  await expect(thumbs).toHaveAttribute('aria-expanded', 'true')
  await expect(row(page, 'temp')).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('[data-region="count"]')).toHaveText('1 / 60')
  await fold.click()
  await expect(fold).toHaveAttribute('aria-expanded', 'true')
  await row(page, 'drive:image/portraits').click()
  await expect(tiles(page)).toHaveCount(3)
  await fold.click()
  await expect(fold).toHaveAttribute('aria-expanded', 'false')
  await expect(tiles(page)).toHaveCount(3)
  await fold.click()
  await expect(fold).toHaveAttribute('aria-expanded', 'true')
  await expect(row(page, 'temp')).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('[data-region="count"]')).toHaveText('1 / 60')
  await row(page, 'drive:image/portraits').click()
  await thumbs.click()
  await fold.click()
  await expect(fold).toHaveAttribute('aria-expanded', 'true')
  await expect(thumbs).toHaveAttribute('aria-expanded', 'true')
  await expect(row(page, 'temp')).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('[data-region="count"]')).toHaveText('1 / 60')
})

test('the Stage: each picture comes up at Fit, centred on the window, filling its height or its width', async ({ page }) => {
  const st = apiState()
  const shape = (n: number, w: number, h: number) => { st.media[n] = { ...st.media[n]!, w, h, url: `${st.media[n]!.url}?w=${w}&h=${h}` } }
  shape(0, 1024, 1024)
  shape(1, 1920, 1080)
  shape(2, 800, 1200)
  await open(page, '/media', new FakeHub(), st)
  await page.locator('[data-stage-img]').waitFor()
  const img = page.locator('[data-stage-img]')
  const view = page.viewportSize()!
  const shown = () => img.evaluate(el => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height } })
  const expectFit = async (w: number, h: number) => {
    await expect.poll(async () => (await shown()).w).toBeGreaterThan(0)
    const sc = Math.min(view.width / w, view.height / h)
    const r = await shown()
    expect([r.w, r.h, r.x + r.w / 2, r.y + r.h / 2].map(Math.round)).toEqual([w * sc, h * sc, view.width / 2, view.height / 2].map(Math.round))
  }
  await expect(img).toHaveAttribute('src', st.media[0]!.url)
  await expectFit(1024, 1024)
  await page.locator('[data-region="thumbs"]').click()
  await page.locator('[data-region="next"]').click()
  await expect(img).toHaveAttribute('src', st.media[1]!.url)
  await expectFit(1920, 1080)
  await page.locator('[data-region="next"]').click()
  await expect(img).toHaveAttribute('src', st.media[2]!.url)
  await expectFit(800, 1200)
  await expect(page.locator('[data-region="stage"]')).toContainText('Fit')
})
