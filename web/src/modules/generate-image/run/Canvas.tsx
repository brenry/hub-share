import type { ReactNode } from 'react'
import { useStore } from '../../../lib/store'
import { Icon } from '../../../ui/Icon'
import { cx } from '../../../ui/cx'
import { draft, edit } from '../draft'
import { advancedOf, withAdvanced } from '../edits'
import { canvasOf, sizesFor } from '../job'
import type { Aspect, Draft, Model } from '../types'
import { autoOf, clipInBox, clipSize, isVideo, refsOf, sizeValue, tierOf, tierOptions, tierSize } from '../video'
import { BarMenu, type BarOption } from './BarMenu'
import s from './Run.module.css'

const ASPECTS: Aspect[] = ['auto', '1:1', '4:3', '3:4', '3:2', '2:3', '16:9', '9:16']

/** Auto's square: dashed, lit cyan like the light. */
function Shape({ lit = false }: { lit?: boolean }) {
  return <i className={cx(s.ar, s.arAuto, lit && s.arLit)} style={{ width: '.875rem', height: '.875rem' }} />
}

const aspectOptions: BarOption<Aspect>[] = ASPECTS.map(a => ({
  value: a, name: a === 'auto' ? 'Auto' : a, label: a === 'auto' ? <><Shape lit /><span>Auto</span></> : <span className="num">{a}</span>,
}))
const sizeOption = (m: number): BarOption<string> => ({ value: String(m), name: `${m} MP`, label: <span className="num">{m} MP</span> })

/** A clip in box 1 sets the size and the shape: the menu is greyed, the clip's size its hover text. */
function Greyed({ d, label, children }: { d: Draft; label: string; children: ReactNode }) {
  const c = clipInBox(d)!
  return <button type="button" className={s.barBtn} aria-label={label} aria-disabled="true" title={`The clip's size, ${c.w}×${c.h}`}
    style={{ color: 'var(--text-dis)', cursor: 'default' }}>{children}</button>
}

/** Auto is the dashed square, lit cyan like the light; a fixed ratio is its numbers in plain grey. With a start frame
 *  in box 1, Auto is the tier's shape nearest the frame's: its size is Auto's hover text. */
export function AspectMenu({ model }: { model: Model | null }) {
  const d = useStore(draft, v => v)
  const aspect = d.aspect
  const auto = isVideo(model) && refsOf(model)?.role === 'start' && d.references.length > 0 ? clipSize({ ...d, aspect: 'auto' }, model) : null
  const hint = auto ? `${auto.width} × ${auto.height}` : undefined
  const options = hint ? aspectOptions.map(o => (o.value === 'auto' ? { ...o, hint } : o)) : aspectOptions
  const button = aspect === 'auto' ? <Shape lit /> : <span className="num">{aspect}</span>
  if (clipInBox(d)) return <Greyed d={d} label="Aspect">{button}</Greyed>
  return <BarMenu<Aspect> label="Aspect" value={aspect} options={options} square={aspect === 'auto'} button={button}
    {...(aspect === 'auto' && hint ? { hint } : {})} onPick={a => edit(x => ({ ...x, aspect: a }))} />
}

/** Megapixels; the canvas it makes is in the hover text. A picture model lists the sizes within its budget, and a
 *  size above it (saved for another model) makes the largest canvas within it. A video model lists its tiers instead
 *  (each stored as its megapixels value); the hover text is the tier's size for the aspect. */
