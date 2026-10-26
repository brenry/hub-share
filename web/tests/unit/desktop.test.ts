import { describe, expect, it } from 'vitest'
import { desktopTags, insideDesktop } from '../../src/lib/desktop'

const UA = 'Mozilla/5.0 (X11; Linux x86_64) Chrome/152.0 Electron/44.7.0 Safari/537.36 HocusPocusDesktop/1.2.1'

describe('the client in navigator.userAgent', () => {
  it('is known by its name alone', () => {
    expect(insideDesktop(UA)).toBe(true)
    expect(insideDesktop('Mozilla/5.0 Firefox/140')).toBe(false)
  })
  it('lists the tags in use, ascending, and nothing when none or malformed', () => {
    expect(desktopTags(`${UA} tags=3,2`)).toEqual([2, 3])
    expect(desktopTags(UA)).toEqual([])
    expect(desktopTags(`${UA} tags=`)).toEqual([])
    expect(desktopTags(`${UA} tags=2,,3`)).toEqual([2, 3])
    expect(desktopTags(`${UA} tags=x`)).toEqual([])
    expect(desktopTags('Mozilla/5.0 Firefox/140 tags=2')).toEqual([])
  })
})
