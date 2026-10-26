// Same-origin JSON calls. Errors carry the server's one plain-English line.
export class HttpError extends Error {
  readonly status: number
  readonly field: string | null
  constructor(status: number, text: string, field: string | null = null) {
    super(text)
    this.status = status
    this.field = field
  }
}

async function parse<T>(res: Response): Promise<T> {
  const type = res.headers.get('content-type') ?? ''
  const body: unknown = type.includes('application/json') ? await res.json() : await res.text()
  if (!res.ok) {
    const b = (typeof body === 'object' && body !== null ? body : {}) as { text?: string; field?: string }
    const text = b.text ?? (typeof body === 'string' && body.length > 0 && body.length < 200 ? body : `Request failed (${res.status})`)
    throw new HttpError(res.status, text, b.field ?? null)
  }
  return body as T
}

export async function getJSON<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { headers: { accept: 'application/json' }, credentials: 'same-origin', ...(signal ? { signal } : {}) })
  return parse<T>(res)
}

export async function sendJSON<T>(method: 'POST' | 'PUT' | 'PATCH' | 'DELETE', url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: { accept: 'application/json', ...(body === undefined ? {} : { 'content-type': 'application/json' }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  return parse<T>(res)
}

export async function sendBlob<T>(method: 'POST' | 'PUT', url: string, blob: Blob): Promise<T> {
  const res = await fetch(url, { method, credentials: 'same-origin', headers: { 'content-type': blob.type }, body: blob })
  return parse<T>(res)
}

export const errorText = (e: unknown): string => (e instanceof Error ? e.message : 'Something went wrong')

export const q = (params: Record<string, string | number>): string =>
  Object.entries(params).map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&')
