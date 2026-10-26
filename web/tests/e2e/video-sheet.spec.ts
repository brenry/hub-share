// The bar's Video button, immediately left of the image sheet's fold (same size, same line): it raises the video sheet,
// which lists only the video models with their rows (size, seconds, text encoder) and LoRAs; the fold's sheet lists
// only the image models. A pick on either sets the draft's model, and the bar says which (Generate image / clip). From a
// model of the other kind, Video and the fold bring back the last picked of their kind (else its default) with its LoRAs.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState, type ApiState } from './fixtures/api'
import { open, settle } from './helpers'
import { fitProblems } from './fit'

const DRAFT = {
  model: 'flux2_klein_9b', lastModel: { image: 'flux2_klein_9b', video: '' }, prompt: 'A grey cat', lorasByModel: {}, aspect: 'auto', size: 1, images: 2,
  advancedByModel: {}, references: [], selected: null, draft: 'A grey cat in the rain',
}
const bar = (page: Page) => page.locator('footer[data-region="bar"]')
const video = (page: Page) => page.locator('[data-region="video-toggle"]')
const fold = (page: Page) => page.locator('[data-region="library-toggle"]')
const sheet = (page: Page) => page.locator('[data-region="library-sheet"]')
const go = (page: Page) => page.locator('[data-region="generate"]')
const putModels = (st: ApiState) => st.calls.filter(c => c.method === 'PUT' && c.path === '/api/generate-image/draft')
  .map(c => (c.body as { model?: string }).model).filter(Boolean)

async function start(page: Page) {
  const r = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await page.locator('[data-lora]').first().waitFor()
  return r
}
/** The names the raised sheet's model picker offers. */
async function offered(page: Page): Promise<string[]> {
  await sheet(page).locator('[data-region="model-picker"]').click()
  const list = page.getByRole('listbox', { name: 'Models' })
  await expect(list).toBeVisible()
  const names = await list.getByRole('option').allTextContents()
  await page.keyboard.press('Escape')
  return names
}

test('Video sits immediately left of the fold, the same size on the same line', async ({ page }) => {
  await start(page)
  await expect(video(page)).toHaveAttribute('aria-label', 'Video')
  const [v, f] = [(await video(page).boundingBox())!, (await fold(page).boundingBox())!]
  expect(Math.abs(v.width - f.width)).toBeLessThanOrEqual(0.5)
  expect(Math.abs(v.height - f.height)).toBeLessThanOrEqual(0.5)
  expect(Math.abs(v.y - f.y)).toBeLessThanOrEqual(0.5)
  expect(v.x + v.width).toBeLessThanOrEqual(f.x + 0.5)
  expect(await bar(page).evaluate(el => [...el.children].map(c => c.getAttribute('data-region')).slice(0, 2))).toEqual(['video-toggle', 'library-toggle'])
})

test('the video sheet lists only video models; the fold\'s lists none; one sheet at a time; Escape hands the focus back', async ({ page }) => {
  await start(page)
  await video(page).click()
  await expect(video(page)).toHaveAttribute('aria-expanded', 'true')
  await expect(fold(page)).toHaveAttribute('aria-expanded', 'false')
  await expect(sheet(page).locator('[data-region="video-sheet"]')).toBeVisible()
  // on a picture model the video sheet asks for a model: no rows, no LoRAs
  await expect(sheet(page).locator('[data-region="model-picker"]')).toHaveText('Choose a model')
  await expect(sheet(page).locator('[data-lora]')).toHaveCount(0)
  expect(await offered(page)).toEqual(['MiniMax H3', 'H3 Omni — Pruned'])

  await fold(page).click()
  await expect(fold(page)).toHaveAttribute('aria-expanded', 'true')
  await expect(video(page)).toHaveAttribute('aria-expanded', 'false')
  await expect(sheet(page).locator('[data-region="library"]')).toBeVisible()
  expect(await offered(page)).toEqual(['Flux 2 Klein 9B', 'Qwen Image Edit Plus', 'Z-Image Turbo'])
  await expect(sheet(page).locator('[data-region="text-encoder"], [data-region="seconds"], [data-region="video-size"]')).toHaveCount(0)

  await video(page).click()
  await page.keyboard.press('Escape')
  await expect(video(page)).toHaveAttribute('aria-expanded', 'false')
  await expect(video(page)).toBeFocused()
  await expect(sheet(page)).toHaveAttribute('inert', '')
})

