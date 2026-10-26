import type { ComponentType } from 'react'
import type { CardProps, ModuleManifest } from '../lib/module'

const manifests = import.meta.glob<ModuleManifest>('../modules/*/manifest.ts', { eager: true, import: 'default' })

/** Tool tabs, from every module folder that has a manifest. */
export const modules: ModuleManifest[] = Object.values(manifests).sort((a, b) => a.order - b.order)

const cardFiles = import.meta.glob<{ default: ComponentType<CardProps> }>('../modules/*/Card.tsx')

/** Settings card panels by module id (the folder name). */
export const cardPanels: Record<string, () => Promise<{ default: ComponentType<CardProps> }>> = Object.fromEntries(
  Object.entries(cardFiles).map(([path, load]) => [path.split('/')[2] ?? '', load]),
)
