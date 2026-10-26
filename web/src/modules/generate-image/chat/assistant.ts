// The chat, mirrored from the hub: one GET per (re)connect, then `assistant.chat` events. The hub carries each
// message to Open WebUI and shows its reply; nothing else is attached. What the assistant does with the tools shows
// where it lands (its draft beside the chat, the bar, the prompt box after a push), never here.
import { useEffect } from 'react'
import { errorText, getJSON, sendJSON } from '../../../lib/http'
import { connects } from '../../../lib/live'
import type { ChatView } from '../../../lib/protocol'
import { createStore, useStore } from '../../../lib/store'
import { useBusEvent } from '../../../lib/useBus'
import { clearWords, settled } from '../draft'
import { note } from '../inputs'

const CHAT = '/api/assistant/chat'
const EMPTY_CHAT: ChatView = { busy: false, messages: [], model: null }
export const chat = createStore<ChatView>(EMPTY_CHAT)

/** Keeps the chat in step with the hub. */
export function useAssistant(): void {
  const n = useStore(connects, v => v)
  useEffect(() => {
    if (n === 0) return
    getJSON<ChatView>(CHAT).then(chat.set, () => {})
  }, [n])
  useBusEvent('assistant.chat', d => chat.set(d as ChatView))
}

/** False when the hub refused; the reason shows in the bar's note line. */
export async function say(text: string): Promise<boolean> {
  try {
    await sendJSON<unknown>('POST', CHAT, { text })
    return true
  } catch (e) {
    note(errorText(e))
    return false
  }
}

/** New chat: the conversation goes, here and in Open WebUI, and the server empties the prompt box and the draft with
 *  it (every window hears `generate-image.draft`); this window shows them empty at once and drops any unsaved edit
 *  of them, and sends the DELETE only once a save already on its way has landed, so nothing of the old chat is
 *  written back after the clearing. */
export function newChat(): void {
  clearWords()
  settled().then(() => sendJSON<ChatView>('DELETE', CHAT)).then(chat.set, e => note(errorText(e)))
}
