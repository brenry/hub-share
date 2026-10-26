import { PromptBox } from '../compose/PromptBox'
import { Queue } from './Queue'
import { SeedLine } from './Seed'
import s from './Run.module.css'

/** Under the page: the prompt box, then one line level with the bar on the right — the job line while one runs,
 *  else the seeds the last render used (`Seed.tsx`). */
export function Dock() {
  return (
    <section className={s.dock} aria-label="Prompt" data-region="dock">
      <PromptBox />
      <div className={s.status} data-region="status">
        <Queue fallback={<SeedLine />} />
      </div>
    </section>
  )
}
