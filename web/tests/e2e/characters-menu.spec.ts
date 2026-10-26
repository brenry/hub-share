// Characters by menu: Add to Characters on a thumbnail (a copy under a typed name), and Rename / Delete character on a
// name in the tree. The drag-and-drop side is in characters.spec.ts, Notes… in characters-notes.spec.ts.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState, type ApiState } from './fixtures/api'
import { fakeChars } from './fixtures/media'
import { row, tiles } from './fixtures/mediaPage'
import { open } from './helpers'

async function media(page: Page, names?: string[]): Promise<ApiState> {
  const st = apiState({ chars: fakeChars(names) })
  await open(page, '/media', new FakeHub(), st)
  await tiles(page).first().waitFor()
  return st
}
const writes = (st: ApiState) => st.calls.filter(c => c.method !== 'GET').map(c => ({ path: c.path, body: c.body }))
const names = (page: Page) => page.locator('[data-region="characters"] [data-row^="char:"]')
const nameBox = (page: Page) => page.getByRole('textbox', { name: 'Character name' })
const imageMenu = (page: Page) => page.getByRole('menu', { name: 'Image' })
const charMenu = (page: Page) => page.getByRole('menu', { name: 'Character' })
const addItem = (page: Page) => imageMenu(page).getByRole('menuitem', { name: 'Add to Characters' })

test('Add to Characters opens the tree and asks for a name under the heading; Enter copies the picture in', async ({ page }) => {
  const st = await media(page, ['Character 42'])
  const fold = page.locator('[data-region="fold"]')
  await fold.click()
  await expect(fold).toHaveAttribute('aria-expanded', 'false')
  const id = st.media[2]!.id
  await tiles(page).nth(2).click({ button: 'right' })
  await expect(addItem(page)).toBeEnabled()
  await addItem(page).click()
  await expect(fold).toHaveAttribute('aria-expanded', 'true')
  await expect(nameBox(page)).toBeFocused()
  expect((await nameBox(page).boundingBox())!.y).toBeGreaterThan((await row(page, 'chars').boundingBox())!.y)
  await nameBox(page).fill('Character 43')
  await nameBox(page).press('Enter')
  await expect(page.getByText('Character 43 added')).toBeVisible()
  await expect(nameBox(page)).toHaveCount(0)
  expect(writes(st)).toEqual([{ path: '/api/media/characters', body: { name: 'Character 43', id } }])
  await expect(names(page)).toHaveText(['Character 42', 'Character 43'])
  await expect(page.locator(`[data-item="${id}"]`)).toBeVisible()
  expect(st.media.some(i => i.id === id)).toBe(true)
})

test('Add to Characters under a name already there (any case) says replaced; Escape asks nothing', async ({ page }) => {
  const st = await media(page, ['Character 42', 'Character 28'])
  const id = st.media[0]!.id
  await tiles(page).first().click({ button: 'right' })
  await addItem(page).click()
  await nameBox(page).fill('character 28')
  await nameBox(page).press('Enter')
  await expect(page.getByText('character 28 replaced')).toBeVisible()
  expect(writes(st)).toEqual([{ path: '/api/media/characters', body: { name: 'character 28', id } }])

  await tiles(page).nth(1).click({ button: 'right' })
  await addItem(page).click()
  await nameBox(page).fill('Character 38')
  await nameBox(page).press('Escape')
  await expect(nameBox(page)).toHaveCount(0)
  await expect(row(page, 'char:Character 38')).toHaveCount(0)
  expect(writes(st)).toHaveLength(1)
})

test('Add to Characters is off with no Characters folder, and with two pictures selected', async ({ page }) => {
  await media(page)
  await tiles(page).first().click({ button: 'right' })
  await expect(addItem(page)).toBeDisabled()
  await expect(addItem(page)).toHaveAttribute('title', 'Choose the Characters folder in Settings → Storage')
  await page.keyboard.press('Escape')
  await expect(imageMenu(page)).toHaveCount(0)

  const page2 = await page.context().newPage()
  await media(page2, ['Character 42'])
  await tiles(page2).nth(0).click()
  await tiles(page2).nth(1).click({ modifiers: ['Control'] })
  await tiles(page2).nth(1).click({ button: 'right' })
  await expect(addItem(page2)).toBeDisabled()
  await expect(addItem(page2)).toHaveAttribute('title', 'One picture at a time')
})

