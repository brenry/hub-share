// The one live line per window.
import { createStore } from './store'
import type { BusError, Declaration, Envelope, GoingOff, Role, Welcome } from './protocol'

export type LinkState = 'connecting' | 'on' | 'cut' | 'off' | 'unpaired'
export type Link = { state: LinkState; since: number; nextTry: number | null; version: string }

export type Socketish = {
  readyState: number
  send: (data: string) => void
  close: () => void
  onopen: (() => void) | null
  onmessage: ((e: { data: unknown }) => void) | null
  onclose: ((e: { code: number }) => void) | null
  onerror: (() => void) | null
}

type Env = {
  open: (url: string) => Socketish
  url: () => string
  reload: () => void
  onWake: (fn: () => void) => void
  random: () => number
  now: () => number
}

type Listener = (d: unknown, env: Envelope) => void
type Pending = { resolve: (d: unknown) => void; reject: (e: BusError) => void }

const CUT_STEPS = [500, 1000, 2000, 4000, 8000]
const OFF_STEPS = [2000, 5000, 10000]
const SLOW = 30000
const LONG_CUT = 10 * 60 * 1000
const CONNECT_TIMEOUT = 10000
const RECEIPT_MAX = 20
const LOST: BusError = { code: 'unavailable', text: 'Connection lost' }

