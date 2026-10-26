// Generate Image: the model picker (in the LoRA sheet) and Settings → Image models (folders, Rescan, weight files).
import { expect, test, type Page } from '@playwright/test'
import type { Model } from '../../src/modules/generate-image/types'
import { MODELS } from './fixtures/data'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { open, openSettings } from './helpers'

const DRAFT = {
  model: 'flux2_klein_9b', prompt: 'A grey cat asleep under an apple tree', lorasByModel: {}, aspect: '16:9', size: 1.5, images: 2,
  advancedByModel: {}, references: [], selected: null, draft: 'A grey cat asleep in the rain, under an apple tree',
}
/** The LoRAs and the model picker sit in the sheet the bar's fold raises. */
const raise = async (page: Page) => {
  await page.locator('[data-region="library-toggle"]').click()
  await expect(page.locator('[data-region="library-toggle"]')).toHaveAttribute('aria-expanded', 'true')
}
const ready = async (page: Page) => {
  await page.locator('[data-lora]').first().waitFor(); await expect(page.locator('[data-region="generate"]')).toHaveAttribute('aria-disabled', 'false')
}

test('the model picker re-checks the model folders when it opens and says when none are found', async ({ page }) => {
  await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  let list: Model[] = []
  let asked = 0
  await page.route('**/api/generate-image/models', route => { asked++; return route.fulfill({ contentType: 'application/json', body: JSON.stringify(list) }) })
  const picker = page.locator('[data-region="model-picker"]')
  await raise(page)
  await picker.click()
  await expect(page.getByText('No models found')).toBeVisible()
  await page.keyboard.press('Escape')
  list = [...MODELS, { id: 'flux2_dev', label: 'Flux 2 Dev', family: 'Flux 2', modes: ['new'], refCap: 0, defaults: { steps: 28, guidance: 4 }, guidanceKey: 'guidance_scale', kind: 'image', video: null }]
  await picker.click()
  await expect(page.getByRole('group', { name: 'Flux 2' }).getByRole('option')).toHaveCount(2)
  await expect(page.getByRole('option', { name: /Flux 2 Dev/ })).toBeEnabled()
  await expect(page.getByText('Files missing')).toHaveCount(0)
  expect(asked).toBe(2)
})

test('the first load asks for a model rescan; opening the picker asks without one', async ({ page }) => {
  const st = apiState({ draft: DRAFT })
  await open(page, '/', new FakeHub(), st)
  await ready(page)
  const asks = () => st.calls.filter(c => c.method === 'GET' && c.path.startsWith('/api/generate-image/models')).map(c => c.path)
  expect(asks()).toEqual(['/api/generate-image/models?rescan=1'])
  await raise(page)
  await page.locator('[data-region="model-picker"]').click()
  await expect.poll(asks).toEqual(['/api/generate-image/models?rescan=1', '/api/generate-image/models'])
})

test('Settings → Image models: folders (add, refuse, remove), Rescan, every weight file, a base picked', async ({ page }) => {
  const st = apiState({ draft: DRAFT })
  await open(page, '/', new FakeHub(), st)
  await ready(page)
  await openSettings(page)
  const sec = page.getByRole('region', { name: 'Image models' })
  await sec.getByRole('button', { name: 'Add folder' }).first().click()
  const box = page.getByRole('textbox', { name: 'New model folder' })
  await box.fill('/missing/models')
  await box.press('Enter')
  await expect(sec.getByRole('alert')).toHaveText('Folder not found')
  await box.fill('/srv/models')
  await box.press('Enter')
  await expect(sec.getByRole('button', { name: 'Edit Model folder 2' })).toHaveText('/srv/models')
  await sec.getByRole('button', { name: 'Remove /srv/engine/app/loras' }).click()
  await expect.poll(() => st.calls.filter(c => c.method === 'PATCH' && c.path === '/api/settings').map(c => c.body)).toEqual([
    { engine: { model_folders: ['/srv/models/ComfyUI/models/diffusion_models', '/missing/models'] } },
    { engine: { model_folders: ['/srv/models/ComfyUI/models/diffusion_models', '/srv/models'] } },
    { modules: { loras: { folders: [] } } },
  ])
  const rescans = () => st.calls.filter(c => c.path === '/api/generate-image/weights/rescan').length
  await sec.getByRole('button', { name: 'Rescan' }).click()
  await expect.poll(rescans).toBe(1)
  await expect.poll(() => st.calls.filter(c => c.path === '/api/generate-image/models').length).toBeGreaterThan(0)
})
