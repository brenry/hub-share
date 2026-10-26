// Character notes: right-click a name → Notes… opens a box under it (Enter is a newline; Ctrl+Enter or leaving the
// box saves, Escape cancels). A name with notes shows a dot and its notes on hover.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState, type ApiState } from './fixtures/api'
import { fakeChars } from './fixtures/media'
import { row, tiles } from './fixtures/mediaPage'
import { open } from './helpers'

async function media(page: Page, names: string[], notes: Record<string, string> = {}): Promise<ApiState> {
  const st = apiState({ chars: fakeChars(names, notes) })
  await open(page, '/media', new FakeHub(), st)
  await tiles(page).first().waitFor()
  return st
}
const writes = (st: ApiState) => st.calls.filter(c => c.method !== 'GET').map(c => ({ path: c.path, body: c.body }))
const charMenu = (page: Page) => page.getByRole('menu', { name: 'Character' })
const notesBox = (page: Page, name: string) => page.getByRole('textbox', { name: `Notes on ${name}` })
const dot = (page: Page, name: string) => row(page, `char:${name}`).getByLabel('Has notes')
async function openNotes(page: Page, name: string) {
  await row(page, `char:${name}`).click({ button: 'right' })
  await charMenu(page).getByRole('menuitem', { name: 'Notes…' }).click()
  await expect(notesBox(page, name)).toBeFocused()
}
const CHARACTER_26 = 'Note 1.\nNote 2.'

test('a name with notes shows a dot and its notes in the row title; one without has neither', async ({ page }) => {
  await media(page, ['Character 42', 'Character 26', 'Character 28'], { 'Character 26': CHARACTER_26 })
  await expect(dot(page, 'Character 26')).toHaveCount(1)
  await expect(row(page, 'char:Character 26')).toHaveAttribute('title', `Character 26\n\n${CHARACTER_26}`)
  await expect(dot(page, 'Character 28')).toHaveCount(0)
  await expect(row(page, 'char:Character 28')).toHaveAttribute('title', 'Character 28')
  await expect(page.locator('[data-region="characters"] [aria-label="Has notes"]')).toHaveCount(1)
  await expect(row(page, 'char:Character 26')).toHaveText('Character 26')
})

test('Notes… opens a box under that name, prefilled, with no cap: a 1001-character note is saved whole', async ({ page }) => {
  const st = await media(page, ['Character 42', 'Character 26', 'Character 28'], { 'Character 26': CHARACTER_26 })
  await openNotes(page, 'Character 26')
  const box = notesBox(page, 'Character 26')
  await expect(box).toHaveValue(CHARACTER_26)
  expect(await box.getAttribute('maxlength')).toBeNull()
  expect(await box.evaluate(e => e.tagName)).toBe('TEXTAREA')
  const y = async (l: ReturnType<typeof row>) => (await l.boundingBox())!.y
  expect(await y(box)).toBeGreaterThan(await y(row(page, 'char:Character 26')))
  expect(await y(box)).toBeLessThan(await y(row(page, 'char:Character 28')))
  await expect(row(page, 'char:Character 26')).toBeVisible()

  await box.fill('x'.repeat(1001))
  await expect(box).toHaveValue('x'.repeat(1001))
  await box.press('Control+Enter')
  await expect(page.getByText('Notes saved for Character 26')).toBeVisible()
  expect(writes(st)).toEqual([{ path: '/api/media/characters/notes', body: { id: 'chars/Character 26.png', notes: 'x'.repeat(1001) } }])
})

test('Enter makes a newline; Ctrl+Enter saves the raw text, the dot and title follow', async ({ page }) => {
  const st = await media(page, ['Character 42', 'Character 28'])
  await openNotes(page, 'Character 28')
  const box = notesBox(page, 'Character 28')
  await expect(box).toHaveValue('')
  await box.pressSequentially('Lives in a cave')
  await box.press('Enter')
  await box.pressSequentially('Wears a cape ')
  await expect(box).toHaveValue('Lives in a cave\nWears a cape ')
  await expect(box).toBeVisible()
  expect(writes(st)).toEqual([])

  await box.press('Control+Enter')
  await expect(page.getByText('Notes saved for Character 28')).toBeVisible()
  await expect(box).toHaveCount(0)
  expect(writes(st)).toEqual([{ path: '/api/media/characters/notes', body: { id: 'chars/Character 28.png', notes: 'Lives in a cave\nWears a cape ' } }])
  await expect(dot(page, 'Character 28')).toHaveCount(1)
  await expect(row(page, 'char:Character 28')).toHaveAttribute('title', 'Character 28\n\nLives in a cave\nWears a cape')
  await expect(dot(page, 'Character 42')).toHaveCount(0)

  await openNotes(page, 'Character 28')
  await expect(notesBox(page, 'Character 28')).toHaveValue('Lives in a cave\nWears a cape')
})

