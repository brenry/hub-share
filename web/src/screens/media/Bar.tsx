import { useRef, useState } from 'react'
import { errorText } from '../../lib/http'
import { bus } from '../../lib/bus'
import { insideDesktop, launchTargets } from '../../lib/desktop'
import { toast } from '../../lib/toast'
import { modules } from '../../shell/registry'
import { Icon } from '../../ui/Icon'
import { Live } from '../../ui/Live'
import { Menu, type MenuAt, type MenuItem } from '../../ui/Menu'
import s from './Media.module.css'

/** `onContinue`: the Stage shows a clip that can be continued. */
type Props = { at: number; shown: number; tree: boolean; thumbs: boolean; onTree: () => void; onThumbs: () => void; onStep: (by: -1 | 1) => void; onContinue: (() => void) | null }

const tool = modules.find(m => m.queue)

/** The low bar in the bottom right, quiet so the eye stays on the picture: the tree and thumbnails buttons
 *  together, then previous / next image with the position small between them, the light (click twice to restart
 *  the Hub), the client's tagged instances or the Hub's (inside HocusPocus Desktop), a utilities fold-up (clear the GPU cache, seed back to
 *  random), Continue while the Stage shows a clip (it goes to box 1) and, in the corner, Generate: one click queues the
 *  Generate tool's saved draft. */
export function Bar({ at, shown, tree, thumbs, onTree, onThumbs, onStep, onContinue }: Props) {
  const [menu, setMenu] = useState<{ at: MenuAt; items: MenuItem[]; row: boolean; label: string } | null>(null)
  const monitorBtn = useRef<HTMLButtonElement>(null)
  const toolsBtn = useRef<HTMLButtonElement>(null)
  const [busy, setBusy] = useState(false)
  const generate = () => {
    if (!tool?.queue || busy) return
    setBusy(true)
    tool.queue().then(reason => toast(reason ?? 'Queued'), e => toast(errorText(e))).finally(() => setBusy(false))
  }
  // A fold-up opens just above the bar, starting at its button.
  const above = (el: HTMLElement | null): MenuAt => ({ x: el!.getBoundingClientRect().left, y: el!.closest('footer')!.getBoundingClientRect().top, up: true })
  const treeTip = tree ? 'Fold the folders away' : 'Show the folders'
  const thumbsTip = thumbs ? 'Lower the thumbnails' : 'Raise the thumbnails'
  // The client opens the instance tagged n when a page asks for `hpd:instance/n`, with its own monitor and full screen;
  // when none is tagged, it opens a saved instance when a page asks for its address: the Hub's.
  const launch: MenuItem[] = launchTargets().map(t => ({ label: t.label, icon: <Icon name="monitor" />, run: () => { window.open(t.url, '_blank', 'noopener') } }))
  const utilities: MenuItem[] = [
    { label: 'Clear the GPU cache', icon: <Icon name="chip" />, run: () => {
      bus.request('gpu.release', {}).then(() => toast('GPU cache cleared'), e => toast(errorText(e)))
    } },
    { label: 'Seed back to random', icon: <Icon name="reseed" />, off: tool?.randomSeed ? null : 'No tool has a seed', run: () => {
      tool?.randomSeed?.().then(() => toast('Seed: random'), e => toast(errorText(e)))
    } },
  ]
  return (
    <footer className={s.bar} data-region="bar">
      <button type="button" className={s.barBtn} onClick={onTree} aria-expanded={tree} title={treeTip} aria-label={treeTip} data-region="fold">
        <Icon name={tree ? 'treeIn' : 'treeOut'} small />
      </button>
      <button type="button" className={s.barBtn} onClick={onThumbs} aria-expanded={thumbs} title={thumbsTip} aria-label={thumbsTip} data-region="thumbs">
        <Icon name={thumbs ? 'thumbsDown' : 'thumbsUp'} small />
      </button>
      <span className={s.step}>
        <button type="button" className={s.stepBtn} onClick={() => onStep(-1)} disabled={at <= 1} title="Previous image" aria-label="Previous image" data-region="prev"><Icon name="back" small /></button>
        <span className={`${s.count} num`} data-region="count">{at} / {shown}</span>
        <button type="button" className={s.stepBtn} onClick={() => onStep(1)} disabled={at >= shown} title="Next image" aria-label="Next image" data-region="next"><Icon name="run" small /></button>
      </span>
      <Live className={s.liveFlat} />
      {insideDesktop() && (
        <button ref={monitorBtn} type="button" className={s.barBtn} title="Open an instance" aria-label="Open an instance" aria-haspopup="menu" data-region="launch"
          onClick={() => setMenu({ at: above(monitorBtn.current), items: launch, row: false, label: 'Open an instance' })}><Icon name="monitor" small /></button>
      )}
      <button ref={toolsBtn} type="button" className={s.barBtn} title="Cache and seed" aria-label="Cache and seed" aria-haspopup="menu" data-region="utilities"
        onClick={() => setMenu({ at: above(toolsBtn.current), items: utilities, row: true, label: 'Cache and seed' })}><Icon name="sliders" small /></button>
      {onContinue && (
        <button type="button" className={s.barBtn} onClick={onContinue} title="Continue this clip" aria-label="Continue this clip" data-region="continue"><Icon name="send" small /></button>
      )}
      {tool?.queue && (
        <button type="button" className={s.go} onClick={generate} disabled={busy} title={tool.label} aria-label={tool.label} data-region="generate">
          <Icon name="spark" small />
        </button>
      )}
      <Menu at={menu?.at ?? null} items={menu?.items ?? []} row={menu?.row ?? false} label={menu?.label ?? ''} onClose={() => setMenu(null)} />
    </footer>
  )
}
