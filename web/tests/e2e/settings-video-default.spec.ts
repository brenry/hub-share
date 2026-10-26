// Settings → Generate Image → Default models: beside Text to image and Reference to image (image models only), a
// "Default video model" select of the video models (or Not set), saved with them (`video` of PUT /api/generate-image/defaults).
import { expect, test } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { open, openSettings } from './helpers'

test('the default video model: Not set and the video models; a pick is saved, shown again after a reload, and cleared', async ({ page }) => {
  const st = apiState()
  await open(page, '/', new FakeHub(), st)
  await openSettings(page)
  await page.locator('[data-card="generate-image"]').click()
  const sec = page.getByRole('region', { name: 'Default models' })
  const pick = sec.getByRole('combobox', { name: 'Default video model' })
  await expect(pick).toHaveValue('')
  await expect(pick.locator('option')).toHaveText(['Not set', 'MiniMax H3', 'H3 Omni — Pruned'])
  // the image defaults list only the image models
  await sec.locator('[data-region="model-picker"]').first().click()
  await expect(page.getByRole('listbox', { name: 'Models' }).getByRole('option')).toHaveText(['Not set', 'Flux 2 Klein 9B', 'Qwen Image Edit Plus', 'Z-Image Turbo'])
  await page.keyboard.press('Escape')

  await pick.selectOption('minimax_h3_ref2va')
  const puts = () => st.calls.filter(c => c.method === 'PUT' && c.path === '/api/generate-image/defaults').map(c => c.body)
  const saved = (video: string | null) => ({ text: null, refs: null, video })
  await expect.poll(puts).toEqual([saved('minimax_h3_ref2va')])

  await page.reload()
  await openSettings(page)
  await page.locator('[data-card="generate-image"]').click()
  await expect(pick).toHaveValue('minimax_h3_ref2va')
  await pick.selectOption('')
  await expect.poll(puts).toEqual([saved('minimax_h3_ref2va'), saved(null)])
  await expect(pick).toHaveValue('')
})
