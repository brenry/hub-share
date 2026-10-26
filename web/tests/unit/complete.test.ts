import { describe, expect, it } from 'vitest'
import { matchesAt, place, type Character } from '../../src/modules/generate-image/compose/complete'

const chars = (...names: string[]): Character[] => names.map(name => ({ name, id: `chars/${name}.png`, w: 8, h: 8, thumb: `/thumbs/chars/${name}.png/336` }))
const LIST = chars('Sup-2', 'Sup-4', 'Bat-1', 'Star-1', 'Sup-1', 'Sup-3')

describe('matchesAt', () => {
  it('finds the names starting with the word before the caret, in name order, case aside', () => {
    expect(matchesAt('a picture of s', 14, LIST)!.matches.map(c => c.name))
      .toEqual(['Star-1', 'Sup-1', 'Sup-2', 'Sup-3', 'Sup-4'])
    expect(matchesAt('SU', 2, LIST)!.matches.map(c => c.name)).toEqual(['Sup-1', 'Sup-2', 'Sup-3', 'Sup-4'])
  })
  it('gives the word span', () => {
    expect(matchesAt('x bat y', 5, LIST)).toMatchObject({ start: 2, end: 5 })
  })
  it('is null with no word or no match', () => {
    expect(matchesAt('a ', 2, LIST)).toBeNull()
    expect(matchesAt('zz', 2, LIST)).toBeNull()
    expect(matchesAt('s', 1, [])).toBeNull()
  })
  it('keeps the thumbnails', () => {
    expect(matchesAt('b', 1, LIST)!.matches).toEqual([{ name: 'Bat-1', id: 'chars/Bat-1.png', w: 8, h: 8, thumb: '/thumbs/chars/Bat-1.png/336' }])
  })
})

describe('place', () => {
  it('puts the name in with a space after it and the caret after the space', () => {
    const pick = matchesAt('of s', 4, LIST)!
    expect(place('of s', pick, 'Sup-4')).toEqual({ text: 'of Sup-4 ', caret: 9 })
  })
  it('uses a space already there instead of adding one', () => {
    const pick = matchesAt('of s at home', 4, LIST)!
    expect(place('of s at home', pick, 'Sup-4')).toEqual({ text: 'of Sup-4 at home', caret: 9 })
  })
  it('adds the space before following text with none', () => {
    const pick = matchesAt('s,x', 1, LIST)!
    expect(place('s,x', pick, 'Star-1')).toEqual({ text: 'Star-1 ,x', caret: 7 })
  })
})
