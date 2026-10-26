import type { Track as TrackT } from './api'
import { secs } from './timeline'
import s from './Scripts.module.css'

/** The mix's words: `Track · <s> s`, `Track · mixing`, `Track · stale · <s> s`, `Track · failed · <why>`,
 *  each followed by ` · <note>` when the mix left the room out. */
export function trackLine(t: TrackT): string {
  const len = typeof t.length_ms === 'number' ? `${secs(t.length_ms)} s` : null
  const parts = t.state === 'current' ? [len]
    : t.state === 'stale' ? ['stale', len]
      : t.state === 'failed' ? ['failed', t.why ?? null]
        : [t.state]
  return ['Track', ...parts, t.note ?? null].filter(Boolean).join(' · ')
}

/** The track on the bar: its line and, when its file is in Sounds, a player of the whole track file;
 *  nothing for `none`. The URL carries the file's time, so a re-mix is heard without a reload. */
export function Track({ track }: { track: TrackT }) {
  if (track.state === 'none') return null
  const line = trackLine(track)
  return <>
    <span className={`${s.trackLine} ell`} data-region="track" data-state={track.state} title={line}>{line}</span>
    {track.url ? <audio key={track.url} className={s.takePlay} controls preload="none" src={track.url} data-region="track-play" /> : null}
  </>
}
