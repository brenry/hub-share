import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { errorText } from '../../lib/http'
import { isTypingTarget } from '../../lib/keys'
import { connects, jobs } from '../../lib/live'
import type { GenerationItem } from '../../lib/protocol'
import { useStore } from '../../lib/store'
import { toast } from '../../lib/toast'
import { useBusEvent } from '../../lib/useBus'
import { Frame } from '../../shell/Frame'
import { Icon } from '../../ui/Icon'
import { Menu, type MenuAt, type MenuItem } from '../../ui/Menu'
import { Scroll } from '../../ui/Scroll'
import { cx } from '../../ui/cx'
import { modules } from '../../shell/registry'
import { Grid } from './Grid'
import { Bar } from './Bar'
import { Clip } from './Clip'
import { Sound } from './Sound'
import { Stage, type Edges } from './Stage'
import { Tree } from './Tree'
import { audienceItem } from './audience'
import { FAVORITES, TEMP, characters, clips as clipStore, drive, erase, favorite, fromGeneration, itemsOf, keepVoice, loadMore, looping, naming, prepend, refresh, sameView, sounds as soundStore, temp, verdictFor, view as viewStore, type MediaItem, type View } from './media'
import { EMPTY_SEL, afterDelete, clear, click, follow, move, selectAll, targets, type Selection } from './selection'
import { useSend } from './useSend'
import s from './Media.module.css'

/** A clip or a sound goes to no reference box, favorite or character: one line each (the hub refuses them the same way). */
const NO_SEND = 'Only pictures can be references'
const NO_FAV = 'Only pictures can be favorites'
const NO_CHAR = 'Only pictures can be characters'
const tool = modules.find(m => m.continueClip)
const stem = (id: string): string => id.split('/').pop()!.replace(/\.[^.]*$/, '')
const empty = (v: View): string => (v.kind === 'clips' ? 'No clips yet.' : v.kind === 'sounds' ? 'No sounds yet.' : v.kind === 'chars' ? 'No characters yet.' : v.kind === 'drive' ? 'No images in this folder.' : v.group === FAVORITES ? 'No favorites yet.' : v.group ? 'Nothing in this group.' : 'No temp generations. New ones land here.')

/** Whether a new file shows in the view: a picture in the Temp (or its group), a clip in the Clips, a sound in the Sounds. */
const shows = (v: View, it: MediaItem): boolean => (v.kind === 'temp' && it.kind === 'image' && (!v.group || v.group === it.group))
  || (v.kind === 'clips' && it.kind === 'clip') || (v.kind === 'sounds' && it.kind === 'sound')
const NEW = { image: 'New generation', clip: 'New clip', sound: 'New sound' } as const

/** The Media window, on the original's plan: the Stage alone on the left; on the right one bar over two thumbnails per
 *  row; the folder tree rolls out from there over the Stage without moving anything. Everything acts on the selection: right-click for the menu, Enter sends to the open
 *  tool's references, F favorites, Del erases for good; a clip is played, looped (L), listed, continued and erased, nothing else.
 *  With the thumbnails (and so the tree) folded, a click near the Stage's left or right edge steps like the bar's previous / next. */
