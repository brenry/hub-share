import { useSyncExternalStore } from 'react'

type Store<T> = {
  get: () => T
  set: (next: T | ((prev: T) => T)) => void
  subscribe: (fn: () => void) => () => void
}

/** A tiny observable value. Subscribers run only when the value really changes. */
export function createStore<T>(initial: T): Store<T> {
  let value = initial
  const subs = new Set<() => void>()
  return {
    get: () => value,
    set: next => {
      const v = typeof next === 'function' ? (next as (prev: T) => T)(value) : next
      if (Object.is(v, value)) return
      value = v
      for (const fn of [...subs]) fn()
    },
    subscribe: fn => {
      subs.add(fn)
      return () => { subs.delete(fn) }
    },
  }
}

/** `pick` must return a primitive or an existing reference, never a fresh object. */
export function useStore<T, S>(store: Store<T>, pick: (v: T) => S): S {
  return useSyncExternalStore(store.subscribe, () => pick(store.get()), () => pick(store.get()))
}
