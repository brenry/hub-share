// Pure: read the one-time pairing fragment (#c=<code>&next=<path>), as `hub pair` prints it.
export function readFragment(hash: string, origin: string): { code: string | null; next: string } {
  const p = new URLSearchParams(hash.replace(/^#/, ''))
  return { code: p.get('c') || null, next: localPath(p.get('next') ?? '/', origin) }
}

/** `next` may only lead to a path on this hub; anything else goes to `/`. */
function localPath(raw: string, origin: string): string {
  try {
    const u = new URL(raw, origin)
    return u.origin === origin ? u.pathname + u.search : '/'
  } catch {
    return '/'
  }
}

export type PairState = 'working' | 'paired' | 'bad' | 'rate' | 'failed'

export const PAIR_TEXT: Record<PairState, string> = {
  working: 'Pairing…',
  paired: 'Paired',
  bad: 'This link is not valid or was already used',
  rate: 'Too many attempts',
  failed: 'Pairing failed',
}

export const stateFor = (status: number): PairState => (status === 429 ? 'rate' : status >= 400 && status < 500 ? 'bad' : 'failed')
