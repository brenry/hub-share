// Styles first: base.css declares the layer order (base, ui, screen) before any module CSS can.
import './styles/tokens.css'
import './styles/base.css'
import { StrictMode, Suspense, lazy, type ComponentType } from 'react'
import { createRoot } from 'react-dom/client'
import { bus } from './lib/bus'
import { feed } from './lib/live'
import { installLock } from './lib/lock'
import type { Role } from './lib/protocol'
import { toast } from './lib/toast'

type Entry = [Role | null, () => Promise<{ default: ComponentType }>]

const screens: Record<string, Entry> = {
  '/': ['workspace', () => import('./shell/Workspace')],
  '/media': ['media', () => import('./screens/media/Media')],
  // The clips page: the same Media window, opened on its Clips section (the server serves the shell at /clips).
  '/clips': ['media', () => import('./screens/media/Media')],
  '/pair': [null, () => import('./screens/pair/Pair')],
}

const path = location.pathname.replace(/\/+$/, '') || '/'
const [role, load] = screens[path] ?? screens['/']!
if (role) {
  feed(bus)
  bus.start(role, new URLSearchParams(location.search).get('label') ?? undefined)
}
document.documentElement.dataset.screen = role ?? 'pair'
const Screen = lazy(load)
installLock()

// A page error is said on the page, never written to the console (nothing of the page leaves it).
const quiet = { onUncaughtError: () => toast('Something went wrong on this page'), onCaughtError: () => {}, onRecoverableError: () => {} }
window.addEventListener('unhandledrejection', e => e.preventDefault())
createRoot(document.getElementById('root')!, quiet).render(
  <StrictMode>
    <Suspense fallback={null}>
      <Screen />
    </Suspense>
  </StrictMode>,
)
