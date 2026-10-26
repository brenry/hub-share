import { useCallback, useEffect, useState, type DragEvent, type MouseEvent, type ReactNode } from 'react'
import { errorText } from '../../lib/http'
import { MEDIA_DRAG, pictures, type DraggedMedia } from '../../lib/protocol'
import { useStore } from '../../lib/store'
import { toast } from '../../lib/toast'
import { Icon } from '../../ui/Icon'
import { Menu, type MenuAt, type MenuItem } from '../../ui/Menu'
import { cx } from '../../ui/cx'
import { CLIPS, FAVORITES, SOUNDS, clips, drive, favFolder, favFolders, favorite, folderMove, folderNew, folderRemove, folderRename, loadFolder, moveTo, refresh, sounds, temp, type View } from './media'
import { Characters } from './Characters'
import s from './Tree.module.css'

const FOLDER_DRAG = 'application/x-hub-folder'
type Edit = { mode: 'new' | 'rename'; path: string; value: string }
type Row = { id: string; depth: number; text: string; active: boolean; count?: number | undefined; expandable?: boolean; expanded?: boolean; dim?: boolean
  lead?: ReactNode; onClick: () => void; drop?: (ids: string[]) => void; dropFolder?: (path: string) => void; menu?: MenuItem[]; dragPath?: string | undefined }

const parent = (p: string) => p.split('/').slice(0, -1).join('/')
const join = (a: string, b: string) => (a ? `${a}/${b}` : b)

/** The organizer: Library (the Temp and its groups; Favorites is the group a picture moves into, and under it the
 *  favorite folders: Drive folders pinned from their right-click menu, listed by name with their subfolders, nothing
 *  moved; a pinned row only shows its folder and unpins), the Characters, the Clips (the clips root: one row, every
 *  clip of every day in one list, no day rows, no fold, no drops), the Sounds (the same, for sounds) and the Drive's folders. One click on a folder shows it
 *  and opens it. Thumbnails drop on Favorites or a Drive folder (both a move); folders drag into folders. */
