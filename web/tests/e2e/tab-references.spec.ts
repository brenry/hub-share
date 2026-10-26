// A character picked by Tab in the prompt box (one match at once, or Enter / a click on a tile) also puts its picture
// in the first free reference box (`inputs.ts` addCharacter). Already in a box: that box flashes, nothing added. No
// box free: "1 not added: references are full". A model that takes no reference pictures: a note, boxes unchanged.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState, type ApiState } from './fixtures/api'
import { fakeChars } from './fixtures/media'
import { open } from './helpers'

const DRAFT = {
  model: 'flux2_klein_9b', prompt: '', lorasByModel: {}, aspect: '16:9', size: 1.5, images: 2,
  advancedByModel: {}, references: [] as { id: string; w: number; h: number }[], selected: null,
}
const MANY = ['Syx-2', 'Byx-1', 'Syx-1', 'Stxy-1', 'Syx-3']
const box = (page: Page) => page.locator('#prompt')
const tiles = (page: Page) => page.getByRole('listbox', { name: 'Characters' })
const options = (page: Page) => tiles(page).getByRole('option')
const lit = (page: Page) => tiles(page).locator('[role="option"][aria-selected="true"]')
const slot = (page: Page, n: number) => page.locator(`[data-socket="reference_${n}"]`)
const pic = (page: Page, n: number) => slot(page, n).locator('img')
const thumb = (name: string) => `/thumbs/chars/${name}.png/336`
const note = (page: Page) => page.locator('[data-region="references"] [role="status"]')
const checks = (st: ApiState) => st.calls.filter(c => c.method === 'POST' && c.path === '/api/media/check')
const refs = (page: Page) => page.locator('[data-region="references"] img')

async function generate(page: Page, names: string[], over: Partial<typeof DRAFT> = {}, cap = 3): Promise<ApiState> {
  const { st } = await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, ...over }, chars: fakeChars(names) }))
  await expect(page.locator('[data-region="references"]')).toHaveAttribute('data-cap', String(cap))
  await box(page).waitFor()
  return st
}

/** Type `text` and press Tab with several matches: the tiles show. */
async function showTiles(page: Page, text: string) {
  await box(page).fill(text)
  await box(page).press('Tab')
  await expect(tiles(page)).toBeVisible()
}

