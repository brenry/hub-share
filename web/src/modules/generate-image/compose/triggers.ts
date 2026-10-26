// Pure: find trigger phrases in the prompt.
const esc = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** Whole-phrase, case-insensitive ranges of any of `words`, sorted and merged. */
export function findRanges(text: string, words: string[]): [number, number][] {
  const out: [number, number][] = []
  for (const w of words) {
    const phrase = w.trim()
    if (!phrase) continue
    const re = new RegExp(`(?<![\\p{L}\\p{N}_])${esc(phrase)}(?![\\p{L}\\p{N}_])`, 'giu')
    for (const m of text.matchAll(re)) out.push([m.index, m.index + m[0].length])
  }
  out.sort((a, b) => a[0] - b[0] || b[1] - a[1])
  const merged: [number, number][] = []
  for (const r of out) {
    const last = merged[merged.length - 1]
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1])
    else merged.push([r[0], r[1]])
  }
  return merged
}

export const hasPhrase = (text: string, phrase: string): boolean => findRanges(text, [phrase]).length > 0

