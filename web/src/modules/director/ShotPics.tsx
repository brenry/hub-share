import { useState, type DragEvent } from 'react'
import { MEDIA_DRAG, type DraggedMedia } from '../../lib/protocol'
import { toast } from '../../lib/toast'
import { api, isProblem, pictureThumb } from './api'
import s from './Scripts.module.css'

/** `ids` with the one at `from` moved to `to`: the tag is the place, so setting a number moves the picture there. */
function move(ids: string[], from: number, to: number): string[] {
  const out = ids.filter((_, i) => i !== from)
  out.splice(to, 0, ids[from]!)
  return out
}

/** A shot's own pictures: dragged from Media, no character made of them, each labelled with the tag its clip uses
 *  (<Picture 1>, <Picture 2>, ... in this order; a picture's number box moves it to that place); a press on its
 *  thumbnail takes it off. Held, they replace the cast's pictures
 *  for this shot (`shotpics.py`). */
export function ShotPics({ name, shot, ids, onChange }: { name: string; shot: string; ids: string[]; onChange: (p: Record<string, string[]>) => void }) {
  const [over, setOver] = useState(false)
  const save = (next: string[]) => {
    void api.setShotPictures(name, shot, next).then(r => {
      if (isProblem(r)) toast(r.problem)
      else onChange(r.pictures ?? {})
    })
  }
  const drop = (e: DragEvent) => {
    setOver(false)
    const raw = e.dataTransfer.getData(MEDIA_DRAG)
    if (!raw) return
    e.preventDefault()
    let items: DraggedMedia[] = []
    try { items = JSON.parse(raw) as DraggedMedia[] } catch { return }
    const added = items.filter(i => i.kind === undefined).map(i => i.id).filter(i => !ids.includes(i))
    if (added.length) save([...ids, ...added])
  }
  return (
    <div className={`${s.shotPics} ${over ? s.on : ''}`} data-shot-pics={shot}
      onDragOver={e => { if ([...e.dataTransfer.types].includes(MEDIA_DRAG)) { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; setOver(true) } }}
      onDragLeave={() => setOver(false)} onDrop={drop}>
      <span className={s.label}>Pictures</span>
      {ids.map((id, k) => (
        <span key={id} className={s.shotPic} data-pic={k + 1}>
          <button type="button" title="Press to take it off" onClick={() => save(ids.filter(x => x !== id))}>
            <img src={pictureThumb(id)} alt="" draggable={false} />
          </button>
          <label>{'<Picture '}
            <input type="number" min={1} max={ids.length} defaultValue={k + 1} key={`${id}@${k}`} aria-label={`Picture ${k + 1} number`}
              onBlur={e => { const n = Math.round(Number(e.currentTarget.value)); if (n >= 1 && n <= ids.length && n !== k + 1) save(move(ids, k, n - 1)) }}
              onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur() }} />{'>'}
          </label>
        </span>
      ))}
    </div>
  )
}
