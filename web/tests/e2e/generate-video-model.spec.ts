// MiniMax H3, a video model of the Generate Image screen: the size menu lists its tiers, one clip a press (the count
// shown off at 1), boxes 1–2 its start and last frame and the rest struck through (video-references.spec), no guidance, the job line says "clip", Settings keeps its Seconds per model
// (frames snapped up to the lattice) — and the bar still fits one line at 1366 and 1920.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState, type ApiState } from './fixtures/api'
import { job, summary } from './fixtures/data'
import { open, openSettings, settle } from './helpers'

const H3 = 'minimax_h3'
const DRAFT = {
  model: H3, prompt: 'A lighthouse', lorasByModel: {}, aspect: '16:9', size: 1.5, images: 3,
  advancedByModel: {}, references: [], selected: null, draft: 'A lighthouse at dusk, waves breaking below',
}
const bar = (page: Page) => page.locator('footer[data-region="bar"]')
const size = (page: Page) => bar(page).getByRole('button', { name: 'Size' })
const ready = async (page: Page) => {
  await bar(page).locator('[data-region="steps"] input').waitFor()
  await expect(page.locator('[data-region="generate"]')).toHaveAttribute('aria-disabled', 'false')
}
const draftOf = (st: ApiState) => st.draft as { size: number; advancedByModel: Record<string, { frames?: number }> }

test('the size menu lists the model\'s tiers (1.5 MP shows the second); hover text is each tier\'s size for the aspect; a pick stores 1 or 2', async ({ page }) => {
  const { st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  await expect(size(page)).toHaveText('720p')
  await expect(size(page)).toHaveAttribute('title', 'Size: 720p · 1280 × 704')
  await size(page).click()
  const list = page.getByRole('listbox', { name: 'Size' })
  await expect(list.getByRole('option')).toHaveText(['540p', '720p'])
  await expect(list.getByRole('option', { name: '720p' })).toHaveAttribute('aria-selected', 'true')
  await expect(list.getByRole('option', { name: '540p' })).toHaveAttribute('aria-selected', 'false')
  await expect(list.getByRole('option', { name: '540p' })).toHaveAttribute('title', '960 × 544')
  await expect(list.getByRole('option', { name: '720p' })).toHaveAttribute('title', '1280 × 704')
  await expect(list.getByText(/MP/)).toHaveCount(0)
  await list.getByRole('option', { name: '540p' }).click()
  await expect.poll(() => draftOf(st).size).toBe(1)
  await expect(size(page)).toHaveAttribute('title', 'Size: 540p · 960 × 544')
  await bar(page).getByRole('button', { name: 'Aspect' }).click()
  await page.getByRole('listbox', { name: 'Aspect' }).getByRole('option', { name: '9:16' }).click()
  await expect(size(page)).toHaveAttribute('title', 'Size: 540p · 544 × 960')
  await size(page).click()
  await expect(list.getByRole('option', { name: '720p' })).toHaveAttribute('title', '704 × 1280')
  await list.getByRole('option', { name: '720p' }).click()
  await expect.poll(() => draftOf(st).size).toBe(2)
  await expect(size(page)).toHaveAttribute('title', 'Size: 720p · 704 × 1280')
})

test('4 MP saved shows the last offered tier; Auto is the tier\'s square', async ({ page }) => {
  await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, size: 4, aspect: 'auto' } }))
  await ready(page)
  await expect(size(page)).toHaveText('720p')
  await expect(size(page)).toHaveAttribute('title', 'Size: 720p · 704 × 704')
  await size(page).click()
  await expect(page.getByRole('listbox', { name: 'Size' }).getByRole('option', { name: '720p' })).toHaveAttribute('aria-selected', 'true')
})

