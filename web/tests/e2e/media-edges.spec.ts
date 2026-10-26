// Media's edge zones: with the thumbnails folded, a click near the Stage's left or right edge steps like ◁ ▷.
// The right zone runs from the counter's left edge to the Stage's right edge; the left zone is as wide.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { tiles } from './fixtures/mediaPage'
import { open } from './helpers'

const count = (page: Page) => page.locator('[data-region="count"]')

/** Opens Media, folds the thumbnails, and returns the live zone geometry (re-measured on each call). */
async function folded(page: Page, fold = true) {
  await open(page, '/media', new FakeHub(), apiState())
  await tiles(page).first().waitFor()
  await page.locator('[data-stage-img]').waitFor()
  if (fold) {
    await page.locator('[data-region="thumbs"]').click()
    await expect(page.locator('[data-region="thumbs"]')).toHaveAttribute('aria-expanded', 'false')
  }
  return async () => {
    const st = (await page.locator('[data-region="stage"]').boundingBox())!
    const c = (await count(page).boundingBox())!
    const right = st.x + st.width
    const w = right - c.x
    return { y: st.y + st.height / 2, mid: st.x + st.width / 2, from: c.x, right, leftTo: st.x + w, left: st.x }
  }
}

test('folded: a click near the right edge steps forward, near the left steps back; the middle does nothing', async ({ page }) => {
  const zone = await folded(page)
  let z = await zone()
  await page.mouse.click(z.right - 4, z.y)
  await expect(count(page)).toHaveText('2 / 60')
  z = await zone()
  await page.mouse.click(z.from + 4, z.y)
  await expect(count(page)).toHaveText('3 / 60')
  z = await zone()
  await page.mouse.click(z.left + 4, z.y)
  await expect(count(page)).toHaveText('2 / 60')
  await page.mouse.click(z.mid, z.y)
  await page.waitForTimeout(150)
  await expect(count(page)).toHaveText('2 / 60')
  // At the start, as with ◁: nothing before the first.
  await page.mouse.click(z.left + 4, z.y)
  await expect(count(page)).toHaveText('1 / 60')
  await page.mouse.click(z.left + 4, z.y)
  await page.waitForTimeout(150)
  await expect(count(page)).toHaveText('1 / 60')
})

test('folded: a press that does not start and end in the same zone never steps', async ({ page }) => {
  const zone = await folded(page)
  const z = await zone()
  // Pan from the middle into the right zone and release there.
  await page.mouse.move(z.mid, z.y)
  await page.mouse.down()
  await page.mouse.move(z.right - 6, z.y, { steps: 6 })
  await page.mouse.up()
  // Pan from the middle into the left zone and release there.
  await page.mouse.move(z.mid, z.y)
  await page.mouse.down()
  await page.mouse.move(z.left + 6, z.y, { steps: 6 })
  await page.mouse.up()
  // Down in the left zone, up in the right zone, and the other way round.
  await page.mouse.move(z.left + 6, z.y)
  await page.mouse.down()
  await page.mouse.move(z.right - 6, z.y, { steps: 6 })
  await page.mouse.up()
  await page.mouse.move(z.right - 6, z.y)
  await page.mouse.down()
  await page.mouse.move(z.left + 6, z.y, { steps: 6 })
  await page.mouse.up()
  // Down in a zone, up in the middle.
  await page.mouse.move(z.right - 6, z.y)
  await page.mouse.down()
  await page.mouse.move(z.mid, z.y, { steps: 6 })
  await page.mouse.up()
  await page.waitForTimeout(150)
  await expect(count(page)).toHaveText('1 / 60')
})

test('folded: two quick clicks in a zone are two steps and no zoom; a double-click in the middle still zooms', async ({ page }) => {
  const zone = await folded(page)
  const stage = page.locator('[data-region="stage"]')
  let z = await zone()
  await page.mouse.dblclick(z.right - 4, z.y)
  await expect(count(page)).toHaveText('3 / 60')
  await page.waitForTimeout(150)
  await expect(stage).toContainText('Fit')
  z = await zone()
  await page.mouse.dblclick(z.left + 4, z.y)
  await expect(count(page)).toHaveText('1 / 60')
  await page.waitForTimeout(150)
  await expect(stage).toContainText('Fit')
  // At the first picture nothing changes under the pointer, so the double-click lands on the same Stage: still no zoom.
  await page.mouse.dblclick(z.left + 4, z.y)
  await page.waitForTimeout(150)
  await expect(stage).toContainText('Fit')
  await expect(count(page)).toHaveText('1 / 60')
  await page.mouse.dblclick(z.mid, z.y)
  await expect(stage).toContainText('100%')
  await expect(count(page)).toHaveText('1 / 60')
  await page.mouse.dblclick(z.mid, z.y)
  await expect(stage).toContainText('Fit')
})

test('folded: the zone boundary follows the counter', async ({ page }) => {
  const zone = await folded(page)
  let z = await zone()
  await page.mouse.click(z.from - 2, z.y)
  await page.mouse.click(z.leftTo + 2, z.y)
  await page.waitForTimeout(150)
  await expect(count(page)).toHaveText('1 / 60')
  await page.mouse.click(z.from + 2, z.y)
  await expect(count(page)).toHaveText('2 / 60')
  z = await zone()
  await page.mouse.click(z.leftTo - 2, z.y)
  await expect(count(page)).toHaveText('1 / 60')
  // A wider window moves the counter, and the zones with it.
  await page.setViewportSize({ width: 1600, height: 900 })
  await expect.poll(async () => Math.round((await zone()).from)).not.toBe(Math.round(z.from))
  z = await zone()
  await page.mouse.click(z.from - 2, z.y)
  await page.waitForTimeout(150)
  await expect(count(page)).toHaveText('1 / 60')
  await page.mouse.click(z.from + 2, z.y)
  await expect(count(page)).toHaveText('2 / 60')
})

test('thumbnails open: edge clicks on the Stage do not step', async ({ page }) => {
  const zone = await folded(page, false)
  const z = await zone()
  await page.mouse.click(z.left + 4, z.y)
  await page.mouse.click(z.leftTo - 4, z.y)
  await page.mouse.dblclick(z.left + 4, z.y)
  await expect(page.locator('[data-region="stage"]')).toContainText('100%')
  await expect(count(page)).toHaveText('1 / 60')
})