test('right-click a name: Notes…, Voice…, Voice sample…, Rename and Delete character', async ({ page }) => {
  await media(page, ['Character 42'])
  await row(page, 'char:Character 42').click({ button: 'right' })
  await expect(charMenu(page).getByRole('menuitem')).toHaveText(['Notes…', 'Voice…', 'Voice sample…', 'Rename', 'Delete character'])
})

test('Rename: the box holds the name; Enter renames and the shown character follows; same or empty name asks nothing', async ({ page }) => {
  const st = await media(page, ['Character 42', 'Character 28'])
  await row(page, 'char:Character 42').click()
  await expect(page.locator('[data-stage-img]')).toHaveAttribute('src', /chars\/Character 42\.png/)

  await row(page, 'char:Character 42').click({ button: 'right' })
  await charMenu(page).getByRole('menuitem', { name: 'Rename' }).click()
  await expect(nameBox(page)).toBeFocused()
  await expect(nameBox(page)).toHaveValue('Character 42')
  await nameBox(page).press('Enter')
  await expect(nameBox(page)).toHaveCount(0)

  await row(page, 'char:Character 28').click({ button: 'right' })
  await charMenu(page).getByRole('menuitem', { name: 'Rename' }).click()
  await nameBox(page).fill('   ')
  await nameBox(page).press('Enter')
  await expect(nameBox(page)).toHaveCount(0)
  await expect(names(page)).toHaveText(['Character 28', 'Character 42'])
  expect(writes(st)).toEqual([])

  await row(page, 'char:Character 42').click({ button: 'right' })
  await charMenu(page).getByRole('menuitem', { name: 'Rename' }).click()
  await nameBox(page).fill('Character 32')
  await nameBox(page).press('Enter')
  await expect(names(page)).toHaveText(['Character 28', 'Character 32'])
  expect(writes(st)).toEqual([{ path: '/api/media/characters/rename', body: { id: 'chars/Character 42.png', name: 'Character 32' } }])
  await expect(row(page, 'char:Character 32')).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('[data-stage-img]')).toHaveAttribute('src', /chars\/Character 32\.png/)
  await expect(page.locator('[data-item="chars/Character 32.png"]')).toHaveAttribute('aria-selected', 'true')
})

test('Rename: Escape cancels; renaming a character not on show leaves the view alone', async ({ page }) => {
  const st = await media(page, ['Character 42', 'Character 28'])
  await row(page, 'char:Character 28').click()
  await row(page, 'char:Character 42').click({ button: 'right' })
  await charMenu(page).getByRole('menuitem', { name: 'Rename' }).click()
  await nameBox(page).fill('Character 35')
  await nameBox(page).press('Escape')
  await expect(nameBox(page)).toHaveCount(0)
  await expect(names(page)).toHaveText(['Character 28', 'Character 42'])
  expect(writes(st)).toEqual([])

  await row(page, 'char:Character 42').click({ button: 'right' })
  await charMenu(page).getByRole('menuitem', { name: 'Rename' }).click()
  await nameBox(page).fill('Character 32')
  await nameBox(page).press('Enter')
  await expect(names(page)).toHaveText(['Character 28', 'Character 32'])
  await expect(row(page, 'char:Character 28')).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('[data-stage-img]')).toHaveAttribute('src', /chars\/Character 28\.png/)
})

test('Delete character removes it; the shown one goes back to the Characters heading', async ({ page }) => {
  const st = await media(page, ['Character 42', 'Character 28', 'Character 41'])
  await row(page, 'char:Character 28').click()
  await row(page, 'char:Character 41').click({ button: 'right' })
  await charMenu(page).getByRole('menuitem', { name: 'Delete character' }).click()
  await expect(page.getByText('Character 41 deleted')).toBeVisible()
  await expect(names(page)).toHaveText(['Character 28', 'Character 42'])
  await expect(row(page, 'char:Character 28')).toHaveAttribute('aria-selected', 'true')

  await row(page, 'char:Character 28').click({ button: 'right' })
  await charMenu(page).getByRole('menuitem', { name: 'Delete character' }).click()
  await expect(page.getByText('Character 28 deleted')).toBeVisible()
  await expect(names(page)).toHaveText(['Character 42'])
  await expect(row(page, 'chars')).toHaveAttribute('aria-selected', 'true')
  await expect(tiles(page)).toHaveCount(1)
  expect(writes(st)).toEqual([
    { path: '/api/media/characters/remove', body: { id: 'chars/Character 41.png' } },
    { path: '/api/media/characters/remove', body: { id: 'chars/Character 28.png' } },
  ])
})
