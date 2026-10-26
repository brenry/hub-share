import { useEffect, useRef } from 'react'
import type { AudioRow } from './api'
import { secs } from './timeline'
import s from './Scripts.module.css'

type Props = { rows: AudioRow[]; selected: string | null; onSelect: (id: string) => void }

/** The take a row would make, in words; `rendering` and `failed · <why>`; a file
 *  only when the take has one. */
export function takeText(t: AudioRow['take']): string {
  const f = t.file ?? ''
  if (t.state === 'none') return `none → ${f}`
  if (t.state === 'stale') return `stale: ${f}`
  if (t.state === 'flagged') return `flagged ${f}${t.why ? ` · ${t.why}` : ''}`
  if (t.state === 'rendering') return 'rendering'
  if (t.state === 'failed') return `failed${t.why ? ` · ${t.why}` : ''}`
  return `ok ${f}`
}

/** A row's first line: its shot, times as the bar writes them, id, who; a line's sample and cap, a cue's kind and length. */
export function headText(r: AudioRow): string {
  const head = `${r.shot} · ${secs(r.start_ms)}–${secs(r.end_ms)} s · ${r.id} · ${r.who}`
  return r.kind === 'line'
    ? `${head} · ${r.sample ?? 'no voice sample'} · cap ${r.seconds} s`
    : `${head} · ${r.who} sound · ${r.seconds} s`
}

/** The audio script of a locked script: one row per line and cue in time order, beside the timeline. A
 *  click selects the row's box on the timeline; the selected box's row is pressed and scrolled into view. */
export function Audio({ rows, selected, onSelect }: Props) {
  const list = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (selected === null) return
    const el = list.current?.querySelector(`[data-audio="${CSS.escape(selected)}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  }, [selected])
  return (
    <section className={s.audio} data-region="audio-script">
      <h2 className={s.audioHead}>Audio script</h2>
      <div ref={list} className={s.audioRows} data-scroll="audio-script">
        {rows.map(r => {
          const on = r.id === selected
          return (
            <button key={r.id} type="button" className={`${s.audioRow} ${on ? s.on : ''}`} aria-pressed={on}
              data-audio={r.id} data-take={r.take.state} onClick={() => onSelect(r.id)}>
              <span className={s.audioLine}>{headText(r)}</span>
              {r.text !== null ? <pre className={s.audioText}>{r.text}</pre>
                : <span className={s.audioProblem} data-region="audio-problem">{r.problem}</span>}
              <span className={s.audioTake}>{`${takeText(r.take)} #${r.hash}`}</span>
            </button>
          )
        })}
      </div>
    </section>
  )
}
