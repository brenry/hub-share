import { describe, expect, it } from 'vitest'
import { EMPTY_SEL, afterDelete, clear, click, follow, move, selectAll, targets } from '../../src/screens/media/selection'

const ORDER = ['a', 'b', 'c', 'd', 'e', 'f', 'g']

describe('Media selection', () => {
  it('click selects one; Ctrl toggles; Shift selects the range from the anchor', () => {
    let s = click(EMPTY_SEL, ORDER, 'b', { ctrl: false, shift: false })
    expect(s).toEqual({ ids: ['b'], anchor: 'b', current: 'b' })
    s = click(s, ORDER, 'e', { ctrl: true, shift: false })
    expect(s.ids).toEqual(['b', 'e'])
    s = click(s, ORDER, 'b', { ctrl: true, shift: false })
    expect(s.ids).toEqual(['e'])
    s = click(s, ORDER, 'd', { ctrl: false, shift: true })
    expect(s.ids).toEqual(['b', 'c', 'd'])
    expect(s.anchor).toBe('b')
    expect(click(s, ORDER, 'a', { ctrl: false, shift: true }).ids).toEqual(['a', 'b'])
  })
  it('Ctrl+A selects all; Esc clears but keeps the Stage image', () => {
    const s = selectAll(ORDER, click(EMPTY_SEL, ORDER, 'c', { ctrl: false, shift: false }))
    expect(s.ids).toEqual(ORDER)
    expect(clear(s)).toEqual({ ids: [], anchor: null, current: 'c' })
  })
  it('arrows move by one or by the real column count; Home and End', () => {
    const s = click(EMPTY_SEL, ORDER, 'b', { ctrl: false, shift: false })
    expect(move(s, ORDER, 'ArrowRight', 3).current).toBe('c')
    expect(move(s, ORDER, 'ArrowLeft', 3).current).toBe('a')
    expect(move(s, ORDER, 'ArrowDown', 3).current).toBe('e')
    expect(move(move(s, ORDER, 'ArrowDown', 3), ORDER, 'ArrowDown', 3).current).toBe('g')
    expect(move(s, ORDER, 'ArrowUp', 3).current).toBe('a')
    expect(move(s, ORDER, 'End', 3)).toEqual({ ids: ['g'], anchor: 'g', current: 'g' })
    expect(move(s, ORDER, 'Home', 3).current).toBe('a')
    expect(move(EMPTY_SEL, [], 'Home', 3)).toBe(EMPTY_SEL)
  })
  it('targets are the selection in grid order, else the current image', () => {
    expect(targets({ ids: ['e', 'a'], anchor: null, current: 'c' }, ORDER)).toEqual(['a', 'e'])
    expect(targets({ ids: [], anchor: null, current: 'c' }, ORDER)).toEqual(['c'])
    expect(targets(EMPTY_SEL, ORDER)).toEqual([])
  })
  it('after delete the Stage moves to the next older image, else the previous', () => {
    expect(afterDelete(ORDER, ['c', 'd'], 'c')).toBe('e')
    expect(afterDelete(ORDER, ['f', 'g'], 'g')).toBe('e')
    expect(afterDelete(['a'], ['a'], 'a')).toBeNull()
  })
  it('Follow never breaks a multi-selection', () => {
    expect(follow({ ids: ['a'], anchor: 'a', current: 'a' }, 'n')).toEqual({ sel: { ids: ['n'], anchor: 'n', current: 'n' }, stole: true })
    const multi = { ids: ['a', 'b'], anchor: 'a', current: 'b' }
    expect(follow(multi, 'n')).toEqual({ sel: multi, stole: false })
  })
})
