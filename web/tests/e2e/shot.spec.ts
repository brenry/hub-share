import { test } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState, chatWithTools } from './fixtures/api'
import { open, openSettings } from './helpers'

// A picture of the Generate screen with a stack, for a design check. Run on demand: npx playwright test shot --grep @shot
const DRAFT = {
  model: 'flux2_klein_9b', prompt: '', aspect: 'auto', size: 1, images: 1, advancedByModel: {}, references: [], selected: null,
  lorasByModel: { flux2_klein_9b: [{ id: 'flux2_klein_9b/style/bold_ink_outlines_0.safetensors', strength: 0.75 },
    { id: 'flux2_klein_9b/people/soft_portrait_light_1.safetensors', strength: 0.45 }, { id: 'flux2_klein_9b/misc_grain_2.safetensors', strength: 1 }] },
}

test('generate screen shot @shot', async ({ page }) => {
  const st = apiState({ draft: DRAFT, chat: chatWithTools(1) })
  const ids = st.loras.slice(0, 3).map(l => l.id)
  DRAFT.lorasByModel.flux2_klein_9b.forEach((a, i) => { a.id = ids[i]! })
  await page.setViewportSize({ width: 1440, height: 960 })
  await open(page, '/', new FakeHub(), st)
  await page.locator('[data-region="bar"]').waitFor()
  await page.locator('[data-region="chat"]').waitFor()
  await page.waitForTimeout(400)
  await page.screenshot({ path: 'shots/generate.png' })
  // The stack lives in the roll-up library sheet now (the LoRA column is gone): open it for a second picture.
  await page.locator('[data-region="library-toggle"]').click()
  await page.locator('[data-region="library-toggle"][aria-expanded="true"]').waitFor()
  await page.locator('[data-region="library-sheet"]:not([inert]) [data-lora]').first().waitFor()
  await page.waitForTimeout(400)
  await page.screenshot({ path: 'shots/generate-library.png' })
})

test('settings and media shots @shot', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 })
  await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await page.locator('[data-region="bar"]').waitFor()
  await openSettings(page)
  await page.getByText('Version').waitFor()
  await page.waitForTimeout(300)
  await page.screenshot({ path: 'shots/settings.png' })
  await open(page, '/media', new FakeHub(), apiState())
  await page.locator('[data-item]').first().waitFor()
  await page.waitForTimeout(400)
  await page.screenshot({ path: 'shots/media.png' })
  await page.locator('[data-item]').nth(2).click()
  await page.locator('[data-item]').nth(5).click({ modifiers: ['Shift'] })
  await page.locator('[data-item]').nth(5).click({ button: 'right' })
  await page.getByRole('menu').waitFor()
  await page.screenshot({ path: 'shots/media-menu.png' })
  await page.keyboard.press('Escape')
  await page.locator('[data-region="fold"]').click()
  await page.waitForTimeout(400)
  await page.screenshot({ path: 'shots/media-folded.png' })
})

test('struck reference boxes @shot', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 })
  await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, model: 'z_image_turbo', lorasByModel: {} } }))
  await page.locator('[data-region="references"][data-cap="0"]').waitFor()
  await page.locator('[data-region="bar"]').screenshot({ path: 'shots/bar-shut.png' })
})
