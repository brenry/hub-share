// The Media thumbnails keep their scrollbar's room: square tiles under a bar that came and went changed size
// every frame at some window heights (measured in the desk client's Electron 44 at zoom 1 and 1.5).
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('the Media grid', () => {
  it('keeps the scrollbar room whether or not the bar shows', () => {
    const css = readFileSync(join(import.meta.dirname, '../../src/screens/media/Media.module.css'), 'utf8')
    const grid = /\n\s*\.grid\s*\{([^}]*)\}/.exec(css)?.[1] ?? ''
    expect(grid).toMatch(/scrollbar-gutter:\s*stable/)
  })
})
