// Stage 4: a video model's reference boxes carry its role. The First / Last model (minimax_h3, `end`) takes a start
// frame in box 1 and a last frame in box 2 (box 3 struck); the Omni model (minimax_h3_ref2va) takes identities in boxes 1–3. A Tab-picked character,
// Media's Send and the job all use them; Auto follows a start frame. The text encoder sits on the video sheet.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState, type ApiState } from './fixtures/api'
import { fakeChars } from './fixtures/media'
import { open, openSettings, settle } from './helpers'
import { fitProblems } from './fit'

const H3 = 'minimax_h3'
const OMNI = 'minimax_h3_ref2va'
const DRAFT = {
  model: H3, prompt: '', lorasByModel: {}, aspect: 'auto', size: 1, images: 1,
  advancedByModel: {}, references: [] as { id: string; w: number; h: number }[], selected: null, draft: 'A lighthouse at dusk',
}
const bar = (page: Page) => page.locator('footer[data-region="bar"]')
const slot = (page: Page, n: number) => page.locator(`[data-socket="reference_${n}"]`)
const box = (page: Page) => page.locator('#prompt')
const note = (page: Page) => page.locator('[data-region="references"] [role="status"]')
const lib = (page: Page) => page.locator('[data-region="video-sheet"], [data-region="library"]')
const encoder = (page: Page) => lib(page).getByRole('combobox', { name: 'Text encoder' })
const draftOf = (st: ApiState) => st.draft as typeof DRAFT & { advancedByModel: Record<string, { text_encoder?: string }> }

async function start(page: Page, over: Partial<typeof DRAFT> = {}, cap = 2, chars?: string[]): Promise<{ hub: FakeHub; st: ApiState }> {
  const r = await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, ...over }, chars: fakeChars(chars) }))
  await expect(page.locator('[data-region="references"]')).toHaveAttribute('data-cap', String(cap))
  return r
}
/** A video model's rows are on the sheet Video raises; a picture model's on the fold's. */
async function raise(page: Page, button = 'video-toggle') {
  await page.locator(`[data-region="${button}"]`).click()
  await expect.poll(() => page.locator('[data-region="library-sheet"]').getAttribute('inert')).toBeNull()
  await expect.poll(() => page.evaluate(() => Math.abs(document.querySelector('[data-region="video-sheet"], [data-region="library"]')!.getBoundingClientRect().top
    - document.querySelector('[data-region="library-sheet"]')!.getBoundingClientRect().top))).toBeLessThan(1)
}

test('start-frame model with `end`: box 1 the Start frame, box 2 the Last frame, box 3 struck; runs without either', async ({ page }) => {
  const { hub } = await start(page)
  for (const [n, label] of [[1, 'Start frame'], [2, 'Last frame']] as const) {
    await expect(slot(page, n)).not.toHaveAttribute('data-shut', 'true')
    await expect(slot(page, n)).toHaveAttribute('title', `${label}: send a picture from Media`)
    await expect(slot(page, n)).toHaveAttribute('aria-label', `${label}, empty`)
  }
  await expect(slot(page, 3)).toHaveAttribute('data-shut', 'true')
  await expect(slot(page, 3)).toHaveAttribute('title', 'Reference 3: this model takes no reference here')
  await expect.poll(() => hub.focus?.sockets.map(x => x.label)).toEqual(['Start frame', 'Last frame'])
  await expect(page.locator('[data-region="generate"]')).toHaveAttribute('aria-disabled', 'false')
})

