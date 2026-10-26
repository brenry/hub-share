// Guidance on the raised LoRA sheet, under the model picker (only for a model that has a guidance key, kept per model
// in the draft; never on the bar, which with Qwen still fits its controls on one line) and the seed line under
// the prompt box (the seeds the last render used; click one to keep it, Random lets it go).
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState, type ApiState } from './fixtures/api'
import { job, summary } from './fixtures/data'
import { open, settle } from './helpers'

const QWEN = 'qwen_image_edit_plus'
const FLUX = 'flux2_klein_9b'
const DRAFT = {
  model: QWEN, prompt: 'A grey cat', lorasByModel: {}, aspect: 'auto', size: 1, images: 2,
  advancedByModel: {}, references: [], selected: null, draft: 'A grey cat in the rain',
}
type Adv = { steps: number; guidance: number | null; seed: { mode: string; value?: number } }
const adv = (st: ApiState, model: string) => (st.draft as { advancedByModel?: Record<string, Adv> } | null)?.advancedByModel?.[model] ?? null
const bar = (page: Page) => page.locator('footer[data-region="bar"]')
const ready = (page: Page) => bar(page).locator('[data-region="steps"] input').waitFor()
const seedLine = (page: Page) => page.locator('[data-region="dock"] [data-region="seed"]')

/** Raise the LoRA sheet with the bar's fold and wait until it is live (not inert). */
async function raise(page: Page) {
  await page.locator('[data-region="library-toggle"]').click()
  await expect(page.locator('[data-region="library-toggle"]')).toHaveAttribute('aria-expanded', 'true')
  await expect.poll(() => page.locator('[data-region="library-sheet"]').getAttribute('inert')).toBeNull()
}
const lib = (page: Page) => page.locator('[data-region="library"]')

test.describe('Guidance (on the raised sheet, under the model)', () => {
  test('hidden for a model without a guidance key (Flux); never on the bar', async ({ page }) => {
    await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, model: FLUX } }))
    await page.locator('[data-lora]').first().waitFor()
    await raise(page)
    await expect(lib(page).locator('[data-region="guidance"]')).toHaveCount(0)
    await expect(page.getByRole('spinbutton', { name: 'Guidance' })).toHaveCount(0)
    await expect(bar(page).locator('[data-region="guidance"]')).toHaveCount(0)
  })

  test('Qwen: labelled Guidance on the sheet (not the bar), default 4; typed and nudged values saved per model, clamped 0..20', async ({ page }) => {
    const { st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
    await ready(page)
    await expect(bar(page).locator('[data-region="guidance"]')).toHaveCount(0)
    await raise(page)
    const g = lib(page).locator('[data-region="guidance"]')
    await expect(g).toBeVisible()
    await expect(lib(page).locator('label:has([data-region="guidance"]) > span').first()).toHaveText('Guidance')
    await expect(g.getByText('G', { exact: true })).toHaveCount(0)          // the old unit is gone
    const input = lib(page).getByRole('spinbutton', { name: 'Guidance' })
    await expect(input).toHaveValue('4')
    await expect(input).toHaveAttribute('min', '0')
    await expect(input).toHaveAttribute('max', '20')
    await expect(input).toHaveAttribute('step', '0.1')

    const more = lib(page).getByRole('button', { name: 'More guidance' })
    const less = lib(page).getByRole('button', { name: 'Less guidance' })
    await more.click()
    await expect(input).toHaveValue('4.5')
    await expect.poll(() => adv(st, QWEN)?.guidance).toBe(4.5)
    await less.click()
    await less.click()
    await expect(input).toHaveValue('3.5')
    await expect.poll(() => adv(st, QWEN)?.guidance).toBe(3.5)

    await input.fill('7.3')
    await expect(input).toHaveValue('7.3')
    await expect.poll(() => adv(st, QWEN)).toEqual({ steps: 20, guidance: 7.3, seed: { mode: 'random' } })
    const puts = st.calls.filter(c => c.method === 'PUT' && c.path === '/api/generate-image/draft')
    expect((puts.at(-1)!.body as { advancedByModel: Record<string, Adv> }).advancedByModel[QWEN]!.guidance).toBe(7.3)
    expect(adv(st, FLUX)).toBeNull()                       // per model: the other models are untouched

    await input.fill('35')
    await expect(input).toHaveValue('20')
    await expect.poll(() => adv(st, QWEN)?.guidance).toBe(20)
    await expect(more).toBeDisabled()
    await input.fill('19.8')
    await more.click()
    await expect(input).toHaveValue('20')
    await input.fill('0.3')
    await less.click()
    await expect(input).toHaveValue('0')
    await expect.poll(() => adv(st, QWEN)?.guidance).toBe(0)
    await expect(less).toBeDisabled()
  })

  test('1366×768: the guidance row fits inside the sheet, "12.5" unclipped', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 })
    await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, advancedByModel: { [QWEN]: { steps: 20, guidance: 12.5, seed: { mode: 'random' } } } } }))
    await ready(page)
    await raise(page)
    await expect(lib(page).getByRole('spinbutton', { name: 'Guidance' })).toHaveValue('12.5')
    await settle(page)
    const m = await lib(page).evaluate(el => {
      const row = el.querySelector<HTMLElement>('label:has([data-region="guidance"])')!
      const r = row.getBoundingClientRect(), l = el.getBoundingClientRect()
      const input = row.querySelector('input')!
      const right = Math.max(...[...row.querySelectorAll('*')].map(k => k.getBoundingClientRect().right))
      return { over: row.scrollWidth - row.clientWidth, past: right - r.right, outside: r.right - l.right, left: l.left - r.left, clip: input.scrollWidth - input.clientWidth }
    })
    expect(m, 'guidance row: overflow / child past row / row past sheet / input text clipped (px)')
      .toEqual({ over: 0, past: expect.any(Number), outside: expect.any(Number), left: expect.any(Number), clip: 0 })
    expect(m.past).toBeLessThanOrEqual(0.5)
    expect(m.outside).toBeLessThanOrEqual(0.5)
    expect(m.left).toBeLessThanOrEqual(0.5)
  })
})