test('one clip a press: the count off at 1, boxes 1–2 the start and last frame and box 3 struck (even with a references default), no guidance; the job and its line', async ({ page }) => {
  const draft = { ...DRAFT, advancedByModel: { [H3]: { steps: 20, guidance: null, seed: { mode: 'random' }, frames: 243 } } }
  const { hub, st } = await open(page, '/', new FakeHub(), apiState({ draft }))
  await ready(page)
  await page.evaluate(() => fetch('/api/generate-image/defaults', { method: 'PUT', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ text: null, refs: 'flux2_klein_9b' }) }))
  await page.reload()
  await ready(page)
  const count = bar(page).locator('[data-region="count"]')
  await expect(count.locator('output')).toHaveText('1')
  await expect(count.getByRole('button', { name: 'More images' })).toBeDisabled()
  await expect(count.getByRole('button', { name: 'Fewer images' })).toBeDisabled()
  await expect(bar(page).locator('[data-region="references"]')).toHaveAttribute('data-cap', '2')
  await expect(bar(page).locator('[data-socket][data-shut]')).toHaveCount(1)
  await expect.poll(() => hub.focus?.sockets.map(x => x.label)).toEqual(['Start frame', 'Last frame'])
  await page.locator('[data-region="video-toggle"]').click()
  await expect(page.locator('[data-region="model-picker"]').first()).toHaveText(/MiniMax H3/)
  await expect(page.locator('[data-region="guidance"]')).toHaveCount(0)
  await expect(page.getByRole('spinbutton', { name: 'Guidance' })).toHaveCount(0)
  await page.locator('[data-region="video-toggle"]').click()

  const go = page.locator('[data-region="generate"]')
  await expect(go).toHaveAttribute('aria-label', 'Generate clip')
  await go.click()
  await expect.poll(() => hub.sent('job.submit').length).toBe(1)
  expect(hub.sent('job.submit')[0]!.d).toEqual({ tool: 'generate-image', kind: 'image', params: {
    tool: 'generate-image', model: H3, mode: 'new', prompt: DRAFT.draft, loras: [], width: 1280, height: 704, images: 1, steps: 20,
    guidance: null, seed: { mode: 'random' }, frames: 243 } })
  const id = [...hub.jobs.keys()][0]!
  expect(hub.jobs.get(id)!.summary).toMatchObject({ kind: 'clip', frames: 243, seconds: 10.13 })
  const clip = summary(H3, [4242], { kind: 'clip', frames: 243, seconds: 10.13, width: 1280, height: 704 })
  hub.setJob(job(id, { state: 'running', started: 1, summary: clip, progress: { phase: 'inference', index: 1, count: 1, step: 4, steps: 20, pct: 20, eta_s: 90, text: '' } }))
  await expect(page.getByText('Generating 1 of 1')).toBeVisible()
  hub.setJob(job(id, { state: 'done', summary: clip, outputs: ['clips/2026-10-13/120000.mp4'] }))
  await expect(page.getByText(/^Done · clip in \d+ s$/)).toBeVisible()
  // then the seed line, as for pictures: the clip's one seed, kept for this model on a click
  const seed = page.locator('[data-region="seed"]')
  await expect(seed).toHaveText(/^Seed\s*4242$/, { timeout: 8000 })
  await seed.getByRole('button', { name: '4242' }).click()
  await expect.poll(() => (st.draft as { advancedByModel: Record<string, { seed?: unknown }> }).advancedByModel[H3]?.seed, { timeout: 4000 })
    .toEqual({ mode: 'fixed', value: 4242 })
})