test('Tab on a character fills the Start frame (the draft stays on H3 with a refs default), a second the Last frame; a third is refused', async ({ page }) => {
  const { st, hub } = await start(page, {}, 2, ['A-1', 'B-1', 'C-1'])
  await page.evaluate(() => fetch('/api/generate-image/defaults', { method: 'PUT', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ text: null, refs: 'flux2_klein_9b' }) }))
  await page.reload()
  await expect(page.locator('[data-region="references"]')).toHaveAttribute('data-cap', '2')
  await box(page).fill('a clip of a')
  await box(page).press('Tab')
  await expect(box(page)).toHaveValue('a clip of A-1 ')
  await expect(slot(page, 1).locator('img')).toHaveAttribute('src', '/thumbs/chars/A-1.png/336')
  await expect(slot(page, 1).locator('img')).toHaveAttribute('alt', 'Start frame')
  await expect(slot(page, 1).getByRole('button', { name: 'Remove start frame' })).toBeVisible()
  await expect.poll(() => draftOf(st).references, { timeout: 4000 }).toEqual([{ id: 'chars/A-1.png', w: 1024, h: 1024 }])
  expect(draftOf(st).model).toBe(H3)
  await page.keyboard.type(' and b')
  await box(page).press('Tab')
  await expect(slot(page, 2).locator('img')).toHaveAttribute('src', '/thumbs/chars/B-1.png/336')
  await expect(slot(page, 2).locator('img')).toHaveAttribute('alt', 'Last frame')
  await expect(slot(page, 2).locator('img')).toHaveAttribute('title', 'Last frame')
  await expect(slot(page, 2).getByRole('button', { name: 'Remove last frame' })).toBeVisible()
  await expect.poll(() => draftOf(st).references.map(r => r.id), { timeout: 4000 }).toEqual(['chars/A-1.png', 'chars/B-1.png'])
  await page.keyboard.type(' and c')
  await box(page).press('Tab')
  await expect(note(page)).toHaveText('1 not added: references are full')
  await expect(page.locator('[data-region="references"] img')).toHaveCount(2)
  await expect(slot(page, 1).locator('img')).toHaveAttribute('src', '/thumbs/chars/A-1.png/336')
  expect(draftOf(st).model).toBe(H3)
  // the job sends both by position
  await page.locator('[data-region="generate"]').click()
  await expect.poll(() => hub.sent('job.submit').length).toBe(1)
  expect((hub.sent('job.submit')[0]!.d as { params: unknown }).params).toMatchObject({ model: H3, mode: 'refs', references: ['chars/A-1.png', 'chars/B-1.png'] })
})

test('identity model: three Identity boxes; Media\'s Send fills them in order', async ({ page }) => {
  const { hub } = await start(page, { model: OMNI }, 3)
  for (const n of [1, 2, 3]) {
    await expect(slot(page, n)).not.toHaveAttribute('data-shut', 'true')
    await expect(slot(page, n)).toHaveAttribute('aria-label', `Identity ${n}, empty`)
  }
  await expect(slot(page, 2)).toHaveAttribute('title', 'Identity 2: send a picture from Media')
  await expect.poll(() => hub.focus?.sockets.map(x => x.label)).toEqual(['Identity 1', 'Identity 2', 'Identity 3'])
  // the Omni model cannot run text only
  await expect(page.locator('[data-region="generate"]')).toHaveAttribute('title', 'Add a reference image')
  const ws = hub.lines.find(l => l.role === 'workspace')!
  const items = ['p1', 'p2'].map(n => ({ id: `out/2026-10-09/${n}.png`, kind: 'image', url: `/files/out/2026-10-09/${n}.png` }))
  hub.send(ws, 'deliver', { tool: 'generate-image', socket: 'reference', from: { role: 'media' }, items }, { id: 'snd1' })
  await expect.poll(() => hub.sent('received').length).toBe(1)
  await expect(slot(page, 1).locator('img')).toHaveAttribute('alt', 'Identity 1')
  await expect(slot(page, 2).locator('img')).toHaveAttribute('alt', 'Identity 2')
  await expect(slot(page, 3)).toHaveAttribute('aria-label', 'Identity 3, empty')
  await expect(page.locator('[data-region="generate"]')).toHaveAttribute('aria-disabled', 'false')
})

test('Auto with a start frame: the tier\'s shape nearest it, in the hover text and the job', async ({ page }) => {
  const frame = { id: 'out/2026-10-09/wide.png', w: 1600, h: 900 }
  const { hub } = await start(page, { references: [frame] })
  const aspect = bar(page).getByRole('button', { name: 'Aspect' })
  await expect(aspect).toHaveAttribute('title', 'Aspect: Auto · 960 × 544')
  await expect(bar(page).getByRole('button', { name: 'Size' })).toHaveAttribute('title', 'Size: 540p · 960 × 544')
  await aspect.click()
  await expect(page.getByRole('listbox', { name: 'Aspect' }).getByRole('option', { name: 'Auto' })).toHaveAttribute('title', '960 × 544')
  await page.keyboard.press('Escape')
  await page.locator('[data-region="generate"]').click()
  await expect.poll(() => hub.sent('job.submit').length).toBe(1)
  expect((hub.sent('job.submit')[0]!.d as { params: unknown }).params).toMatchObject({ model: H3, mode: 'refs', references: [frame.id], width: 960, height: 544, images: 1 })
  // without the frame Auto is the tier's square, no size in the hover text
  await slot(page, 1).getByRole('button', { name: 'Remove start frame' }).click()
  await expect(aspect).toHaveAttribute('title', 'Aspect: Auto')
  await expect(bar(page).getByRole('button', { name: 'Size' })).toHaveAttribute('title', 'Size: 540p · 736 × 736')
})