test('a pick on the video sheet sets the draft\'s model and the bar shows it; its rows reach the draft; the fold picks back', async ({ page }) => {
  const { st } = await start(page)
  await expect(go(page)).toHaveAttribute('aria-label', 'Generate 2 images')
  await video(page).click()
  await sheet(page).locator('[data-region="model-picker"]').click()
  await page.getByRole('option', { name: 'MiniMax H3' }).click()
  await expect(sheet(page).locator('[data-region="model-picker"]')).toHaveText('MiniMax H3')
  await expect(go(page)).toHaveAttribute('aria-label', 'Generate clip')
  await expect(bar(page).getByRole('button', { name: 'Size' })).toHaveText('540p')
  await expect.poll(() => putModels(st), { timeout: 4000 }).toEqual(['minimax_h3'])
  // its rows: the size tiers, the seconds, the text encoder; no Detail (that is Omni's); no Guidance
  const rows = sheet(page).locator('[data-region="video-sheet"] label')
  await expect(rows.locator('> span:first-child')).toHaveText(['Size', 'Seconds', 'Text encoder'])
  const size = sheet(page).getByRole('combobox', { name: 'Size' })
  await expect(size.locator('option')).toHaveText(['540p', '720p'])
  await size.selectOption('2')
  await expect(bar(page).getByRole('button', { name: 'Size' })).toHaveText('720p')
  const seconds = sheet(page).getByRole('spinbutton', { name: 'Seconds' })
  await expect(seconds).toHaveValue('5.2')
  await seconds.fill('8')
  await seconds.press('Enter')
  await expect(seconds).toHaveValue('8')
  await expect.poll(() => (st.draft as { advancedByModel: Record<string, { frames?: number }>; size: number }), { timeout: 4000 })
    .toMatchObject({ size: 2, advancedByModel: { minimax_h3: { frames: 192 } } })

  await fold(page).click()
  await expect(sheet(page).locator('[data-region="model-picker"]')).toHaveText('Flux 2 Klein 9B')
  await expect(go(page)).toHaveAttribute('aria-label', 'Generate 2 images')
  await sheet(page).locator('[data-region="model-picker"]').click()
  await page.getByRole('option', { name: 'Z-Image Turbo' }).click()
  await expect(go(page)).toHaveAttribute('aria-label', 'Generate 2 images')
  await expect(bar(page).getByRole('button', { name: 'Size' })).toHaveText('2 MP')
})

const picker = (page: Page) => sheet(page).locator('[data-region="model-picker"]')
const strength = (page: Page, name: string) => sheet(page).getByRole('button', { name: `${name} strength` })
async function pick(page: Page, name: string) {
  await picker(page).click()
  await page.getByRole('option', { name }).click()
  await expect(picker(page)).toHaveText(name)
}