test.describe('the seed line', () => {
  test('hidden with no job, and with a job that carries no seeds', async ({ page }) => {
    await open(page, '/', new FakeHub({ jobs: [job('j_D', { state: 'done', outputs: ['a'] })] }), apiState({ draft: DRAFT }))
    await ready(page)
    await settle(page)
    await expect(seedLine(page)).toHaveCount(0)
  })

  test('hidden when the job\'s model is unknown', async ({ page }) => {
    const done = job('j_D', { state: 'done', outputs: ['a'], summary: summary('gone_model', [5]) })
    await open(page, '/', new FakeHub({ jobs: [done] }), apiState({ draft: DRAFT }))
    await ready(page)
    await settle(page)
    await expect(seedLine(page)).toHaveCount(0)
  })

  test('the newest done job\'s seeds; keep 222 (fixed, pressed, cyan), then Random lets it go', async ({ page }) => {
    const old = job('j_A', { state: 'done', created: 1, outputs: ['a'], summary: summary(FLUX, [9]) })
    const last = job('j_B', { state: 'done', created: 2, outputs: ['a', 'b'], summary: summary(QWEN, [111, 222]) })
    const { st } = await open(page, '/', new FakeHub({ jobs: [old, last] }), apiState({ draft: { ...DRAFT, model: FLUX } }))
    await page.locator('[data-lora]').first().waitFor()
    const line = seedLine(page)
    await expect(line).toBeVisible()
    await expect(line.locator('> span').first()).toHaveText('Seeds')
    const nums = line.locator('button[aria-pressed]')
    await expect(nums).toHaveText(['111', '222'])
    await expect(nums.nth(0)).toHaveAttribute('aria-pressed', 'false')
    await expect(nums.nth(1)).toHaveAttribute('aria-pressed', 'false')
    await expect(line.getByRole('button', { name: 'Random' })).toHaveCount(0)

    const seedNum = await nums.nth(1).getAttribute('class')
    await nums.nth(1).click()
    // saved for the job's model (Qwen), not the current one (Flux)
    await expect.poll(() => adv(st, QWEN)?.seed).toEqual({ mode: 'fixed', value: 222 })
    expect(adv(st, FLUX)).toBeNull()
    await expect(nums.nth(1)).toHaveAttribute('aria-pressed', 'true')
    await expect(nums.nth(0)).toHaveAttribute('aria-pressed', 'false')
    await expect(nums.nth(1)).toHaveClass(/seedKept/)
    expect(seedNum).toMatch(/seedNum/)
    await expect.poll(() => nums.nth(1).evaluate(e => getComputedStyle(e).color)).toBe('rgb(0, 211, 242)')   // hovered, still cyan
    await page.mouse.move(0, 0)
    const [kept, plain, accent] = await page.evaluate(() => {
      const b = [...document.querySelectorAll<HTMLElement>('[data-region="seed"] button[aria-pressed]')]
      return [getComputedStyle(b[1]!).color, getComputedStyle(b[0]!).color, getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()]
    })
    expect(kept).toBe('rgb(0, 211, 242)')
    expect(plain).not.toBe(kept)
    expect(accent).not.toBe('')

    await line.getByRole('button', { name: 'Random' }).click()
    await expect.poll(() => adv(st, QWEN)?.seed).toEqual({ mode: 'random' })
    await expect(nums.nth(1)).toHaveAttribute('aria-pressed', 'false')
    await expect(nums.nth(1)).not.toHaveClass(/seedKept/)
    await expect(line.getByRole('button', { name: 'Random' })).toHaveCount(0)
  })

  test('one seed says Seed; a seed kept already shows pressed', async ({ page }) => {
    const done = job('j_D', { state: 'done', outputs: ['a'], summary: summary(QWEN, [42]) })
    const kept = { ...DRAFT, advancedByModel: { [QWEN]: { steps: 20, guidance: 4, seed: { mode: 'fixed', value: 42 } } } }
    await open(page, '/', new FakeHub({ jobs: [done] }), apiState({ draft: kept }))
    const line = seedLine(page)
    await expect(line.locator('> span').first()).toHaveText('Seed')
    await expect(line.getByRole('button', { name: '42' })).toHaveAttribute('aria-pressed', 'true')
    await expect(line.getByRole('button', { name: 'Random' })).toBeVisible()
  })

  test('hidden while a job runs (the running line shows instead); back once it is done', async ({ page }) => {
    const done = job('j_A', { state: 'done', created: 1, outputs: ['a'], summary: summary(QWEN, [7]) })
    const progress = { phase: 'inference', index: 1, count: 2, step: 1, steps: 20, pct: 10, eta_s: null, text: '' }
    const running = job('j_B', { state: 'running', created: 2, started: 2, progress, summary: summary(QWEN, [111, 222]) })
    const { hub } = await open(page, '/', new FakeHub({ jobs: [done, running] }), apiState({ draft: DRAFT }))
    await ready(page)
    await expect(page.locator('[data-region="queue"]')).toBeVisible()
    await expect(page.locator('[data-region="queue"]').getByRole('button', { name: 'Cancel' })).toBeVisible()
    await expect(seedLine(page)).toHaveCount(0)

    hub.setJob({ ...running, state: 'done', progress: null, outputs: ['a', 'b'] })
    await expect(page.locator('[data-region="queue"]')).toContainText('Done')            // the short Done first
    await expect(seedLine(page)).toHaveCount(0)
    await expect(seedLine(page).locator('button[aria-pressed]')).toHaveText(['111', '222'], { timeout: 8000 })
    await expect(page.locator('[data-region="queue"]')).toHaveCount(0)
  })
})

