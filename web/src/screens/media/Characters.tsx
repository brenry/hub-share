import { useEffect, useRef, useState, type DragEvent, type MouseEvent } from 'react'
import { errorText } from '../../lib/http'
import { MEDIA_DRAG, pictures, type DraggedMedia } from '../../lib/protocol'
import { useStore } from '../../lib/store'
import { toast } from '../../lib/toast'
import { Icon } from '../../ui/Icon'
import { Menu, type MenuAt, type MenuItem } from '../../ui/Menu'
import { cx } from '../../ui/cx'
import { characters, loadCharacters, naming, putCharacter, putVoiceSample, removeCharacter, renameCharacter, saveCharacterNotes, saveCharacterVoice, type View } from './media'
import s from './Tree.module.css'

const first = (e: DragEvent): string | null => {
  const raw = e.dataTransfer.getData(MEDIA_DRAG)
  return raw ? pictures(JSON.parse(raw) as DraggedMedia[])[0]?.id ?? null : null
}
const INDENT = 'calc(var(--sp-3) + 1.125rem)'

/** Characters: the folder of named pictures (Settings → Storage → Characters), listed by name — the file
 *  name without its extension. A click shows the character. A picture dropped on the heading, or Add to Characters
 *  on a thumbnail, asks for a name and is copied in (the picture stays where it was); dropped on a name, it replaces
 *  that character's picture. Right-click a name for its notes (what the picture does not show, kept inside its file and
 *  read by the assistant; Ctrl+Enter or leaving the box saves, Escape cancels), for the words for its voice (a
 *  speech model speaks its lines in them until it has a voice sample; kept the same way), for Voice sample… (an
 *  mp3 or wav file, chosen from the computer — or dropped on the name — becomes the voice sample: made a WAV in the browser,
 *  whole, replacing the one it had), to rename the character
 *  (the file is renamed, its voice sample with it) or to delete it (the file is erased, no trash). A name with notes
 *  shows them on hover. */
