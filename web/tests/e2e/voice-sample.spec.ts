// A recording as a character's voice: right-click a name → Voice sample… → an mp3 or wav; or the
// file dropped on the name. The browser sends a 16-bit WAV at 32 kHz, whole; under 2 s nothing is sent.
import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState, type ApiState } from './fixtures/api'
import { fakeChars } from './fixtures/media'
import { row, tiles } from './fixtures/mediaPage'
import { open } from './helpers'

const fixture = (name: string) => new URL(`./fixtures/${name}`, import.meta.url).pathname

async function media(page: Page, names: string[]): Promise<ApiState> {
  const st = apiState({ chars: fakeChars(names) })
  await open(page, '/media', new FakeHub(), st)
  await tiles(page).first().waitFor()
  return st
}
const sent = (st: ApiState) => st.calls.filter(c => c.path.startsWith('/api/characters/sample'))
const sampleOf = (st: ApiState, name: string) => st.chars.items.find(c => c.name === name)?.sample
async function choose(page: Page, name: string, file: string) {
  const chooser = page.waitForEvent('filechooser')
  await row(page, `char:${name}`).click({ button: 'right' })
  await page.getByRole('menu', { name: 'Character' }).getByRole('menuitem', { name: 'Voice sample…' }).click()
  await (await chooser).setFiles(fixture(file))
}

test('Voice sample… takes an mp3 file: a WAV at 32 kHz goes to the hub and the character has its sample', async ({ page }) => {
  const st = await media(page, ['Character 8', 'Character 42'])
  await choose(page, 'Character 8', 'voice-3s.mp3')
  await expect(page.getByText('Voice sample saved for Character 8', { exact: true })).toBeVisible()
  const [call] = sent(st)
  expect(call!.path).toBe('/api/characters/sample?id=chars%2FCharacter%208.png')
  expect(call!.body).toMatchObject({ tags: ['RIFF', 'WAVE', 'fmt ', 'data'], channels: 2, rate: 32000, bits: 16, type: 'audio/wav' })
  expect((call!.body as { seconds: number }).seconds).toBeGreaterThan(2.9)
  expect(sampleOf(st, 'Character 8')).toBe(true)
  await expect(row(page, 'char:Character 8').getByLabel('Has a voice sample')).toBeVisible()      // shown on its row
  expect(sampleOf(st, 'Character 42')).toBe(false)
})

test('a wav works the same; one over 15 s is sent whole', async ({ page }) => {
  const st = await media(page, ['Character 8', 'Character 42'])
  await choose(page, 'Character 42', 'voice-3s.wav')
  await expect(page.getByText('Voice sample saved for Character 42', { exact: true })).toBeVisible()
  expect(sent(st)[0]!.body).toMatchObject({ channels: 1, rate: 32000 })
  await choose(page, 'Character 8', 'voice-20s.mp3')
  await expect(page.getByText('Voice sample saved for Character 8', { exact: true })).toBeVisible()
  expect((sent(st)[1]!.body as { seconds: number }).seconds).toBeGreaterThan(19.9)
})

test('under 2 s is refused in one line and nothing is sent', async ({ page }) => {
  const st = await media(page, ['Character 8'])
  await choose(page, 'Character 8', 'voice-1s.wav')
  await expect(page.getByText('A voice sample is at least 2 seconds')).toBeVisible()
  expect(sent(st)).toHaveLength(0)
  expect(sampleOf(st, 'Character 8')).toBe(false)
})

async function dropFile(page: Page, name: string, file: string, type: string) {
  const b64 = readFileSync(fixture(file)).toString('base64')
  const dt = await page.evaluateHandle(([data, fname, ftype]) => {
    const t = new DataTransfer()
    t.items.add(new File([Uint8Array.from(atob(data!), c => c.charCodeAt(0))], fname!, { type: ftype! }))
    return t
  }, [b64, file, type])
  const target = row(page, `char:${name}`)
  await target.dispatchEvent('dragover', { dataTransfer: dt })
  await target.dispatchEvent('drop', { dataTransfer: dt })
}

test('a sound file dropped on a name becomes that character\'s sample; another file is refused', async ({ page }) => {
  const st = await media(page, ['Character 8', 'Character 42'])
  await dropFile(page, 'Character 42', 'voice-3s.wav', 'audio/wav')
  await expect(page.getByText('Voice sample saved for Character 42', { exact: true })).toBeVisible()
  expect(sent(st)).toHaveLength(1)
  expect(sampleOf(st, 'Character 42')).toBe(true)
  await dropFile(page, 'Character 8', 'voice-3s.wav', 'image/png')          // a .wav by its name is a sound
  await expect(page.getByText('Voice sample saved for Character 8', { exact: true })).toBeVisible()
  expect(sent(st)).toHaveLength(2)
  const png = readFileSync(fixture('voice-1s.wav')).toString('base64')
  const dt = await page.evaluateHandle(data => {
    const t = new DataTransfer()
    t.items.add(new File([Uint8Array.from(atob(data), c => c.charCodeAt(0))], 'face.png', { type: 'image/png' }))
    return t
  }, png)
  await row(page, 'char:Character 8').dispatchEvent('drop', { dataTransfer: dt })
  await expect(page.getByText('A voice sample is an mp3 or wav file')).toBeVisible()
  expect(sent(st)).toHaveLength(2)
})