test('Settings → Generate Image: Seconds for the video model, snapped up to the lattice, the frames in the hover text; Reset keeps the text encoder', async ({ page }) => {
  const ENC = { ...DRAFT, advancedByModel: { [H3]: { steps: 20, guidance: null, seed: { mode: 'random' }, text_encoder: 'gguf_q2_k' } } }
  const { st } = await open(page, '/', new FakeHub(), apiState({ draft: ENC }))
  await ready(page)
  await openSettings(page)
  await page.locator('[data-card="generate-image"]').click()
  const sec = page.getByRole('region', { name: 'MiniMax H3' })
  const seconds = sec.getByRole('spinbutton', { name: 'Seconds' })
  await expect(seconds).toHaveValue('5.2')
  await expect(seconds).toHaveAttribute('title', '124 frames')
  await expect(sec.getByRole('radio', { name: 'Random' })).toHaveAttribute('aria-checked', 'true')
  await expect(sec.getByRole('spinbutton', { name: 'Guidance' })).toHaveCount(0)
  await expect(sec.getByRole('button', { name: 'Reset to model defaults' })).toHaveCount(0)

  await seconds.fill('6')
  await seconds.press('Enter')
  await expect(seconds).toHaveValue('6.6')
  await expect(seconds).toHaveAttribute('title', '158 frames')
  await expect.poll(() => draftOf(st).advancedByModel?.[H3]?.frames, { timeout: 4000 }).toBe(158)
  await seconds.fill('30')
  await seconds.blur()
  await expect(seconds).toHaveValue('14.4')
  await expect(seconds).toHaveAttribute('title', '345 frames')
  await seconds.fill('5.2')
  await seconds.press('Enter')
  await expect(seconds).toHaveAttribute('title', '124 frames')
  await seconds.fill('10')
  await seconds.press('Enter')
  await expect(seconds).toHaveValue('10.1')
  await expect.poll(() => draftOf(st).advancedByModel?.[H3]?.frames, { timeout: 4000 }).toBe(243)
  // label-only: the frame count is hover text, never a sentence on the card
  await expect(page.locator('[data-region="settings"]').getByText(/frames/)).toHaveCount(0)
  await sec.getByRole('button', { name: 'Reset to model defaults' }).click()
  await expect(seconds).toHaveValue('5.2')
  // the text encoder lives on the LoRA sheet: Reset leaves it
  await expect.poll(() => draftOf(st).advancedByModel?.[H3], { timeout: 4000 })
    .toEqual({ steps: 20, guidance: null, seed: { mode: 'random' }, text_encoder: 'gguf_q2_k' })
})

test.describe('the bar with the video model', () => {
  test.use({ userAgent: 'Mozilla/5.0 HocusPocusDesktop/1.2.1 tags=1,2,3' })
  const WORST = { ...DRAFT, size: 4, images: 6, advancedByModel: { [H3]: { steps: 100, guidance: null, seed: { mode: 'random' } } } }
  for (const [w, h] of [[1366, 768], [1920, 1080]] as const) {
    test(`is one line at ${w}×${h}, the tier and the off count included`, async ({ page }) => {
      await page.setViewportSize({ width: w, height: h })
      await open(page, '/', new FakeHub(), apiState({ draft: WORST }))
      await ready(page)
      await expect(bar(page).locator('[data-region="launch"]')).toBeVisible()
      await expect(size(page)).toHaveText('720p')
      await expect(bar(page).locator('[data-region="count"] output')).toHaveText('1')
      await settle(page)
      const m = await bar(page).evaluate(el => {
        const kids = [...el.children].map(c => c.getBoundingClientRect()).filter(r => r.width > 0 && r.height > 0)
        const controls = el.querySelector<HTMLElement>(':scope > span:has([data-region="references"])')!
        const c = controls.getBoundingClientRect()
        const right = Math.max(...[...controls.children].map(k => k.getBoundingClientRect().right))
        return { mids: kids.map(r => r.top + r.height / 2), over: controls.scrollWidth - controls.clientWidth, past: right - c.right }
      })
      expect(Math.max(...m.mids) - Math.min(...m.mids)).toBeLessThanOrEqual(2)
      expect(m.over).toBeLessThanOrEqual(0)
      expect(m.past).toBeLessThanOrEqual(0.5)
      const b = (await bar(page).boundingBox())!
      expect(b.x + b.width).toBeLessThanOrEqual(w + 0.5)
      expect(b.y + b.height).toBeLessThanOrEqual(h + 0.5)
    })
  }
})

test('a redraw from the hub never says a model switch', async ({ page }) => {
  const hub = new FakeHub()
  await open(page, '/', hub, apiState())
  await page.locator('footer[data-region="bar"]').waitFor()
  hub.broadcast('generate-image.draft', { switched: 'Krea 2 Turbo Edit' }, 'workspace')
  hub.broadcast('generate-image.draft', {}, 'workspace')
  await page.waitForTimeout(300)
  await expect(page.getByRole('status').filter({ hasText: 'switched the model' })).toHaveCount(0)
})
