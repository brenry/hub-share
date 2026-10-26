// Connection states: On, Power cut, Switched off, Not paired; boot reload; pairing page.
import { expect, test } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { open } from './helpers'

const cover = (page: import('@playwright/test').Page) => page.locator('[data-cover]')
// The page made inert by a cut; the shut LoRA sheet is inert by design and is not counted.
const inert = (page: import('@playwright/test').Page) => page.locator('[inert]:not([data-region="library-sheet"])')
// A model picked in the pulldown: the bar shows its LoRAs (no model is chosen for it).
const picked = () => apiState({ draft: { model: 'flux2_klein_9b' } })

test('a short drop shows nothing; a longer one blurs and recovers, then re-sends focus and sockets', async ({ page }) => {
  const { hub } = await open(page, '/', new FakeHub(), picked())
  await page.locator('[data-lora]').first().waitFor()
  const sockets = hub.sent('sockets').length
  hub.closeAll(1011)
  await page.waitForTimeout(1000)
  await expect(cover(page)).toHaveCount(0)
  await expect.poll(() => hub.lines.length).toBe(1)
  expect(hub.sent('focus').length).toBeGreaterThanOrEqual(2)
  expect(hub.sent('sockets').length).toBeGreaterThan(sockets)

  hub.refuse = true
  hub.closeAll(4030)
  await expect(cover(page)).toHaveAttribute('data-cover', 'cut', { timeout: 4000 })
  await expect(page.getByText('Reconnecting…').first()).toBeVisible()
  expect(await inert(page).count()).toBe(1)
  hub.refuse = false
  await expect(cover(page)).toHaveCount(0, { timeout: 12000 })
  expect(await inert(page).count()).toBe(0)
})

test('Switched off dims the page and offers Check now', async ({ page }) => {
  const { hub } = await open(page, '/', new FakeHub(), picked())
  await page.locator('[data-lora]').first().waitFor()
  hub.refuse = true
  hub.broadcast('going_off', { reason: 'shutdown', back_in_s: null })
  hub.closeAll(4000)
  await expect(cover(page)).toHaveAttribute('data-cover', 'off')
  await expect(page.getByText('Switched off')).toBeVisible()
  hub.refuse = false
  await page.getByRole('button', { name: 'Check now' }).click()
  await expect(cover(page)).toHaveCount(0)
})

test('an unpaired screen says so and stops retrying', async ({ page }) => {
  const hub = new FakeHub()
  await page.routeWebSocket(/\/bus$/, ws => { hub.got.push({ t: 'try' }); ws.close({ code: 4003, reason: '' }) })
  await page.goto('/media')
  await expect(cover(page)).toHaveAttribute('data-cover', 'unpaired')
  await expect(page.getByText('Not paired')).toBeVisible()
  await page.waitForTimeout(2000)
  expect(hub.got).toHaveLength(1)
})

test('a new controller boot reloads the page', async ({ page }) => {
  const { hub } = await open(page, '/media', new FakeHub(), apiState())
  await page.locator('[data-item]').first().waitFor()
  await page.evaluate(() => { (window as unknown as { marker: number }).marker = 1 })
  hub.boot = 'b0000000000000002'
  hub.closeAll(4001)
  await expect.poll(() => page.evaluate(() => (window as unknown as { marker?: number }).marker ?? 0), { timeout: 8000 }).toBe(0)
  await page.locator('[data-item]').first().waitFor()
})

test('pairing: a good code continues to the next page; a bad one says so', async ({ page }) => {
  const st = apiState()
  await open(page, '/pair#c=bad', new FakeHub(), st)
  await expect(page.locator('[data-pair="bad"]')).toHaveText('This link is not valid or was already used')
  expect(page.url()).not.toContain('#c=')
  await page.goto('about:blank')
  await page.goto('/pair#c=good&next=/media')
  await page.waitForURL(u => u.pathname === '/media')
  expect(st.calls.filter(c => c.path === '/api/pair').map(c => c.body)).toEqual([{ code: 'bad' }, { code: 'good' }])
})

test('runs under the controller CSP with no violations and no requests off the hub origin', async ({ page }) => {
  const CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
  const violations: string[] = []
  const foreign: string[] = []
  page.on('console', m => { if (/Content Security Policy/i.test(m.text())) violations.push(m.text()) })
  page.on('request', r => { if (!r.url().startsWith('http://127.0.0.1:4173/') && !r.url().startsWith('ws://127.0.0.1:4173/')) foreign.push(r.url()) })
  await page.route(u => u.pathname === '/' || u.pathname === '/media', async route => {
    const res = await route.fetch()
    await route.fulfill({ response: res, headers: { ...res.headers(), 'content-security-policy': CSP } })
  })
  await open(page, '/', new FakeHub(), picked())
  await page.locator('[data-lora]').first().waitFor()
  await page.goto('/media')
  await page.locator('[data-item]').first().waitFor()
  expect(violations).toEqual([])
  expect(foreign).toEqual([])
})
