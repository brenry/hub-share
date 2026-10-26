// Review screenshots at a 2000 × 1130 CSS px window (npm run shots). Not part of the regular run.
import { test, type Page } from '@playwright/test'
import { job } from './fixtures/data'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import type { ChatView } from '../../src/lib/protocol'
import { open, openSettings, settle } from './helpers'

const DIR = process.env.SHOT_DIR ?? 'build-shots/v2'
const DRAFT = {
  model: 'flux2_klein_9b', prompt: 'A grey cat asleep under an apple tree after rain, animestyle, wet leaves catching the last light, shallow depth of field',
  lorasByModel: { flux2_klein_9b: [{ id: 'flux2_klein_9b/photography/anime_cel_shade_1.safetensors', strength: 0.8 },
    { id: 'flux2_klein_9b/style/realism_engine_5.safetensors', strength: 0.5 }] },
  aspect: '16:9', size: 1.5, images: 2, advancedByModel: {}, references: [],
  selected: 'flux2_klein_9b/photography/anime_cel_shade_1.safetensors',
}
const T = 1791561600
const CHAT: ChatView = { busy: false, model: 'qwen3.5:9b', messages: [
  { id: 'm1', role: 'user', text: 'A grey cat asleep under an apple tree after rain. Anime look.', at: T, seconds: null },
  { id: 'm2', role: 'assistant', text: 'A grey cat asleep under an apple tree after rain, animestyle, wet leaves catching the last light, shallow depth of field.', at: T + 6, seconds: 5.8 },
  { id: 'm3', role: 'user', text: 'Warmer light, and put a wet stone wall behind the tree.', at: T + 60, seconds: null },
  { id: 'm4', role: 'assistant', text: 'A grey cat asleep under an apple tree after rain, animestyle, warm amber evening light, a wet stone wall behind the tree.', at: T + 65, seconds: 4.2 },
] }
const RUNNING = job('j_RUN00001', { state: 'running', started: 1791561604, progress: { phase: 'inference', index: 1, count: 2, step: 3, steps: 4, pct: 38, eta_s: 6, text: 'Denoising' } })

async function shoot(page: Page, name: string): Promise<void> {
  await page.waitForTimeout(500)
  await settle(page)
  await page.screenshot({ path: `${DIR}/${name}.png` })
}

test.describe('2000×1130', () => {
  test.use({ viewport: { width: 2000, height: 1130 } })
  test('@shots generate', async ({ page }) => {
    await open(page, '/', new FakeHub({ jobs: [RUNNING, job('j_WAIT0001')] }), apiState({ draft: DRAFT, chat: CHAT }))
    await page.locator('[data-region="draft"]').waitFor()
    await page.locator('[data-region="bar"]').waitFor()
    await shoot(page, 'generate-2000x1130')
    await page.screenshot({ path: `${DIR}/REVIEW-generate.png` })
    // The LoRA column is gone; the stack is in the roll-up library sheet.
    await page.locator('[data-region="library-toggle"]').click()
    await page.locator('[data-region="library-sheet"]:not([inert]) [data-lora]').first().waitFor()
    await shoot(page, 'generate-library-2000x1130')
  })
  test('@shots settings main', async ({ page }) => {
    await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
    await openSettings(page)
    await page.locator('[data-region="settings"] h2').first().waitFor()
    await shoot(page, 'settings-main-2000x1130')
  })
  test('@shots media', async ({ page }) => {
    const hub = new FakeHub()
    hub.focus = { screen: 'scr_X', tool: 'generate-image', label: 'Generate Image', mode: 'refs', primary: 'reference', sockets: [
      { id: 'reference_1', group: 'reference', label: 'Reference 1', accepts: ['image'], filled: true },
      { id: 'reference_2', group: 'reference', label: 'Reference 2', accepts: ['image'], filled: false }] }
    hub.ghostWorkspaces = 1
    await open(page, '/media', hub)
    await page.locator('[data-stage-img]').waitFor()
    await shoot(page, 'media-2000x1130')
  })
})

test.describe('1366×768', () => {
  test.use({ viewport: { width: 1366, height: 768 } })
  test('@shots generate small window', async ({ page }) => {
    await open(page, '/', new FakeHub({ jobs: [RUNNING, job('j_WAIT0001')] }), apiState({ draft: DRAFT, chat: CHAT }))
    await page.locator('[data-region="draft"]').waitFor()
    await page.locator('[data-region="bar"]').waitFor()
    await shoot(page, 'generate-1366x768')
  })
})
