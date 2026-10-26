import type { ComponentType } from 'react'

/** A tool tab. Its folder is `modules/<id>/`; deleting the folder removes the tab. */
export type ModuleManifest = {
  id: string
  label: string
  order: number
  load: () => Promise<{ default: ComponentType<ToolProps> }>
  /** Queues one job from the tool's saved draft (the Media window's Generate). Resolves to null, or the reason it did not. */
  queue?: () => Promise<string | null>
  /** The current model's seed back to random (Media's bar). */
  randomSeed?: () => Promise<unknown>
  /** Puts a clip in box 1 to continue it (Media's Continue). Resolves to null, or the reason it did not. */
  continueClip?: (id: string) => Promise<string | null>
}

export type ToolProps = { visible: boolean }

/** A Settings card panel: `modules/<module id>/Card.tsx`. `changed` refreshes the card summaries. */
export type CardProps = { changed: () => void }

export type CardInfo = { module: string; title: string; order: number; summary: string; status: 'ok' | 'attention' | 'off' | 'error' }