// With a guidance model (Qwen) the bar's controls still fit one line: guidance is not on it, the count shows.
test.describe('the bar with Qwen', () => {
  test.use({ userAgent: 'Mozilla/5.0 HocusPocusDesktop/1.2.1 tags=1,2,3' })
  const WORST = {
    ...DRAFT, aspect: '16:9', size: 1.5, images: 6,
    advancedByModel: { [QWEN]: { steps: 100, guidance: 12.5, seed: { mode: 'random' } } },
    references: [{ id: 'out/2026-10-09/r1.png', w: 1200, h: 800 }, { id: 'out/2026-10-09/r2.png', w: 800, h: 1200 }],
  }
  for (const [w, h] of [[1366, 768], [1920, 1080]] as const) {
    test(`one line at ${w}×${h}, nothing clipped, the image count visible`, async ({ page }) => {
      await page.setViewportSize({ width: w, height: h })
      await open(page, '/', new FakeHub(), apiState({ draft: WORST }))
      await ready(page)
      const b = bar(page)
      await expect(b.locator('[data-region="launch"]')).toBeVisible()
      await expect(b.locator('[data-region="steps"] input')).toHaveValue('100')
      await expect(b.locator('[data-region="guidance"]')).toHaveCount(0)
      await expect(b.locator('[data-socket] img')).toHaveCount(2)
      const count = b.locator('[data-region="count"]')
      await expect(count.locator('output')).toHaveText('6')
      await expect(count).toBeVisible()
      await settle(page)
      const m = await b.evaluate(el => {
        const kids = [...el.children].map(c => c.getBoundingClientRect()).filter(r => r.width > 0 && r.height > 0)
        const controls = el.querySelector<HTMLElement>(':scope > span:has([data-region="references"])')!
        const c = controls.getBoundingClientRect()
        const right = Math.max(...[...controls.children].map(k => k.getBoundingClientRect().right))
        const n = el.querySelector<HTMLElement>('[data-region="count"]')!.getBoundingClientRect()
        const steps = el.querySelector<HTMLInputElement>('[data-region="steps"] input')!
        return { mids: kids.map(r => r.top + r.height / 2), over: controls.scrollWidth - controls.clientWidth, past: right - c.right,
          clipped: steps.scrollWidth - steps.clientWidth, width: c.width, need: controls.scrollWidth, countIn: n.left >= c.left && n.right <= c.right + 0.5 && n.width > 0 }
      })
      expect(Math.max(...m.mids) - Math.min(...m.mids), `vertical centres ${m.mids.join(', ')}`).toBeLessThanOrEqual(2)
      expect.soft(m.clipped, 'steps "100" clipped (scrollWidth - clientWidth)').toBe(0)
      expect.soft(m.over, `controls overflow: need ${m.need}px, have ${m.width.toFixed(1)}px`).toBeLessThanOrEqual(0)
      expect(m.past, 'last control past the controls group (px)').toBeLessThanOrEqual(0.5)
      expect(m.countIn, 'the image count lies inside the controls group').toBe(true)
      const g = (await b.locator('[data-region="generate"]').boundingBox())!
      expect(g.x + g.width).toBeLessThanOrEqual(w)
      expect(g.y + g.height).toBeLessThanOrEqual(h)
    })
  }
})
