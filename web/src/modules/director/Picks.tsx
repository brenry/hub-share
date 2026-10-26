import { useCallback, useEffect, useState, type MouseEvent } from 'react'
import { toast } from '../../lib/toast'
import { api, isProblem, type Script } from './api'
import { reload } from './load'
import { idOf, shotOfBox } from './moves'
import { ShotPics } from './ShotPics'
import { boxes, secs, type Box } from './timeline'
import s from './Scripts.module.css'

/** Boxes picked by hand, as any app does: a click picks one; Shift-click picks every box of that row between the last
 *  click and this one; Alt-, Ctrl- or Cmd-click adds or drops one. Delete or Backspace (outside a text field) removes
 *  every picked box, one by one, then the script is read again. */
export function usePicks(name: string | null, script: Script | null) {
  const [picked, setPicked] = useState<string[]>([])
  const [from, setFrom] = useState<string | null>(null)
  useEffect(() => { setPicked([]); setFrom(null) }, [name])
  const pick = useCallback((b: Box, e: MouseEvent) => {
    if (e.shiftKey && from && script) {
      const row = boxes(script).filter(x => x.row === b.row).sort((x, y) => x.start - y.start).map(x => x.id)
      const i = row.indexOf(from), j = row.indexOf(b.id)
      if (i >= 0 && j >= 0) return setPicked(row.slice(Math.min(i, j), Math.max(i, j) + 1))
    }
    setFrom(b.id)
    if (e.altKey || e.ctrlKey || e.metaKey) setPicked(p => (p.includes(b.id) ? p.filter(x => x !== b.id) : [...p, b.id]))
    else setPicked([b.id])
  }, [from, script])
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key !== 'Delete' && e.key !== 'Backspace') return
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
      if (!name || !script || picked.length === 0) return
      e.preventDefault()
      const all = boxes(script)
      const ids = picked.map(p => all.find(b => b.id === p)).filter((b): b is Box => !!b)
        .map(b => idOf(script, b)).filter((x): x is string => !!x)
      setPicked([])
      void (async () => {
        for (const id of ids) {
          const r = await api.edit(name, { op: 'remove', id })
          if (isProblem(r)) { toast(r.problem); break }
        }
        await reload()
      })()
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [name, script, picked])
  return { picked, pick }
}

/** One field of a shot in the list, typed in; saved on leaving it (Enter leaves a one-line field). */
function Box1({ label, text, rows = 1, save }: { label: string; text: string; rows?: number; save: (v: string) => void }) {
  const done = (v: string) => { if (v !== text) save(v) }
  return (
    <label className={s.field}>
      <span className={s.label}>{label}</span>{' '}
      {rows > 1
        ? <textarea key={text} defaultValue={text} rows={rows} data-field={label} onBlur={e => done(e.currentTarget.value)} />
        : <input key={text} defaultValue={text} data-field={label} onBlur={e => done(e.currentTarget.value)}
            onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur() }} />}
    </label>
  )
}

/** The shots down the right, each one's number and seconds (a click picks it, as on the timeline), then its Framing,
 *  Move, Action and Seconds to read and type in: what each holds is what render sends. */
export function ShotList({ name, script, picked, onPick }: { name: string | null; script: Script; picked: string[]; onPick: (b: Box, e: MouseEvent) => void }) {
  const shots = boxes(script).filter(b => b.row === 'shots')
  const [pics, setPics] = useState<Record<string, string[]>>({})
  useEffect(() => { if (name) void api.shotPictures(name).then(r => setPics(r.pictures ?? {}), () => setPics({})) }, [name])
  const change = (id: string, fields: Record<string, unknown>) => {
    if (!name) return
    void api.edit(name, { op: 'change', id, fields }).then(r => {
      if (isProblem(r)) toast(r.problem)
      return reload()
    })
  }
  return (
    <div className={s.shotList} data-region="shot-list" data-scroll="shot-list">
      <Importer name={name} />
      {shots.map(b => {
        const placed = shotOfBox(script, b)
        if (!placed) return null
        const { id, shot } = placed
        const cam = typeof shot.camera === 'object' && shot.camera ? shot.camera : { framing: shot.camera ?? '' }
        return (
          <div key={b.id} className={`${s.shotItem} ${picked.includes(b.id) ? s.on : ''}`} data-shot={b.id}>
            <button type="button" className={s.shotHead} aria-pressed={picked.includes(b.id)} onClick={e => onPick(b, e)}>
              {b.shot} · {secs(b.end - b.start)} s
            </button>
            <Box1 label="Framing" text={cam.framing ?? ''} save={v => change(id, { camera: { ...cam, framing: v } })} />
            <Box1 label="Move" text={cam.move ?? ''} save={v => change(id, { camera: { ...cam, move: v } })} />
            <Box1 label="Action" text={shot.action ?? ''} rows={4} save={v => change(id, { action: v })} />
            <Box1 label="Seconds" text={shot.seconds === undefined ? '' : String(shot.seconds)}
              save={v => change(id, { seconds: Number(v) || 0 })} />
            {name ? <ShotPics name={name} shot={id} ids={pics[id] ?? []} onChange={setPics} /> : null}
          </div>
        )
      })}
    </div>
  )
}

/** Paste a MiniMax H3 prompt and press Import: one shot per time range of its description, added at the end. */
function Importer({ name }: { name: string | null }) {
  const [text, setText] = useState('')
  const go = () => {
    if (!name || !text.trim()) return
    void api.edit(name, { op: 'import', text }).then(r => {
      if (isProblem(r)) toast(r.problem)
      else setText('')
      return reload()
    })
  }
  return (
    <div className={s.shotItem} data-region="import">
      <textarea value={text} rows={3} placeholder="Paste a MiniMax H3 prompt" aria-label="Import prompt"
        onChange={e => setText(e.currentTarget.value)} />
      <button type="button" className={s.shotHead} onClick={go} disabled={!name || !text.trim()}>Import</button>
    </div>
  )
}
