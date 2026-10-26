// The bar's Steps and Count: Steps is a typeable number (saved per model), nudged by keys and the small arrows; − n + sets images.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { open } from './helpers'

const DRAFT = {
  model: 'flux2_klein_9b', prompt: 'B', lorasByModel: {}, aspect: '16:9', size: 1.5, images: 2,
  advancedByModel: {}, references: [], selected: null, draft: 'D',
}
const ready = (page: Page) => page.locator('[data-lora]').first().waitFor()
type Saved = { advancedByModel?: Record<string, { steps: number }>; images?: number }

test('Steps takes a typed number and saves it for the model; keys and arrows nudge it', async ({ page }) => {
  const { hub, st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  const steps = page.getByRole('spinbutton', { name: 'Steps' })
  await expect(steps).toHaveValue('4')
  await steps.fill('25')
  await expect(steps).toHaveValue('25')
  const puts = () => st.calls.filter(c => c.path === '/api/generate-image/draft' && c.method === 'PUT').map(c => c.body as Saved)
  await expect.poll(() => puts().some(b => b.advancedByModel?.flux2_klein_9b?.steps === 25), { timeout: 4000 }).toBe(true)
  await steps.press('ArrowUp')
  await expect(steps).toHaveValue('26')
  await steps.press('ArrowDown')
  await steps.press('ArrowDown')
  await expect(steps).toHaveValue('24')
  await page.getByRole('button', { name: 'More steps' }).click()
  await expect(steps).toHaveValue('25')
  await page.getByRole('button', { name: 'Fewer steps' }).click()
  await page.getByRole('button', { name: 'Fewer steps' }).click()
  await expect(steps).toHaveValue('23')
  await expect.poll(() => (st.draft as Saved).advancedByModel?.flux2_klein_9b?.steps, { timeout: 4000 }).toBe(23)
  await page.locator('[data-region="generate"]').click()
  await expect.poll(() => hub.sent('job.submit').length).toBe(1)
  expect((hub.sent('job.submit')[0]!.d as { params: { steps: number } }).params.steps).toBe(23)
})

test('− and + set how many images one press makes, within 1 to 6', async ({ page }) => {
  const { hub, st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  const count = page.locator('[data-region="count"]')
  const [fewer, more] = [count.getByRole('button', { name: 'Fewer images' }), count.getByRole('button', { name: 'More images' })]
  await expect(count.locator('output')).toHaveText('2')
  await more.click()
  await expect(count.locator('output')).toHaveText('3')
  await fewer.click(); await fewer.click()
  await expect(count.locator('output')).toHaveText('1')
  await expect(fewer).toBeDisabled()
  for (let i = 0; i < 5; i++) await more.click()
  await expect(count.locator('output')).toHaveText('6')
  await expect(more).toBeDisabled()
  await fewer.click()
  await expect(count.locator('output')).toHaveText('5')
  await expect.poll(() => (st.draft as Saved).images, { timeout: 4000 }).toBe(5)
  await page.locator('[data-region="generate"]').click()
  await expect.poll(() => hub.sent('job.submit').length).toBe(1)
  expect((hub.sent('job.submit')[0]!.d as { params: { images: number } }).params.images).toBe(5)
})
