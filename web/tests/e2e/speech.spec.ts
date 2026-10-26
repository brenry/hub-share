// Stage 12: a character speaks a typed line. In Generate's pulldown the speech model; Character 8's picture in its
// one box; Generate line → the job; the WAV lands in Media → Sounds, plays there, and Keep as voice of… → Character 8 gives
// the character its voice sample. Voice… on a character keeps the words for its voice.
import { expect, test, type Page } from '@playwright/test'
import type { GenerationItem } from '../../src/lib/protocol'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { SPEECH, job, summary } from './fixtures/data'
import { fakeChars } from './fixtures/media'
import { row, tiles } from './fixtures/mediaPage'
import { open } from './helpers'

const CHARACTER_8 = { id: 'chars/Character 8.png', w: 1024, h: 1024 }
const DRAFT = {
  model: 'flux2_klein_9b', lastModel: { image: 'flux2_klein_9b', video: '' }, prompt: '', lorasByModel: {}, aspect: 'auto', size: 1, images: 2,
  advancedByModel: {}, references: [CHARACTER_8], selected: null, draft: 'Stay right there!',
}
const SOUND = 'sounds/2026-10-17/120000-000.wav'
const bar = (page: Page) => page.locator('footer[data-region="bar"]')
const generation = (id: string): GenerationItem => ({ id, kind: 'sound', url: `/files/${id}`, thumb: null, w: null, h: null, created: 1791562000, job: 'j_line', seconds: 4.2 })

test('the speech model from the pulldown: one box, no size, shape, steps or count; Generate line sends the line and the character', async ({ page }) => {
  const { hub } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT, extraModels: [SPEECH], chars: fakeChars(['Character 8']) }))
  await bar(page).locator('[data-region="steps"] input').waitFor()
  await page.locator('[data-region="library-toggle"]').click()
  await page.locator('[data-region="model-picker"]').first().click()
  await page.getByRole('option', { name: SPEECH.label }).click()
  await expect(bar(page).locator('[data-region="references"]')).toHaveAttribute('data-cap', '1')
  await expect(bar(page).locator('[data-region="steps"]')).toHaveCount(0)
  await expect(bar(page).locator('[data-region="count"]')).toHaveCount(0)
  await expect(bar(page).getByRole('button', { name: 'Size' })).toHaveCount(0)
  await expect(bar(page).getByRole('button', { name: 'Aspect' })).toHaveCount(0)
  const go = page.locator('[data-region="generate"]')
  await expect(go).toHaveAttribute('aria-label', 'Generate line')
  await expect(go).toHaveAttribute('aria-disabled', 'false')
  await go.click()
  await expect.poll(() => hub.sent('job.submit').length).toBe(1)
  expect(hub.sent('job.submit')[0]!.d).toMatchObject({ params: { model: SPEECH.id, mode: 'refs', prompt: DRAFT.draft, references: [CHARACTER_8.id], loras: [] } })
  const id = [...hub.jobs.keys()][0]!
  const line = summary(SPEECH.id, [7], { kind: 'sound' })
  hub.setJob(job(id, { state: 'running', started: 1, summary: line, progress: { phase: 'inference', index: 1, count: 1, step: 4, steps: 20, pct: 20, eta_s: 30, text: '' } }))
  await expect(page.getByText('Generating 1 of 1')).toBeVisible()
  hub.setJob(job(id, { state: 'done', summary: line, outputs: [SOUND] }))
  await expect(page.getByText(/^Done · line in \d+ s$/)).toBeVisible()
})

test('a picture that is no character blocks the press in one line', async ({ page }) => {
  const draft = { ...DRAFT, model: SPEECH.id, references: [{ id: 'out/2026-10-09/r1.png', w: 1200, h: 800 }] }
  await open(page, '/', new FakeHub(), apiState({ draft, extraModels: [SPEECH] }))
  const go = page.locator('[data-region="generate"]')
  await expect(go).toHaveAttribute('aria-disabled', 'true')
  await expect(go).toHaveAttribute('title', "Drop one character's picture")
})

test('the line lands in Sounds and plays; Keep as voice of… → Character 8 gives the character its voice sample', async ({ page }) => {
  const hub = new FakeHub()
  const st = apiState({ chars: fakeChars(['Character 8', 'Character 17']) })
  await open(page, '/media', hub, st)
  await tiles(page).first().waitFor()
  await expect(row(page, 'sounds')).toHaveText('Sounds')
  st.sounds.unshift({ id: SOUND, kind: 'sound', url: `/files/${SOUND}`, thumb: null, w: null, h: null, createdAt: 1791562000, group: '', fav: false, seconds: 4.2 })
  hub.broadcast('generation', { item: generation(SOUND) }, 'media')
  await expect(page.getByText('New sound')).toBeVisible()
  await expect(row(page, 'sounds')).toHaveText('Sounds1')
  await expect(page.locator('[data-item^="sounds/"]')).toHaveCount(0)
  await row(page, 'sounds').click()
  await expect(tiles(page)).toHaveCount(1)
  await expect(tiles(page).first()).toHaveText('4.2 s')
  // a sound drags to Edit Video's tracks, as a sound
  await expect(tiles(page).first()).toHaveAttribute('draggable', 'true')
  const raw = await tiles(page).first().evaluate(el => {
    const dt = new DataTransfer()
    el.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: dt }))
    return dt.getData('application/x-hub-media')
  })
  expect(JSON.parse(raw)).toEqual([expect.objectContaining({ id: SOUND, kind: 'sound', seconds: 4.2 })])
  await expect(page.locator('[data-region="sound"] audio')).toHaveAttribute('src', `/files/${SOUND}`)
  await tiles(page).first().click({ button: 'right' })
  const menu = page.getByRole('menu', { name: 'Sound' })
  await expect(menu.getByRole('menuitem', { name: 'Favorite' })).toBeDisabled()
  const keep = menu.getByRole('menuitem', { name: 'Keep as voice of…' })
  await keep.hover()
  await page.getByRole('menu', { name: 'Keep as voice of…' }).getByRole('menuitem', { name: 'Character 8' }).click()
  await expect(page.getByText('Voice of Character 8 kept')).toBeVisible()
  expect(st.calls.filter(c => c.path === '/api/media/keep-voice').map(c => c.body)).toEqual([{ id: SOUND, name: 'Character 8' }])
  expect(st.chars.items.find(c => c.name === 'Character 8')!.sample).toBe(true)
})

test('Voice… on a character keeps the words for its voice; Ctrl+Enter saves', async ({ page }) => {
  const st = apiState({ chars: fakeChars(['Character 8']) })
  await open(page, '/media', new FakeHub(), st)
  await tiles(page).first().waitFor()
  await row(page, 'char:Character 8').click({ button: 'right' })
  await page.getByRole('menu', { name: 'Character' }).getByRole('menuitem', { name: 'Voice…' }).click()
  const box = page.getByRole('textbox', { name: 'Voice of Character 8' })
  await expect(box).toBeFocused()
  await box.fill('low, deep gravelly voice, slow')
  await box.press('Control+Enter')
  await expect(page.getByText('Voice saved for Character 8')).toBeVisible()
  expect(st.calls.filter(c => c.path === '/api/media/characters/voice').map(c => c.body)).toEqual([
    { id: 'chars/Character 8.png', voice: 'low, deep gravelly voice, slow' }])
  expect(st.chars.items[0]!.voice).toBe('low, deep gravelly voice, slow')
})
