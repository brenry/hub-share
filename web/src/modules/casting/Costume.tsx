import { useStore } from '../../lib/store'
import { Button } from '../../ui/Button'
import { Field } from '../../ui/Field'
import { cx } from '../../ui/cx'
import type { Costume } from './api'
import { BitBox, picSrc } from './Bits'
import { COSTUME_PICTURES, type CostumeForm } from './form'
import { Sheet } from './Sheet'
import { againCostume, approveCostume, armed, castCostume, dropCostume, dropCostumePicture, editCostume, removeCostume } from './costume'
import { edit, form as castForm, pressing } from './load'
import s from './Casting.module.css'

const FACES = ['Face', 'Three-quarter face']

/** The tab's one Prompt box: sent as typed after the fields with every Cast, a costume's too; held by the
 *  hub in memory only. */
export function PromptBox() {
  const text = useStore(castForm, f => f?.prompt ?? '')
  return <>
    <span className={s.lab}>Prompt</span>
    <textarea className={s.prompt} aria-label="Prompt" value={text} rows={4} spellCheck={false} data-region="casting-prompt"
      onChange={e => { const prompt = e.target.value; edit(f => ({ ...f, prompt })) }} />
  </>
}

/** A costume's boxes: 1-2 the character's approved face frames (fixed, no lines), 3-9 the costume pictures with their
 *  lines, then its words. */
export function CostumeBoxes({ costume, form }: { costume: Costume; form: CostumeForm }) {
  const files = costume.files
  return <>
    <div className={s.boxes} data-region="casting-boxes" data-costume={costume.variant}>
      {FACES.map((alt, k) => (
        <div key={alt} className={s.box} data-box={k + 1} data-filled data-face>
          <div className={s.pic}>
            {costume.face_thumbs[k] ? <img src={costume.face_thumbs[k]} alt={alt} draggable={false} /> : null}
            <span className={cx(s.badge, 'num')} aria-hidden="true">{k + 1}</span>
          </div>
        </div>
      ))}
      {Array.from({ length: COSTUME_PICTURES }, (_, i) => {
        const bit = form.pictures[i]
        return (
          <BitBox key={i} box={i + 3} bit={bit} src={bit ? picSrc(bit.id, files?.pictures, files?.picture_urls) : null}
            onDrop={items => void dropCostume(i, items)} onRemove={() => dropCostumePicture(i)}
            onLines={l => editCostume(f => ({ ...f, pictures: f.pictures.map((b, j) => (j === i ? { ...b, ...l } : b)) }))} />
        )
      })}
    </div>
    <div className={s.facts} data-region="casting-words">
      <span className={s.lab}>Costume</span>
      <Field label="Costume" value={form.words} onChange={words => editCostume(f => ({ ...f, words }))} />
      <PromptBox />
    </div>
  </>
}

/** A costume's sheet: the six views, orbit and presses, plus Remove (a second press confirms). */
export function CostumeSheet({ costume }: { costume: Costume }) {
  const busy = useStore(pressing, x => x)
  const sure = useStore(armed, x => x)
  const known = costume.state !== 'none' || !!costume.record
  return <>
    <Sheet draft={costume} acts={{ cast: castCostume, again: againCostume, approve: approveCostume }} />
    {known ? (
      <div className={s.presses}>
        <Button variant={sure ? 'danger' : 'default'} disabled={busy} onClick={() => void removeCostume()} data-region="casting-remove">
          {sure ? `Remove ${costume.variant}` : 'Remove'}
        </Button>
      </div>
    ) : null}
  </>
}
