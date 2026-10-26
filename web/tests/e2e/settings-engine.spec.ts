// Settings → Image engine: the memory profiles (general, and for video models: the general one or its own) and the video
// sizes the size menu offers, saved with PATCH /api/settings.
import { expect, test } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { open, openSettings } from './helpers'

test('the memory profile shows the engine\'s own, lists the profiles by number, and saves the one picked', async ({ page }) => {
  const { st } = await open(page, '/', new FakeHub(), apiState())
  await openSettings(page)
  const engine = page.getByRole('region', { name: 'Image engine' })
  const pick = engine.getByRole('combobox', { name: 'Memory profile', exact: true })
  await expect(pick).toHaveValue('engine')
  await expect(pick.locator('option')).toHaveText(["Engine's own", '1 · High RAM / high VRAM', '3.5 · Very low RAM / high VRAM',
    '4 · Low RAM / low VRAM', '5 · Very low RAM / low VRAM, fail safe'])
  await expect(engine.getByText('Takes effect at the next engine start')).toBeVisible()
  await pick.selectOption('5')
  await expect(pick).toHaveValue('5')
  await pick.selectOption('3.5')
  await pick.selectOption('engine')
  const patches = () => st.calls.filter(c => c.method === 'PATCH' && c.path === '/api/settings').map(c => c.body)
  await expect.poll(patches).toEqual([{ engine: { profile: 5 } }, { engine: { profile: 3.5 } }, { engine: { profile: 'engine' } }])
  expect(st.settings.engine.profile).toBe('engine')
})

test('a saved profile is shown as saved', async ({ page }) => {
  const st = apiState()
  st.settings.engine.profile = 4
  await open(page, '/', new FakeHub(), st)
  await openSettings(page)
  await expect(page.getByRole('combobox', { name: 'Memory profile', exact: true })).toHaveValue('4')
})

test('the video memory profile sits under the first, follows it by default, and saves the one picked', async ({ page }) => {
  const { st } = await open(page, '/', new FakeHub(), apiState())
  await openSettings(page)
  const engine = page.getByRole('region', { name: 'Image engine' })
  const pick = engine.getByRole('combobox', { name: 'Video memory profile' })
  await expect(pick).toHaveValue('same')
  await expect(pick.locator('option')).toHaveText(['Same as above', "Engine's own", '1 · High RAM / high VRAM',
    '3.5 · Very low RAM / high VRAM', '4 · Low RAM / low VRAM', '5 · Very low RAM / low VRAM, fail safe'])
  const boxes = engine.getByRole('combobox')
  await expect(boxes).toHaveCount(2)
  await expect(boxes.nth(0)).toHaveAccessibleName('Memory profile')
  await pick.selectOption('4')
  await pick.selectOption('engine')
  await pick.selectOption('same')
  const patches = () => st.calls.filter(c => c.method === 'PATCH' && c.path === '/api/settings').map(c => c.body)
  await expect.poll(patches).toEqual([{ engine: { profile_video: 4 } }, { engine: { profile_video: 'engine' } }, { engine: { profile_video: 'same' } }])
  await expect(engine.getByRole('combobox', { name: 'Memory profile', exact: true })).toHaveValue('engine')
})

test('the video sizes: the catalog\'s names, the offered ones on, at least one and at most three', async ({ page }) => {
  const { st } = await open(page, '/', new FakeHub(), apiState())
  await openSettings(page)
  const engine = page.getByRole('region', { name: 'Image engine' })
  const size = (n: string) => engine.getByRole('switch', { name: n, exact: true })
  for (const [n, on] of [['480p', true], ['540p', true], ['720p', false], ['1080p', false]] as const)
    await expect(size(n)).toHaveAttribute('aria-checked', String(on))
  await size('1080p').click()
  await expect(size('1080p')).toHaveAttribute('aria-checked', 'true')
  await expect(size('720p')).toBeDisabled()
  await size('480p').click()
  await size('540p').click()
  await expect(size('1080p')).toBeDisabled()
  const patches = () => st.calls.filter(c => c.method === 'PATCH' && c.path === '/api/settings').map(c => c.body)
  const tiers = (t: string[]) => ({ modules: { 'generate-image': { video_tiers: t } } })
  await expect.poll(patches).toEqual([tiers(['480p', '540p', '1080p']), tiers(['540p', '1080p']), tiers(['1080p'])])
  expect(st.settings.video_tiers.offered).toEqual(['1080p'])
})

test('no catalog read yet: no sizes to pick', async ({ page }) => {
  const st = apiState()
  st.settings.video_tiers = { names: [], offered: [] }
  await open(page, '/', new FakeHub(), st)
  await openSettings(page)
  await expect(page.getByRole('region', { name: 'Image engine' }).getByRole('switch')).toHaveCount(0)
})
