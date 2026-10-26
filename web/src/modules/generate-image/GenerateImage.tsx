import { useEffect, useMemo, useRef, useState } from 'react'
import { useCtrlEnter } from '../../lib/keys'
import { connects } from '../../lib/live'
import type { ToolProps } from '../../lib/module'
import { useStore } from '../../lib/store'
import { cx } from '../../ui/cx'
import { Article } from './chat/Article'
import { Chat } from './chat/Chat'
import { useAssistant } from './chat/assistant'
import { draft, edit, loadDraft } from './draft'
import { switchKind } from './edits'
import { LoraLibrary } from './library/LoraLibrary'
import { loadLoras } from './loras'
import { VideoSheet } from './library/VideoSheet'
import { defaults, loadModels, modelList, type SheetKind } from './modelList'
import { Dock } from './run/Dock'
import { Taskbar } from './run/Taskbar'
import { useSockets } from './sockets'
import { useGenerate } from './useGenerate'
import s from './GenerateImage.module.css'

/** The Generate screen, on the Media window's plan. Left: the assistant's draft as a two-column page, the prompt box
 *  (the assistant's input) under it. Right: a column holding the assistant's replies, with one bar in the bottom right
 *  corner; the image sheet (its fold) or the video sheet (Video) rolls up from that bar over the replies without moving anything. Generate — the
 *  bar's button or Ctrl+Enter — renders the draft; nothing ever renders the prompt box. */
export default function GenerateImage({ visible }: ToolProps) {
  const d = useStore(draft, v => v)
  const models = useStore(modelList, v => v)
  const [sheet, setSheet] = useState<SheetKind | null>(null)
  const [shown, setShown] = useState<SheetKind>('image')   // what the sheet holds, kept while it rolls down
  useAssistant()

  const connected = useStore(connects, n => n)
  useEffect(() => { void loadDraft() }, [])
  useEffect(() => {
    if (connected > 0) void loadModels(connected === 1)   // the first connection = this page load: full rescan
  }, [connected])

  const model = useMemo(() => models?.find(m => m.id === d.model) ?? null, [models, d.model])   // none: "Pick a model"

  useEffect(() => {
    const id = d.model
    if (!id) return
    void loadLoras(id)
    const again = () => void loadLoras(id)
    window.addEventListener('focus', again)
    return () => window.removeEventListener('focus', again)
  }, [d.model])

  useSockets(d, model)
  const gen = useGenerate(d, model)
  useCtrlEnter(gen.go, visible)
  // One sheet at a time: the fold raises the image sheet, Video the video sheet; the raised one's button lowers it,
  // the other's swaps it. From a model of the other kind the button also brings back the last of its own (`switchKind`)
  // and raises its sheet. The sheet takes the focus when it rises; Escape lowers it and hands the focus back to its button.
  const raise = (kind: SheetKind) => {
    const next = switchKind(draft.get(), models ?? [], defaults.get(), kind)
    if (next) edit(() => next)
    setShown(kind)
    setSheet(s => (!next && s === kind ? null : kind))
  }
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!sheet) return
    requestAnimationFrame(() => box.current?.querySelector<HTMLElement>('[data-region="model-picker"]')?.focus())
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || document.querySelector(':popover-open')) return
      setSheet(null)
      document.querySelector<HTMLElement>(`[data-region="${sheet === 'video' ? 'video-toggle' : 'library-toggle'}"]`)?.focus()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [sheet])

  return (
    <div className={s.work}>
      <section className={s.main} aria-label="Compose" data-region="compose">
        <Article />
        <Dock />
      </section>
      <div className={s.side} data-region="side">
        <Chat />
        <div className={cx(s.sheetBox, !sheet && s.sheetShut)} inert={!sheet} data-region="library-sheet">
          <div className={s.sheet} ref={box}>{shown === 'video' ? <VideoSheet models={models ?? []} model={model} /> : <LoraLibrary models={models ?? []} model={model} />}</div>
        </div>
        <Taskbar model={model} press={gen} sheet={sheet} onSheet={raise} />
      </div>
    </div>
  )
}