export function Tree({ view, onView }: { view: View; onView: (v: View) => void }) {
  const t = useStore(temp, x => x)
  const cl = useStore(clips, x => x)
  const so = useStore(sounds, x => x)
  const favCount = t.groups.find(g => g.name === FAVORITES)?.count ?? 0
  const folders = useStore(drive, d => d)
  const favs = useStore(favFolders, x => x)
  const [open, setOpen] = useState<Set<string>>(() => new Set(['temp', 'fav', 'drive:']))
  const [editing, setEditing] = useState<Edit | null>(null)
  const [dropOn, setDropOn] = useState('')
  const [menu, setMenu] = useState<{ at: MenuAt; items: MenuItem[] } | null>(null)
  useEffect(() => { if (!folders['']) loadFolder('').catch(e => toast(errorText(e))) }, [folders])
  // A pinned folder is read once it is listed, so its row shows its count and opens only when it has subfolders.
  useEffect(() => { for (const f of favs) if (f.ok && !folders[f.path]) loadFolder(f.path).catch(() => {}) }, [favs, folders])
  const unset = Boolean(folders['']?.unset)

  const toggle = (id: string, force?: boolean) => setOpen(o => { const n = new Set(o); if (force ?? !n.has(id)) n.add(id); else n.delete(id); return n })
  const fail = (e: unknown) => toast(errorText(e))
  const pickDrive = (path: string, id: string) => {
    const active = view.kind === 'drive' && view.path === path
    onView({ kind: 'drive', path })
    toggle(id, active ? undefined : true)
    if (!folders[path]) loadFolder(path).catch(fail)
  }
  const dropItems = (e: DragEvent, run: (ids: string[]) => void) => {
    e.preventDefault(); setDropOn('')
    const raw = e.dataTransfer.getData(MEDIA_DRAG)
    const ids = raw ? pictures(JSON.parse(raw) as DraggedMedia[]).map(x => x.id) : []
    if (ids.length) run(ids)
  }
  const commit = useCallback(async () => {
    const ed = editing
    setEditing(null)
    if (!ed || !ed.value.trim()) return
    try {
      if (ed.mode === 'new') {
        const r = await folderNew(ed.path, ed.value)
        await loadFolder(ed.path); toggle(`drive:${ed.path}`, true); onView({ kind: 'drive', path: r.path })
      } else {
        const r = await folderRename(ed.path, ed.value)
        await refresh(); if (view.kind === 'drive' && view.path === ed.path) onView({ kind: 'drive', path: r.path })
      }
    } catch (e) { fail(e) }
  }, [editing, onView, view])
  const remove = (path: string) => {
    folderRemove(path).then(async () => {
      await refresh()
      if (view.kind === 'drive' && (view.path === path || view.path.startsWith(path + '/'))) onView({ kind: 'drive', path: parent(path) })
      toast('Folder deleted')
    }).catch(fail)
  }
  const isFav = (path: string) => favs.some(f => f.path === path)
  const starItem = (path: string): MenuItem => {
    const on = !isFav(path)
    return { label: on ? 'Add to Favorites' : 'Remove from Favorites', icon: <Icon name="star" className={s.star} />,
      run: () => favFolder(path, on).then(() => toast(on ? 'Added to Favorites' : 'Removed from Favorites')).catch(fail) }
  }
  const folderMenu = (path: string): MenuItem[] => [
    ...(path ? [starItem(path)] : []),
    { label: 'New folder inside', icon: <Icon name="plus" />, run: () => { setEditing({ mode: 'new', path, value: '' }); toggle(`drive:${path}`, true) } },
    ...(path ? [
      { label: 'Rename', icon: <Icon name="pen" />, run: () => setEditing({ mode: 'rename', path, value: path.split('/').pop()! }) },
      { sep: true } as MenuItem,
      { label: 'Delete folder', icon: <Icon name="x" />, danger: true, run: () => remove(path) },
    ] : []),
  ]
  const openMenu = (e: MouseEvent, items: MenuItem[]) => { e.preventDefault(); e.stopPropagation(); setMenu({ at: { x: e.clientX, y: e.clientY }, items }) }

  const row = (o: Row) => (
    <div key={o.id} role="treeitem" aria-selected={o.active} aria-expanded={o.expandable ? Boolean(o.expanded) : undefined} data-row={o.id}
      className={cx(s.row, o.active && s.on, o.dim && s.gone, dropOn === o.id && s.drop)} style={{ paddingLeft: `calc(var(--sp-3) + ${o.depth} * 1.125rem)` }}
      onClick={o.onClick} onContextMenu={o.menu ? e => openMenu(e, o.menu!) : undefined}
      draggable={Boolean(o.dragPath)} onDragStart={o.dragPath ? e => { e.dataTransfer.setData(FOLDER_DRAG, o.dragPath!); e.dataTransfer.effectAllowed = 'move' } : undefined}
      onDragOver={o.drop || o.dropFolder ? e => { e.preventDefault(); setDropOn(o.id) } : undefined} onDragLeave={() => setDropOn('')}
      onDrop={o.drop || o.dropFolder ? e => {
        const folder = e.dataTransfer.getData(FOLDER_DRAG)
        if (folder && o.dropFolder) { e.preventDefault(); setDropOn(''); o.dropFolder(folder); return }
        if (o.drop) dropItems(e, o.drop)
      } : undefined}>
      <span className={s.chev}>{o.expandable && <Icon name="right" small className={cx(s.chevIcon, o.expanded && s.open)} />}</span>
      {o.lead}
      <span className={s.text}>{o.text}</span>
      {o.count ? <span className={cx(s.count, 'num')}>{o.count}</span> : null}
    </div>
  )
  const editRow = (depth: number) => editing && (
    <input key="edit" autoFocus value={editing.value} aria-label="Folder name" className={s.edit} style={{ marginLeft: `calc(var(--sp-3) + ${depth} * 1.125rem)` }}
      onChange={e => setEditing({ ...editing, value: e.target.value })} onBlur={() => void commit()}
      onKeyDown={e => { if (e.key === 'Enter') void commit(); if (e.key === 'Escape') setEditing(null) }} />
  )
  // A Drive folder's rows: the folder, then its subfolders while it is open; the folder's operations and drops.
  const driveRows = (path: string, depth: number): ReactNode[] => {
    const id = `drive:${path}`, f = folders[path], isOpen = open.has(id)
    const name = path ? path.split('/').pop()! : f?.name || 'Drive'
    if (editing?.mode === 'rename' && editing.path === path) return [editRow(depth)]
    return [
      row({ id, depth, text: name, active: view.kind === 'drive' && view.path === path, count: f?.items.length,
        expandable: !f || f.dirs.length > 0, expanded: isOpen && Boolean(f), onClick: () => pickDrive(path, id), menu: folderMenu(path), dragPath: path || undefined,
        drop: ids => moveTo(ids, path).then(n => toast(n === 1 ? `Moved to ${name}` : `${n} moved to ${name}`)).catch(fail),
        dropFolder: from => { if (from !== path) folderMove([from], path).then(refresh).catch(fail) } }),
      ...(isOpen && f ? f.dirs.flatMap(d => driveRows(join(path, d), depth + 1)) : []),
      ...(editing?.mode === 'new' && editing.path === path ? [editRow(depth + 1)] : []),
    ]
  }
  // A pinned folder's rows under Favorites: the folder and, open, its subfolders, each with its own open state
  // (`fav:<pinned>` and `fav:<pinned>><path>`), a look and a star only: no drops, no drags, no folder operations.
  const favRows = (pinned: string, path: string, depth: number): ReactNode[] => {
    const id = path === pinned ? `fav:${pinned}` : `fav:${pinned}>${path}`, f = folders[path], isOpen = open.has(id)
    return [
      row({ id, depth, text: path.split('/').pop()!, active: view.kind === 'drive' && view.path === path, count: f?.items.length,
        expandable: !f || f.dirs.length > 0, expanded: isOpen && Boolean(f), onClick: () => pickDrive(path, id), menu: [starItem(path)] }),
      ...(isOpen && f ? f.dirs.flatMap(d => favRows(pinned, join(path, d), depth + 1)) : []),
    ]
  }
  const goneRow = (path: string, name: string): ReactNode[] => [row({
    id: `fav:${path}`, depth: 1, text: name, active: false, dim: true, onClick: () => toast('That folder is not in the Drive now'),
    menu: [{ label: 'Remove from Favorites', icon: <Icon name="star" />, run: () => favFolder(path, false).then(() => toast('Removed from Favorites')).catch(fail) }],
  })]
  const tempActive = (g: string) => view.kind === 'temp' && view.group === g
  const groups = t.groups.filter(g => g.name !== FAVORITES)
  return (
    <nav className={s.tree} aria-label="Folders" data-region="tree" onContextMenu={e => e.preventDefault()}>
      <div className={s.label}><span>Library</span></div>
      {row({ id: 'temp', depth: 0, text: 'Temp', active: tempActive(''), count: t.total, expandable: groups.length > 0, expanded: open.has('temp'),
        lead: <span className={cx(s.dot, t.total === 0 && s.dotOff)} />, onClick: () => { const a = tempActive(''); onView({ kind: 'temp', group: '' }); if (groups.length) toggle('temp', a ? undefined : true) } })}
      {open.has('temp') && groups.map(g => row({ id: `temp/${g.name}`, depth: 1, text: g.name, active: tempActive(g.name), count: g.count, onClick: () => onView({ kind: 'temp', group: g.name }) }))}
      <div className={s.sep} />
      {row({ id: 'fav', depth: 0, text: FAVORITES, active: tempActive(FAVORITES), count: favCount, lead: <Icon name="star" small className={s.star} />,
        expandable: favs.length > 0, expanded: open.has('fav'),
        onClick: () => { const a = tempActive(FAVORITES); onView({ kind: 'temp', group: FAVORITES }); if (favs.length) toggle('fav', a ? undefined : true) },
        drop: ids => favorite(ids, true).then(() => toast(ids.length > 1 ? `${ids.length} favorites` : 'Favorite')).catch(fail) })}
      {open.has('fav') && <div role="tree" aria-label="Favorite folders">{favs.flatMap(f => (f.ok ? favRows(f.path, f.path, 1) : goneRow(f.path, f.name)))}</div>}
      <div className={s.sep} />
      <Characters view={view} onView={onView} />
      <div className={s.sep} />
      {row({ id: 'clips', depth: 0, text: 'Clips', active: view.kind === 'clips', count: cl.total, lead: <span className={cx(s.dot, cl.total === 0 && s.dotOff)} />,
        onClick: () => onView(CLIPS) })}
      {row({ id: 'sounds', depth: 0, text: 'Sounds', active: view.kind === 'sounds', count: so.total, lead: <span className={cx(s.dot, so.total === 0 && s.dotOff)} />,
        onClick: () => onView(SOUNDS) })}
      <div className={cx(s.label, s.drive)}><span>Drive</span>
        {!unset && <button type="button" className={s.plus} title="New folder" aria-label="New folder" onClick={() => { setEditing({ mode: 'new', path: '', value: '' }); toggle('drive:', true) }}><Icon name="plus" small /></button>}
      </div>
      {unset ? <p className={s.unset} data-region="drive-unset">Choose your folder in Settings → Storage → Drive.</p>
        : <div role="tree" aria-label="Drive">{driveRows('', 0)}</div>}
      <Menu at={menu?.at ?? null} items={menu?.items ?? []} onClose={() => setMenu(null)} label="Folder" />
    </nav>
  )
}
