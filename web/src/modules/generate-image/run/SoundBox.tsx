import type { DragEvent } from 'react'
import { errorText } from '../../../lib/http'
import { MEDIA_DRAG, type DraggedMedia } from '../../../lib/protocol'
import { useStore } from '../../../lib/store'
import { isSoundFile, toSequenceWav } from '../../../lib/wav'
import { Icon } from '../../../ui/Icon'
import { cx } from '../../../ui/cx'
import { api } from '../api'
import { draft, edit } from '../draft'
import { note } from '../inputs'
import type { Model, SoundSlot } from '../types'
import { soundOf, stemOf } from '../video'
import s from './Run.module.css'

/** The line for a sound whose length the screen was not given (the hub's own, `clipsound.UNREAD`). */
export const UNREAD = 'The Hub cannot read the length of this sound'

const put = (sound: SoundSlot | null): void => edit(d => ({ ...d, sound }))

/** A sound from Media → Sounds, or a sound file from this computer (made a WAV and kept in Sounds, as Edit Video's). */
async function drop(e: DragEvent): Promise<void> {
  e.preventDefault()
  const media = e.dataTransfer.getData(MEDIA_DRAG)
  if (media) {
    const sound = (JSON.parse(media) as DraggedMedia[]).find(i => i.kind === 'sound')
    if (!sound) return
    if (typeof sound.seconds === 'number' && sound.seconds > 0) put({ id: sound.id, seconds: sound.seconds })
    else note(UNREAD)
    return
  }
  const file = [...e.dataTransfer.files].find(isSoundFile)
  if (!file) return
  try {
    const { blob } = await toSequenceWav(file)
    const up = await api.sound(blob)
    put({ id: up.id, seconds: up.seconds })
  } catch (err) {
    note(errorText(err))
  }
}

/** after the picture boxes, for a model that keeps a sound as its clip's. It shows the sound's name and
 *  length; the clip is that long. Remove empties it, as a picture box. Empty, it shows the sound icon, so it is not
 *  taken for a fourth picture box. */
export function SoundBox({ model }: { model: Model | null }) {
  const d = useStore(draft, v => v)
  if (!model?.video?.soundtrack) return null
  const sound = soundOf(d, model)
  const dnd = { onDragOver: (e: DragEvent) => e.preventDefault(), onDrop: (e: DragEvent) => { void drop(e) } }
  if (!sound) return <span className={cx(s.slot, s.sound)} title="Sound: send a sound from Media" aria-label="Sound, empty" data-socket="sound" {...dnd}><Icon name="sound" /></span>
  const name = stemOf(sound.id)
  return (
    <div className={cx(s.slot, s.filled, s.sound)} title={name} data-socket="sound" data-sound={sound.id} {...dnd}>
      <span className={cx('ell', 't-meta')}>{name}</span>
      <span className="num t-meta">{sound.seconds.toFixed(1)} s</span>
      <button type="button" className={s.remove} aria-label="Remove sound" onClick={() => put(null)}><Icon name="x" small /></button>
    </div>
  )
}
