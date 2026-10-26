import { useEffect, useState } from 'react'
import { toast } from '../../lib/toast'
import { api, isProblem, type VideoLora } from './api'
import s from './Scripts.module.css'

/** The Storyboard's Video LoRAs under the shot list (Settings → Video LoRA): each one's toggle and strength, saved at
 *  once; only the Storyboard's render uses the ones toggled on. */
export function VideoLoras() {
  const [list, setList] = useState<VideoLora[]>([])
  useEffect(() => { void api.videoLoras().then(r => setList(r.loras ?? []), () => setList([])) }, [])
  const set = (path: string, change: { on?: boolean; strength?: number }) => {
    setList(l => l.map(x => (x.path === path ? { ...x, ...change } : x)))      // shown at once, the Hub's answer after
    void api.videoLora(path, change).then(r => {
      if (isProblem(r)) toast(r.problem)
      return api.videoLoras().then(x => setList(x.loras ?? []))
    })
  }
  return (
    <div className={s.loraList} data-region="video-loras" data-scroll="video-loras">
      {list.map(l => (
        <label key={l.path} className={s.loraRow} title={l.path} data-lora={l.name}>
          <input type="checkbox" checked={l.on} onChange={e => set(l.path, { on: e.currentTarget.checked })} />
          <span className="ell">{l.name}</span>
          <input type="number" min={0} max={2} step={0.05} defaultValue={l.strength} key={`${l.path}@${l.strength}`}
            onBlur={e => { const v = Number(e.currentTarget.value); if (v !== l.strength) set(l.path, { strength: v }) }}
            onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur() }} />
        </label>
      ))}
    </div>
  )
}
