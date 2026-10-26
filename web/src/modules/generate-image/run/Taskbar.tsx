import { useRef, useState } from 'react'
import { bus } from '../../../lib/bus'
import { insideDesktop, launchTargets } from '../../../lib/desktop'
import { errorText } from '../../../lib/http'
import { settingsOpen } from '../../../lib/settingsOpen'
import { useStore } from '../../../lib/store'
import { toast } from '../../../lib/toast'
import { Icon } from '../../../ui/Icon'
import { Live } from '../../../ui/Live'
import { Menu, type MenuAt, type MenuItem } from '../../../ui/Menu'
import { api } from '../api'
import { draft } from '../draft'
import type { SheetKind } from '../modelList'
import type { Model } from '../types'
import { isVideo } from '../video'
import type { Press } from '../useGenerate'
import { AspectMenu, Count, SizeMenu, Steps } from './Canvas'
import { generateLabel } from './jobs'
import { Slots } from './Slots'
import s from './Run.module.css'

type Props = { model: Model | null; press: Press; sheet: SheetKind | null; onSheet: (kind: SheetKind) => void }

/** The bar in the bottom right corner, one line, as on Media: Video (the video sheet) and the image sheet's fold, the reference boxes, size and
 *  shape, steps and the image count (guidance is on the raised sheet, under the model); then the light, the instances (inside HocusPocus Desktop), a fold-up of Settings,
 *  the GPU cache and the seed, and in the corner Generate, which renders the assistant's draft. */
export function Taskbar({ model, press, sheet, onSheet }: Props) {
  const images = useStore(draft, d => d.images)
  const [menu, setMenu] = useState<{ at: MenuAt; items: MenuItem[]; row: boolean; label: string } | null>(null)
  const monitorBtn = useRef<HTMLButtonElement>(null)
  const toolsBtn = useRef<HTMLButtonElement>(null)
  const above = (el: HTMLElement | null): MenuAt => ({ x: el!.getBoundingClientRect().left, y: el!.closest('footer')!.getBoundingClientRect().top, up: true })
  const launch: MenuItem[] = launchTargets().map(t => ({ label: t.label, icon: <Icon name="monitor" />, run: () => { window.open(t.url, '_blank', 'noopener') } }))
  const utilities: MenuItem[] = [
    { label: 'Settings', icon: <Icon name="sliders" />, run: () => settingsOpen.set(true) },
    { label: 'Clear the GPU cache', icon: <Icon name="chip" />, run: () => {
      bus.request('gpu.release', {}).then(() => toast('GPU cache cleared'), e => toast(errorText(e)))
    } },
    { label: 'Seed back to random', icon: <Icon name="reseed" />, run: () => {
      api.randomSeed().then(() => toast('Seed: random'), e => toast(errorText(e)))
    } },
  ]
  const library = sheet === 'image'
  const libraryTip = library ? 'Lower the LoRAs' : 'Raise the LoRAs and the model'
  const clip = isVideo(model)
  const line = model?.kind === 'speech'          // a line: one character's picture in box 1, no size, steps or count
  const label = generateLabel(images, clip, line)
  return (
    <footer className={s.bar} data-region="bar">
      <button type="button" className={s.barIcon} onClick={() => onSheet('video')} aria-expanded={sheet === 'video'} title="Video" aria-label="Video" data-region="video-toggle">
        <Icon name="video" small />
      </button>
      <button type="button" className={s.barIcon} onClick={() => onSheet('image')} aria-expanded={library} title={libraryTip} aria-label={libraryTip} data-region="library-toggle">
        <Icon name={library ? 'thumbsDown' : 'thumbsUp'} small />
      </button>
      <span className={s.controls}>
        <Slots model={model} />
        {!line && <>
          <SizeMenu model={model} />
          <AspectMenu model={model} />
          {model && <Steps model={model} />}
          <Count one={clip} />
        </>}
      </span>
      <Live className={s.liveFlat} />
      {insideDesktop() && (
        <button ref={monitorBtn} type="button" className={s.barIcon} title="Open an instance" aria-label="Open an instance" aria-haspopup="menu" data-region="launch"
          onClick={() => setMenu({ at: above(monitorBtn.current), items: launch, row: false, label: 'Open an instance' })}><Icon name="monitor" small /></button>
      )}
      <button ref={toolsBtn} type="button" className={s.barIcon} title="Settings, cache and seed" aria-label="Settings, cache and seed" aria-haspopup="menu" data-region="utilities"
        onClick={() => setMenu({ at: above(toolsBtn.current), items: utilities, row: true, label: 'Settings, cache and seed' })}><Icon name="sliders" small /></button>
      <button type="button" className={s.go} onClick={press.go} aria-disabled={press.reason !== null} title={press.reason ?? `${label} from the draft`}
        aria-label={label} data-region="generate"><Icon name="spark" small /></button>
      <Menu at={menu?.at ?? null} items={menu?.items ?? []} row={menu?.row ?? false} label={menu?.label ?? ''} onClose={() => setMenu(null)} />
    </footer>
  )
}
