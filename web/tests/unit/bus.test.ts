import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createBus, type Socketish } from '../../src/lib/bus'
import type { Envelope } from '../../src/lib/protocol'

class FakeSocket implements Socketish {
  readyState = 0
  sent: Envelope[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: { data: unknown }) => void) | null = null
  onclose: ((e: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  send(data: string) { this.sent.push(JSON.parse(data) as Envelope) }
  close() { this.readyState = 3 }
  open() { this.readyState = 1; this.onopen?.() }
  msg(t: string, d: unknown = {}, extra: Partial<Envelope> = {}) { this.onmessage?.({ data: JSON.stringify({ t, d, ...extra }) }) }
  drop(code: number) { this.readyState = 3; this.onclose?.({ code }) }
}

const welcome = (boot = 'b1') => ({ proto: 1, boot, version: '0.1.0', you: { screen: 's', role: 'workspace', lanes: [] },
  limits: { max_bytes: 65536, deliver_timeout_s: 5, beat_after_s: 25, silence_s: 60 }, tools: [], presence: {}, focus: null, jobs: [], gpu: {}, settings: {} })

function setup(random: number | (() => number) = 0.5) {
  const sockets: FakeSocket[] = []
  let wake = () => {}
  const reload = vi.fn()
  const bus = createBus({
    open: () => { const s = new FakeSocket(); sockets.push(s); return s },
    url: () => 'ws://hub/bus', reload, onWake: fn => { wake = fn }, random: typeof random === 'function' ? random : () => random, now: () => Date.now(),
  })
  bus.start('workspace', 'Left')
  const last = () => sockets[sockets.length - 1]!
  const connect = (boot = 'b1') => { last().open(); last().msg('welcome', welcome(boot), { re: 'h1' }) }
  return { bus, sockets, last, connect, reload, wake: () => wake() }
}

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers() })