export function Characters({ view, onView }: { view: View; onView: (v: View) => void }) {
  const { unset, items } = useStore(characters, x => x)
  const asking = useStore(naming, x => x)
  const [renaming, setRenaming] = useState<{ id: string; value: string } | null>(null)
  const [noting, setNoting] = useState<{ id: string; value: string; field: 'notes' | 'voice' } | null>(null)
  const [menu, setMenu] = useState<{ at: MenuAt; items: MenuItem[] } | null>(null)
  const [dropOn, setDropOn] = useState('')
  const picker = useRef<HTMLInputElement>(null)
  const sampleFor = useRef<{ id: string; name: string } | null>(null)
  useEffect(() => { loadCharacters().catch(() => {}) }, [])
  const fail = (e: unknown) => toast(errorText(e))
  const put = (name: string, id: string, done: string) => putCharacter(name, id).then(() => toast(done)).catch(fail)
  const commit = () => {
    const n = naming.get()
    naming.set(null)
    const name = n?.value.trim()
    if (!n || !name) return
    const had = items.some(c => c.name.toLowerCase() === name.toLowerCase())
    put(name, n.id, had ? `${name} replaced` : `${name} added`)
  }
  const commitRename = () => {
    const r = renaming
    setRenaming(null)
    const old = items.find(c => c.id === r?.id)
    const name = r?.value.trim()
    if (!r || !old || !name || name === old.name) return
    renameCharacter(r.id, name).then(id => {
      if (view.kind === 'chars' && view.focus === r.id) onView({ kind: 'chars', focus: id })
      toast(`Renamed to ${name}`)
    }).catch(fail)
  }
  const commitNotes = () => {
    const n = noting
    setNoting(null)
    const was = items.find(c => c.id === n?.id)
    if (!n || !was || n.value.trim() === was[n.field]) return
    const word = n.field === 'voice' ? 'Voice' : 'Notes'
    const save = n.field === 'voice' ? saveCharacterVoice : saveCharacterNotes
    save(n.id, n.value).then(id => {
      if (view.kind === 'chars' && view.focus === n.id && id !== n.id) onView({ kind: 'chars', focus: id })
      toast(n.value.trim() ? `${word} saved for ${was.name}` : `${word} cleared for ${was.name}`)
    }).catch(fail)
  }
  const sample = (id: string, name: string, file: File) => putVoiceSample(id, file)
    .then(() => toast(`Voice sample saved for ${name}`)).catch(fail)
  const choose = (id: string, name: string) => {
    sampleFor.current = { id, name }
    if (picker.current) { picker.current.value = ''; picker.current.click() }
  }
  const dropped = (e: DragEvent, id: string, name: string) => {
    const pic = first(e)
    if (pic) { if (pic !== id) put(name, pic, `${name} replaced`); return }
    const file = e.dataTransfer.files[0]
    if (file) sample(id, name, file)
  }
  const remove = (id: string, name: string) => removeCharacter(id).then(() => {
    if (view.kind === 'chars' && view.focus === id) onView({ kind: 'chars', focus: '' })
    toast(`${name} deleted`)
  }).catch(fail)
  const openMenu = (e: MouseEvent, id: string, name: string, notes: string, voice: string) => {
    e.preventDefault(); e.stopPropagation()
    setMenu({ at: { x: e.clientX, y: e.clientY }, items: [
      { label: 'Notes…', icon: <Icon name="chat" />, run: () => setNoting({ id, value: notes, field: 'notes' }) },
      { label: 'Voice…', icon: <Icon name="chat" />, run: () => setNoting({ id, value: voice, field: 'voice' }) },
      { label: 'Voice sample…', icon: <Icon name="chat" />, run: () => choose(id, name) },
      { label: 'Rename', icon: <Icon name="pen" />, run: () => setRenaming({ id, value: name }) },
      { sep: true } as MenuItem,
      { label: 'Delete character', icon: <Icon name="x" />, danger: true, run: () => void remove(id, name) },
    ] })
  }
  const over = (key: string) => (e: DragEvent) => { e.preventDefault(); setDropOn(key) }
  const all = view.kind === 'chars' && !view.focus

  return (
    <div data-region="characters">
      <div role="treeitem" aria-selected={all} data-row="chars" className={cx(s.row, all && s.on, dropOn === 'chars' && s.drop)}
        style={{ paddingLeft: 'var(--sp-3)' }} onClick={() => onView({ kind: 'chars', focus: '' })}
        onDragOver={unset ? undefined : over('chars')} onDragLeave={() => setDropOn('')}
        onDrop={unset ? undefined : e => { e.preventDefault(); setDropOn(''); const id = first(e); if (id) naming.set({ id, value: '' }) }}>
        <span className={s.chev} />
        <span className={s.text}>Characters</span>
        {items.length ? <span className={cx(s.count, 'num')}>{items.length}</span> : null}
      </div>
      {asking && (
        <input autoFocus value={asking.value} aria-label="Character name" placeholder="Name" className={s.edit} style={{ marginLeft: INDENT }}
          onChange={e => naming.set({ ...asking, value: e.target.value })} onBlur={commit}
          onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') naming.set(null) }} />
      )}
      {unset && <p className={s.unset} data-region="characters-unset">Choose your Characters folder in Settings → Storage → Characters.</p>}
      {items.map(c => {
        if (renaming?.id === c.id) {
          return <input key={c.id} autoFocus value={renaming.value} aria-label="Character name" className={s.edit} style={{ marginLeft: INDENT }}
            onChange={e => setRenaming({ ...renaming, value: e.target.value })} onBlur={commitRename}
            onKeyDown={e => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setRenaming(null) }} />
        }
        const on = view.kind === 'chars' && view.focus === c.id
        return [
          <div key={c.id} role="treeitem" aria-selected={on} data-row={`char:${c.name}`} title={c.notes ? `${c.name}\n\n${c.notes}` : c.name}
            className={cx(s.row, on && s.on, dropOn === c.id && s.drop)} style={{ paddingLeft: INDENT }}
            onClick={() => onView({ kind: 'chars', focus: c.id })} onContextMenu={e => openMenu(e, c.id, c.name, c.notes, c.voice)}
            onDragOver={over(c.id)} onDragLeave={() => setDropOn('')}
            onDrop={e => { e.preventDefault(); setDropOn(''); dropped(e, c.id, c.name) }}>
            <span className={s.chev} />
            <span className={s.text}>{c.name}</span>
            {c.notes ? <span className={s.noted} aria-label="Has notes" /> : null}
            {c.sample ? <Icon name="sound" small label="Has a voice sample" className={s.voiced} /> : null}
            {c.views?.length ? <span className={cx('num', 't-meta', s.views)} aria-label={`${c.views.length} views`}>+{c.views.length}</span> : null}
          </div>,
          noting?.id === c.id && (
            <textarea key={`${c.id}:${noting.field}`} autoFocus value={noting.value} rows={noting.field === 'voice' ? 2 : 6}
              aria-label={noting.field === 'voice' ? `Voice of ${c.name}` : `Notes on ${c.name}`}
              placeholder={noting.field === 'voice' ? 'How they sound' : 'What the picture does not show: where they live, what they wear or carry, how they behave'}
              className={cx(s.edit, s.notes)} style={{ marginLeft: INDENT }}
              onChange={e => setNoting({ ...noting, value: e.target.value })} onBlur={commitNotes}
              onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); commitNotes() } if (e.key === 'Escape') setNoting(null) }} />
          ),
        ]
      })}
      <input ref={picker} type="file" hidden accept=".mp3,.wav,audio/mpeg,audio/wav" aria-label="Voice sample file"
        onChange={e => { const f = e.target.files?.[0], who = sampleFor.current; if (f && who) sample(who.id, who.name, f) }} />
      <Menu at={menu?.at ?? null} items={menu?.items ?? []} onClose={() => setMenu(null)} label="Character" />
    </div>
  )
}