test.describe('one match', () => {
  test('Tab puts the name in and the picture in reference 1; the next character goes in reference 2', async ({ page }) => {
    const st = await generate(page, ['Syx-4', 'Byx-1'])
    await box(page).fill('an image of s')
    await box(page).press('Tab')
    await expect(box(page)).toHaveValue('an image of Syx-4 ')
    await expect(pic(page, 1)).toHaveAttribute('src', thumb('Syx-4'))
    await expect(pic(page, 2)).toHaveCount(0)
    expect(checks(st).map(c => c.body)).toEqual([{ items: ['chars/Syx-4.png'] }])
    await page.keyboard.type('and b')
    await box(page).press('Tab')
    await expect(box(page)).toHaveValue('an image of Syx-4 and Byx-1 ')
    await expect(pic(page, 2)).toHaveAttribute('src', thumb('Byx-1'))
    await expect(pic(page, 1)).toHaveAttribute('src', thumb('Syx-4'))
    await expect(pic(page, 3)).toHaveCount(0)
    await expect(box(page)).toBeFocused()
    // the picture loads, with the character's size kept in the draft
    await expect.poll(() => pic(page, 2).evaluate(i => (i as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
    await expect.poll(() => (st.draft as typeof DRAFT).references, { timeout: 4000 }).toEqual([
      { id: 'chars/Syx-4.png', w: 1024, h: 1024 }, { id: 'chars/Byx-1.png', w: 1024, h: 1024 },
    ])
  })
})

test.describe('several matches', () => {
  test('Tab to the 2nd tile and Enter: that character fills the first free box', async ({ page }) => {
    await generate(page, MANY, { references: [{ id: 'out/2026-10-09/r1.png', w: 1200, h: 800 }] })
    await showTiles(page, 'draw s')
    await box(page).press('Tab')
    await expect(lit(page)).toHaveText('Syx-1')
    await box(page).press('Enter')
    await expect(box(page)).toHaveValue('draw Syx-1 ')
    await expect(pic(page, 2)).toHaveAttribute('src', thumb('Syx-1'))
    await expect(pic(page, 1)).toHaveAttribute('src', '/thumbs/out/2026-10-09/r1.png/336')
    await expect(pic(page, 3)).toHaveCount(0)
  })

  test('a click on a tile fills the first free box', async ({ page }) => {
    await generate(page, MANY)
    await showTiles(page, 'draw s')
    await options(page).filter({ hasText: 'Syx-3' }).click()
    await expect(box(page)).toHaveValue('draw Syx-3 ')
    await expect(pic(page, 1)).toHaveAttribute('src', thumb('Syx-3'))
    await expect(refs(page)).toHaveCount(1)
  })

  test('Escape on the tiles fills no box', async ({ page }) => {
    const st = await generate(page, MANY)
    await showTiles(page, 'draw s')
    await box(page).press('Tab')
    await box(page).press('Escape')
    await expect(tiles(page)).toHaveCount(0)
    await page.waitForTimeout(300)
    await expect(refs(page)).toHaveCount(0)
    await expect(box(page)).toHaveValue('draw s')
    expect(checks(st)).toHaveLength(0)
  })
})

test.describe('nothing added', () => {
  test('the same character again: its box flashes, no second box filled', async ({ page }) => {
    const st = await generate(page, ['Syx-4', 'Byx-1'])
    await box(page).fill('s')
    await box(page).press('Tab')
    await expect(pic(page, 1)).toHaveAttribute('src', thumb('Syx-4'))
    // let the first flash end, so the next one is this pick's
    await expect(slot(page, 1)).not.toHaveClass(/flash/)
    await page.keyboard.type('and s')
    await box(page).press('Tab')
    await expect(box(page)).toHaveValue('Syx-4 and Syx-4 ')
    await expect(slot(page, 1)).toHaveClass(/flash/)
    await expect(slot(page, 1)).not.toHaveClass(/flash/)
    await expect(refs(page)).toHaveCount(1)
    await expect(pic(page, 2)).toHaveCount(0)
    expect(checks(st)).toHaveLength(1)
  })

  test('the boxes the model allows are full: nothing replaced, a note', async ({ page }) => {
    const full = [{ id: 'out/2026-10-09/r1.png', w: 1, h: 1 }, { id: 'out/2026-10-09/r2.png', w: 1, h: 1 }]
    const st = await generate(page, ['Syx-4', 'Byx-1'], { model: 'qwen_image_edit_plus', references: full }, 2)
    await expect(slot(page, 3)).toHaveAttribute('data-shut', 'true')
    await box(page).fill('s')
    await box(page).press('Tab')
    await expect(box(page)).toHaveValue('Syx-4 ')
    await expect(note(page)).toHaveText('1 not added: references are full')
    await expect(pic(page, 1)).toHaveAttribute('src', '/thumbs/out/2026-10-09/r1.png/336')
    await expect(pic(page, 2)).toHaveAttribute('src', '/thumbs/out/2026-10-09/r2.png/336')
    await expect(refs(page)).toHaveCount(2)
    expect(checks(st)).toHaveLength(0)
  })

  test('all three boxes full on a 3-box model: nothing replaced, a note', async ({ page }) => {
    const full = [1, 2, 3].map(i => ({ id: `out/2026-10-09/r${i}.png`, w: 1, h: 1 }))
    await generate(page, ['Syx-4'], { references: full })
    await box(page).fill('s')
    await box(page).press('Tab')
    await expect(note(page)).toHaveText('1 not added: references are full')
    for (const i of [1, 2, 3]) await expect(pic(page, i)).toHaveAttribute('src', `/thumbs/out/2026-10-09/r${i}.png/336`)
  })

  test('a model that takes no reference pictures: a note, the boxes unchanged', async ({ page }) => {
    const st = await generate(page, ['Syx-4', 'Byx-1'], { model: 'z_image_turbo' }, 0)
    await box(page).fill('b')
    await box(page).press('Tab')
    await expect(box(page)).toHaveValue('Byx-1 ')
    await expect(note(page)).toHaveText('This model takes no reference pictures')
    await expect(refs(page)).toHaveCount(0)
    for (const i of [1, 2, 3]) await expect(slot(page, i)).toHaveAttribute('data-shut', 'true')
    expect(checks(st)).toHaveLength(0)
  })
})
