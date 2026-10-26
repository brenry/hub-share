// Plain-English numbers: sizes, durations, counts.
export const gb = (mb: number): string => (mb / 1024).toFixed(1).replace(/\.0$/, '')

export const count = (n: number): string => n.toLocaleString('en-US')

export const plural = (n: number, one: string, many = one + 's'): string => `${count(n)} ${n === 1 ? one : many}`

export function about(seconds: number): string {
  if (seconds < 60) return `about ${Math.max(1, Math.round(seconds))} s`
  return `about ${Math.round(seconds / 60)} min`
}

export const clock = (unixSeconds: number): string =>
  new Date(unixSeconds * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })

export function ago(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))} s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`
  return `${Math.round(seconds / 3600)} h ago`
}
