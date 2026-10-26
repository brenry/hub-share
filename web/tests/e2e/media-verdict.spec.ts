// The judges' verdict on a clip: the Stage shows the finished job's `notes.verdict` for the
// clip it made, for as long as the session keeps that job (the Media window has the jobs lane); nothing for a clip no
// job in memory made.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { job } from './fixtures/data'
import { fakeChars } from './fixtures/media'
import { row, tiles } from './fixtures/mediaPage'
import { open } from './helpers'

const stage = (page: Page) => page.locator('[data-region="stage"]')

test('the Stage shows the judges\' verdict on a clip the session\'s jobs made, and nothing on one they did not', async ({ page }) => {
  const st = apiState({ chars: fakeChars(['Character 17']) })
  const said = "Character 7's face held (0.62); Character 7's mouth moves with the words (0.81)"
  const hub = new FakeHub({ jobs: [job('j_face', { state: 'done', created: 1791561700, outputs: ['clips/2026-10-13/180000.mp4'], notes: { verdict: said } })] })
  await open(page, '/clips', hub, st)
  await tiles(page).first().waitFor()
  const verdict = stage(page).locator('[data-region="verdict"]')
  await expect(verdict).toHaveText(said)
  await tiles(page).nth(1).click()
  await expect(verdict).toHaveCount(0)
  await tiles(page).first().click()
  await expect(verdict).toHaveCount(1)
  // a clip judged while the window is open: the jobs lane brings it
  hub.setJob(job('j_two', { state: 'done', created: 1791561800, outputs: ['clips/2026-10-13/179900.mp4'], notes: { verdict: 'Character 11\'s face held (0.55)' } }))
  await tiles(page).nth(1).click()
  await expect(verdict).toHaveText("Character 11's face held (0.55)")
  hub.dropJob('j_two')                       // the job forgotten (the session ended): the verdict goes with it
  await expect(verdict).toHaveCount(0)
})

test('a spoken line on the Stage shows the words judge\'s line under its player', async ({ page }) => {
  const SOUND = 'sounds/2026-10-13/120000.wav'
  const st = apiState({ chars: fakeChars(['Character 17']) })
  st.sounds.push({ id: SOUND, kind: 'sound', url: `/files/${SOUND}`, thumb: null, w: null, h: null, createdAt: 1791562000, group: '', fav: false, seconds: 4.2 })
  const hub = new FakeHub({ jobs: [job('j_words', { state: 'done', created: 1791561700, outputs: [SOUND], notes: { verdict: 'Heard 95% of the words' } })] })
  await open(page, '/media', hub, st)
  await tiles(page).first().waitFor()
  await row(page, 'sounds').click()
  await expect(tiles(page)).toHaveCount(1)
  await expect(page.locator('[data-region="sound"] [data-region="verdict"]')).toHaveText('Heard 95% of the words')
})
