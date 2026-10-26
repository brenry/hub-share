import { describe, expect, it } from 'vitest'
import { profileOf, tierLocked, toggleTier } from '../../src/shell/settings/coreSettings'

const tiers = { names: ['480p', '540p', '720p', '1080p'], offered: ['480p', '540p'] }

describe('Settings → Image engine', () => {
  it('reads a memory profile from its menu value', () => {
    expect(['engine', 'same', '5', '3.5'].map(profileOf)).toEqual(['engine', 'same', 5, 3.5])
  })

  it('switches a video size in the catalog order', () => {
    expect(toggleTier(tiers, '1080p', true)).toEqual(['480p', '540p', '1080p'])
    expect(toggleTier({ ...tiers, offered: ['720p'] }, '480p', true)).toEqual(['480p', '720p'])
    expect(toggleTier(tiers, '480p', false)).toEqual(['540p'])
    expect(toggleTier({ ...tiers, offered: ['540p', '8k'] }, '720p', true)).toEqual(['540p', '720p'])
  })

  it('keeps one size and no more than the menu has places', () => {
    expect(tierLocked(tiers, '480p', 3)).toBe(false)
    expect(tierLocked(tiers, '720p', 3)).toBe(false)
    expect(tierLocked({ ...tiers, offered: ['540p'] }, '540p', 3)).toBe(true)
    expect(tierLocked({ ...tiers, offered: ['480p', '540p', '720p'] }, '1080p', 3)).toBe(true)
    expect(tierLocked({ ...tiers, offered: ['480p', '540p', '720p'] }, '720p', 3)).toBe(false)
    expect(tierLocked(tiers, '720p', 2)).toBe(true)
  })
})
