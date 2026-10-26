// A fake controller on page.routeWebSocket: hello/welcome, presence, focus, jobs and the delivery handshake.
import type { Page, WebSocketRoute } from '@playwright/test'
import type { ChatView, Envelope, Focus, Job, Presence, ToolInfo } from '../../../src/lib/protocol'
import { MODELS, SPEECH, job, summary } from './data'

type Line = { ws: WebSocketRoute; role: string; screen: string; page: Page }

export class FakeHub {
  boot = 'b3f9c2a71d0e44c1'
  session = 's1a2b3c4d5e6f708'
  lines: Line[] = []
  got: Envelope[] = []
  jobs = new Map<string, Job>()
  focus: Focus | null = null
  engines: Presence['engines'] = { gpu0: 'ready' }
  refuse = false
  ghostWorkspaces = 0
  answerDeliveries = true
  /** The tools the welcome lists: Generate Image alone unless a spec gives more (the Workspace hides other tabs). */
  tools: ToolInfo[] = [{ id: 'generate-image', title: 'Generate Image', tab: { label: 'Generate Image', order: 10 }, sockets: [] }]
  private n = 0

  constructor(init: { jobs?: Job[]; tools?: ToolInfo[] } = {}) {
    for (const j of init.jobs ?? []) this.jobs.set(j.id, j)
    if (init.tools) this.tools = init.tools
  }

  async attach(page: Page): Promise<void> {
    await page.routeWebSocket(/\/bus$/, ws => this.accept(ws, page))
    page.on('close', () => { for (const l of this.lines.filter(x => x.page === page)) this.gone(l) })
  }

  presence(): Presence {
    const count = (r: string) => new Set(this.lines.filter(l => l.role === r).map(l => l.screen)).size
    return { screens: { workspace: count('workspace') + this.ghostWorkspaces, media: count('media'), aux: 0 }, labels: { media: [] }, engines: this.engines }
  }

  send(l: Line, t: string, d: unknown, extra: Partial<Envelope> = {}): void {
    l.ws.send(JSON.stringify({ t, d, ...extra }))
  }

  broadcast(t: string, d: unknown, role?: string): void {
    for (const l of this.lines) if (!role || l.role === role) this.send(l, t, d)
  }

  /** The jobs lane: the workspace's, and the Media window's (a clip's verdict on the Stage). */
  setJob(j: Job): void {
    this.jobs.set(j.id, j)
    for (const role of ['workspace', 'media']) this.broadcast('job', j, role)
  }

  dropJob(id: string): void {
    this.jobs.delete(id)
    for (const role of ['workspace', 'media']) this.broadcast('job.gone', { id }, role)
  }

  /** Module lane events, as the assistant and the generate_image tool publish them. */
  chat(v: ChatView): void { this.broadcast('assistant.chat', v, 'workspace') }

  closeAll(code: number): void {
    for (const l of [...this.lines]) l.ws.close({ code, reason: '' })
    this.lines = []
  }

  sent(t: string): Envelope[] {
    return this.got.filter(e => e.t === t)
  }

  private accept(ws: WebSocketRoute, page: Page): void {
    if (this.refuse) { ws.close({ code: 1011, reason: '' }); return }
    let line: Line | null = null
    ws.onMessage(raw => {
      const msg = JSON.parse(String(raw)) as Envelope
      this.got.push(msg)
      const d = (msg.d ?? {}) as Record<string, unknown>
      if (msg.t === 'hello') {
        line = { ws, role: String(d.role), screen: String(d.screen), page }
        this.lines.push(line)
        this.send(line, 'welcome', {
          proto: 1, boot: this.boot, version: '0.1.0', session: this.session, you: { screen: line.screen, role: line.role, lanes: [] },
          limits: { max_bytes: 65536, deliver_timeout_s: 5, beat_after_s: 25, silence_s: 60 },
          tools: this.tools,
          presence: this.presence(), focus: this.focus, jobs: [...this.jobs.values()], settings: {},
        }, msg.id ? { re: msg.id } : {})
        this.broadcast('presence', this.presence())
        return
      }
      if (!line) return
      this.handle(line, msg, d)
    })
    ws.onClose(() => { if (line) this.gone(line) })
  }

  private gone(line: Line): void {
    if (!this.lines.includes(line)) return
    this.lines = this.lines.filter(l => l !== line)
    if (line.role === 'workspace' && this.focus?.screen === line.screen) { this.focus = null; this.broadcast('focus', null, 'media') }
    this.broadcast('presence', this.presence())
  }

  private handle(line: Line, msg: Envelope, d: Record<string, unknown>): void {
    const reply = (body: unknown) => this.send(line, 'reply', body, msg.id ? { re: msg.id } : {})
    if (msg.t === 'sockets') {
      this.focus = { ...(d as unknown as Focus), screen: line.screen, label: 'Generate Image' }
      this.broadcast('focus', this.focus, 'media')
    } else if (msg.t === 'job.submit') {
      const id = `j_${String(++this.n).padStart(8, '0')}`
      const params = d.params as { images: number; model?: string; frames?: number; width: number; height: number }
      reply({ job: id, state: 'queued', position: 1 })
      // The hub draws the seeds when it plans the job, so the summary carries them from the start; a video model's
      // job stays kind "image" and its summary says "clip", with frames and seconds
      const seeds = Array.from({ length: params.images }, (_, i) => 1000 * this.n + i + 1)
      const video = MODELS.find(m => m.id === params.model)?.video
      const frames = params.frames ?? video?.frames.default ?? 0
      const clip = video ? { kind: 'clip' as const, frames, seconds: Math.round((frames / video.fps) * 100) / 100, width: params.width, height: params.height }
        : params.model === SPEECH.id ? { kind: 'sound' as const } : {}
      this.setJob(job(id, { title: video ? '1 clip · MiniMax H3' : `${params.images} images · Flux 2 Klein 9B`, created: 1791561600 + this.n,
        summary: summary(params.model ?? 'flux2_klein_9b', seeds, clip) }))
    } else if (msg.t === 'job.cancel') {
      reply({ job: d.job, state: 'cancelled' })
      this.dropJob(String(d.job))
    } else if (msg.t === 'send') {
      const ws = this.lines.find(l => l.role === 'workspace' && l.screen === this.focus?.screen)
      if (!ws) { this.send(line, 'delivery', { status: 'failed', reason: 'no_tool', text: 'No tool is open' }, { re: String(msg.id) }); return }
      if (!this.answerDeliveries) return
      const items = (d.items as string[]).map(id => ({ id, kind: 'image', url: `/files/${id}` }))
      this.pending.set(String(msg.id), line)
      this.send(ws, 'deliver', { tool: 'generate-image', socket: d.socket, from: { role: 'media' }, items }, { id: String(msg.id) })
    } else if (msg.t === 'gpu.release') {
      reply({ ok: true })
    } else if (msg.t === 'received') {
      const media = this.pending.get(String(msg.re))
      if (media) this.send(media, 'delivery', { status: 'done', tool: 'generate-image', toolLabel: 'Generate Image', ...d }, { re: String(msg.re) })
    }
  }

  private pending = new Map<string, Line>()
}
