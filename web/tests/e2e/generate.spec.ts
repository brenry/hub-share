// Generate Image flows: generate → queue → done, Ctrl+Enter, blocking, draft save, the draft article's Clear (no Copy), LoRAs.
import { expect, test, type Page } from '@playwright/test'
import { job } from './fixtures/data'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { open } from './helpers'

const DRAFT = {
  model: 'flux2_klein_9b', prompt: 'A grey cat asleep under an apple tree', lorasByModel: {}, aspect: '16:9', size: 1.5, images: 2,
  advancedByModel: {}, references: [], selected: null, draft: 'A grey cat asleep in the rain, under an apple tree',
}
/** The canvas a size makes is in the Size button's hover text. */
const canvas = (page: Page) => page.getByRole('button', { name: 'Size' })
/** The LoRAs and the model picker sit in the sheet the bar's fold raises. */
const raise = async (page: Page) => {
  await page.locator('[data-region="library-toggle"]').click()
  await expect(page.locator('[data-region="library-toggle"]')).toHaveAttribute('aria-expanded', 'true')
}
const ready = async (page: Page) => {
  await page.locator('[data-lora]').first().waitFor(); await expect(page.locator('[data-region="generate"]')).toHaveAttribute('aria-disabled', 'false')
}

test('generate → queue → done', async ({ page }) => {
  const { hub } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  await expect(canvas(page)).toHaveAttribute('title', /1680 × 944/)
  await page.locator('[data-region="generate"]').click()
  await expect.poll(() => hub.sent('job.submit').length).toBe(1)
  expect(hub.sent('job.submit')[0]!.d).toEqual({ tool: 'generate-image', kind: 'image', params: {
    tool: 'generate-image', model: 'flux2_klein_9b', mode: 'new', prompt: 'A grey cat asleep in the rain, under an apple tree', loras: [],
    width: 1680, height: 944, images: 2, steps: 4, guidance: null, seed: { mode: 'random' } } })
  const id = [...hub.jobs.keys()][0]!
  await expect(page.getByText('1 waiting in queue')).toBeVisible()
  hub.setJob(job(id, { state: 'running', started: 1, progress: { phase: 'loading', index: 1, count: 2, step: 0, steps: 4, pct: 0, eta_s: null, text: 'Loading Flux 2 Klein 9B' } }))
  await expect(page.getByText('Loading Flux 2 Klein 9B')).toBeVisible()
  hub.setJob(job(id, { state: 'running', started: 1, progress: { phase: 'inference', index: 1, count: 2, step: 3, steps: 4, pct: 38, eta_s: 6, text: '' } }))
  await expect(page.getByText('Generating 1 of 2')).toBeVisible()
  await expect(page.getByText('38% · about 6 s')).toBeVisible()
  await page.getByRole('button', { name: 'Cancel' }).isEnabled()
  hub.setJob(job(id, { state: 'done', outputs: ['a', 'b'] }))
  await expect(page.getByText(/^Done · 2 images in \d+ s$/)).toBeVisible()
  await expect(page.locator('[data-region="queue"]')).toHaveCount(0, { timeout: 6000 })
})

test('Cancel and Clear go to the controller; a failure shows until dismissed', async ({ page }) => {
  const running = job('j_R', { state: 'running', progress: { phase: 'inference', index: 1, count: 1, step: 1, steps: 4, pct: 10, eta_s: null, text: '' } })
  const { hub } = await open(page, '/', new FakeHub({ jobs: [running, job('j_W', { created: 2 })] }), apiState({ draft: DRAFT }))
  await ready(page)
  await expect(page.getByText('10% · estimating…')).toBeVisible()
  await page.locator('[data-region="status"]').getByRole('button', { name: 'Clear' }).click()
  await expect.poll(() => hub.sent('job.clear').map(e => e.d)).toEqual([{ lane: 'image.gpu0' }])
  await page.getByRole('button', { name: 'Cancel' }).click()
  await expect.poll(() => hub.sent('job.cancel').map(e => e.d)).toEqual([{ job: 'j_R' }])
  hub.setJob(job('j_F', { state: 'failed', error: { stage: 'generation', text: 'Out of GPU memory' } }))
  await expect(page.getByText('Failed: Out of GPU memory')).toBeVisible()
  await page.getByRole('button', { name: 'Dismiss' }).click()
  await expect.poll(() => hub.sent('job.dismiss').map(e => e.d)).toEqual([{ job: 'j_F' }])
})

