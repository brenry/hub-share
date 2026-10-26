import type { ToolProps } from '../../lib/module'
import { useStore } from '../../lib/store'
import { Field } from '../../ui/Field'
import { Live } from '../../ui/Live'
import { Scroll } from '../../ui/Scroll'
import { Segmented } from '../../ui/Segmented'
import { Select } from '../../ui/Select'
import { Stepper } from '../../ui/Stepper'
import { cx } from '../../ui/cx'
import { ROWS, SEAT, SIDES, itemThumb, type Draft, type Role, type Side, type Summary } from './api'
import { Bits } from './Bits'
import { Chips } from './Chips'
import { CostumeBoxes, CostumeSheet, PromptBox } from './Costume'
import { costume, costumeForm, variant } from './costume'
import { choose, edit, form, list, open, pick, problem, sit, useCasting } from './load'
import { Sheet } from './Sheet'
import { isCast, type Form } from './form'
import s from './Casting.module.css'

/** The role a character's approved record holds, or none. */
const roleOf = (d: Draft): Role | null => (isCast(d) ? ((d.record?.role as Role | undefined) ?? d.role ?? 'cast') : null)

/** Every character in Characters, its picture and name; `cast` or `audience` on one with an approved sheet. */
function People({ all, current }: { all: readonly Summary[] | null; current: string | null }) {
  return (
    <Scroll name="casting-list" className={s.list} data-region="casting-list" role="listbox" aria-label="Characters">
      {all?.length === 0 ? <div className={s.empty}>No characters</div> : null}
      {(all ?? []).map(c => (
        <button key={c.name} type="button" role="option" aria-selected={c.name === current} data-character={c.name}
          className={cx(s.person, c.name === current && s.on)} onClick={() => choose(c.name)}>
          <img src={itemThumb(c.picture, 96)} alt="" draggable={false} />
          <span className="ell">{c.name}</span>
          {c.cast ? <span className={s.cast} data-cast={c.role ?? 'cast'}>{c.role ?? 'cast'}</span> : null}
        </button>
      ))}
    </Scroll>
  )
}

const SIDE_OPTIONS = SIDES.map(v => ({ value: v, label: v[0]!.toUpperCase() + v.slice(1) }))

/** The character's facts, then Cast | Audience and, for Audience, the seat: Side and Row. */
function Facts({ f }: { f: Form }) {
  const seat = f.seat ?? SEAT
  return (
    <div className={s.facts} data-region="casting-facts">
      <span className={s.lab}>Description</span>
      <Field label="Description" value={f.facts.build} onChange={build => edit(x => ({ ...x, facts: { ...x.facts, build } }))} />
      <PromptBox />
      <span className={s.lab}>Role</span>
      <Segmented<Role> label="Role" value={f.role ?? 'cast'} onChange={pick}
        options={[{ value: 'cast', label: 'Cast' }, { value: 'audience', label: 'Audience' }]} />
      {f.role === 'audience' ? <>
        <span className={s.lab}>Side</span>
        <Select label="Side" value={seat.side} options={SIDE_OPTIONS} onChange={side => void sit({ ...seat, side: side as Side })} />
        <span className={s.lab}>Row</span>
        <Stepper label="Row" value={seat.row} min={1} max={ROWS} onChange={row => void sit({ ...seat, row })} />
      </> : null}
    </div>
  )
}

/** The Casting tab: the characters at the left; the open one at the right, its costumes'
 *  chips over its nine boxes with their lines and its facts (or a costume's boxes and words), then the sheet with
 *  its presses; the bar under it. */
export default function Casting({ visible }: ToolProps) {
  useCasting(visible)
  const all = useStore(list, x => x)
  const draft = useStore(open, x => x)
  const f = useStore(form, x => x)
  const pressed = useStore(problem, x => x)
  const v = useStore(variant, x => x)
  const c = useStore(costume, x => x)
  const cf = useStore(costumeForm, x => x)
  const look = v !== null && c && cf ? c : null
  const shown = look ?? draft
  const line = pressed ?? (shown && shown.state !== 'failed' ? shown.problem ?? null : null)
  const picture = all?.find(x => x.name === draft?.name)?.picture ?? null
  const role = draft ? roleOf(draft) : null
  return (
    <div className={s.tab} data-region="casting">
      <div className={s.main}>
        <People all={all} current={draft?.name ?? null} />
        {draft && f ? <>
          <Scroll name="casting-boxes" className={s.left}>
            <h2 className={s.who}>{draft.name}{role ? <span className={s.cast}>{role}</span> : null}</h2>
            {role === 'cast' ? <Chips name={draft.name} chips={draft.costumes ?? []} open={look ? v : null} /> : null}
            {look && cf ? <CostumeBoxes costume={look} form={cf} /> : <>
              <Bits headshot={draft.headshot.id ?? picture} form={f} files={draft.files} />
              <Facts f={f} />
            </>}
          </Scroll>
          <Scroll name="casting-sheet" className={s.right}>
            {look ? <CostumeSheet costume={look} /> : <Sheet draft={draft} />}
            {line ? <div className={s.problem} role="status" data-region="casting-problem">{line}</div> : null}
          </Scroll>
        </> : <div className={s.none}>{line ? <span className={s.problem} role="status" data-region="casting-problem">{line}</span> : null}</div>}
      </div>
      <footer className={s.bar} data-region="casting-bar">
        <span className={cx(s.grow, 'ell')}>{draft ? (look ? `${draft.name} · ${look.variant}` : draft.name) : 'Casting'}</span>
        <Live className={s.liveFlat} />
      </footer>
    </div>
  )
}
