// Generate — the bar's button and Ctrl+Enter alike — renders the assistant's DRAFT; nothing ever renders the prompt
// box (the words typed to the assistant).
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { open } from './helpers'

const DRAFT = {
  model: 'flux2_klein_9b', prompt: 'B', lorasByModel: {}, aspect: '16:9', size: 1.5, images: 2,
  advancedByModel: {}, references: [], selected: null, draft: 'D',
}
const prompts = (hub: FakeHub) => hub.sent('job.submit').map(e => (e.d as { params: { prompt: string } }).params.prompt)
const ready = (page: Page) => page.locator('[data-lora]').first().waitFor()

test('the bar\'s Generate and Ctrl+Enter in the box both send the draft; the box is never sent and stays', async ({ page }) => {
  const { hub } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  await expect(page.locator('#prompt')).toHaveValue('B')
  await expect(page.locator('[data-region="draft"]')).toContainText('D')
  const go = page.locator('[data-region="generate"]')
  await expect(go).toHaveAttribute('aria-disabled', 'false')
  await go.click()
  await expect.poll(() => prompts(hub)).toEqual(['D'])
  await page.locator('#prompt').press('Control+Enter')
  await expect.poll(() => prompts(hub)).toEqual(['D', 'D'])
  await expect(page.locator('#prompt')).toHaveValue('B')
})

test('with an empty draft neither Generate nor Ctrl+Enter sends anything; both say The draft is empty', async ({ page }) => {
  const { hub } = await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, draft: '' } }))
  await ready(page)
  const go = page.locator('[data-region="generate"]')
  await expect(go).toHaveAttribute('aria-disabled', 'true')
  await expect(go).toHaveAttribute('title', 'The draft is empty')
  await go.click({ force: true })                   // aria-disabled only: the press still runs and says why
  await expect(page.getByRole('status').getByText('The draft is empty').first()).toBeVisible()
  await page.waitForTimeout(300)
  expect(hub.sent('job.submit')).toHaveLength(0)
  // the box holds text, but Ctrl+Enter renders the draft only: nothing is sent
  await expect(page.getByRole('status').getByText('The draft is empty')).toHaveCount(0, { timeout: 8000 })   // the first toast goes
  await page.locator('#prompt').press('Control+Enter')
  await expect(page.getByRole('status').getByText('The draft is empty').first()).toBeVisible()
  await page.waitForTimeout(300)
  expect(hub.sent('job.submit')).toHaveLength(0)
})

test('with an empty box Ctrl+Enter still sends the draft', async ({ page }) => {
  const { hub } = await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, prompt: '' } }))
  await ready(page)
  await page.locator('#prompt').press('Control+Enter')
  await expect.poll(() => prompts(hub)).toEqual(['D'])
  await expect(page.getByRole('status').getByText('Write a prompt')).toHaveCount(0)
})
