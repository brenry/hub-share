import { toast } from '../../lib/toast'
import { api, isProblem, pictureThumb, type Context as ContextDef, type EditOp, type Member, type SetDef } from './api'
import { reload } from './load'
import s from './Scripts.module.css'

function send(name: string | null, op: EditOp) {
  if (!name) return
  void api.edit(name, op).then(r => {
    if (isProblem(r)) toast(r.problem)
    return reload()
  })
}

/** One labelled field of a card, always shown, typed in: what it holds is what render sends. Saved on leaving
 *  it (Enter leaves a one-line field); emptied, it is taken off. */
function Field({ label, text, rows = 1, save }: { label: string; text: string; rows?: number; save: (v: string) => void }) {
  const done = (v: string) => { if (v !== text) save(v) }
  return (
    <label className={s.field}>
      <span className={s.label}>{label}</span>{' '}
      {rows > 1
        ? <textarea key={text} defaultValue={text} rows={rows} data-field={label} onBlur={e => done(e.currentTarget.value)} />
        : <input key={text} defaultValue={text} data-field={label} onBlur={e => done(e.currentTarget.value)}
            onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur() }} />}
    </label>
  )
}

/** A cast member's card: its picture, name, tag and fields; with no picture in Characters, `No picture in Characters`
 *  where the picture would be. */
function MemberCard({ member, picture, missing, name, tag }: { member: Member; picture: string | undefined; missing: boolean; name: string | null; tag?: string }) {
  const save = (field: 'look' | 'costume' | 'ignore' | 'home') => (value: string) =>
    send(name, { op: 'member', member: member.name, field, value })
  return (
    <div className={s.card} data-card={member.name}>
      <div className={s.who}>
        {picture ? <img className={s.picture} src={pictureThumb(picture)} alt={member.name} /> : null}
        {missing ? <div className={s.memberProblem} data-region="member-problem">No picture in Characters</div> : null}
        <div className={s.cardName}>{member.name}</div>
        {tag ? <div className={s.label} data-tag={tag}>{tag}</div> : null}
      </div>
      <Field label="Look" text={member.look ?? ''} save={save('look')} />
      <Field label="Costume" text={member.costume ?? ''} save={save('costume')} />
      <Field label="Ignore" text={member.ignore ?? ''} save={save('ignore')} />
      <Field label="Home" text={member.home === undefined ? '' : String(member.home)} save={save('home')} />
    </div>
  )
}

/** Each member with a home, by name at that % across the set, a tick under it. */
function Places({ cast }: { cast: Member[] }) {
  const placed = cast.filter(m => m.home !== undefined)
  if (placed.length === 0) return null
  return (
    <div className={s.field}>
      <span className={s.label}>Places</span>
      <div className={s.strip} data-region="places">
        {placed.map(m => (
          <div key={m.name} className={s.place} style={{ left: `${m.home}%` }} data-place={m.name}>
            <span>{m.name}</span><i className={s.placeTick} />
          </div>
        ))}
      </div>
    </div>
  )
}

function SetCard({ set, cast, name }: { set: SetDef; cast: Member[]; name: string | null }) {
  const save = (field: 'name' | 'description' | 'elements' | 'props') => (value: string) => send(name, { op: 'set', field, value })
  const props = (set.props ?? []).map(p => `${p.name}${p.description ? `: ${p.description}` : ''}`).join('\n')
  return (
    <div className={`${s.card} ${s.setCard}`} data-card={set.name}>
      <Field label="Set" text={set.name ?? ''} save={save('name')} />
      <Field label="Description" text={set.description ?? ''} rows={2} save={save('description')} />
      <Field label="Elements" text={(set.elements ?? []).join(', ')} save={save('elements')} />
      <Field label="Props" text={props} rows={3} save={save('props')} />
      <Places cast={cast} />
    </div>
  )
}

/** The scene context above the timeline: the style line, a card per cast member, then the set's. Every
 *  field is typed in (`cards.py`) or written by the Director; render sends what each holds. */
export function Context({ context, pictures, unpictured, name }: { context: ContextDef; pictures: Record<string, string>; unpictured: string[]; name: string | null }) {
  return (
    <>
      <div className={s.context} data-scroll="script-set" data-region="set-panel">
        <div className={s.style} data-region="style">
          <Field label="Style" text={context.style ?? ''} save={v => send(name, { op: 'set', field: 'style', value: v })} />
        </div>
        <SetCard set={context.set ?? { name: '' }} cast={context.cast} name={name} />
      </div>
      <div className={s.context} data-scroll="script-context" data-region="context">
        <div className={s.cards}>
          {context.cast.map((m, i) => <MemberCard key={m.name} member={m} picture={pictures[m.name]} missing={unpictured.includes(m.name)} name={name}
            tag={`<Subject ${i + 1}> · <Picture ${i + 1}>`} />)}
        </div>
      </div>
    </>
  )
}
