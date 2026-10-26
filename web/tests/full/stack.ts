// The real stack as a process: `python -m hub serve` (real worker on the fake engine, the built UI).
import { execFileSync, spawn, type ChildProcess } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

const ROOT = resolve(import.meta.dirname, '../../..')
const PY = join(ROOT, '.venv/bin/python')
const ENGINE_PY = process.env.HUB_TEST_ENGINE_PYTHON ?? '/usr/bin/python3'

type Paths = { engine: string }

const freePort = (): Promise<number> => new Promise((ok, fail) => {
  const s = createServer()
  s.once('error', fail)
  s.listen(0, '127.0.0.1', () => {
    const { port } = s.address() as { port: number }
    s.close(() => ok(port))
  })
})

function waitLine(p: ChildProcess, re: RegExp, ms = 30_000): Promise<string> {
  return new Promise((ok, fail) => {
    let seen = ''
    const t = setTimeout(() => fail(new Error(`timed out waiting for ${re}; output: ${seen}`)), ms)
    const feed = (b: Buffer) => {
      seen += b.toString()
      const m = seen.match(re)
      if (m) { clearTimeout(t); ok(m[0]) }
    }
    p.stdout?.on('data', feed)
    p.stderr?.on('data', (b: Buffer) => { seen += b.toString() })
    p.once('close', code => { clearTimeout(t); fail(new Error(`exited ${code} before ${re}: ${seen}`)) })
  })
}

const exited = (p: ChildProcess): Promise<void> =>
  p.exitCode !== null || p.signalCode !== null ? Promise.resolve() : new Promise(ok => p.once('close', () => ok()))

export class Stack {
  readonly dir = mkdtempSync(join(tmpdir(), 'hub-full-'))
  readonly data = join(this.dir, 'data')
  readonly errors: string[] = []
  port = 0
  paths!: Paths
  hub: ChildProcess | null = null

  get origin(): string { return `http://127.0.0.1:${this.port}` }

  private env(): NodeJS.ProcessEnv {
    return { PATH: process.env.PATH, HOME: join(this.dir, 'home'), LANG: 'C.UTF-8' }
  }

  cli(...args: string[]): string {
    return execFileSync(PY, ['-m', 'hub', ...args], { cwd: ROOT, env: this.env(), encoding: 'utf8' })
  }

  async init(): Promise<void> {
    if (!existsSync(join(ROOT, 'web/dist/index.html'))) throw new Error('run npm run build first')
    mkdirSync(join(this.dir, 'home'))
    this.paths = JSON.parse(execFileSync(PY, [join(import.meta.dirname, 'prepare.py'), this.dir], { encoding: 'utf8', env: this.env() })) as Paths
    this.port = await freePort()
    this.cli('init', '--data', this.data, '--bind', '127.0.0.1', '--port', String(this.port),
      '--engine-root', this.paths.engine, '--engine-python', ENGINE_PY)
  }

  /** A one-time pairing code, as `hub pair` prints it in its link. */
  pairLink(name: string): string {
    return this.cli('pair', '--data', this.data, '--name', name).trim()
  }

  async startHub(): Promise<void> {
    const p = spawn(PY, ['-m', 'hub', 'serve', '--data', this.data], { cwd: ROOT, env: this.env() })
    p.stderr.on('data', (b: Buffer) => this.errors.push(`hub: ${b}`))
    this.hub = p
    await waitLine(p, /hub started on .*/)
  }

  /** SIGTERM the hub; with `restart`, leave the marker `hub restart` leaves. */
  async stopHub(restart = false): Promise<void> {
    if (!this.hub) return
    if (restart) {
      mkdirSync(join(this.data, 'run'), { recursive: true })
      writeFileSync(join(this.data, 'run', 'restart'), '')
    }
    const p = this.hub
    this.hub = null
    const stopped = waitLine(p, /hub stopped/)
    p.kill('SIGTERM')
    await stopped
  }

  async mcp(key: string, method: string, params: unknown): Promise<{ status: number; body: unknown }> {
    const res = await fetch(`${this.origin}/mcp`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream', 'mcp-protocol-version': '2025-11-25',
        authorization: `Bearer ${key}` },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
    })
    return { status: res.status, body: await res.json().catch(() => null) }
  }

  async close(): Promise<void> {
    if (this.hub) { this.hub.kill('SIGTERM'); await exited(this.hub) }
    rmSync(this.dir, { recursive: true, force: true })
  }
}
