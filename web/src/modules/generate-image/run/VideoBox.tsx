import type { DragEvent } from 'react'
import { MEDIA_DRAG, type DraggedMedia } from '../../../lib/protocol'
import { useStore } from '../../../lib/store'
import { Icon } from '../../../ui/Icon'
import { cx } from '../../../ui/cx'
import { draft, edit } from '../draft'
import { note } from '../inputs'
import type { Model, VideoSlot } from '../types'
import { stemOf, videoOf } from '../video'
import s from './Run.module.css'

/** The lines the hub refuses with (`clipvideo`), said here before the press. */
export const VIDEO_UNREAD = 'The Hub cannot read this clip'
export const VIDEO_SHORT = 'A reference video is at least 2 s'
export const SHORTEST = 2

const put = (video: VideoSlot | null): void => edit(d => ({ ...d, video }))

/** A clip from Media → Clips; one under 2 s, or whose length the screen was not given, is not placed. */
export function placeVideo(id: string, seconds: unknown): boolean {
  if (typeof seconds !== 'number' || seconds <= 0) { note(VIDEO_UNREAD); return false }
  if (seconds < SHORTEST) { note(VIDEO_SHORT); return false }
  put({ id, seconds })
  return true
}

function drop(e: DragEvent): void {
  e.preventDefault()
  const media = e.dataTransfer.getData(MEDIA_DRAG)
  const clip = media ? (JSON.parse(media) as DraggedMedia[]).find(i => i.kind === 'clip') : undefined
  if (clip) placeVideo(clip.id, clip.seconds)
}

/** after the Sound box (or the picture boxes), for a model that takes a reference video. It shows the
 *  clip's name and length; the engine keeps its first seconds as the camera and set. Remove empties it. Empty, it
 *  shows the video icon. */
export function VideoBox({ model }: { model: Model | null }) {
  const d = useStore(draft, v => v)
  if (!model?.video?.reference_video) return null
  const video = videoOf(d, model)
  const dnd = { onDragOver: (e: DragEvent) => e.preventDefault(), onDrop: drop }
  if (!video) return <span className={cx(s.slot, s.sound)} title="Video: drop a clip from Media" aria-label="Video, empty" data-socket="video" {...dnd}><Icon name="video" /></span>
  const name = stemOf(video.id)
  return (
    <div className={cx(s.slot, s.filled, s.sound)} title={name} data-socket="video" data-video={video.id} {...dnd}>
      <span className={cx('ell', 't-meta')}>{name}</span>
      <span className="num t-meta">{video.seconds.toFixed(1)} s</span>
      <button type="button" className={s.remove} aria-label="Remove video" onClick={() => put(null)}><Icon name="x" small /></button>
    </div>
  )
}