export function SizeMenu({ model }: { model: Model | null }) {
  const d = useStore(draft, v => v)
  const v = isVideo(model) ? model.video : null
  const { width, height } = isVideo(model) ? clipSize(d, model) : canvasOf(d, model?.budget)
  if (clipInBox(d)) return <Greyed d={d} label="Size"><span className="num">{v ? tierOf(v, d.size).name : `${d.size} MP`}</span></Greyed>
  const options = isVideo(model) ? tierOptions(model.video).map(o => {
    const t = tierSize(model.video, Number(o.value), d.aspect, autoOf(d, model))
    return { ...o, label: <span className="num">{o.name}</span>, hint: `${t.width} × ${t.height}` }
  }) : sizesFor(model?.budget).map(sizeOption)
  return <BarMenu<string> key={v ? 'tiers' : 'mp'} label="Size" value={v ? sizeValue(v, d.size) : String(d.size)} options={options}
    hint={`${width} × ${height}`} button={v ? <span className="num">{tierOf(v, d.size).name}</span> : sizeOption(d.size).label}
    onPick={x => edit(y => ({ ...y, size: Number(x) }))} />
}

/** Steps for the current model (kept per model): the number, typed or nudged with the small arrows beside it. A model
 *  that runs its own steps (`lockSteps`) shows them, the control off. */
export function Steps({ model }: { model: Model }) {
  const d = useStore(draft, v => v)
  const locked = model.lockSteps === true
  const steps = locked ? model.defaults.steps : advancedOf(d, model).steps
  const put = (v: number) => { if (!locked && Number.isFinite(v) && v >= 1) edit(x => withAdvanced(x, model, { steps: Math.min(100, Math.round(v)) })) }
  return (
    <span className={s.steps} title={locked ? `${model.label} runs ${steps} steps` : 'Steps'} data-region="steps">
      <input type="number" className={cx(s.number, 'num')} aria-label="Steps" value={steps} min={1} max={100} step={1}
        disabled={locked} onChange={e => put(Number(e.target.value))} />
      <span className={s.arrows}>
        <button type="button" aria-label="More steps" disabled={locked || steps >= 100} onClick={() => put(steps + 1)}><Icon name="up" small /></button>
        <button type="button" aria-label="Fewer steps" disabled={locked || steps <= 1} onClick={() => put(steps - 1)}><Icon name="down" small /></button>
      </span>
    </span>
  )
}

/** Guidance for the current model (kept per model), for a model that has it: the number, typed or nudged by half a
 *  step with the small arrows beside it. It sits on the raised sheet under the model (`LoraLibrary.tsx`). */
export function Guidance({ model }: { model: Model }) {
  const d = useStore(draft, v => v)
  const g = advancedOf(d, model).guidance ?? model.defaults.guidance ?? 0
  const put = (v: number) => { if (Number.isFinite(v)) edit(x => withAdvanced(x, model, { guidance: Math.min(20, Math.max(0, Math.round(v * 10) / 10)) })) }
  return (
    <span className={s.steps} title="Guidance" data-region="guidance">
      <input type="number" className={cx(s.number, 'num')} aria-label="Guidance" value={g} min={0} max={20} step={0.1}
        onChange={e => put(Number(e.target.value))} />
      <span className={s.arrows}>
        <button type="button" aria-label="More guidance" disabled={g >= 20} onClick={() => put(g + 0.5)}><Icon name="up" small /></button>
        <button type="button" aria-label="Less guidance" disabled={g <= 0} onClick={() => put(g - 0.5)}><Icon name="down" small /></button>
      </span>
    </span>
  )
}

/** How many pictures one press makes: − n +. A video model makes one clip: 1, both buttons off. */
export function Count({ one = false }: { one?: boolean }) {
  const images = useStore(draft, d => d.images)
  const n = one ? 1 : images
  const put = (v: number) => edit(x => ({ ...x, images: Math.max(1, Math.min(6, v)) }))
  return (
    <span role="group" aria-label="Images" className={s.count} title={one ? 'One clip' : 'Images'} data-region="count" aria-disabled={one || undefined}>
      <button type="button" aria-label="Fewer images" disabled={one || n <= 1} onClick={() => put(n - 1)}><Icon name="minus" small /></button>
      <output className="num" aria-live="polite">{n}</output>
      <button type="button" aria-label="More images" disabled={one || n >= 6} onClick={() => put(n + 1)}><Icon name="plus" small /></button>
    </span>
  )
}
