import { useEffect, useLayoutEffect, useMemo, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { useStore } from '../../../lib/store'
import { chat, say } from '../chat/assistant'
import { draft, edit } from '../draft'
import { stackOf } from '../edits'
import { loras } from '../loras'
import { characterList, matchesAt, picker, place, type Character, type Pick } from './complete'
import { Picker } from './Picker'
import { addCharacter } from '../inputs'
import { findRanges } from './triggers'
import s from './Compose.module.css'

/** Put a character's name in place of the word, a space after it (the caret goes after the space), and its picture
 *  in the first free reference box. */
function put(el: HTMLTextAreaElement, pick: Pick, c: Character): void {
  picker.set(null)
  const done = place(draft.get().prompt, pick, c.name)
  edit(d => ({ ...d, prompt: done.text }))
  requestAnimationFrame(() => { el.focus(); el.setSelectionRange(done.caret, done.caret) })
  void addCharacter({ id: c.id, w: c.w, h: c.h })
}

const MODIFIERS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'AltGraph', 'CapsLock'])

/** With tiles on show: Tab and Shift+Tab (or the arrows) move the cyan ring, Enter puts the lit name in, Escape
 *  closes them and changes nothing; any other key closes them and goes on as typed. -> whether the key was theirs. */
function pickerKey(e: KeyboardEvent<HTMLTextAreaElement>): boolean {
  const open = picker.get()
  if (!open) return false
  if (MODIFIERS.has(e.key)) return true // Shift alone (on the way to Shift+Tab) leaves the tiles open
  const n = open.pick.matches.length
  const step = e.key === 'Tab' ? (e.shiftKey ? -1 : 1) : e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
  if (step) { e.preventDefault(); picker.set({ ...open, i: (open.i + step + n) % n }); return true }
  if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) {
    e.preventDefault()
    put(e.currentTarget, open.pick, open.pick.matches[open.i]!)
    return true
  }
  picker.set(null)
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); return true }
  return false
}

/** Tab completes a character's name (`complete.ts`): one match goes in at once with a space after it; several show
 *  their tiles. The box keeps the focus. */
function completeOnTab(e: KeyboardEvent<HTMLTextAreaElement>): boolean {
  if (e.key !== 'Tab' || e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return false
  e.preventDefault()
  const el = e.currentTarget
  const text = el.value, caret = el.selectionStart
  if (el.selectionEnd !== caret) return true
  void characterList().then(list => {
    const pick = matchesAt(text, caret, list)
    if (!pick || draft.get().prompt !== text) return
    if (pick.matches.length === 1) put(el, pick, pick.matches[0]!)
    else picker.set({ pick, i: 0 })
  }, () => {})
  return true
}

/** Enter sends the box to the assistant and clears it (ignored while it works); Shift+Enter is a newline; Ctrl+Enter
 *  renders the draft; Tab completes a character's name. */
function sendOnEnter(e: KeyboardEvent<HTMLTextAreaElement>): void {
  if (pickerKey(e) || completeOnTab(e)) return
  if (e.key !== 'Enter' || e.shiftKey || e.ctrlKey || e.metaKey || e.altKey || e.nativeEvent.isComposing) return
  e.preventDefault()
  const text = e.currentTarget.value.trim()
  if (!text || chat.get().busy) return
  edit(d => ({ ...d, prompt: '' }))
  void say(text).then(ok => { if (!ok) edit(d => (d.prompt ? d : { ...d, prompt: text })) })
}

/** A textarea over a mirror that tints the active LoRAs' trigger words: the words typed to the assistant. Nothing writes
 *  into it but typing, and nothing renders it: Generate (the bar's button, Ctrl+Enter) renders the assistant's draft.
 *  New chat empties it. */
export function PromptBox() {
  const prompt = useStore(draft, d => d.prompt)
  const stack = useStore(draft, d => stackOf(d))
  const items = useStore(loras, l => l.items)
  const inner = useRef<HTMLDivElement>(null)
  const area = useRef<HTMLTextAreaElement | null>(null)
  const sync = () => {
    const t = area.current
    const m = inner.current
    if (!t || !m) return
    m.style.width = `${t.clientWidth}px`
    m.style.transform = `translateY(${-t.scrollTop}px)`
  }
  useLayoutEffect(sync)
  useEffect(() => {
    const ro = new ResizeObserver(sync)
    if (area.current) ro.observe(area.current)
    return () => ro.disconnect()
  }, [])
  const words = useMemo(() => {
    const on = new Set(stack.map(l => l.id))
    return items.filter(l => on.has(l.id)).flatMap(l => l.fileTriggers)
  }, [stack, items])
  const tinted = useMemo(() => {
    const parts: ReactNode[] = []
    let at = 0
    for (const [a, b] of findRanges(prompt, words)) {
      parts.push(prompt.slice(at, a), <mark key={a}>{prompt.slice(a, b)}</mark>)
      at = b
    }
    parts.push(prompt.slice(at), '​')
    return parts
  }, [prompt, words])

  return (
    <div className={s.promptBlock} data-region="prompt-block">
      <Picker onPick={c => { const open = picker.get(); if (open && area.current) put(area.current, open.pick, c) }} />
      <div className={s.prompt}>
        <div className={s.mirror} aria-hidden="true"><div ref={inner}>{tinted}</div></div>
        <textarea id="prompt" data-scroll="prompt" ref={area} value={prompt} aria-label="Prompt" spellCheck={false}
          onChange={e => { const v = e.target.value; edit(d => ({ ...d, prompt: v })) }} onKeyDown={sendOnEnter}
          onScroll={sync} onBlur={() => picker.set(null)} />
      </div>
    </div>
  )
}
