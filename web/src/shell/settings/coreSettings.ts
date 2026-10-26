/** The engine's memory profile: 'engine' leaves the engine's own, 'same' (video models only) follows the general one,
 *  else one of the engine's profile numbers. */
export type Profile = 'engine' | 'same' | number

export const profileOf = (v: string): Profile => (v === 'engine' || v === 'same' ? v : Number(v))

/** The engine's video tier names (its catalog) and the ones the size menu offers. */
export type VideoTiers = { names: string[]; offered: string[] }

/** Whether a tier's switch can move: the last one offered stays, and no more than `max` are offered. */
export const tierLocked = (t: VideoTiers, name: string, max: number): boolean =>
  t.offered.includes(name) ? t.offered.length <= 1 : t.offered.length >= max

/** The tiers offered once `name` is switched, in the catalog's order. */
export const toggleTier = (t: VideoTiers, name: string, on: boolean): string[] =>
  t.names.filter(n => (n === name ? on : t.offered.includes(n)))
