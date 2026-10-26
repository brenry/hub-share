// The scene's audience: a sound of Sounds kept as its applause, laughter or gasps, filed by the
// Hub as `sounds/audience/<kind>.wav`, replacing the one there; the next scene uses it. Media hears `media.changed`.
import { sendJSON } from '../../lib/http'

export const AUDIENCE = [['applause', 'Applause'], ['laughter', 'Laughter'], ['gasps', 'Gasps']] as const

/** The sound `id` kept as the audience's `kind`. -> its new id. */
export async function keepAudience(id: string, kind: string): Promise<string> {
  return (await sendJSON<{ id: string }>('POST', '/api/sounds/audience', { id, kind })).id
}

/** Media's `Keep as audience…` entry for the chosen sounds: one sound at a time, the three kinds as its sub-menu;
 *  `said` gets the toast's line (or the refusal's). */
export function audienceItem(chosen: string[], said: (text: string) => void, failed: (e: unknown) => void) {
  return {
    label: 'Keep as audience…', off: chosen.length > 1 ? 'One sound at a time' : null, run: () => {},
    sub: AUDIENCE.map(([kind, label]) => ({ label, run: () => {
      const id = chosen[0]
      if (id) keepAudience(id, kind).then(() => said(`${label} kept for the audience`)).catch(failed)
    } })),
  }
}
