import { useStore } from '../../../lib/store'
import { cx } from '../../../ui/cx'
import { picker, type Character } from './complete'
import s from './Compose.module.css'

/** The characters a Tab found, as tiles over the prompt box, in name order: each its picture and its name, the lit
 *  one ringed in cyan. Tab moves along them, Enter or a click puts one in, Escape closes them (`PromptBox.tsx`). */
export function Picker({ onPick }: { onPick: (c: Character) => void }) {
  const open = useStore(picker, p => p)
  if (!open) return null
  return (
    <div className={s.picker} role="listbox" aria-label="Characters" data-region="character-picker">
      {open.pick.matches.map((c, i) => (
        <button key={c.name} type="button" role="option" aria-selected={i === open.i} title={c.name} tabIndex={-1}
          className={cx(s.tile, i === open.i && s.tileOn)}
          onMouseDown={e => e.preventDefault()} onClick={() => onPick(c)}>
          <img src={c.thumb} alt="" draggable={false} />
          <span>{c.name}</span>
        </button>
      ))}
    </div>
  )
}