test('the raised sheet: Text encoder under the model for a video model, saved per model; the card shows only Seconds', async ({ page }) => {
  const { st } = await start(page)
  await raise(page)
  await expect(lib(page).locator('[data-region="text-encoder"] > span')).toHaveText('Text encoder')
  await expect(encoder(page)).toHaveValue('nvfp4_awq')
  await expect(encoder(page).locator('option')).toHaveText(['NVFP4 AWQ (Recommended)', 'GGUF Q2_K (Lowest RAM)', 'GGUF Q4_K_M · not found', 'Quanto INT8 · not found'])
  const picker = (await lib(page).locator('[data-region="model-picker"]').first().boundingBox())!
  const row = (await lib(page).locator('[data-region="text-encoder"]').boundingBox())!
  expect(row.y).toBeGreaterThanOrEqual(picker.y + picker.height - 1)
  await encoder(page).selectOption('gguf_q2_k')
  await expect.poll(() => draftOf(st).advancedByModel?.[H3]?.text_encoder, { timeout: 4000 }).toBe('gguf_q2_k')
  const put = st.calls.filter(c => c.method === 'PUT' && c.path === '/api/generate-image/draft').at(-1)!
  expect((put.body as typeof DRAFT & { advancedByModel: Record<string, { text_encoder?: string }> }).advancedByModel[H3]!.text_encoder).toBe('gguf_q2_k')
  await page.keyboard.press('Escape')
  await openSettings(page)
  await page.locator('[data-card="generate-image"]').click()
  const sec = page.getByRole('region', { name: 'MiniMax H3' })
  await expect(sec.getByRole('spinbutton', { name: 'Seconds' })).toHaveValue('5.2')
  await expect(page.getByRole('combobox', { name: 'Text encoder' })).toHaveCount(0)
  await expect(page.locator('[data-region="settings"]').getByText('Text encoder')).toHaveCount(0)
})

test('the sheet shows no Text encoder for a picture model; Qwen keeps its Guidance', async ({ page }) => {
  await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, model: 'qwen_image_edit_plus' } }))
  await bar(page).locator('[data-region="steps"] input').waitFor()
  await raise(page, 'library-toggle')
  await expect(lib(page).locator('[data-region="guidance"]')).toBeVisible()
  await expect(lib(page).locator('[data-region="text-encoder"]')).toHaveCount(0)
})

test('1366×768: the sheet fits with the Text encoder row; the longest name unclipped by the sheet', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 })
  await start(page, { advancedByModel: { [H3]: { steps: 20, guidance: null, seed: { mode: 'random' }, text_encoder: 'gguf_q2_k' } } })
  await raise(page)
  await expect(encoder(page)).toHaveValue('gguf_q2_k')
  await settle(page)
  const m = await lib(page).evaluate(el => {
    const row = el.querySelector<HTMLElement>('[data-region="text-encoder"]')!
    const sel = row.querySelector('select')!
    const r = row.getBoundingClientRect(), l = el.getBoundingClientRect(), s = sel.getBoundingClientRect()
    const label = row.querySelector('span')!.getBoundingClientRect()
    return { over: row.scrollWidth - row.clientWidth, sel: s.right - r.right, outside: r.right - l.right, left: l.left - r.left,
      overlap: label.right - s.left, mid: Math.abs((label.top + label.height / 2) - (s.top + s.height / 2)), width: s.width }
  })
  expect(m.over).toBe(0)
  expect(m.sel).toBeLessThanOrEqual(0.5)
  expect(m.outside).toBeLessThanOrEqual(0.5)
  expect(m.left).toBeLessThanOrEqual(0.5)
  expect(m.overlap).toBeLessThanOrEqual(0)
  expect(m.mid).toBeLessThanOrEqual(1)
  expect(m.width).toBeGreaterThan(80)
  expect(await fitProblems(page, ['[data-region="video-sheet"]'])).toEqual([])
})