test('Video and the fold bring back the last model of their kind, each with its own LoRA strengths and rows', async ({ page }) => {
  const lorasByModel = { minimax_h3_ref2va: [{ id: 'minimax_h3_ref2va/drift.safetensors', strength: 0.6 }],
    z_image_turbo: [{ id: 'z_image_turbo/ink.safetensors', strength: 1.4 }] }
  const { st } = await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, lorasByModel } }))
  await page.locator('[data-lora]').first().waitFor()
  // nothing of the kind remembered and no default: Video only raises its sheet, which asks for a model
  await video(page).click()
  await expect(picker(page)).toHaveText('Choose a model')
  await pick(page, 'H3 Omni — Pruned')
  await strength(page, 'drift').press('ArrowUp')
  await expect(strength(page, 'drift')).toHaveText('0.61')
  await sheet(page).getByRole('combobox', { name: 'Detail' }).selectOption('max')

  await fold(page).click()
  await expect(picker(page)).toHaveText('Flux 2 Klein 9B')
  await pick(page, 'Z-Image Turbo')
  await expect(strength(page, 'ink')).toHaveText('1.40')

  await video(page).click()
  await expect(video(page)).toHaveAttribute('aria-expanded', 'true')
  await expect(picker(page)).toHaveText('H3 Omni — Pruned')
  await expect(strength(page, 'drift')).toHaveText('0.61')
  await expect(sheet(page).getByRole('combobox', { name: 'Detail' })).toHaveValue('max')
  await expect(go(page)).toHaveAttribute('aria-label', 'Generate clip')
  await expect(bar(page).getByRole('button', { name: 'Size' })).toHaveText('540p')

  await fold(page).click()
  await expect(fold(page)).toHaveAttribute('aria-expanded', 'true')
  await expect(picker(page)).toHaveText('Z-Image Turbo')
  await expect(strength(page, 'ink')).toHaveText('1.40')
  await expect(go(page)).toHaveAttribute('aria-label', 'Generate 2 images')
  await expect(bar(page).getByRole('button', { name: 'Size' })).toHaveText('1 MP')
  // already on the kind: the fold only lowers its sheet
  await fold(page).click()
  await expect(fold(page)).toHaveAttribute('aria-expanded', 'false')
  await expect.poll(() => st.draft, { timeout: 4000 }).toMatchObject({ model: 'z_image_turbo',
    lastModel: { image: 'z_image_turbo', video: 'minimax_h3_ref2va' }, lorasByModel: { minimax_h3_ref2va: [{ strength: 0.61 }] } })
})

for (const [from, kind, to, label] of [['flux2_klein_9b', 'video', 'MiniMax H3', 'Generate clip'], ['minimax_h3', 'image', 'Z-Image Turbo', 'Generate 2 images']] as const) {
  test(`nothing remembered: the ${kind} default (${to}) comes with the button`, async ({ page }) => {
    await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, model: from, lastModel: { image: '', video: '' } },
      defaults: { text: 'z_image_turbo', refs: null, video: 'minimax_h3' } }))
    await bar(page).locator('[data-region="steps"] input').waitFor()
    await (kind === 'video' ? video : fold)(page).click()
    await expect(picker(page)).toHaveText(to)
    await expect(go(page)).toHaveAttribute('aria-label', label)
  })
}

for (const [w, h] of [[1366, 768], [1920, 1080]] as const) {
  test(`${w}×${h}: the bar keeps one line with Video; the raised video sheet fits`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h })
    await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, model: 'minimax_h3_ref2va', images: 6,
      references: [{ id: 'out/2026-10-09/r1.png', w: 1200, h: 800 }] } }))
    await bar(page).locator('[data-region="steps"] input').waitFor()
    await video(page).click()
    await expect(sheet(page).locator('[data-region="detail"]')).toBeVisible()
    await page.waitForTimeout(300)
    await settle(page)
    const m = await bar(page).evaluate(el => {
      const mids = [...el.children].map(c => c.getBoundingClientRect()).filter(r => r.width > 0).map(r => r.top + r.height / 2)
      const controls = el.querySelector<HTMLElement>(':scope > span:has([data-region="references"])')!
      return { spread: Math.max(...mids) - Math.min(...mids), over: controls.scrollWidth - controls.clientWidth }
    })
    expect(m.spread).toBeLessThanOrEqual(2)
    expect(m.over).toBeLessThanOrEqual(0)
    expect(await fitProblems(page, ['[data-region="bar"]', '[data-region="video-sheet"]'])).toEqual([])
  })
}
