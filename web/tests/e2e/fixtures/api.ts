// page.route fixtures for every HTTP route the UI calls.
import type { Page, Route } from '@playwright/test'
import type { ChatView } from '../../../src/lib/protocol'
import type { LoraItem, Model } from '../../../src/modules/generate-image/types'
import { continueRoute } from './continue'
import { MODELS, clipItems, makeLoras, mediaItems } from './data'
import { fakeChars, mediaRoute, sampleRoute, type FakeChars, type FakeDrive, fakeDrive } from './media'
import { png, tint } from './png'
import { WAV } from './wav'
import { WEBM } from './webm'
import { modelFiles, modelFilesRoute } from './modelfiles'
import type { Listing } from '../../../src/shell/settings/ModelFiles'

export type ApiState = {
  draft: unknown
  loras: LoraItem[]
  media: ReturnType<typeof mediaItems>
  /** The clips root (`GET /api/media?root=clips`). */
  clips: ReturnType<typeof clipItems>
  /** The sounds root (`GET /api/media?root=sounds`). */
  sounds: ReturnType<typeof clipItems>
  /** Models the hub lists besides MODELS (the speech model, for its own spec). */
  extraModels: Model[]
  drive: FakeDrive
  chars: FakeChars
  calls: { method: string; path: string; body: unknown }[]
  uploads: number
  settings: typeof SETTINGS
  chat: ChatView
  owuiModels: { ok: boolean; text: string; models: string[] }
  weights: Weights
  /** Settings -> Model files (`GET/PUT /api/generate-image/model-files`). */
  modelFiles: Listing
  owuiServers: { ok: boolean; text: string; servers: { id: string; name: string }[] }
  owuiTools: string
  /** Settings -> Assistant -> Replies kept (the hub's `keep`, 1 to 20). */
  owuiKeep: number
  /** Settings -> Assistant -> Context length (the hub's `context`: 0, or 2048 to 131072). */
  owuiContext: number
  mcpKey: string
  /** Settings' default models (`GET/PUT /api/generate-image/defaults`). */
  defaults: { text: string | null; refs: string | null; video: string | null }
  /** The fake hub's bus, for a route whose server side tells the windows (set by `open`). */
  broadcast: ((t: string, d: unknown) => void) | null
}

export function apiState(over: Partial<ApiState> = {}): ApiState {
  return { draft: null, loras: makeLoras(24), media: mediaItems(60), clips: clipItems(5), sounds: [], extraModels: [], drive: fakeDrive(), chars: fakeChars(), calls: [], uploads: 0, settings: structuredClone(SETTINGS),
    chat: EMPTY_CHAT, owuiModels: { ok: true, text: 'Connected · 3 models', models: ['qwen3.5:9b', 'gemma3:12b', 'llama3.2:3b'] },
    weights: weights(), modelFiles: modelFiles(),
    owuiServers: { ok: true, text: '2 tool servers', servers: [{ id: 'hub', name: 'Hub' }, { id: 'hp', name: 'HocusPocus' }] }, owuiTools: '', owuiKeep: 6, owuiContext: 8192, mcpKey: 'hub_mcp_Qm7tX2c9VbL4nR8wKp3s', defaults: { text: null, refs: null, video: null }, broadcast: null, ...over }
}

type Profile = 'engine' | 'same' | number
const PROFILES = [{ value: 'engine' as Profile, label: "Engine's own" }, { value: 1, label: '1 · High RAM / high VRAM' },
  { value: 3.5, label: '3.5 · Very low RAM / high VRAM' }, { value: 4, label: '4 · Low RAM / low VRAM' }, { value: 5, label: '5 · Very low RAM / low VRAM, fail safe' }]
export const SETTINGS = {
  drive: '/srv/models/ComfyUI', characters: '',
  engine: { root: '/srv/engine/app', python: '/srv/engine/app/env/bin/python', ok: true,
    profile: 'engine' as Profile, profiles: PROFILES,
    profile_video: 'same' as Profile, video_profiles: [{ value: 'same' as Profile, label: 'Same as above' }, ...PROFILES] },
  video_tiers: { names: ['480p', '540p', '720p', '1080p'], offered: ['480p', '540p'] }, video_tiers_max: 3,
  image_model_folders: ['/srv/models/ComfyUI/models/diffusion_models'], lora_folders: ['/srv/engine/app/loras'],
  gpus: [{ name: 'GPU 1', total_mb: 32768 }], vram: { idle_unload: true, idle_minutes: 10 },
}
const CARDS = [
  { module: 'generate-image', title: 'Generate Image', order: 880, summary: 'Random seed', status: 'ok' },
  { module: 'network', title: 'Network', order: 900, summary: 'Port 42010 · 1 device connected', status: 'ok' },
  { module: 'assistant', title: 'Assistant', order: 920, summary: 'On · 1 client', status: 'attention' },
]
const NETWORK = {
  server: { bind: ['192.168.0.10', '127.0.0.1'], port: 42010 },
  devices: [
    { id: 'd_desk', name: 'Desk', addrs: ['192.168.0.11'], connected: 3, you: true },
    { id: 'd_local', name: 'This server', addrs: ['127.0.0.1'], connected: 0, you: false },
  ],
  pairing: [],
}
const ASSISTANT = {
  on: true, endpoints: ['http://192.168.0.10:42010/mcp'], openwebui: { url: 'http://127.0.0.1:3000', model: 'qwen3.5:9b', key: true, tools: '', keep: 6, context: 8192 },
  clients: [{ addr: '127.0.0.1', name: 'Open WebUI', at: Date.now() / 1000 - 40, status: 'OK' }], port: 42010,
}