describe('bus', () => {
  it('says hello with role, screen and label, then is On after welcome', () => {
    const { bus, last, connect } = setup()
    expect(bus.link.get().state).toBe('connecting')
    last().open()
    const hello = last().sent[0]!
    expect(hello.t).toBe('hello')
    expect(hello.d).toMatchObject({ proto: 1, role: 'workspace', label: 'Left', subs: null })
    expect(String((hello.d as { screen: string }).screen)).toMatch(/^scr_[0-9A-Z]{8}$/)
    connect()
    expect(bus.link.get()).toMatchObject({ state: 'on', version: '0.1.0' })
  })

  it('replays focus and sockets after a reconnect', () => {
    const { bus, last, connect } = setup()
    connect()
    bus.focus('generate-image')
    bus.declare({ tool: 'generate-image', mode: 'new', primary: null, sockets: [] })
    last().drop(1011)
    vi.advanceTimersByTime(700)
    connect()
    const types = last().sent.map(m => m.t)
    expect(types).toEqual(['hello', 'focus', 'sockets'])
  })

  it('backs off 0.5, 1, 2, 4, 8, 8 s with jitter on a power cut', () => {
    const { bus, sockets, last, connect } = setup(0.5)
    connect()
    last().drop(1006)
    expect(bus.link.get().state).toBe('cut')
    for (const ms of [500, 1000, 2000, 4000, 8000, 8000]) {
      const n = sockets.length
      vi.advanceTimersByTime(ms - 1)
      expect(sockets.length).toBe(n)
      vi.advanceTimersByTime(1)
      expect(sockets.length).toBe(n + 1)
      last().drop(1006)
    }
  })

  it('jitters by ±20 %', () => {
    const lo = setup(0)
    lo.connect(); lo.last().drop(1011)
    expect(lo.bus.link.get().nextTry! - Date.now()).toBe(400)
    const hi = setup(0.999)
    hi.connect(); hi.last().drop(1011)
    expect(hi.bus.link.get().nextTry! - Date.now()).toBe(600)
  })

  it('tries every 30 s after ten minutes of power cut', () => {
    const { bus, last, connect } = setup()
    connect()
    last().drop(1006)
    vi.advanceTimersByTime(10 * 60 * 1000)
    last().drop(1006)
    expect(bus.link.get().nextTry! - Date.now()).toBe(30000)
  })

  it('treats going_off shutdown and 4000 as Switched off with slow checks', () => {
    const { bus, sockets, last, connect } = setup()
    connect()
    last().msg('going_off', { reason: 'shutdown', back_in_s: null })
    last().drop(1001)
    expect(bus.link.get().state).toBe('off')
    expect(bus.link.get().nextTry! - Date.now()).toBe(2000)
    vi.advanceTimersByTime(2000)
    last().drop(1006)
    expect(bus.link.get().state).toBe('off')
    expect(bus.link.get().nextTry! - Date.now()).toBe(5000)
    vi.advanceTimersByTime(5000); last().drop(1006)
    expect(bus.link.get().nextTry! - Date.now()).toBe(10000)
    vi.advanceTimersByTime(10000); last().drop(1006)
    expect(bus.link.get().nextTry! - Date.now()).toBe(30000)
    expect(sockets.length).toBe(4)
  })

  it('restart (4001) is a power cut, not off', () => {
    const { bus, last, connect } = setup()
    connect()
    last().msg('going_off', { reason: 'restart', back_in_s: 10 })
    last().drop(4001)
    expect(bus.link.get().state).toBe('cut')
  })

  it('stops retrying when not paired (4003)', () => {
    const { bus, sockets, last } = setup()
    last().open()
    last().drop(4003)
    expect(bus.link.get().state).toBe('unpaired')
    vi.advanceTimersByTime(120000)
    expect(sockets.length).toBe(1)
  })

  it('takes a fresh screen id and reconnects at once when replaced (4009)', () => {
    let n = 0
    const { sockets, last, connect } = setup(() => (n++ % 10) / 10)
    connect()
    const first = (last().sent[0]!.d as { screen: string }).screen
    last().drop(4009)
    vi.advanceTimersByTime(0)
    expect(sockets.length).toBe(2)
    last().open()
    expect((last().sent[0]!.d as { screen: string }).screen).not.toBe(first)
  })

  it('reloads the page when the controller boot changes', () => {
    const { last, connect, reload } = setup()
    connect('b1')
    last().drop(1012)
    vi.advanceTimersByTime(600)
    connect('b1')
    expect(reload).not.toHaveBeenCalled()
    last().drop(1012)
    vi.advanceTimersByTime(600)
    connect('b2')
    expect(reload).toHaveBeenCalledOnce()
  })

  it('counts 60 s of silence as a power cut; any frame resets the watchdog', () => {
    const { bus, last, connect } = setup()
    connect()
    vi.advanceTimersByTime(50000)
    last().msg('beat')
    vi.advanceTimersByTime(50000)
    expect(bus.link.get().state).toBe('on')
    vi.advanceTimersByTime(10001)
    expect(bus.link.get().state).toBe('cut')
  })

  it('answers requests by id and rejects pending ones when the line drops', async () => {
    const { bus, last, connect } = setup()
    connect()
    const ok = bus.request('job.submit', { tool: 'x' })
    const id = last().sent[last().sent.length - 1]!.id!
    last().msg('reply', { job: 'j1' }, { re: id })
    await expect(ok).resolves.toEqual({ job: 'j1' })
    const bad = bus.request('job.submit', {})
    const id2 = last().sent[last().sent.length - 1]!.id!
    last().msg('error', { code: 'invalid', text: 'Write a prompt' }, { re: id2 })
    await expect(bad).rejects.toMatchObject({ text: 'Write a prompt' })
    const lost = bus.request('job.cancel', {})
    last().drop(1011)
    await expect(lost).rejects.toMatchObject({ code: 'unavailable' })
  })

  it('queues receipts while cut (at most 20) and sends them after welcome', () => {
    const { bus, last, connect } = setup()
    connect()
    last().drop(1011)
    for (let i = 0; i < 25; i++) bus.receipt(`snd_${i}`, { placed: [], refused: [] })
    vi.advanceTimersByTime(700)
    connect()
    const receipts = last().sent.filter(m => m.t === 'received')
    expect(receipts).toHaveLength(20)
    expect(receipts[0]!.re).toBe('snd_5')
  })

  it('tries again at once on wake (focus, online, visible)', () => {
    const { sockets, last, connect, wake } = setup()
    connect()
    last().drop(1006)
    wake()
    expect(sockets.length).toBe(2)
  })

  it('emits other messages to listeners', () => {
    const { bus, last, connect } = setup()
    const seen: unknown[] = []
    const off = bus.on('job', d => seen.push(d))
    connect()
    last().msg('job', { id: 'j1' })
    off()
    last().msg('job', { id: 'j2' })
    expect(seen).toEqual([{ id: 'j1' }])
  })
})
