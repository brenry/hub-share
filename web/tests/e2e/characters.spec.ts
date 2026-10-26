// Characters: the folder of named pictures, listed by name in the Media tree (click shows, a drop on a name
// replaces, a drop on the heading adds under a typed name), and its folder in Settings → Storage.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState, type ApiState } from './fixtures/api'
import { fakeChars } from './fixtures/media'
import { row, tiles } from './fixtures/mediaPage'
import { open, openSettings } from './helpers'

async function media(page: Page, names?: string[]): Promise<ApiState> {
  const st = apiState({ chars: fakeChars(names) })
  await open(page, '/media', new FakeHub(), st)
  await tiles(page).first().waitFor()
  return st
}
const posts = (st: ApiState) => st.calls.filter(c => c.method === 'POST' && c.path === '/api/media/characters').map(c => c.body)
const section = (page: Page) => page.locator('[data-region="characters"]')

test('the section sits between Favorites and the Drive and lists the characters by name, with their count', async ({ page }) => {
  await media(page, ['Character 42', 'Character 28', 'Character 41'])
  await expect(section(page).locator('[data-row^="char:"]')).toHaveText(['Character 28', 'Character 41', 'Character 42'])
  await expect(row(page, 'chars')).toContainText('Characters')
  await expect(row(page, 'chars')).toContainText('3')
  await expect(page.locator('[data-region="characters-unset"]')).toHaveCount(0)
  const y = async (id: string) => (await row(page, id).boundingBox())!.y
  expect(await y('fav')).toBeLessThan(await y('chars'))
  expect(await y('char:Character 42')).toBeLessThan(await y('drive:'))
})

test('the heading shows every character picture; a name puts that picture on the Stage', async ({ page }) => {
  await media(page, ['Character 42', 'Character 28', 'Character 41'])
  await row(page, 'chars').click()
  await expect(row(page, 'chars')).toHaveAttribute('aria-selected', 'true')
  await expect(tiles(page)).toHaveCount(3)
  await expect(tiles(page).first()).toHaveAttribute('data-item', 'chars/Character 28.png')
  await row(page, 'char:Character 42').click()
  await expect(row(page, 'char:Character 42')).toHaveAttribute('aria-selected', 'true')
  await expect(row(page, 'chars')).toHaveAttribute('aria-selected', 'false')
  await expect(page.locator('[data-item="chars/Character 42.png"]')).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('[data-stage-img]')).toHaveAttribute('src', /chars\/Character 42\.png/)
  await row(page, 'char:Character 41').click()
  await expect(page.locator('[data-stage-img]')).toHaveAttribute('src', /chars\/Character 41\.png/)
  await expect(page.locator('[data-item][aria-selected="true"]')).toHaveCount(1)
})

test('a thumbnail dropped on a name replaces that character', async ({ page }) => {
  const st = await media(page, ['Character 42', 'Character 28'])
  const id = st.media[0]!.id
  await tiles(page).first().dragTo(row(page, 'char:Character 28'))
  await expect(page.getByText('Character 28 replaced')).toBeVisible()
  expect(posts(st)).toEqual([{ name: 'Character 28', id }])
  await expect(section(page).locator('[data-row^="char:"]')).toHaveText(['Character 28', 'Character 42'])
  await expect.poll(() => st.calls.filter(c => c.method === 'GET' && c.path === '/api/media/characters').length).toBeGreaterThan(1)
})

test('a thumbnail dropped on the heading asks for a name: Enter adds it, Escape cancels', async ({ page }) => {
  const st = await media(page, ['Character 42'])
  const id = st.media[1]!.id
  await tiles(page).nth(1).dragTo(row(page, 'chars'))
  const name = page.getByRole('textbox', { name: 'Character name' })
  await expect(name).toBeFocused()
  await name.fill('Character 43')
  await name.press('Enter')
  await expect(page.getByText('Character 43 added')).toBeVisible()
  await expect(name).toHaveCount(0)
  expect(posts(st)).toEqual([{ name: 'Character 43', id }])
  await expect(row(page, 'char:Character 43')).toBeVisible()
  await expect(row(page, 'chars')).toContainText('2')

  await tiles(page).first().dragTo(row(page, 'chars'))
  await name.fill('Character 38')
  await name.press('Escape')
  await expect(name).toHaveCount(0)
  await expect(row(page, 'char:Character 38')).toHaveCount(0)
  expect(posts(st)).toHaveLength(1)
})

test('with no Characters folder the section says where to choose one; a drop on the heading asks nothing', async ({ page }) => {
  const st = await media(page)
  await expect(page.locator('[data-region="characters-unset"]')).toHaveText('Choose your Characters folder in Settings → Storage → Characters.')
  await expect(section(page).locator('[data-row^="char:"]')).toHaveCount(0)
  await tiles(page).first().dragTo(row(page, 'chars'))
  await expect(page.getByRole('textbox', { name: 'Character name' })).toHaveCount(0)
  expect(posts(st)).toEqual([])
  await row(page, 'chars').click()
  await expect(page.getByText('No characters yet.')).toBeVisible()
})

test('Settings → Storage: a Characters row under Drive that saves {paths: {characters}}', async ({ page }) => {
  const { st } = await open(page, '/', new FakeHub(), apiState())
  await openSettings(page)
  const edit = page.getByRole('button', { name: 'Edit Characters' })
  await expect(edit).toBeVisible()
  expect((await page.getByRole('button', { name: 'Edit Drive' }).boundingBox())!.y).toBeLessThan((await edit.boundingBox())!.y)
  await edit.click()
  const box = page.getByRole('textbox', { name: 'Characters' })
  await expect(box).toBeFocused()
  await box.fill('/srv/Characters')
  await box.press('Enter')
  await expect(edit).toHaveText('/srv/Characters')
  expect(st.calls.filter(c => c.method === 'PATCH' && c.path === '/api/settings').map(c => c.body)).toEqual([{ paths: { characters: '/srv/Characters' } }])
})