const EMPTY_CHAT: ChatView = { busy: false, messages: [], model: null }
/** A conversation of `n` turns (user, reply), oldest first. */
export function chatView(n: number, busy = false): ChatView {
  const messages = Array.from({ length: n }, (_, i) => [
    { id: `u${i}`, role: 'user' as const, text: `A grey cat asleep under an apple tree, take ${i + 1}. Make it rain.`, at: 1791561600 + i * 60, seconds: null },
    { id: `a${i}`, role: 'assistant' as const, text: 'A grey cat curled under an apple tree, rain on the leaves, late light.', at: 1791561620 + i * 60, seconds: 4.2 },
  ]).flat()
  return { busy, messages, model: 'qwen3.5:9b' }
}

/** A conversation whose last turn failed: the server shows it as an "error" line, never sent on. */
export function chatWithError(text = 'Open WebUI did not answer: connection refused'): ChatView {
  const v = chatView(1)
  return { ...v, messages: [...v.messages, { id: 'e0', role: 'error' as const, text, at: 1791561700, seconds: null }] }
}

/** `n` turns in tool-server mode, as the hub sends them: every other turn the assistant edited the box or made a
 *  picture and said nothing (so the turn adds nothing: two of your messages in a row), the others a short reply. */
export function chatWithTools(n: number): ChatView {
  const messages = Array.from({ length: n }, (_, i) => [
    { id: `u${i}`, role: 'user' as const, text: `Make a cat picture, take ${i + 1}`, at: 1791561600 + i * 60, seconds: null },
    ...(i % 2 ? [] : [{ id: `a${i}`, role: 'assistant' as const, text: 'Queued two images of the cat.', at: 1791561620 + i * 60, seconds: 4.2 }]),
  ]).flat()
  return { busy: false, messages, model: 'qwen3.5:9b' }
}

/** The Image models panel: the engine's own file, a registered newcomer, two files nothing matches. */
type Weight = {
  path: string; name: string; folder: string | null; size_mb: number; status: 'known' | 'pointer' | 'unknown'
  model: string | null; base: string | null; suggested: string | null; candidates: string[]; chosen: string | null
}
export type Weights = { bases: { id: string; name: string }[]; files: Weight[] }
const FOLDER = '/srv/models/ComfyUI/models/diffusion_models'
const weight = (name: string, size_mb: number, over: Partial<Weight> = {}): Weight => ({
  path: `${FOLDER}/${name}`, name, folder: FOLDER, size_mb, status: 'unknown', model: null, base: null, suggested: null, candidates: [], chosen: null, ...over,
})
function weights(): Weights {
  return {
    bases: [{ id: 'flux2_klein_9b', name: 'Flux 2 Klein 9B' }, { id: 'krea2_turbo', name: 'Krea 2 Turbo' }, { id: 'krea2_raw', name: 'Krea 2 RAW' }],
    files: [
      weight('flux-2-klein-9b.safetensors', 18_200, { status: 'known', model: 'flux2_klein_9b' }),
      weight('krea2-raw-re0.75-fp8.safetensors', 12_100, { status: 'pointer', model: 'auto_krea2_raw_re0_75_fp8', base: 'krea2_turbo', suggested: 'krea2_turbo', candidates: ['krea2_turbo', 'krea2_raw'] }),
      weight('umt5_xxl_fp8.safetensors', 9_300),
      weight('ae.safetensors', 320),
    ],
  }
}

/** The sent fields merge into the draft; as the hub, a model sent is kept as the last of its kind (`lastModel`, which
 *  a window never writes). */
function putDraft(draft: unknown, body: unknown): unknown {
  const { lastModel: _, ...sent } = body as { model?: string; lastModel?: unknown }
  const d: Record<string, unknown> = { ...(draft ?? {}) as object, ...sent }
  const model = sent.model
  const kind = MODELS.find(x => x.id === model)?.kind
  return kind ? { ...d, lastModel: { image: '', video: '', ...(d.lastModel as object), [kind]: model } } : d
}