test('Ctrl+Enter makes exactly one job, even with key repeat', async ({ page }) => {
  const { hub } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  await page.locator('#prompt').focus()
  await page.keyboard.down('Control')
  await page.keyboard.down('Enter')
  for (let i = 0; i < 10; i++) await page.locator('#prompt').dispatchEvent('keydown', { key: 'Enter', ctrlKey: true, repeat: true })
  await page.keyboard.up('Enter')
  await page.keyboard.up('Control')
  await page.locator('[data-region="draft"]').focus()
  await page.keyboard.press('Control+Enter')
  await expect.poll(() => hub.sent('job.submit').length).toBe(2)
  await page.waitForTimeout(300)
  expect(hub.sent('job.submit')).toHaveLength(2)
  // both presses render the draft, never the box; the box keeps its typed words
  expect(hub.sent('job.submit').map(e => (e.d as { params: { prompt: string } }).params.prompt)).toEqual([DRAFT.draft, DRAFT.draft])
  await expect(page.locator('#prompt')).toHaveValue('A grey cat asleep under an apple tree')
})

test('blocked Generate shows the reason and sends nothing', async ({ page }) => {
  const { hub } = await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, prompt: '', draft: '' } }))
  await page.locator('[data-lora]').first().waitFor()
  await expect(page.locator('[data-region="generate"]')).toHaveAttribute('aria-disabled', 'true')
  await expect(page.locator('[data-region="generate"]')).toHaveAttribute('title', 'The draft is empty')
  await page.locator('[data-region="generate"]').click({ force: true })
  await page.locator('#prompt').fill('words in the box')        // the box is never rendered: Ctrl+Enter is blocked too
  await page.locator('#prompt').press('Control+Enter')
  await page.waitForTimeout(300)
  expect(hub.sent('job.submit')).toHaveLength(0)
})

test('the draft is saved to the server 1 s after the last change', async ({ page }) => {
  const { st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  await page.locator('#prompt').fill('A red fox')
  await page.getByRole('button', { name: 'Size' }).click()
  await page.getByRole('option', { name: '2 MP' }).click()
  await expect.poll(() => (st.draft as { prompt: string; size: number } | null)?.prompt, { timeout: 4000 }).toBe('A red fox')
  expect((st.draft as { size: number }).size).toBe(2)
  await page.reload()
  await expect(page.locator('#prompt')).toHaveValue('A red fox')
  await expect(canvas(page)).toHaveAttribute('title', /1936 × 1088/)
})

test('a reconnect into a new session drops the prompt and the references the window kept', async ({ page }) => {
  const { hub, st } = await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, references: [{ id: 'out/2026-10-09/r1.png', w: 1200, h: 800 }] } }))
  await ready(page)
  await expect(page.locator('#prompt')).toHaveValue('A grey cat asleep under an apple tree')
  await page.locator('#prompt').fill('A red fox')
  await expect.poll(() => (st.draft as { prompt: string } | null)?.prompt, { timeout: 4000 }).toBe('A red fox')
  // The link drops for longer than the grace: the server forgot the session and hands back the settings alone.
  st.draft = { ...DRAFT, prompt: undefined, references: undefined, selected: undefined }
  hub.session = 's2222222222222222'
  hub.closeAll(1006)
  await expect(page.locator('#prompt')).toHaveValue('', { timeout: 10000 })
  await expect(page.locator('[data-socket] img')).toHaveCount(0)
  await page.waitForTimeout(1500)
  const puts = () => st.calls.filter(c => c.path === '/api/generate-image/draft' && c.method === 'PUT')
  const saved = puts()
  expect(saved.filter(c => (c.body as { prompt?: string }).prompt === 'A red fox')).toHaveLength(1)
  expect(saved.slice(1).every(c => !(c.body as { prompt?: string }).prompt)).toBe(true)
  await page.getByRole('button', { name: 'Size' }).click()
  await page.getByRole('option', { name: '2 MP' }).click()
  await expect.poll(() => puts().length, { timeout: 4000 }).toBeGreaterThan(saved.length)
  const last = puts().pop()!.body as Record<string, unknown>
  expect(Object.keys(last)).toEqual(['size'])
  expect('prompt' in last || 'references' in last).toBe(false)
})

