import { describe, expect, it } from 'vitest'
import { findRanges, hasPhrase } from '../../src/modules/generate-image/compose/triggers'

describe('trigger ranges', () => {
  it('matches whole phrases, case-insensitively', () => {
    expect(findRanges('An Inkstyle cat, inkstyles', ['inkstyle'])).toEqual([[3, 11]])
    expect(findRanges('bold black outlines here', ['black outlines', 'bold'])).toEqual([[0, 4], [5, 19]])
  })
  it('merges overlaps and ignores empty words', () => {
    expect(findRanges('bold black outlines', ['bold black', 'black outlines', ' '])).toEqual([[0, 19]])
  })
  it('escapes regex characters', () => {
    expect(hasPhrase('a (b) c', '(b)')).toBe(true)
    expect(hasPhrase('a b c', '.')).toBe(false)
  })
})
