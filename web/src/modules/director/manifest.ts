import type { ModuleManifest } from '../../lib/module'

export default {
  id: 'director',
  label: 'Storyboard',
  order: 30,
  load: () => import('./Scripts'),
} satisfies ModuleManifest
