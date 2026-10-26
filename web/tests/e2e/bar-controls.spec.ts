// The bar's controls: Aspect (Auto = the accent square, a ratio = plain text), the Settings round trip through the
// fold-up, and Steps / images (typed and nudged, saved to the draft).
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState, type ApiState } from './fixtures/api'
import { open, openSettings } from './helpers'

const DRAFT = {
  model: 'flux2_klein_9b', prompt: 'A grey cat', lorasByModel: {}, aspect: 'auto', size: 1, images: 2,
  advancedByModel: {}, references: [], selected: null, draft: 'A grey cat in the rain',
}
const ready = (page: Page) => page.locator('[data-lora]').first().waitFor()
const saved = (st: ApiState) => st.draft as { aspect: string; images: number; advancedByModel: Record<string, { steps: number }> } | null

test('Aspect: Auto is the accent square; 16:9 is its text alone; the ratios in the menu carry no square', async ({ page }) => {
  const { st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  const aspect = page.getByRole('button', { name: 'Aspect' })
  const square = aspect.locator('i')
  await expect(square).toHaveCount(1)
  await expect(square).toHaveClass(/arLit/)
  const [color, accent] = await page.evaluate(() => {
    const sq = document.querySelector('[aria-label="Aspect"] i')!
    const probe = document.createElement('i')
    probe.style.color = 'var(--accent)'
    document.body.append(probe)
    const a = getComputedStyle(probe).color
    probe.remove()
    return [getComputedStyle(sq).color, a]
  })
  expect(color).toBe(accent)
  expect(accent).toBe('rgb(0, 211, 242)')                     // the studio palette's cyan on the workspace
  await expect(aspect).toHaveText('')

  await aspect.click()
  const menu = page.getByRole('listbox', { name: 'Aspect' })
  await expect(menu.getByRole('option')).toHaveCount(8)
  await expect(menu.getByRole('option', { name: 'Auto' }).locator('i')).toHaveCount(1)
  await expect(menu.locator('[role="option"]:not([aria-label="Auto"]) i')).toHaveCount(0)
  await menu.getByRole('option', { name: '16:9' }).click()
  await expect(aspect).toHaveText('16:9')
  await expect(square).toHaveCount(0)
  await expect.poll(() => saved(st)?.aspect, { timeout: 4000 }).toBe('16:9')

  await aspect.click()
  await expect(menu.locator('[role="option"]:not([aria-label="Auto"]) i')).toHaveCount(0)
  await expect(menu.getByRole('option', { name: '16:9' })).toHaveText('16:9')
})

test('Settings round trip: the fold-up opens Settings; Close Settings brings the Generate screen and its bar back', async ({ page }) => {
  await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  const bar = page.locator('footer[data-region="bar"]')
  await expect(page.locator('[data-region="settings-close"]')).toHaveCount(0)   // no foot while Generate shows
  await page.locator('[data-region="utilities"]').click()
  const strip = page.getByRole('menu', { name: 'Settings, cache and seed' })
  await expect(strip.getByRole('menuitem')).toHaveCount(3)
  await expect(strip.getByRole('menuitem').first()).toHaveAccessibleName('Settings')
  await strip.getByRole('menuitem', { name: 'Settings' }).click()
  await expect(page.locator('[data-region="settings"]')).toBeVisible()
  await expect(bar).toBeHidden()
  const close = page.locator('[data-region="settings-close"]')
  await expect(close).toHaveAccessibleName('Close Settings')
  await close.click()
  await expect(page.locator('[data-region="settings"]')).toHaveCount(0)
  await expect(bar).toBeVisible()
  await expect(page.locator('[data-region="generate"]')).toBeVisible()
  // a tab closes Settings too
  await openSettings(page)
  await page.getByRole('tab').first().click()
  await expect(page.locator('[data-region="settings"]')).toHaveCount(0)
  await expect(bar).toBeVisible()
})

test('Steps is typeable and saved; its arrows and the images − + change the draft', async ({ page }) => {
  const { st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  const steps = page.locator('[data-region="steps"] input')
  await expect(steps).toHaveAccessibleName('Steps')
  await expect(steps).toHaveValue('4')
  await steps.fill('25')
  await expect.poll(() => saved(st)?.advancedByModel?.flux2_klein_9b?.steps, { timeout: 4000 }).toBe(25)
  expect(st.calls.some(c => c.method === 'PUT' && c.path === '/api/generate-image/draft'
    && (c.body as { advancedByModel?: Record<string, { steps: number }> }).advancedByModel?.flux2_klein_9b?.steps === 25)).toBe(true)
  await page.getByRole('button', { name: 'More steps' }).click()
  await expect(steps).toHaveValue('26')
  await page.getByRole('button', { name: 'Fewer steps' }).click()
  await page.getByRole('button', { name: 'Fewer steps' }).click()
  await expect(steps).toHaveValue('24')
  await expect.poll(() => saved(st)?.advancedByModel?.flux2_klein_9b?.steps, { timeout: 4000 }).toBe(24)

  const count = page.locator('[data-region="count"] output')
  await expect(count).toHaveText('2')
  await page.getByRole('button', { name: 'More images' }).click()
  await page.getByRole('button', { name: 'More images' }).click()
  await expect(count).toHaveText('4')
  await page.getByRole('button', { name: 'Fewer images' }).click()
  await expect(count).toHaveText('3')
  await expect.poll(() => saved(st)?.images, { timeout: 4000 }).toBe(3)
  await expect(page.locator('[data-region="generate"]')).toHaveAccessibleName('Generate 3 images')
})