test('leaving the box saves', async ({ page }) => {
  const st = await media(page, ['Character 42', 'Character 28'])
  await openNotes(page, 'Character 42')
  await notesBox(page, 'Character 42').fill('Note 3.')
  await row(page, 'chars').click()
  await expect(page.getByText('Notes saved for Character 42')).toBeVisible()
  await expect(notesBox(page, 'Character 42')).toHaveCount(0)
  expect(writes(st)).toEqual([{ path: '/api/media/characters/notes', body: { id: 'chars/Character 42.png', notes: 'Note 3.' } }])
  await expect(row(page, 'char:Character 42')).toHaveAttribute('title', 'Character 42\n\nNote 3.')
})

test('emptying the notes clears them: "Notes cleared", the dot goes', async ({ page }) => {
  const st = await media(page, ['Character 26', 'Character 28'], { 'Character 26': CHARACTER_26 })
  await openNotes(page, 'Character 26')
  await notesBox(page, 'Character 26').fill('  \n ')
  await notesBox(page, 'Character 26').press('Control+Enter')
  await expect(page.getByText('Notes cleared for Character 26')).toBeVisible()
  expect(writes(st)).toEqual([{ path: '/api/media/characters/notes', body: { id: 'chars/Character 26.png', notes: '  \n ' } }])
  await expect(dot(page, 'Character 26')).toHaveCount(0)
  await expect(row(page, 'char:Character 26')).toHaveAttribute('title', 'Character 26')
})

test('unchanged notes (after trim) send nothing, by Ctrl+Enter or by blur', async ({ page }) => {
  const st = await media(page, ['Character 26', 'Character 28'], { 'Character 26': CHARACTER_26 })
  await openNotes(page, 'Character 26')
  await notesBox(page, 'Character 26').press('Control+Enter')
  await expect(notesBox(page, 'Character 26')).toHaveCount(0)

  await openNotes(page, 'Character 26')
  await notesBox(page, 'Character 26').fill(`\n  ${CHARACTER_26}  \n`)
  await row(page, 'chars').click()
  await expect(notesBox(page, 'Character 26')).toHaveCount(0)

  await openNotes(page, 'Character 28')
  await notesBox(page, 'Character 28').fill('   ')
  await notesBox(page, 'Character 28').press('Control+Enter')
  await expect(notesBox(page, 'Character 28')).toHaveCount(0)
  await expect(page.getByText(/^Notes (saved|cleared)/)).toHaveCount(0)
  expect(writes(st)).toEqual([])
})

test('Escape cancels: nothing sent, the notes stay as they were', async ({ page }) => {
  const st = await media(page, ['Character 26', 'Character 28'], { 'Character 26': CHARACTER_26 })
  await openNotes(page, 'Character 26')
  await notesBox(page, 'Character 26').fill('Something else')
  await notesBox(page, 'Character 26').press('Escape')
  await expect(notesBox(page, 'Character 26')).toHaveCount(0)
  await openNotes(page, 'Character 26')
  await expect(notesBox(page, 'Character 26')).toHaveValue(CHARACTER_26)
  await notesBox(page, 'Character 26').press('Escape')
  await expect(notesBox(page, 'Character 26')).toHaveCount(0)
  await expect(row(page, 'char:Character 26')).toHaveAttribute('title', `Character 26\n\n${CHARACTER_26}`)
  expect(writes(st)).toEqual([])
})

test('the shown character follows its new id when saving notes turns a JPEG into a PNG', async ({ page }) => {
  const st = await media(page, ['Character 30.jpg', 'Character 28'])
  await row(page, 'char:Character 30').click()
  await expect(page.locator('[data-stage-img]')).toHaveAttribute('src', /chars\/Character 30\.jpg/)
  await openNotes(page, 'Character 30')
  await notesBox(page, 'Character 30').fill('Robot figure')
  await notesBox(page, 'Character 30').press('Control+Enter')
  await expect(page.getByText('Notes saved for Character 30')).toBeVisible()
  expect(writes(st)).toEqual([{ path: '/api/media/characters/notes', body: { id: 'chars/Character 30.jpg', notes: 'Robot figure' } }])
  await expect(row(page, 'char:Character 30')).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('[data-stage-img]')).toHaveAttribute('src', /chars\/Character 30\.png/)
  await expect(page.locator('[data-item="chars/Character 30.png"]')).toHaveAttribute('aria-selected', 'true')
})

test('notes on a character not on show leave the view alone', async ({ page }) => {
  const st = await media(page, ['Character 30.jpg', 'Character 28'])
  await row(page, 'char:Character 28').click()
  await openNotes(page, 'Character 30')
  await notesBox(page, 'Character 30').fill('Robot figure')
  await notesBox(page, 'Character 30').press('Control+Enter')
  await expect(page.getByText('Notes saved for Character 30')).toBeVisible()
  expect(st.chars.items.map(c => c.id)).toEqual(['chars/Character 28.png', 'chars/Character 30.png'])
  await expect(row(page, 'char:Character 28')).toHaveAttribute('aria-selected', 'true')
  await expect(row(page, 'char:Character 30')).toHaveAttribute('aria-selected', 'false')
  await expect(page.locator('[data-stage-img]')).toHaveAttribute('src', /chars\/Character 28\.png/)
})
