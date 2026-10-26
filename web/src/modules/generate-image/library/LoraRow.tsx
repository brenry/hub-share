import { Fragment } from 'react'
import { Button } from '../../../ui/Button'
import { DragNumber } from '../../../ui/DragNumber'
import { cx } from '../../../ui/cx'
import { Cover } from '../Cover'
import type { LoraItem } from '../types'
import { share, stem } from './order'
import s from './LoraLibrary.module.css'

/** The file name, breakable after each underscore so a long one wraps there and is never cut. */
function Name({ lora }: { lora: LoraItem }) {
  const parts = stem(lora).split('_')
  return <>{parts.map((p, i) => <Fragment key={i}>{p}{i < parts.length - 1 && <>_<wbr /></>}</Fragment>)}</>
}

const hint = (l: LoraItem): string => (l.fileTriggers.length ? `${stem(l)}\n${l.fileTriggers.join(', ')}` : stem(l))

type Common = { lora: LoraItem; selected: boolean; tabbable: boolean; onSelect: () => void }

/** A LoRA on the model's stack: its strength as a line along the top and a number to drag; × takes it off. */
export function SavedRow({ lora, strength, selected, tabbable, onSelect, onStrength, onOff }:
  Common & { strength: number; onStrength: (v: number, done: boolean) => void; onOff: () => void }) {
  return (
    <div role="option" id={`lora-${lora.id}`} aria-selected={selected} aria-checked="true" tabIndex={tabbable ? 0 : -1}
      className={cx(s.row, s.saved, selected && s.sel)} title={hint(lora)} data-lora={lora.id} onClick={onSelect}>
      <span className={s.line} style={{ width: `${share(strength) * 100}%` }} aria-hidden="true" />
      <Cover lora={lora} size={96} className={s.cover} />
      <span className={s.name}><Name lora={lora} /></span>
      <DragNumber label={`${stem(lora)} strength`} value={strength} min={0} max={2} step={0.01} perPx={0.005} reset={lora.defaultStrength}
        onChange={v => onStrength(v, false)} onCommit={v => onStrength(v, true)} />
      <Button variant="ghost" small icon="x" className={s.off} aria-label={`Take ${stem(lora)} off`}
        onClick={e => { e.stopPropagation(); onOff() }} />
    </div>
  )
}

/** A LoRA in the model's folder that is not on: a click puts it on. A dot marks a file that is new. */
export function OtherRow({ lora, fresh, selected, tabbable, onSelect, onOn }: Common & { fresh: boolean; onOn: () => void }) {
  return (
    <div role="option" id={`lora-${lora.id}`} aria-selected={selected} aria-checked="false" tabIndex={tabbable ? 0 : -1}
      className={cx(s.row, selected && s.sel)} title={hint(lora)} data-lora={lora.id} data-new={fresh ? '' : undefined}
      onClick={onSelect} onDoubleClick={onOn}>
      <span className={s.coverWrap}><Cover lora={lora} size={96} className={s.cover} />{fresh && <i className={s.dot} aria-label="New file" />}</span>
      <span className={cx(s.name, s.nameOff)}><Name lora={lora} /></span>
      <Button variant="ghost" small icon="plus" className={s.on} aria-label={`Put ${stem(lora)} on`}
        onClick={e => { e.stopPropagation(); onOn() }} />
    </div>
  )
}
