// Tab in the prompt box completes a character's name from the Characters folder (names are the file names without
// their extension). The word before the caret is matched against the start of each name, case aside. One name: it
// goes in at once, with a space after it. Several: their tiles show over the box (`Picker.tsx`); Tab moves along
// them, Enter puts the lit one in, Escape leaves the text as it was. The name picked also puts the character's
// picture in the first free reference box (`inputs.ts` addCharacter).
import { getJSON } from '../../../lib/http'
import { createStore } from '../../../lib/store'

export type Character = { name: string; id: string; w: number; h: number; thumb: string }
/** The word being completed (`start`–`end` in the text) and the characters whose names start with it. */
export type Pick = { start: number; end: number; matches: Character[] }

/** The characters with their thumbnails, read fresh at each Tab (files in the folder may be renamed at any time). */
export const characterList = (): Promise<Character[]> =>
  getJSON<{ items: Character[] }>('/api/generate-image/characters').then(r => r.items)

/** The tiles on show: the pick and the lit tile; null when none. */
export const picker = createStore<{ pick: Pick; i: number } | null>(null)

/** The characters whose names start with the word that ends at `caret`, in name order; null when there is no word
 *  or no name starts with it. */
export function matchesAt(text: string, caret: number, list: Character[]): Pick | null {
  const word = /\S*$/.exec(text.slice(0, caret))![0]
  if (!word) return null
  const matches = list.filter(c => c.name.toLowerCase().startsWith(word.toLowerCase()))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }))
  return matches.length ? { start: caret - word.length, end: caret, matches } : null
}

/** The text with `name` in place of the word, a space after it (the one already there is used), and the caret
 *  after that space, so typing goes straight on. */
export function place(text: string, pick: Pick, name: string): { text: string; caret: number } {
  const rest = text.slice(pick.end)
  const spaced = rest.startsWith(' ') ? name : `${name} `
  return { text: text.slice(0, pick.start) + spaced + rest, caret: pick.start + name.length + 1 }
}
