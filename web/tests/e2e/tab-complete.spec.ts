// Tab in the prompt box completes a character's name (the Characters folder's file names). One match goes in at once
// with a space after it; several show their tiles over the box (a listbox), Tab/arrows move the cyan ring, Enter or a
// click puts the lit one in, Escape/typing/blur close them. The box keeps the focus throughout.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState, type ApiState } from './fixtures/api'
import { fakeChars } from './fixtures/media'
import { open } from './helpers'

const DRAFT = {
  model: 'flux2_klein_9b', prompt: '', lorasByModel: {}, aspect: '16:9', size: 1.5, images: 2,
  advancedByModel: {}, references: [], selected: null,
}
const MANY = ['Syx-2', 'Byx-1', 'Syx-1', 'Stxy-1', 'Syx-3']
const box = (page: Page) => page.locator('#prompt')
const tiles = (page: Page) => page.getByRole('listbox', { name: 'Characters' })
const options = (page: Page) => tiles(page).getByRole('option')
const caret = (page: Page) => box(page).evaluate(el => [(el as HTMLTextAreaElement).selectionStart, (el as HTMLTextAreaElement).selectionEnd])
const lit = (page: Page) => tiles(page).locator('[role="option"][aria-selected="true"]')
const chatPosts = (st: ApiState) => st.calls.filter(c => c.method === 'POST' && c.path === '/api/assistant/chat')

async function generate(page: Page, names?: string[]): Promise<ApiState> {
  const { st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT, chars: fakeChars(names) }))
  await page.locator('[data-lora]').first().waitFor()
  return st
}

/** Type `text` and press Tab with several matches: the tiles show. */
async function showTiles(page: Page, text: string) {
  await box(page).fill(text)
  await box(page).press('Tab')
  await expect(tiles(page)).toBeVisible()
}

test.describe('one match', () => {
  test('Tab puts the name in with a space after it; the caret after the space, the focus in the box', async ({ page }) => {
    const st = await generate(page, ['Syx-4', 'Byx-1'])
    await box(page).fill('can you make an image of s')
    await box(page).press('Tab')
    await expect(box(page)).toHaveValue('can you make an image of Syx-4 ')
    await expect(box(page)).toBeFocused()
    await expect.poll(() => caret(page)).toEqual([31, 31])
    await expect(tiles(page)).toHaveCount(0)
    expect(st.calls.filter(c => c.method === 'GET' && c.path === '/api/generate-image/characters')).toHaveLength(1)
    await page.keyboard.type('flying')
    await expect(box(page)).toHaveValue('can you make an image of Syx-4 flying')
  })

  test('a space already after the word is used, not doubled; the rest of the text stays', async ({ page }) => {
    await generate(page, ['Syx-4', 'Byx-1'])
    await box(page).fill('a picture of s and a dog')
    await box(page).evaluate(el => (el as HTMLTextAreaElement).setSelectionRange(14, 14))
    await box(page).press('Tab')
    await expect(box(page)).toHaveValue('a picture of Syx-4 and a dog')
    await expect.poll(() => caret(page)).toEqual([19, 19])
    await expect(box(page)).toBeFocused()
  })

  test('mid-text with no space after: the space goes in and the rest follows it', async ({ page }) => {
    await generate(page, ['Syx-4', 'Byx-1'])
    await box(page).fill('byx,s')
    await box(page).evaluate(el => (el as HTMLTextAreaElement).setSelectionRange(3, 3))
    await box(page).press('Tab')
    await expect(box(page)).toHaveValue('Byx-1 ,s')
    await expect.poll(() => caret(page)).toEqual([6, 6])
  })
})

