// A MiniMax H3 model that keeps a sound as its clip's has a Sound box after the picture boxes. A sound from
// Media → Sounds (or a sound file from this computer, kept in Sounds) goes in it; it shows the sound's name and
// length, the clip's seconds are the sound's and not editable, and Generate sends the sound. Another model: no box.
import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { H3_OMNI, MODELS } from './fixtures/data'
import type { Model } from '../../src/modules/generate-image/types'
import { open } from './helpers'

const HEARS: Model = { ...MODELS.find(m => m.id === 'minimax_h3_ref2va')!, id: 'minimax_h3_ref2va_pruned', label: 'H3 Omni Sound',
  video: { ...H3_OMNI, soundtrack: 'AS' } }
const LINE = 'sounds/2026-10-17/120000-000.wav'
const CHARACTER_7 = { id: 'out/2026-10-09/r1.png', w: 1200, h: 800 }
const DRAFT = { model: HEARS.id, prompt: '', lorasByModel: {}, aspect: 'auto', size: 1, images: 1, advancedByModel: {},
  references: [CHARACTER_7], selected: null, draft: 'Character 7 stands on a bare stage, talking to the camera.' }
const bar = (page: Page) => page.locator('footer[data-region="bar"]')
const sheet = (page: Page) => page.locator('[data-region="library-sheet"]')
const box = (page: Page) => bar(page).locator('[data-socket="sound"]')
const fixture = (name: string) => new URL(`./fixtures/${name}`, import.meta.url)

async function dropMedia(page: Page, items: unknown[]) {
  const dt = await page.evaluateHandle(json => { const t = new DataTransfer(); t.setData('application/x-hub-media', json); return t }, JSON.stringify(items))
  await box(page).dispatchEvent('dragover', { dataTransfer: dt })
  await box(page).dispatchEvent('drop', { dataTransfer: dt })
}

test('a sound from Media goes in the Sound box, fixes the seconds and goes with the press', async ({ page }) => {
  const { hub } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT, extraModels: [HEARS] }))
  await expect(box(page)).toHaveAttribute('aria-label', 'Sound, empty')
  await dropMedia(page, [{ id: LINE, w: 0, h: 0, kind: 'sound', seconds: 14 }])
  await expect(box(page)).toHaveAttribute('data-sound', LINE)
  await expect(box(page)).toContainText('120000-000')
  await expect(box(page)).toContainText('14.0 s')
  await page.locator('[data-region="video-toggle"]').click()
  const seconds = sheet(page).locator('[data-region="seconds"] input')
  await expect(seconds).toHaveValue('14')
  await expect(seconds).toBeDisabled()
  await page.keyboard.press('Escape')
  await page.locator('[data-region="generate"]').click()
  await expect.poll(() => hub.sent('job.submit').length).toBe(1)
  expect(hub.sent('job.submit')[0]!.d).toMatchObject({ params: { model: HEARS.id, sound: LINE, references: [CHARACTER_7.id] } })
  await box(page).getByRole('button', { name: 'Remove sound' }).click()
  await expect(box(page)).toHaveAttribute('aria-label', 'Sound, empty')
})

test('a sound file from this computer lands in Sounds and goes in the box', async ({ page }) => {
  await open(page, '/', new FakeHub(), apiState({ draft: DRAFT, extraModels: [HEARS] }))
  await page.route('**/api/sounds/upload', route => route.fulfill({ json: { id: 'sounds/2026-10-17/up1.wav', seconds: 3 } }))
  const b64 = readFileSync(fixture('voice-3s.wav')).toString('base64')
  const dt = await page.evaluateHandle(data => {
    const t = new DataTransfer()
    t.items.add(new File([Uint8Array.from(atob(data), c => c.charCodeAt(0))], 'Character 7 line.wav', { type: 'audio/wav' }))
    return t
  }, b64)
  await box(page).dispatchEvent('drop', { dataTransfer: dt })
  await expect(box(page)).toHaveAttribute('data-sound', 'sounds/2026-10-17/up1.wav')
  await expect(box(page)).toContainText('3.0 s')
})

test('a model that keeps no sound has no Sound box', async ({ page }) => {
  await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, sound: { id: LINE, seconds: 14 } }, extraModels: [HEARS] }))
  await expect(box(page)).toHaveAttribute('data-sound', LINE)
  await page.locator('[data-region="video-toggle"]').click()
  await sheet(page).locator('[data-region="model-picker"]').click()
  await page.getByRole('option', { name: 'H3 Omni — Pruned' }).click()
  await expect(bar(page).locator('[data-region="references"]')).toBeVisible()
  await expect(box(page)).toHaveCount(0)
})
