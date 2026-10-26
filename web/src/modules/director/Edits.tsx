import { useCallback, useState, type MouseEvent, type ReactNode } from 'react'
import { toast } from '../../lib/toast'
import { Icon } from '../../ui/Icon'
import { Menu, type MenuAt, type MenuItem } from '../../ui/Menu'
import { api, isProblem, type EditOp, type Script } from './api'
import { Ask, type AskT } from './Ask'
import { reload } from './load'
import { addAt, idOf, moveOf, shotAt, speakers } from './moves'
import type { Box } from './timeline'

const CUES = ['effect', 'music', 'reaction']

export type Edits = {
  /** A box dropped with its start at `ms`. */
  onMove: (b: Box, ms: number) => void
  /** A shot's end dragged: its seconds become `seconds` (the shots after it move with it). */
  onStretch: (b: Box, seconds: number) => void
  onBoxMenu: (e: MouseEvent, b: Box) => void
  /** Empty timeline at `ms`; `who` the speaker of the lines row it is on. */
  onEmptyMenu: (e: MouseEvent, ms: number, who: string | null) => void
  view: ReactNode
}

/** The timeline's hand edits, each one `/edit` call; a refusal is its one line, else the script again. */
export function useEdits(name: string | null, script: Script | null): Edits {
  const [menu, setMenu] = useState<{ at: MenuAt; items: MenuItem[]; label: string } | null>(null)
  const [ask, setAsk] = useState<AskT | null>(null)
  const closeAsk = useCallback(() => setAsk(null), [])
  const send = (op: EditOp | null) => {
    if (!name || !op) return
    void api.edit(name, op).then(r => {
      if (isProblem(r)) toast(r.problem)
      return reload()
    })
  }
  const asking = (e: MouseEvent, label: string, fields: AskT['fields'], done: AskT['done'], blank = false) => () =>
    setAsk({ x: e.clientX, y: e.clientY, label, fields, done, blank })

  const onMove = (b: Box, ms: number) => { if (script) send(moveOf(script, b, ms)) }
  const onStretch = (b: Box, seconds: number) => {
    const id = script ? idOf(script, b) : null
    if (id !== null) send({ op: 'change', id, fields: { seconds } })
  }

  /** A shot's Edit: its framing, move, action and seconds as typed. */
  const shotEdit = (e: MouseEvent, id: string): MenuItem | null => {
    const shot = script?.scenes.flatMap(sc => sc.shots).find(sh => sh.id === id)
    if (!shot) return null
    const cam = typeof shot.camera === 'object' && shot.camera ? shot.camera : { framing: shot.camera ?? '' }
    const was = { framing: cam.framing ?? '', move: cam.move ?? '', action: shot.action ?? '',
                  seconds: shot.seconds === undefined ? '' : String(shot.seconds) }
    return { label: 'Edit', icon: <Icon name="pen" />, run: asking(e, 'Edit shot', [
      { key: 'framing', label: 'Framing', value: was.framing },
      { key: 'move', label: 'Move', value: was.move },
      { key: 'action', label: 'Action', value: was.action },
      { key: 'seconds', label: 'Seconds', value: was.seconds },
    ], v => {
      const now = { framing: v.framing ?? was.framing, move: v.move ?? was.move, action: v.action ?? was.action,
                    seconds: v.seconds ?? was.seconds }
      const fields: Record<string, unknown> = {}
      if (now.framing !== was.framing || now.move !== was.move) fields.camera = { ...cam, framing: now.framing, move: now.move }   // '' takes the move off
      if (now.action !== was.action) fields.action = now.action
      if (now.seconds !== was.seconds) fields.seconds = Number(now.seconds) || 0
      if (Object.keys(fields).length) send({ op: 'change', id, fields })
    }, true) }
  }
  const renderShot = (id: string): MenuItem => ({ label: 'Render this shot', icon: <Icon name="refresh" />, run: () => {
    if (!name) return
    void api.render(name, id).then(r => { if (isProblem(r)) toast(r.problem) })
  } })

  const onBoxMenu = (e: MouseEvent, b: Box) => {
    e.preventDefault()
    const id = script ? idOf(script, b) : null
    if (!script || id === null) return
    const ev = b.ev
    const edit: MenuItem | null = ev?.kind === 'line'
      ? { label: 'Edit', icon: <Icon name="pen" />, run: asking(e, 'Edit', [
          { key: 'speaker', label: 'Speaker', value: ev.speaker, options: [...new Set([ev.speaker, ...speakers(script)])] },
          { key: 'words', label: 'Words', value: ev.words },
        ], v => {
          const fields = Object.fromEntries(Object.entries(v).filter(([k, x]) => x !== (k === 'words' ? ev.words : ev.speaker)))
          if (Object.keys(fields).length) send({ op: 'change', id, fields })
        }) }
      : ev?.kind === 'cue'
        ? { label: 'Edit', icon: <Icon name="pen" />, run: asking(e, 'Edit', [{ key: 'words', label: 'Words', value: ev.words }],
            v => { if (v.words !== ev.words) send({ op: 'change', id, fields: { words: v.words! } }) }) }
        : ev === null && !b.panel ? shotEdit(e, id) : null
    setMenu({ at: { x: e.clientX, y: e.clientY }, label: 'Box', items: [
      ...(edit ? [edit] : []),
      ...(ev === null && !b.panel ? [renderShot(id)] : []),
      { label: 'Delete', icon: <Icon name="trash" />, danger: true, run: () => send({ op: 'remove', id }) },
    ] })
  }

  const onEmptyMenu = (e: MouseEvent, ms: number, who: string | null) => {
    e.preventDefault()
    if (!script) return
    const at = addAt(script, ms)
    const cast = speakers(script)
    const here = shotAt(script, ms)
    const scene = here?.scene ?? 1
    setMenu({ at: { x: e.clientX, y: e.clientY }, label: 'Timeline', items: [
      { label: 'Add line', icon: <Icon name="plus" />, off: !at ? 'No shot' : cast.length ? null : 'No cast',
        run: asking(e, 'Add line', [
          { key: 'speaker', label: 'Speaker', value: who && cast.includes(who) ? who : cast[0] ?? '', options: cast },
          { key: 'words', label: 'Words', value: '' },
        ], v => { if (at) send({ op: 'add_line', shot: at.shot, speaker: v.speaker!, words: v.words!, start_ms: at.start_ms }) }) },
      { label: 'Add cue', icon: <Icon name="plus" />, off: at ? null : 'No shot',
        run: asking(e, 'Add cue', [
          { key: 'cue', label: 'Cue', value: CUES[0]!, options: CUES },
          { key: 'words', label: 'Words', value: '' },
        ], v => { if (at) send({ op: 'add_cue', shot: at.shot, cue: v.cue as 'effect', words: v.words!, start_ms: at.start_ms }) }) },
      { label: 'Add shot', icon: <Icon name="plus" />, off: script.scenes.length ? null : 'No scene',
        run: asking(e, 'Add shot', [{ key: 'framing', label: 'Framing', value: '' }],
          v => send({ op: 'add_shot', scene, camera: { framing: v.framing! }, ...(here ? { after: here.id } : {}) })) },
    ] })
  }

  const view = <>
    <Menu at={menu?.at ?? null} items={menu?.items ?? []} label={menu?.label ?? 'Timeline'} onClose={() => setMenu(null)} />
    <Ask ask={ask} onClose={closeAsk} />
  </>
  return { onMove, onStretch, onBoxMenu, onEmptyMenu, view }
}