const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

export async function mockApi(page: Page, st: ApiState): Promise<void> {
  await page.route(/\/(files|thumbs)\//, route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (/^\/files\/clips\//.test(path)) return route.fulfill({ contentType: 'video/webm', body: WEBM })
    if (/^\/files\/sounds\//.test(path)) return route.fulfill({ contentType: 'audio/wav', body: WAV })
    const [a, b] = tint(path.replace(/\/\d+$/, ''))
    const big = path.startsWith('/files/')
    // A picture is 1680 × 944 unless its url says `?w=…&h=…` (a spec that needs a shape).
    const w = Number(url.searchParams.get('w')) || 1680, h = Number(url.searchParams.get('h')) || 944
    return route.fulfill({ contentType: 'image/png', body: big ? png(w, h, a, b) : png(264, 148, a, b) })
  })
  await page.route(/\/api\//, async route => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname
    const m = req.method()
    const body = req.postDataBuffer() && req.headers()['content-type']?.includes('json') ? req.postDataJSON() : null
    st.calls.push({ method: m, path: p + url.search, body })
    if (p === '/api/loras/thumb') { const [a, b] = tint(url.searchParams.get('id') ?? ''); return route.fulfill({ contentType: 'image/png', body: png(96, 96, a, b) }) }
    if (p === '/api/generate-image/models') return json(route, [...MODELS, ...st.extraModels])
    if (p === '/api/generate-image/weights' || p === '/api/generate-image/weights/rescan') return json(route, st.weights)
    if (p === '/api/generate-image/weights/base') {
      const { path, base } = body as { path: string; base: string }
      const f = st.weights.files.find(x => x.path === path)
      if (!f) return json(route, { code: 'invalid', field: 'path', text: 'That file is not in the model folders' }, 400)
      Object.assign(f, base === '' ? { status: 'unknown', model: null, base: null, chosen: '' }
        : { status: 'pointer', model: `auto_${f.name.replace(/\W+/g, '_')}`, base, chosen: base })
      return json(route, st.weights)
    }
    if (p === '/api/generate-image/model-files') return modelFilesRoute(route, st, m, body)
    if (p === '/api/generate-image/characters') return json(route, { items: st.chars.items.map(c => ({ name: c.name, id: c.id, w: c.w, h: c.h, thumb: c.thumb })) })
    if (p === '/api/generate-image/seed/random') return json(route, { ok: true })
    if (p === '/api/generate-image/continue') return continueRoute(route, st, body)
    if (p === '/api/generate-image/draft') { if (m === 'PUT') st.draft = putDraft(st.draft, body); return json(route, st.draft) }
    if (p === '/api/generate-image/defaults') { if (m === 'PUT') st.defaults = body as ApiState['defaults']; return json(route, st.defaults) }
    if (p === '/api/loras') return json(route, url.searchParams.get('model') === 'flux2_klein_9b' ? st.loras : [])
    if (p.startsWith('/api/loras/')) return json(route, {})
    if (p === '/api/upload') return json(route, { id: `out/2026-10-09/12000${++st.uploads}-000.png` })
    if (p === '/api/media/check') return json(route, { placed: (body as { items: string[] }).items.map(item => ({ item, id: item })) })
    if (p === '/api/characters/sample') return sampleRoute(route, st, url)
    if (p.startsWith('/api/media')) return mediaRoute(route, st, m, p, url, body)
    if (p === '/api/settings/restart') return json(route, { restarting: true })
    if (p === '/api/settings') return m === 'PATCH' ? patchSettings(route, st, body as Patch) : json(route, st.settings)
    if (p === '/api/cards') return json(route, CARDS)
    if (p === '/api/network' || p.startsWith('/api/network/')) return json(route, p === '/api/network/pair' ? { link: 'http://192.168.0.10:42010/pair#c=Qm7tX2c9VbL4nR8w', expires: 1791562200 } : NETWORK)
    const assistant = () => ({ ...ASSISTANT, openwebui: { ...ASSISTANT.openwebui, tools: st.owuiTools, keep: st.owuiKeep, context: st.owuiContext } })
    if (p === '/api/assistant') return json(route, assistant())
    if (p === '/api/assistant/mcp-key' && m === 'POST') { st.mcpKey = 'hub_mcp_Zr8vN1y5WqT6hJ2dLx9c'; return json(route, { mcp_key: st.mcpKey }) }
    if (p === '/api/assistant/openwebui/models') return json(route, st.owuiModels)
    if (p === '/api/assistant/openwebui/tool-servers') return json(route, st.owuiServers)
    if (p === '/api/assistant/openwebui') {
      const tools = (body as { tools?: string } | null)?.tools
      if (m === 'PATCH' && tools !== undefined) st.owuiTools = tools
      const keep = (body as { keep?: unknown } | null)?.keep
      if (m === 'PATCH' && keep !== undefined && !(Number.isInteger(keep) && (keep as number) >= 1 && (keep as number) <= 20))
        return json(route, { code: 'invalid', field: 'keep', text: 'Replies kept must be a whole number from 1 to 20' }, 400)
      if (m === 'PATCH' && keep !== undefined) st.owuiKeep = keep as number
      const ctx = (body as { context?: unknown } | null)?.context
      if (m === 'PATCH' && ctx !== undefined && !(ctx === 0 || (Number.isInteger(ctx) && (ctx as number) >= 2048 && (ctx as number) <= 131072)))
        return json(route, { code: 'invalid', field: 'context', text: 'Context length must be 0 or a whole number from 2048 to 131072' }, 400)
      if (m === 'PATCH' && ctx !== undefined) st.owuiContext = ctx as number
      const url = (body as { url?: string } | null)?.url
      if (m === 'PATCH' && url !== undefined && !/^http:\/\/(127\.0\.0\.1|localhost|\[::1\])(:|\/|$)/.test(url))
        return json(route, { code: 'invalid', field: 'url', text: 'Open WebUI must be on this computer: use 127.0.0.1' }, 400)
      return json(route, assistant())
    }
    if (p === '/api/assistant/port') return json(route, { port: (body as { port: number }).port, endpoints: [`http://192.168.0.10:${(body as { port: number }).port}/mcp`] })
    if (p === '/api/assistant/chat' && m === 'POST') return st.chat.busy ? json(route, { text: 'The assistant is busy' }, 409) : json(route, { turn: 'u_new' }, 202)
    if (p === '/api/assistant/chat') {
      // New chat: the hub also empties the Generate session's prompt box and the assistant's draft (`chat.cleared`)
      if (m === 'DELETE') { st.chat = EMPTY_CHAT; st.draft = { ...((st.draft ?? {}) as object), prompt: '', draft: '' }; st.broadcast?.('generate-image.draft', {}) }
      return json(route, st.chat)
    }
    if (p === '/api/pair') { const code = (body as { code: string }).code; return code === 'good' ? json(route, { device: 'd_new' }) : json(route, { text: 'Bad code' }, 403) }
    if (p.startsWith('/api/sequence/') || p.startsWith('/api/director/') || p.startsWith('/api/casting/') || p === '/api/sounds/upload') return route.fallback()
    return json(route, { text: 'Not found' }, 404)
  })
}

