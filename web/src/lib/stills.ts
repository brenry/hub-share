// One still frame of a clip, made in this window's memory: one hidden player at a time loads the clip, seeks to the
// frame, a canvas turns it into a small JPEG, and the player is emptied at once (its decoder released). Tiles show the
// JPEG. A list of clips therefore never holds a player per tile, each with a decoder of its own open at once.
// Nothing is written anywhere; the stills go with the window.
//
// The newest request is drawn first (the tiles on screen now), and a request no tile wants any more is dropped, so a
// fast scroll never makes the visible tiles wait behind the ones scrolled past.
import { createStore } from './store'

const MAX = 400            // stills kept; the oldest is dropped (and its memory freed) past this
const WIDTH = 320          // a still's width in pixels at most (tiles are smaller)
const WAIT_MS = 10_000     // a clip that gives no frame in this time gets none

type Job = { key: string; url: string; at: number; done: (src: string | null) => void }

const ready = new Map<string, string>()                    // key -> object URL, oldest first
const pending = new Map<string, Promise<string | null>>()
const wanted = new Map<string, number>()                   // key -> tiles waiting for it
const queue: Job[] = []
let running = false

const keyOf = (url: string, at: number): string => `${url}@${at}`
/** Settings → Hardware → Clip previews, as the hub's settings say (`vram.clip_previews`): null until this window's
 *  first welcome, and nothing is drawn before then; false: no clip is ever loaded until it is played. */
export const previews = createStore<boolean | null>(null)
previews.subscribe(() => { if (previews.get() !== null) void pump() })

/** The still already made for this clip and time, else null. */
export function stillNow(url: string, at = 0.1): string | null {
  return ready.get(keyOf(url, at)) ?? null
}

/** The still of `url` at `at` seconds (an object URL), made once and kept; null when the clip gives no frame or no
 *  tile wants it any more. Each call is one tile's interest until `forget`. */
export function still(url: string, at = 0.1): Promise<string | null> {
  const key = keyOf(url, at)
  if (previews.get() === false) return Promise.resolve(null)       // off: no player is ever made
  const have = ready.get(key)
  if (have) {
    ready.delete(key)
    ready.set(key, have)
    return Promise.resolve(have)
  }
  wanted.set(key, (wanted.get(key) ?? 0) + 1)
  const waiting = pending.get(key)
  if (waiting) return waiting
  const made = new Promise<string | null>(done => {
    queue.push({ key, url, at, done })
  })
  pending.set(key, made)
  void pump()
  return made
}

/** A tile no longer wants this still (it left the screen or changed clip). */
export function forget(url: string, at = 0.1): void {
  const key = keyOf(url, at)
  const n = (wanted.get(key) ?? 0) - 1
  if (n > 0) wanted.set(key, n)
  else wanted.delete(key)
}

async function pump(): Promise<void> {
  if (running || previews.get() === null) return                 // the hub has not said yet: wait for it
  running = true
  try {
    for (let job = queue.pop(); job; job = queue.pop()) {                  // newest first
      if (!wanted.has(job.key) || previews.get() === false) {             // nobody waits, or switched off
        pending.delete(job.key)
        job.done(null)
        continue
      }
      let src: string | null = null
      try {
        src = await draw(job.url, job.at)
      } catch {
        src = null
      }
      pending.delete(job.key)
      wanted.delete(job.key)
      if (src) {
        ready.set(job.key, src)
        for (const [k, u] of ready) {
          if (ready.size <= MAX) break
          ready.delete(k)
          URL.revokeObjectURL(u)
        }
      }
      job.done(src)
    }
  } finally {
    running = false
  }
}

function draw(url: string, at: number): Promise<string | null> {
  return new Promise(resolve => {
    const v = document.createElement('video')
    v.muted = true
    v.playsInline = true
    v.preload = 'metadata'                              // only the header and the frame sought, never the whole clip
    let over = false
    const end = (src: string | null) => {
      if (over) return
      over = true
      clearTimeout(timer)
      v.onloadedmetadata = v.onseeked = v.onerror = null
      v.removeAttribute('src')
      v.load()                                          // empties the player: its decoder and buffers go now
      resolve(src)
    }
    const timer = setTimeout(() => end(null), WAIT_MS)
    v.onerror = () => end(null)
    v.onloadedmetadata = () => {
      const last = Number.isFinite(v.duration) ? Math.max(0, v.duration - 0.05) : at
      v.currentTime = Math.min(Math.max(at, 0), last)
    }
    v.onseeked = () => {
      if (over) return
      const w = v.videoWidth
      const h = v.videoHeight
      if (!w || !h) { end(null); return }
      const scale = Math.min(1, WIDTH / w)
      const canvas = document.createElement('canvas')
      canvas.width = Math.max(1, Math.round(w * scale))
      canvas.height = Math.max(1, Math.round(h * scale))
      const g = canvas.getContext('2d')
      if (!g) { end(null); return }
      g.drawImage(v, 0, 0, canvas.width, canvas.height)
      canvas.toBlob(b => { if (!over) end(b ? URL.createObjectURL(b) : null) }, 'image/jpeg', 0.82)
    }
    v.src = url
  })
}

/** Test hook: everything forgotten. */
export function _resetStills(on: boolean | null = true): void {
  previews.set(on)
  for (const u of ready.values()) URL.revokeObjectURL(u)
  ready.clear()
  pending.clear()
  wanted.clear()
  queue.length = 0
  running = false
}