export default function Media() {
  const view = useStore(viewStore, v => v)
  const t = useStore(temp, x => x)
  const cl = useStore(clipStore, x => x)
  const so = useStore(soundStore, x => x)
  const clips = view.kind === 'clips'
  const soundsView = view.kind === 'sounds'
  const d = useStore(drive, x => x)
  const c = useStore(characters, x => x)
  const loop = useStore(looping, x => x)
  const items = useMemo(() => itemsOf(view), [view, t, cl, so, d, c]) // eslint-disable-line react-hooks/exhaustive-deps
  const order = useMemo(() => items.map(i => i.id), [items])
  const [sel, setSel] = useState<Selection>(EMPTY_SEL)
  const [open, setOpen] = useState(true)
  const [thumbs, setThumbs] = useState(true)
  const [menu, setMenu] = useState<MenuAt | null>(null)
  const selRef = useRef(sel)
  selRef.current = sel
  const chosen = targets(sel, order)
  const others = chosen.some(id => items.find(i => i.id === id)?.kind !== 'sound')
  const { send, label: sendLabel, off: sendOff, state: sendState, sound, video } = useSend(chosen.length, others)

  const connected = useStore(connects, n => n)
  useEffect(() => { if (connected > 0) refresh().catch(e => toast(errorText(e))) }, [connected])
  useBusEvent('generation', data => {
    const it = fromGeneration((data as { item: GenerationItem }).item)
    prepend(it)
    const r = shows(view, it) ? follow(selRef.current, it.id) : null
    if (r?.stole) setSel(r.sel)
    else toast(NEW[it.kind])
  })
  useBusEvent('media.changed', () => { refresh().catch(() => {}) })
  // A character picked in the tree comes up on the Stage.
  useEffect(() => {
    if (view.kind === 'chars' && view.focus && order.includes(view.focus) && sel.current !== view.focus) {
      setSel({ ids: [view.focus], anchor: view.focus, current: view.focus })
    }
  }, [view, order]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (sel.current === null || !order.includes(sel.current)) {
      const first = order[0] ?? null
      if (first !== sel.current) setSel(x => (x.current !== null && order.includes(x.current) ? x : { ...x, ids: x.ids.filter(id => order.includes(id)), current: first }))
    }
  }, [order, sel.current])
  const body = useRef<HTMLDivElement>(null)
  const step = useCallback((by: -1 | 1) => setSel(x => move(x, order, by < 0 ? 'ArrowLeft' : 'ArrowRight', 2)), [order])
  const edges = useMemo<Edges>(() => ({ at: () => body.current?.querySelector('[data-region="count"]')?.getBoundingClientRect().left ?? null, step }), [step])
  const setView = useCallback((v: View) => { if (!sameView(v, viewStore.get())) { viewStore.set(v); setSel(EMPTY_SEL) } }, [])
  // The tree never stands alone: it opens with the thumbnails (both open when both were folded) and folds with them.
  // Whatever opens comes up on Temp, wherever the window was when it folded.
  const toggleTree = () => {
    if (!thumbs) { setThumbs(true); setOpen(true); setView(TEMP) } else if (open) setOpen(false); else { setOpen(true); setView(TEMP) }
  }
  const toggleThumbs = () => { if (thumbs) { setThumbs(false); setOpen(false) } else { setThumbs(true); setView(TEMP) } }

  const current = items.find(i => i.id === sel.current) ?? null
  const verdict = useStore(jobs, m => (current && current.kind !== 'image' ? verdictFor(m.values(), current.id) : null))   // a string: no redraw per tick
  const allFav = chosen.length > 0 && chosen.every(id => items.find(i => i.id === id)?.fav)
  const anyClip = chosen.some(id => items.find(i => i.id === id)?.kind === 'clip')
  const anySound = chosen.some(id => items.find(i => i.id === id)?.kind === 'sound')
  const notPicture = anyClip || anySound
  const anyClipRef = useRef(notPicture)
  anyClipRef.current = notPicture
  // A sound goes to the Sound box of the pulldown's model, through the Hub, from any screen: Put in Sound.
  const toSound = useRef<(() => void) | null>(null)
  toSound.current = anySound ? () => { if (sound.off) toast(sound.off); else send(chosen, 'sound') } : null
  const clipOn = useRef(false)
  clipOn.current = current?.kind === 'clip'

  const remove = useCallback(async () => {
    const ids = targets(selRef.current, order)
    if (ids.length === 0) return
    try {
      const n = await erase(ids)
      setSel({ ids: [], anchor: null, current: afterDelete(order, ids, selRef.current.current) })
      toast(n === 1 ? 'Deleted' : `${n} deleted`)
    } catch (e) { toast(errorText(e)) }
  }, [order])
  // Continue (the menu and the bar): the clip goes to box 1 of Generate Image; it stays where it is, still selected.
  const goOn = useCallback((id: string) => {
    tool?.continueClip?.(id).then(reason => toast(reason ?? `Continue: ${stem(id)} is in box 1`)).catch(e => toast(errorText(e)))
  }, [])
  // Loop (the menu and L): the Stage's clip player plays its clip round and round, every clip after it too.
  const toggleLoop = useCallback(() => { const on = !looping.get(); looping.set(on); toast(on ? 'Looping' : 'Stopped looping') }, [])
  const star = useCallback(() => {
    const ids = targets(selRef.current, order)
    if (ids.length === 0) return
    const on = !ids.every(id => itemsOf(viewStore.get()).find(i => i.id === id)?.fav)
    favorite(ids, on).then(moved => {
      setSel({ ids: moved, anchor: moved[0] ?? null, current: moved[0] ?? null })
      toast(on ? (ids.length > 1 ? `${ids.length} favorites` : 'Favorite') : 'Favorite removed')
    }).catch(e => toast(errorText(e)))
  }, [order])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (isTypingTarget(el) || el.closest?.('[role="menu"]') || ((e.key === 'Enter' || e.key === ' ') && el.closest?.('button'))) return
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') { e.preventDefault(); setSel(x => selectAll(order, x)); return }
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(e.key)) { e.preventDefault(); setSel(x => move(x, order, e.key, 2)); return }
      if (e.key === 'Enter') { e.preventDefault(); if (toSound.current) toSound.current(); else if (anyClipRef.current) toast(NO_SEND); else send(targets(selRef.current, order)); return }
      if (e.key === 'Delete') { e.preventDefault(); void remove(); return }
      if (e.key.toLowerCase() === 'l' && clipOn.current) { e.preventDefault(); toggleLoop(); return }
      if (e.key.toLowerCase() === 'f') { e.preventDefault(); if (anyClipRef.current) toast(NO_FAV); else star(); return }
      if (e.key === 'Escape') setSel(clear)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [order, remove, send, star, toggleLoop])

  // One image and references already in the tool: the first line folds out to the left with each reference slot.
  const slots = chosen.length === 1 && !notPicture && sendState.menu.some(m => m.label.startsWith('Replace')) ? sendState.menu.filter(m => m.socket.startsWith('reference')) : []
  const menuItems: MenuItem[] = [
    anySound
      ? { label: sound.label, icon: <Icon name="sound" />, key: 'Enter', off: sound.off, run: () => send(chosen, 'sound') }
      : { label: sendLabel, icon: <Icon name="send" />, key: 'Enter', off: notPicture ? NO_SEND : slots.length ? null : sendOff, run: () => send(chosen),
          ...(slots.length ? { sub: slots.map(m => ({ label: m.label, run: () => send(chosen, m.socket) })) } : {}) },
    ...(anyClip ? [{ label: video.label, icon: <Icon name="video" />, off: video.off, run: () => send(chosen, 'video') }, { label: 'Continue', icon: <Icon name="send" />, off: chosen.length > 1 ? 'One clip at a time' : tool ? null : 'Generate Image is not here',
      run: () => { if (chosen[0]) goOn(chosen[0]) } },
    { label: loop ? 'Stop looping' : 'Loop', icon: <Icon name="refresh" />, key: 'L', run: toggleLoop }] : []),
    ...(anySound ? [{ label: 'Keep as voice of…', icon: <Icon name="chat" />,
      off: chosen.length > 1 ? 'One sound at a time' : c.unset ? 'Choose the Characters folder in Settings → Storage' : c.items.length === 0 ? 'No characters yet' : null,
      run: () => {}, sub: c.items.map(ch => ({ label: ch.name, run: () => { const id = chosen[0]; if (id) keepVoice(id, ch.name).then(() => toast(`Voice of ${ch.name} kept`)).catch(e => toast(errorText(e))) } })) },
      { ...audienceItem(chosen, toast, e => toast(errorText(e))), icon: <Icon name="sound" /> }] : []),
    { label: allFav ? 'Remove favorite' : 'Favorite', icon: <Icon name="star" />, key: 'F', off: notPicture ? NO_FAV : null, run: star },
    { label: 'Add to Characters', icon: <Icon name="copy" />, off: notPicture ? NO_CHAR : c.unset ? 'Choose the Characters folder in Settings → Storage' : chosen.length !== 1 ? 'One picture at a time' : null,
      run: () => { const id = chosen[0]; if (id) { setThumbs(true); setOpen(true); naming.set({ id, value: '' }) } } },
    { sep: true },
    { label: chosen.length > 1 ? `Delete ${chosen.length}` : 'Delete', icon: <Icon name="x" />, key: 'Del', danger: true, run: () => void remove() },
  ]
  const more = view.kind === 'temp' && t.more ? () => loadMore('out') : clips && cl.more ? () => loadMore('clips') : soundsView && so.more ? () => loadMore('sounds') : null
  const openMenu = (e: MouseEvent) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY }) }

  return (
    <Frame>
      <div ref={body} className={s.body} data-region="media">
        <div className={s.stageBox}>{current && (current.kind === 'clip'
          ? <Clip key={current.url} src={current.url} w={current.w} h={current.h} side={thumbs} loop={loop} edges={thumbs ? undefined : edges}
              verdict={verdict} />
          : current.kind === 'sound' ? <Sound key={current.url} src={current.url} name={stem(current.id)} verdict={verdict} />
          : <Stage key={current.url} src={current.url} edges={thumbs ? undefined : edges} />)}</div>
        <div className={cx(s.side, !thumbs && s.sideShut)} data-region="side">
          <div className={cx(s.tree, !open && s.treeShut)} data-region="tree-col" inert={!open}>
            <Scroll name="media-tree" className={s.treeScroll}><Tree view={view} onView={setView} /></Scroll>
          </div>
          <div className={cx(s.gridBox, !thumbs && s.gridShut)} inert={!thumbs} data-region="thumbs-box">
            <Grid items={items} sel={sel} more={more} empty={empty(view)} label={clips ? 'Clips' : soundsView ? 'Sounds' : 'Images'}
              onPick={(id, mods) => setSel(x => click(x, order, id, mods))} onMenu={openMenu} />
          </div>
          <Bar at={current ? order.indexOf(current.id) + 1 : 0} shown={items.length} tree={open} thumbs={thumbs} onTree={toggleTree} onThumbs={toggleThumbs}
            onStep={step} onContinue={current?.kind === 'clip' && tool ? () => goOn(current.id) : null} />
        </div>
      </div>
      <Menu at={menu} items={menuItems} onClose={() => setMenu(null)} label={clips ? 'Clip' : soundsView ? 'Sound' : 'Image'} />
    </Frame>
  )
}
