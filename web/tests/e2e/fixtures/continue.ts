// POST /api/generate-image/continue as the hub answers it (stage 6 §4): the clip is checked and stays where it is
// (`clips/<day>/<time>.mp4`, flat), the session's box 1 holds it, the draft goes onto a model that continues (the
// draft's own when it does, else the first), and every window hears `generate-image.draft`.
import type { Route } from '@playwright/test'
import type { ApiState } from './api'
import { MODELS } from './data'

const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
const refuse = (route: Route, text: string) => json(route, { code: 'invalid', field: 'id', text }, 400)

export function continueRoute(route: Route, st: ApiState, body: unknown): Promise<void> {
  const id = String((body as { id?: unknown } | null)?.id ?? '')
  const clip = st.clips.find(c => c.id === id)
  if (!clip) return refuse(route, 'The clip to continue is gone')
  if (clip.w === null || clip.h === null || clip.seconds == null) return refuse(route, 'This clip is not an MP4 the hub can read')
  const d = (st.draft ?? {}) as { model?: string }
  const takers = MODELS.filter(m => m.video?.continues)
  const model = takers.find(m => m.id === d.model) ?? takers[0]
  if (!model) return refuse(route, 'No model here can continue a clip')
  st.draft = { ...d, model: model.id, references: [{ id: clip.id, w: clip.w, h: clip.h, kind: 'clip', seconds: clip.seconds }] }
  st.broadcast?.('generate-image.draft', {})
  return json(route, { id: clip.id, model: model.id, label: model.label })
}
