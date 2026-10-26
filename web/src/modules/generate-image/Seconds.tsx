import { useState } from 'react'
import { cx } from '../../ui/cx'
import type { VideoFacts } from './types'
import { secondsOf, stepMax, stepSeconds, toFrames } from './video'

/** A video model's clip length, kept as frames on its lattice: typed seconds snap up when the box is left or Enter is
 *  pressed; the frame count is the hover text. Continuing a clip (`step`), it is the seconds added, up to the longest
 *  step. On Settings → Generate Image and on the video sheet. A clip that follows a sound (`sound`) is the
 *  sound's length: shown, not editable. */
export function Seconds({ video, frames, step, put, className, sound }: { video: VideoFacts; frames: number; step: boolean; put: (frames: number) => void; className: string | undefined; sound?: number | undefined }) {
  const [text, setText] = useState<string | null>(null)
  if (sound !== undefined) return <input type="number" className={cx(className, 'num')} aria-label="Seconds" value={String(sound)} disabled readOnly />
  const max = step ? stepMax(video) : video.frames.max
  const commit = () => {
    if (text === null) return
    const v = Number(text)
    setText(null)
    if (text.trim() && Number.isFinite(v)) put(Math.min(max, toFrames(video, v)))
  }
  return <>
    <input type="number" className={cx(className, 'num')} aria-label="Seconds" title={`${frames} frames`} value={text ?? String(secondsOf(video, frames))}
      min={secondsOf(video, video.frames.min)} max={secondsOf(video, max)} step={0.1}
      onChange={e => setText(e.target.value)} onBlur={commit} onKeyDown={e => { if (e.key === 'Enter') commit() }} />
    {step && <span className="num t-meta" data-region="step">+{stepSeconds(video, frames)} s</span>}
  </>
}
