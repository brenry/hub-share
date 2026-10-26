import { test, expect } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { open } from './helpers'

// The bar stays one line at a narrow window with the widest values (1.5 MP, three boxes). The full check, with
// the monitor button and every viewport, is in bar-line.spec.ts; this one keeps the picture.
test('the bar stays on one line at 1366 @shot', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 })
  await open(page, '/', new FakeHub(), apiState({ draft: { model: 'flux2_klein_9b', prompt: '', lorasByModel: {}, aspect: 'auto', size: 1.5, images: 1, advancedByModel: {}, references: [], selected: null } }))
  await page.locator('[data-region="bar"]').waitFor()
  await page.locator('[data-region="bar"]').screenshot({ path: 'shots/bar-1366.png' })
  const tops = await page.evaluate(() => [...document.querySelector('[data-region="bar"]')!.children].filter(c => c.getBoundingClientRect().width > 0 && c.getBoundingClientRect().height > 0).map(c => Math.round(c.getBoundingClientRect().top + c.getBoundingClientRect().height / 2)))
  expect(Math.max(...tops) - Math.min(...tops)).toBeLessThanOrEqual(2)
  const gen = page.locator('[data-region="generate"]')
  const box = (await gen.boundingBox())!
  expect(box.x + box.width).toBeLessThanOrEqual(1366)
  // Small windows still work: every part of the redesigned Generate screen stays inside the window.
  for (const r of ['compose', 'draft', 'dock', 'status', 'side', 'chat', 'bar', 'library-toggle', 'utilities', 'generate']) {
    const b = (await page.locator(`[data-region="${r}"]`).first().boundingBox())
    expect(b, r).not.toBeNull()
    expect([r, b!.x >= 0, b!.y >= 0, b!.x + b!.width <= 1366 + 0.5, b!.y + b!.height <= 768 + 0.5]).toEqual([r, true, true, true, true])
  }
  await expect(page.locator('#prompt')).toBeVisible()
})
