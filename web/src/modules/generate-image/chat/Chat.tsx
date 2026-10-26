import { useEffect, useLayoutEffect, useRef } from 'react'
import { useStore } from '../../../lib/store'
import { Scroll } from '../../../ui/Scroll'
import { cx } from '../../../ui/cx'
import type { Msg } from '../../../lib/protocol'
import { chat, newChat } from './assistant'
import s from './Chat.module.css'

/** Within this distance of the bottom, the chat follows new messages. */
const FOLLOW_PX = 48

/** The assistant's replies in the right column, newest at the bottom, each on its own card; the typed words stay in the
 *  prompt box and are not repeated here. What it does with the tools shows on the page (the draft), on the bar and in
 *  Media. The Hub's own line (a job's end) is a card as a reply is. A turn with no reply shows one error line; while a
 *  reply is awaited, the dots. The first row holds the
 *  model's name and New chat, on the same margin as the cards. */
export function Chat() {
  const { busy, messages, model } = useStore(chat, v => v)
  const box = useRef<HTMLDivElement>(null)
  const follow = useRef(true)
  const toEnd = () => { const el = box.current; if (el && follow.current) el.scrollTop = el.scrollHeight }
  useLayoutEffect(() => {
    if (messages.at(-1)?.role === 'user') follow.current = true
    toEnd()
  }, [messages, busy])
  useEffect(() => {
    const ro = new ResizeObserver(toEnd)
    if (box.current) ro.observe(box.current)
    return () => ro.disconnect()
  }, [])
  const empty = messages.length === 0

  return (
    <div className={s.chat} data-region="chat">
      <div className={s.head} data-region="chat-head">
        <span className="ell">{model}</span>
        {!empty && <button type="button" className={s.link} onClick={newChat}>New chat</button>}
      </div>
      <Scroll name="chat" ref={box} className={s.log} aria-label="Assistant" aria-live="polite"
        onScroll={e => { const el = e.currentTarget; follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < FOLLOW_PX }}>
        {empty ? null : (
          <div className={s.msgs}>
            {messages.map(line)}
            {busy && <span className={s.wait}><span className={s.dots} aria-hidden="true"><i /><i /><i /></span><span>Waiting for Open WebUI…</span></span>}
          </div>
        )}
      </Scroll>
    </div>
  )
}

const secs = (n: number) => `${n.toFixed(1)} s`

/** One line: a reply with its seconds under it, the Hub's line as a reply's card without seconds, or an error line;
 *  `user` messages and any other role are not shown. */
function line(m: Msg) {
  if (m.role === 'hub') return <div key={m.id} className={s.reply}><p>{m.text}</p></div>
  if (m.role === 'assistant') return <div key={m.id} className={s.reply}><p>{m.text}</p>{m.seconds != null && <span className={cx('num', s.secs)}>{secs(m.seconds)}</span>}</div>
  if (m.role === 'error') return <p key={m.id} className={s.error} role="alert">{m.text}</p>
  return null
}