test('a setting the tool server changes lands on the bar even while the window has an unsaved prompt', async ({ page }) => {
  const { hub, st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  await expect(canvas(page)).toBeVisible()
  await page.locator('#prompt').fill('change to 4 MP')         // unsaved for the next second
  st.draft = { ...(st.draft as object), size: 4 }               // the assistant set 4 MP meanwhile
  hub.broadcast('generate-image.draft', {}, 'workspace')
  await expect(page.getByRole('button', { name: 'Size' })).toHaveText(/4 MP/)
  await page.waitForTimeout(1500)
  const puts = st.calls.filter(c => c.path === '/api/generate-image/draft' && c.method === 'PUT').map(c => c.body as Record<string, unknown>)
  expect(puts.length).toBeGreaterThan(0)
  expect(puts.every(b => !('size' in b))).toBe(true)
  expect((st.draft as { size: number; prompt: string }).size).toBe(4)
  expect((st.draft as { prompt: string }).prompt).toBe('change to 4 MP')
})

test('the draft article follows the server live while the prompt box stays; it never reaches the box; Clear empties it', async ({ page }) => {
  const { hub, st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  const [box, panel] = [page.locator('#prompt'), page.locator('[data-region="draft"]')]
  const puts = () => st.calls.filter(c => c.path === '/api/generate-image/draft' && c.method === 'PUT').map(c => c.body)
  const assistantWrites = (draft: string) => { st.draft = { ...(st.draft as object), draft }; hub.broadcast('generate-image.draft', {}, 'workspace') }
  await expect(panel).toContainText(DRAFT.draft)
  assistantWrites('A grey cat asleep under a volcano')             // set_generate_image_settings {draft}
  await expect(panel).toContainText('A grey cat asleep under a volcano')
  await expect(box).toHaveValue(DRAFT.prompt)                      // the box: untouched
  await box.fill('my own words')                                   // unsaved for the next second
  assistantWrites('A grape orchard under a volcano')               // rewritten in place: one draft, live
  await expect(panel).toHaveText(/^A grape orchard under a volcano/)
  await expect.poll(puts, { timeout: 4000 }).toEqual([{ prompt: 'my own words' }])   // the unsaved edit was typed: kept
  // no way from the draft into the box: the page's foot (lower right corner) holds Clear only
  const foot = panel.locator('[data-region="draft-foot"]')
  await expect(foot.getByRole('button')).toHaveText(['Clear'])
  await expect(page.getByRole('button', { name: /Copy/ })).toHaveCount(0)
  const [p, f] = [(await panel.boundingBox())!, (await foot.boundingBox())!]
  expect(p.x + p.width - (f.x + f.width)).toBeLessThan(40)
  expect(p.y + p.height - (f.y + f.height)).toBeLessThan(40)
  expect(f.x - p.x).toBeGreaterThan(p.width / 2)
  await foot.getByRole('button', { name: 'Clear' }).click()
  await expect(panel).toHaveText("The assistant's draft appears here")
  await expect(box).toHaveValue('my own words')
  await expect.poll(puts, { timeout: 4000 }).toEqual([{ prompt: 'my own words' }, { draft: '' }])
})

test('LoRAs: on and off, strength by keys and by drag, prompt untouched', async ({ page }) => {
  const { st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  const id = 'flux2_klein_9b/photography/anime_cel_shade_1.safetensors'
  const row = page.locator(`[data-lora="${id}"]`)
  await raise(page)
  await expect(row).toHaveAttribute('aria-checked', 'false')
  await row.dblclick()
  await expect(row).toHaveAttribute('aria-checked', 'true')
  await expect(page.locator('[role="listbox"][aria-label="LoRAs"] [aria-checked="true"]')).toHaveCount(1)
  await expect(page.locator('#prompt')).toHaveValue('A grey cat asleep under an apple tree')
  const num = page.getByRole('button', { name: 'anime_cel_shade_1 strength' })
  await expect(num).toHaveText('1.00')
  await num.focus()
  await page.keyboard.press('ArrowLeft')
  await expect(num).toHaveText('0.99')
  await page.keyboard.press('Shift+ArrowLeft')
  await expect(num).toHaveText('0.89')
  const box = (await num.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 - 60, box.y + box.height / 2, { steps: 6 })
  await page.mouse.up()
  await expect(num).toHaveText('0.59')
  await expect.poll(() => (st.draft as { lorasByModel: Record<string, { id: string; strength: number }[]> } | null)?.lorasByModel.flux2_klein_9b?.[0]?.strength, { timeout: 3000 }).toBe(0.59)
  await page.getByRole('button', { name: 'Take anime_cel_shade_1 off' }).click()
  await expect(row).toHaveAttribute('aria-checked', 'false')
  await expect(page.locator('[role="listbox"][aria-label="LoRAs"] [aria-checked="true"]')).toHaveCount(0)
})
