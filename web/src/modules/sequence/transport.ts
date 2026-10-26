// The playhead, shared by the player, the strip and the bar: the sequence time, whether it plays, and a counter that
// moves on every seek (the player follows the counter; playback moves only the time).
import { createStore } from '../../lib/store'

export const transport = createStore({ t: 0, playing: false, seek: 0 })

export const seekTo = (t: number): void => transport.set(x => ({ ...x, t: Math.max(0, t), seek: x.seek + 1 }))

export const setPlaying = (playing: boolean): void => transport.set(x => (x.playing === playing ? x : { ...x, playing }))

/** Playback's own move: no seek. */
export const tick = (t: number): void => transport.set(x => (x.t === t ? x : { ...x, t }))