type Patch = { vram?: typeof SETTINGS.vram; paths?: { drive?: string; characters?: string }
  engine?: { root?: string; python?: string; model_folders?: string[]; profile?: Profile; profile_video?: Profile }
  modules?: { loras?: { folders: string[] }; 'generate-image'?: { video_tiers: string[] } } }

/** Like the controller: a path containing "missing" is refused with one line; otherwise the edit applies. */
function patchSettings(route: Route, st: ApiState, b: Patch) {
  const values: [string, string][] = [
    ...Object.entries(b.paths ?? {}).map(([k, v]): [string, string] => [`paths.${k}`, v]),
    ...(['root', 'python'] as const).filter(k => b.engine?.[k] !== undefined).map((k): [string, string] => [`engine.${k}`, b.engine![k]!]),
    ...(b.engine?.model_folders ?? []).map((v, i): [string, string] => [`engine.model_folders[${i}]`, v]),
    ...(b.modules?.loras?.folders ?? []).map((v, i): [string, string] => [`modules.loras.folders[${i}]`, v]),
  ]
  const bad = values.find(([, v]) => v.includes('missing'))
  if (bad) return json(route, { code: 'invalid', field: bad[0], text: bad[0] === 'engine.python' ? 'Not a Python' : 'Folder not found' }, 400)
  const s = st.settings
  st.settings = {
    ...s, vram: b.vram ?? s.vram, drive: b.paths?.drive ?? s.drive, characters: b.paths?.characters ?? s.characters,
    engine: { ...s.engine, root: b.engine?.root ?? s.engine.root, python: b.engine?.python ?? s.engine.python, profile: b.engine?.profile ?? s.engine.profile,
      profile_video: b.engine?.profile_video ?? s.engine.profile_video },
    video_tiers: { ...s.video_tiers, offered: b.modules?.['generate-image']?.video_tiers ?? s.video_tiers.offered },
    image_model_folders: b.engine?.model_folders ?? s.image_model_folders, lora_folders: b.modules?.loras?.folders ?? s.lora_folders,
  }
  return json(route, st.settings)
}