export function createBus(env: Env) {
  const link = createStore<Link>({ state: 'connecting', since: env.now(), nextTry: null, version: '' })
  const listeners = new Map<string, Set<Listener>>()
  const pending = new Map<string, Pending>()
  let ws: Socketish | null = null
  let role: Role = 'workspace'
  let label: string | undefined
  let screen = newScreenId()
  let boot: string | null = null
  let attempt = 0
  let cutSince = 0
  let mode: 'cut' | 'off' | 'slow' = 'cut'
  let goingOff: GoingOff['reason'] | null = null
  let silenceMs = 60000
  let retry: ReturnType<typeof setTimeout> | undefined
  let watchdog: ReturnType<typeof setTimeout> | undefined
  let seq = 0
  let lastFocus: string | null = null
  let lastSockets: Declaration | null = null
  const receipts: Envelope[] = []

  function newScreenId(): string {
    return 'scr_' + Math.floor(env.random() * 36 ** 8).toString(36).toUpperCase().padStart(8, '0')
  }

  function setState(state: LinkState, nextTry: number | null = null) {
    const cur = link.get()
    const since = cur.state === state ? cur.since : env.now()
    link.set({ ...cur, state, since, nextTry })
  }

  function raw(msg: Envelope): boolean {
    if (!ws || ws.readyState !== 1) return false
    ws.send(JSON.stringify(msg))
    return true
  }

  function emit(t: string, d: unknown, e: Envelope) {
    for (const fn of [...(listeners.get(t) ?? [])]) fn(d, e)
  }

  function arm(ms: number) {
    clearTimeout(watchdog)
    watchdog = setTimeout(() => {
      const dead = ws
      if (!dead) return
      dead.onclose = dead.onmessage = dead.onopen = dead.onerror = null
      dead.close()
      closed(1006)
    }, ms)
  }

  function connect() {
    clearTimeout(retry)
    if (ws) return
    const s = env.open(env.url())
    ws = s
    arm(CONNECT_TIMEOUT)
    s.onopen = () => {
      raw({ t: 'hello', id: 'h' + ++seq, d: { proto: 1, role, screen, label: label ?? null, subs: null } })
    }
    s.onmessage = e => {
      if (typeof e.data !== 'string') return
      let msg: Envelope
      try { msg = JSON.parse(e.data) as Envelope } catch { return }
      if (msg && typeof msg.t === 'string') handle(msg)
    }
    s.onclose = e => { if (ws === s) closed(e.code) }
    s.onerror = () => {}
  }

  function handle(msg: Envelope) {
    arm(silenceMs)
    if (msg.t === 'welcome') {
      const w = msg.d as Welcome
      if (boot !== null && w.boot !== boot) { env.reload(); return }
      boot = w.boot
      silenceMs = Math.max(5, w.limits?.silence_s ?? 60) * 1000
      arm(silenceMs)
      attempt = 0
      goingOff = null
      link.set({ state: 'on', since: env.now(), nextTry: null, version: w.version })
      if (lastFocus !== null) raw({ t: 'focus', d: { tool: lastFocus } })
      if (lastSockets) raw({ t: 'sockets', d: lastSockets })
      for (const r of receipts.splice(0)) raw(r)
      emit('welcome', w, msg)
      return
    }
    if (msg.t === 'going_off') { goingOff = (msg.d as GoingOff).reason; return }
    if (msg.t === 'beat') return
    if ((msg.t === 'reply' || msg.t === 'error') && msg.re && pending.has(msg.re)) {
      const p = pending.get(msg.re)!
      pending.delete(msg.re)
      if (msg.t === 'reply') p.resolve(msg.d)
      else p.reject(msg.d as BusError)
      return
    }
    emit(msg.t, msg.d, msg)
  }

  function closed(code: number) {
    ws = null
    clearTimeout(watchdog)
    for (const p of pending.values()) p.reject(LOST)
    pending.clear()
    if (code === 4003) { setState('unpaired'); return }
    if (code === 4009) screen = newScreenId()
    const prev = link.get().state
    let next: typeof mode = 'cut'
    if (code === 4000 || goingOff === 'shutdown') next = 'off'
    else if (code === 4013) next = 'slow'
    else if (prev === 'off' && code === 1006) next = 'off'
    if (prev === 'on' || next !== mode) attempt = 0
    if (next !== 'off' && prev !== 'cut') cutSince = env.now()
    mode = next
    goingOff = null
    schedule(code === 4009 ? 0 : delay())
  }

  function delay(): number {
    const n = attempt++
    if (mode === 'slow') return SLOW
    if (mode === 'off') return OFF_STEPS[n] ?? SLOW
    if (env.now() - cutSince >= LONG_CUT) return SLOW
    const base = CUT_STEPS[Math.min(n, CUT_STEPS.length - 1)]!
    return Math.round(base * (0.8 + env.random() * 0.4))
  }

  function schedule(ms: number) {
    clearTimeout(retry)
    setState(mode === 'off' ? 'off' : 'cut', env.now() + ms)
    retry = setTimeout(connect, ms)
  }

  function nudge() {
    const s = link.get().state
    if ((s === 'cut' || s === 'off') && !ws) connect()
  }

  return {
    link,
    start(r: Role, l?: string) {
      role = r
      label = l
      env.onWake(nudge)
      connect()
    },
    screen: () => screen,
    on(t: string, fn: Listener): () => void {
      const set = listeners.get(t) ?? new Set<Listener>()
      set.add(fn)
      listeners.set(t, set)
      return () => { set.delete(fn) }
    },
    send(t: string, d: unknown, id?: string): boolean {
      return raw(id === undefined ? { t, d } : { t, id, d })
    },
    request(t: string, d: unknown): Promise<unknown> {
      const id = 'r' + ++seq
      return new Promise((resolve, reject) => {
        if (!raw({ t, id, d })) { reject(LOST); return }
        pending.set(id, { resolve, reject })
      })
    },
    focus(tool: string) {
      lastFocus = tool
      raw({ t: 'focus', d: { tool } })
    },
    declare(decl: Declaration) {
      lastSockets = decl
      raw({ t: 'sockets', d: decl })
    },
    receipt(re: string, d: unknown) {
      const r: Envelope = { t: 'received', re, d }
      if (raw(r)) return
      receipts.push(r)
      if (receipts.length > RECEIPT_MAX) receipts.shift()
    },
    nudge,
  }
}

export type Bus = ReturnType<typeof createBus>

export const bus = createBus({
  open: url => new WebSocket(url) as unknown as Socketish,
  url: () => `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/bus`,
  reload: () => { void fetch('/', { cache: 'reload' }).finally(() => location.reload()) },
  onWake: fn => {
    window.addEventListener('online', fn)
    window.addEventListener('focus', fn)
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') fn() })
  },
  random: Math.random,
  now: Date.now,
})
