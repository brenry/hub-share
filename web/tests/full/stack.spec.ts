// Full stack: the real controller + real image worker on the fake engine + the built UI, driven in Chromium.
// Run: npm run build && npm run full
import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import type { Job } from '../../src/lib/protocol'
import { Stack } from './stack'

type Frame = { t: string; d?: { item?: { id: string; created: number } } }

let stack: Stack
let ctx: BrowserContext
let work: Page
let media: Page
const frames: Frame[] = []
const jobFrames: Job[] = []

test.describe.configure({ mode: 'serial' })

test.beforeAll(async ({ browser }) => {
  stack = new Stack()
  await stack.init()
  await stack.startHub()
  ctx = await browser.newContext({ baseURL: stack.origin, viewport: { width: 1920, height: 1080 } })
})

test.afterAll(async () => {
  await ctx?.close()
  await stack?.close()
})

test('1 · a screen pairs with a hub pair link', async () => {
  work = await ctx.newPage()
  work.on('websocket', ws => ws.on('framereceived', f => {
    const m = JSON.parse(String(f.payload)) as { t: string; d: Job }
    if (m.t === 'job') jobFrames.push(m.d)
  }))
  await work.goto(stack.pairLink('Desk'))
  await expect(work).toHaveURL(`${stack.origin}/`)
  await expect(work.locator('[data-region="model-picker"]')).toBeVisible()
})

test('2 · Generate Image: model, LoRA, prompt, 2 images; /media gets both live (3)', async () => {
  media = await ctx.newPage()
  media.on('websocket', ws => ws.on('framereceived', f => { frames.push(JSON.parse(String(f.payload)) as Frame) }))
  await media.goto('/media')
  await expect(media.locator('[data-live]')).toHaveText('Live')

  await work.locator('[data-region="model-picker"]').click()
  await work.getByRole('option', { name: /Flux 2 Klein 9B/ }).click()
  const lora = work.locator('[data-lora="flux2_klein_9b/grain.safetensors"]')
  await lora.dblclick()
  await expect(work.getByRole('list', { name: 'Active LoRAs' })).toContainText('Film Grain')
  await work.locator('#prompt').fill('A lighthouse at dusk')
  const images = work.getByRole('group', { name: 'Images' })
  while ((await images.locator('output').textContent()) !== '2') await images.getByRole('button', { name: 'More images' }).click()
  await work.locator('[data-region="generate"]').click()
  await expect(work.getByText(/^Done · 2 images in \d+ s$/)).toBeVisible({ timeout: 60_000 })
  const states = jobFrames.map(j => j.state)
  expect(states.slice(0, 1)).toEqual(['queued'])
  expect(states).toContain('running')
  expect(states.at(-1)).toBe('done')
  expect(jobFrames.some(j => j.progress !== null && j.progress.count === 2)).toBe(true)

  await expect(media.locator('[data-item]')).toHaveCount(2)
  const live = frames.filter(f => f.t === 'generation').map(f => f.d!.item!)
  expect(live).toHaveLength(2)
  const list = await (await media.request.get('/api/media?limit=10')).json() as { items: { id: string; createdAt: number }[] }
  for (const g of live) {
    const listed = list.items.find(i => i.id === g.id)!
    expect(Math.abs(listed.createdAt - g.created)).toBeLessThan(5)
    expect(Math.abs(g.created - Date.now() / 1000)).toBeLessThan(120)
  }
})

test('4 · Media Send places a reference in Generate; both pages confirm', async () => {
  await media.locator('[data-item]').first().click()
  await expect(media.locator('[data-send-main]')).toHaveAttribute('title', 'Add as reference')
  await media.locator('[data-send-main]').click()
  await expect(media.getByText('Added to Generate Image · Reference 1')).toBeVisible()
  await expect(work.locator('[data-socket="reference_1"] img')).toBeVisible()
  await work.getByRole('button', { name: 'Remove reference 1' }).click()
})

async function openCard(card: string): Promise<void> {
  if (!(await work.locator('[data-card]').first().isVisible())) await work.getByRole('banner').getByRole('button', { name: 'Settings' }).click()
  await work.locator(`[data-card="${card}"]`).click()
}

test('5 · MCP: the draft set lands beside the chat, not in the prompt box; push_draft fills the box; only Generate renders', async () => {
  await openCard('assistant')
  await work.getByRole('switch', { name: 'Assistant access' }).click()
  const { mcp_key: key } = await (await work.request.get('/api/assistant')).json() as { mcp_key: string }
  const listed = await stack.mcp(key, 'tools/list', {})
  expect((listed.body as { result: { tools: { name: string }[] } }).result.tools.map(t => t.name)).toEqual(
    ['get_generate_image_settings', 'set_generate_image_settings', 'list_image_models', 'push_draft', 'list_loras'])
  const set = await stack.mcp(key, 'tools/call', { name: 'set_generate_image_settings', arguments: { draft: 'A red kite' } })
  expect(set.status).toBe(200)
  await work.getByRole('tab', { name: 'Generate Image' }).click()
  await expect(work.locator('[data-region="draft"]')).toContainText('A red kite')
  await expect(work.locator('#prompt')).toHaveValue('A lighthouse at dusk')
  const pushed = await stack.mcp(key, 'tools/call', { name: 'push_draft', arguments: {} })
  expect(pushed.status).toBe(200)
  await expect(work.locator('#prompt')).toHaveValue('A red kite')
  await expect(work.locator('[data-region="draft"]')).toContainText('A red kite')
  await expect(media.locator('[data-item]')).toHaveCount(2)       // no tool rendered anything
  await work.locator('[data-region="generate"]').click()           // the Generate press renders the box
  await expect(work.getByText(/^Done · 2 images in \d+ s$/)).toBeVisible({ timeout: 60_000 })
  await expect(media.locator('[data-item]')).toHaveCount(4)
})

test('6 · Settings cards: Network shows the device', async () => {
  await work.getByRole('banner').getByRole('button', { name: 'Settings' }).click()
  await expect(work.getByText(`${stack.data}/outputs`)).toBeVisible()
  await work.getByRole('combobox', { name: 'Idle minutes' }).selectOption('30')
  await expect.poll(async () => ((await (await work.request.get('/api/settings')).json()) as { vram: { idle_minutes: number } }).vram.idle_minutes).toBe(30)
  await openCard('assistant')
  await expect(work.getByText(/^127\.0\.0\.1 · \d+ s ago$/)).toBeVisible()
  await expect(work.getByLabel('Clients').getByText('OK', { exact: true })).toBeVisible()
  await openCard('network')
  const devices = work.getByLabel('Devices')
  await expect(devices.getByText('This device')).toBeVisible()
  await expect(devices.getByText('127.0.0.1 · Connected · 2 windows')).toBeVisible()
})

test('7 · restart: the page reconnects and reloads. Stop: Switched off', async () => {
  await work.evaluate(() => { (window as unknown as { marker: number }).marker = 1 })
  await stack.stopHub(true)
  await stack.startHub()
  await expect.poll(() => work.evaluate(() => (window as unknown as { marker?: number }).marker), { timeout: 30_000 }).toBeUndefined()
  await expect(work.locator('[data-cover]')).toHaveCount(0, { timeout: 15_000 })
  await stack.stopHub(false)
  await expect(work.locator('[data-cover="off"]')).toContainText('Switched off')
  await expect(media.locator('[data-cover="off"]')).toContainText('Switched off')
})
