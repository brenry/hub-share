// Server routes used by Generate Image.
import { getJSON, q, sendBlob, sendJSON } from '../../lib/http'
import type { LoraItem, Model } from './types'

const itemPath = (id: string): string => id.split('/').map(encodeURIComponent).join('/')

/** The default model for text to image, for reference to image (image models) and for a clip (a video model);
 *  null = not set. */
export type Defaults = { text: string | null; refs: string | null; video: string | null }

export const api = {
  /** `rescan` makes the hub look at the model folders again (a page refresh does this). */
  models: (rescan = false) => getJSON<Model[]>(`/api/generate-image/models${rescan ? '?rescan=1' : ''}`),
  draft: () => getJSON<unknown>('/api/generate-image/draft'),
  saveDraft: (d: unknown) => sendJSON<unknown>('PUT', '/api/generate-image/draft', d),
  randomSeed: () => sendJSON<unknown>('POST', '/api/generate-image/seed/random', {}),
  /** The clip goes in box 1 and the draft onto a model that continues it (the hub picks). */
  continueClip: (id: string) => sendJSON<{ id: string; model: string; label: string }>('POST', '/api/generate-image/continue', { id }),
  defaults: () => getJSON<Defaults>('/api/generate-image/defaults'),
  saveDefaults: (d: Defaults) => sendJSON<Defaults>('PUT', '/api/generate-image/defaults', d),
  loras: (model: string) => getJSON<LoraItem[]>(`/api/loras?${q({ model })}`),
  patchUser: (id: string, body: { strength: number }) =>
    sendJSON<unknown>('PATCH', `/api/loras/user?${q({ id })}`, body),
  /** A picture from this computer lands in Temp; its id comes back. */
  upload: (file: Blob) => sendBlob<{ id: string }>('POST', '/api/upload', file),
  /** A sound from this computer, made a WAV in the browser, lands in Sounds (as Edit Video's); its id and length. */
  sound: (wav: Blob) => sendBlob<{ id: string; seconds: number }>('POST', '/api/sounds/upload', wav),
  /** Media items confirmed as pictures the hub can read; each is used as it is (`id` = `item`). */
  check: (items: string[]) => sendJSON<{ placed: { item: string; id: string }[] }>('POST', '/api/media/check', { items }),
}

/** LoRA cover thumbnail (96 or 336 px); the cover URL doubles as its cache key. */
export const loraThumb = (l: { id: string; cover: { url: string } | null }, size: 96 | 336): string | null =>
  l.cover ? `/api/loras/thumb?${q({ id: l.id, size, v: l.cover.url })}` : null

/** A media item's file (a clip plays from it). */
export const itemFile = (id: string): string => `/files/${itemPath(id)}`

/** Media items are served through the thumbnail route. */
export const itemThumb = (id: string, size: 96 | 336 | 1024 = 336): string => `/thumbs/${itemPath(id)}/${size}`