test.describe('several matches', () => {
  test('Tab shows the tiles above the box in name order, the first lit; the text unchanged', async ({ page }) => {
    await generate(page, MANY)
    await showTiles(page, 'an image of s')
    const list = tiles(page)
    await expect(list).toHaveAttribute('data-region', 'character-picker')
    await expect(options(page)).toHaveCount(4)
    await expect(options(page)).toHaveText(['Stxy-1', 'Syx-1', 'Syx-2', 'Syx-3'])
    for (const o of await options(page).all()) await expect(o.locator('img')).toHaveCount(1)
    await expect(options(page).first()).toHaveAttribute('aria-selected', 'true')
    await expect(lit(page)).toHaveCount(1)
    await expect(box(page)).toHaveValue('an image of s')
    await expect(box(page)).toBeFocused()
    const [l, b] = [await list.boundingBox(), await box(page).boundingBox()]
    expect(l!.y + l!.height).toBeLessThanOrEqual(b!.y)
    // the thumbnails load
    await expect.poll(() => options(page).first().locator('img').evaluate(i => (i as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
  })

  test('a longer word narrows the tiles', async ({ page }) => {
    await generate(page, MANY)
    await showTiles(page, 'sy')
    await expect(options(page)).toHaveText(['Syx-1', 'Syx-2', 'Syx-3'])
  })

  test('Tab and ArrowRight move forward (wrapping), Shift+Tab and ArrowLeft back', async ({ page }) => {
    await generate(page, MANY)
    await showTiles(page, 's')
    await box(page).press('Tab')
    await expect(lit(page)).toHaveText('Syx-1')
    await box(page).press('ArrowRight')
    await expect(lit(page)).toHaveText('Syx-2')
    await box(page).press('Tab')
    await expect(lit(page)).toHaveText('Syx-3')
    await box(page).press('Tab')
    await expect(lit(page)).toHaveText('Stxy-1')
    await box(page).press('Shift+Tab')
    await expect(lit(page)).toHaveText('Syx-3')
    await box(page).press('ArrowLeft')
    await expect(lit(page)).toHaveText('Syx-2')
    await expect(box(page)).toBeFocused()
    await expect(box(page)).toHaveValue('s')
  })

  test('Enter puts the lit name in and closes the tiles, and does not send to the assistant', async ({ page }) => {
    const st = await generate(page, MANY)
    await showTiles(page, 'draw s')
    await box(page).press('Tab')
    await box(page).press('Enter')
    await expect(box(page)).toHaveValue('draw Syx-1 ')
    await expect(tiles(page)).toHaveCount(0)
    await expect(box(page)).toBeFocused()
    await expect.poll(() => caret(page)).toEqual([11, 11])
    await page.waitForTimeout(150)
    expect(chatPosts(st)).toHaveLength(0)
    // with the tiles closed Enter sends as usual
    await box(page).press('Enter')
    await expect.poll(() => chatPosts(st).length).toBe(1)
  })

  test('a click on a tile puts it in; the focus stays in the box', async ({ page }) => {
    const st = await generate(page, MANY)
    await box(page).fill('draw s and a dog')
    await box(page).evaluate(el => (el as HTMLTextAreaElement).setSelectionRange(6, 6))
    await box(page).press('Tab')
    await expect(tiles(page)).toBeVisible()
    await options(page).filter({ hasText: 'Syx-3' }).click()
    await expect(box(page)).toHaveValue('draw Syx-3 and a dog')
    await expect(tiles(page)).toHaveCount(0)
    await expect(box(page)).toBeFocused()
    await expect.poll(() => caret(page)).toEqual([11, 11])
    expect(chatPosts(st)).toHaveLength(0)
  })

  test('the lit tile has the cyan ring, the others not', async ({ page }) => {
    await generate(page, MANY)
    await showTiles(page, 's')
    await box(page).press('Tab')
    const ring = () => tiles(page).evaluate(list => {
      const probe = document.createElement('i')
      probe.style.borderColor = 'var(--accent)'
      list.appendChild(probe)
      const accent = getComputedStyle(probe).borderTopColor
      probe.remove()
      return [...list.querySelectorAll('[role="option"]')].map(o => getComputedStyle(o).borderTopColor === accent)
    })
    await expect.poll(ring).toEqual([false, true, false, false])
    await expect(lit(page)).toHaveClass(/tileOn/)
    for (const i of [0, 2, 3]) await expect(options(page).nth(i)).not.toHaveClass(/tileOn/)
  })
})

test.describe('closing the tiles', () => {
  test('Escape closes them; the text unchanged', async ({ page }) => {
    await generate(page, MANY)
    await showTiles(page, 'an image of s')
    await box(page).press('Tab')
    await box(page).press('Escape')
    await expect(tiles(page)).toHaveCount(0)
    await expect(box(page)).toHaveValue('an image of s')
    await expect(box(page)).toBeFocused()
  })

  test('typing a letter closes them and the letter is typed', async ({ page }) => {
    await generate(page, MANY)
    await showTiles(page, 'an image of s')
    await page.keyboard.type('t')
    await expect(tiles(page)).toHaveCount(0)
    await expect(box(page)).toHaveValue('an image of st')
    await box(page).press('Tab')
    await expect(box(page)).toHaveValue('an image of Stxy-1 ')
  })

  test('leaving the box closes them', async ({ page }) => {
    await generate(page, MANY)
    await showTiles(page, 's')
    await box(page).evaluate(el => (el as HTMLTextAreaElement).blur())
    await expect(tiles(page)).toHaveCount(0)
    await expect(box(page)).toHaveValue('s')
  })
})

test.describe('nothing to complete', () => {
  test('no name matches: Tab changes nothing and does not leave the box', async ({ page }) => {
    await generate(page, ['Syx-4', 'Byx-1'])
    await box(page).fill('an image of x')
    await box(page).press('Tab')
    await page.waitForTimeout(150)
    await expect(box(page)).toHaveValue('an image of x')
    await expect(box(page)).toBeFocused()
    await expect(tiles(page)).toHaveCount(0)
    await box(page).fill('an image of ')
    await box(page).press('Tab')
    await page.waitForTimeout(150)
    await expect(box(page)).toHaveValue('an image of ')
    await expect(box(page)).toBeFocused()
  })

  test('with no Characters folder Tab keeps the focus and changes nothing', async ({ page }) => {
    await generate(page)
    await box(page).fill('an image of s')
    await box(page).press('Tab')
    await page.waitForTimeout(150)
    await expect(box(page)).toHaveValue('an image of s')
    await expect(box(page)).toBeFocused()
    await expect(tiles(page)).toHaveCount(0)
  })

  test('Shift+Tab with no tiles moves the focus as usual', async ({ page }) => {
    await generate(page, ['Syx-4'])
    await box(page).fill('an image of s')
    await box(page).press('Shift+Tab')
    await expect(box(page)).not.toBeFocused()
    await expect(box(page)).toHaveValue('an image of s')
  })
})
