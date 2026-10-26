// Review screenshots at 2560 × 1440 (npm run shots). Not part of the regular run.
import { test } from '@playwright/test'
import { job } from './fixtures/data'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { open, openSettings, settle } from './helpers'

const DIR = process.env.SHOT_DIR ?? 'build-shots'
const DRAFT = {
  model: 'flux2_klein_9b', prompt: 'A grey cat asleep under an apple tree after rain, animestyle, wet leaves catching the last light, shallow depth of field',
  lorasByModel: { flux2_klein_9b: [{ id: 'flux2_klein_9b/photography/anime_cel_shade_1.safetensors', strength: 0.8 },
    { id: 'flux2_klein_9b/characters/paper_cutout_2.safetensors', strength: 0.2 }, { id: 'flux2_klein_9b/style/realism_engine_5.safetensors', strength: 0.5 }] },
  aspect: '16:9', size: 1.5, images: 2, advancedByModel: {}, references: [{ id: 'out/2026-10-09/ref1.png', w: 1200, h: 800 }],
  selected: 'flux2_klein_9b/photography/anime_cel_shade_1.safetensors',
}

test.use({ viewport: { width: 2560, height: 1440 } })

test('@shots generate', async ({ page }) => {
  const running = job('j_RUN00001', { state: 'running', started: 1791561604, progress: { phase: 'inference', index: 1, count: 2, step: 3, steps: 4, pct: 38, eta_s: 6, text: 'Denoising' } })
  await open(page, '/', new FakeHub({ jobs: [running, job('j_WAIT0001')] }), apiState({ draft: DRAFT }))
  await page.locator('[data-region="draft"]').waitFor()
  await page.locator('[data-region="bar"]').waitFor()
  await page.waitForTimeout(500)
  await settle(page)
  await page.screenshot({ path: `${DIR}/generate-2560.png` })
})

for (const view of ['main', 'network', 'assistant']) {
  test(`@shots settings ${view}`, async ({ page }) => {
    await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
    await openSettings(page)
    if (view !== 'main') await page.locator(`[data-card="${view}"]`).click()
    await page.locator('[data-region="settings"] h2').first().waitFor()
    await page.waitForTimeout(400)
    await settle(page)
    await page.screenshot({ path: `${DIR}/settings-${view}-2560.png` })
  })
}

test('@shots media', async ({ page }) => {
  const hub = new FakeHub()
  hub.focus = { screen: 'scr_X', tool: 'generate-image', label: 'Generate Image', mode: 'refs', primary: 'reference', sockets: [
    { id: 'reference_1', group: 'reference', label: 'Reference 1', accepts: ['image'], filled: true },
    { id: 'reference_2', group: 'reference', label: 'Reference 2', accepts: ['image'], filled: false },
    { id: 'reference_3', group: 'reference', label: 'Reference 3', accepts: ['image'], filled: false }] }
  hub.ghostWorkspaces = 1
  await open(page, '/media', hub)
  await page.locator('[data-item]').first().waitFor()
  await page.locator('[data-item]').nth(3).click({ modifiers: ['Control'] })
  await page.waitForTimeout(500)
  await settle(page)
  await page.screenshot({ path: `${DIR}/media-2560.png` })
})
