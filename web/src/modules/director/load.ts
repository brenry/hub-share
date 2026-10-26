// The list of scripts and the open one, mirrored from the hub: loaded on every (re)connect and whenever the tab is
// shown, and again on each `director.changed` the script tools publish, which opens the script they
// wrote. Nothing is kept in the browser: a new window opens the most recently changed script.
import { useEffect } from 'react'
import { errorText } from '../../lib/http'
import { connects } from '../../lib/live'
import { useBusEvent } from '../../lib/useBus'
import { createStore, useStore } from '../../lib/store'
import { toast } from '../../lib/toast'
import { api, type Opened, type Summary } from './api'

export const list = createStore<readonly Summary[] | null>(null)
export const open = createStore<Opened | null>(null)
let name: string | null = null
let asked = 0                                      // an older answer never covers a newer one

const newest = (all: readonly Summary[]): string | null =>
  all.reduce<Summary | null>((a, s) => (!a || s.changed > a.changed ? s : a), null)?.name ?? null

export async function reload(): Promise<void> {
  const mine = ++asked
  try {
    const all = await api.all()
    if (mine !== asked) return
    list.set(all)
    if (name === null || !all.some(s => s.name === name)) name = newest(all)
    const one = name === null ? null : await api.one(name)
    if (mine === asked) open.set(one)
  } catch (e) {
    if (mine === asked) toast(errorText(e))
  }
}

type Changed = { name: string; revision: number }

/** A script the tools wrote: the list again, and that script opened and drawn (the one being written is shown). */
export function changed(d: Changed): void {
  name = d.name
  void reload()
}

export function choose(n: string): void {
  name = n
  void reload()
}

/** -> true when renamed. */
export async function rename(to: string): Promise<boolean> {
  if (name === null) return false
  try {
    name = (await api.rename(name, to)).name
  } catch (e) {
    toast(errorText(e))
    return false
  }
  await reload()
  return true
}

export async function removeOpen(): Promise<void> {
  if (name === null) return
  try {
    await api.remove(name)
    name = null
  } catch (e) {
    toast(errorText(e))
  }
  await reload()
}

/** Loads on every (re)connect and each time the tab is shown, and follows `director.changed`; mounted once, by the
 *  tab. */
export function useScripts(visible: boolean): void {
  const n = useStore(connects, x => x)
  useEffect(() => { if (n > 0 && visible) void reload() }, [n, visible])
  useBusEvent('director.changed', d => changed(d as Changed))
}
