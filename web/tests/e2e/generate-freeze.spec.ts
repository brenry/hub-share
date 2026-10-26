// Regression for the tool-server freeze: a stranded `changed` key must not hide later tool-server values on the bar.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { open } from './helpers'

const DRAFT = {
  model: 'flux2_klein_9b', prompt: 'A grey cat asleep under an apple tree', lorasByModel: {}, aspect: '16:9', size: 1.5, images: 2,
  advancedByModel: {}, references: [], selected: null, draft: 'A grey cat asleep in the rain',
}
const ready = async (page: Page) => {
  await page.locator('[data-lora]').first().waitFor(); await expect(page.locator('[data-region="generate"]')).toHaveAttribute('aria-disabled', 'false')
}
test('a tool-server bar change still lands after a failed draft save — no permanent freeze', async ({ page }) => {
  // Regression: a window keeps unsaved keys in a `changed` set that masks the server's value for those keys in
  // loadDraft. If a save PUT fails it must be retried, else the key is stranded and every later value the tool
  // server sets for it is hidden (the bar freezes after the first change). See draft.ts save()/retry().
  const { hub, st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  const steps = page.locator('[data-region="steps"] input')
  await expect(steps).toHaveValue('4')
  let puts = 0
  await page.route(/\/api\/generate-image\/draft$/, async route => {
    if (route.request().method() === 'PUT' && puts++ < 2) return route.fulfill({ status: 500, contentType: 'application/json', body: '{"text":"blip"}' })
    return route.fallback()
  })
  await page.getByRole('button', { name: 'More steps' }).click()     // stages advancedByModel; the first save PUT fails
  await expect(steps).toHaveValue('5')
  await page.waitForTimeout(3500)                                     // the retry eventually lands and clears `changed`
  st.draft = { ...(st.draft as object), advancedByModel: { flux2_klein_9b: { steps: 42, guidance: null, seed: { mode: 'random' } } } }
  hub.broadcast('generate-image.draft', {}, 'workspace')             // the assistant sets steps to 42
  await expect(steps).toHaveValue('42')                              // frozen at 5 before the fix
})

