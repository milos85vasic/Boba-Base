/**
 * @fileoverview In-memory fake of the chrome.storage.local API for unit tests.
 *
 * Real chrome.* is unavailable in the Vitest/jsdom environment. This fake
 * implements the subset of chrome.storage used by src/shared/storage.ts
 * (local.get/set/remove + onChanged add/remove) backed by a plain Map, so the
 * storage tests assert real read-back behaviour against the production module
 * rather than a mock that always agrees.
 *
 * @module tests/unit/chrome-fake
 */

type StorageRecord = Record<string, unknown>;
type ChangeListener = (
  changes: Record<string, { oldValue?: unknown; newValue?: unknown }>,
  areaName: string,
) => void;

/** Create a fresh fake chrome.storage backing store + API surface. */
export function createChromeStorageFake() {
  const store = new Map<string, unknown>();
  const listeners = new Set<ChangeListener>();

  const local = {
    async get(
      keys?: string | string[] | null,
    ): Promise<StorageRecord> {
      const out: StorageRecord = {};
      if (keys === null || keys === undefined) {
        for (const [k, v] of store) out[k] = v;
        return out;
      }
      const list = Array.isArray(keys) ? keys : [keys];
      for (const k of list) {
        if (store.has(k)) out[k] = store.get(k);
      }
      return out;
    },
    async set(items: StorageRecord): Promise<void> {
      const changes: Record<string, { oldValue?: unknown; newValue?: unknown }> = {};
      for (const [k, v] of Object.entries(items)) {
        const oldValue = store.get(k);
        store.set(k, v);
        changes[k] = { oldValue, newValue: v };
      }
      emit(changes);
    },
    async remove(keys: string | string[]): Promise<void> {
      const list = Array.isArray(keys) ? keys : [keys];
      const changes: Record<string, { oldValue?: unknown; newValue?: unknown }> = {};
      for (const k of list) {
        if (store.has(k)) {
          changes[k] = { oldValue: store.get(k), newValue: undefined };
          store.delete(k);
        }
      }
      if (Object.keys(changes).length > 0) emit(changes);
    },
  };

  function emit(
    changes: Record<string, { oldValue?: unknown; newValue?: unknown }>,
  ): void {
    for (const l of listeners) l(changes, "local");
  }

  const onChanged = {
    addListener(l: ChangeListener): void {
      listeners.add(l);
    },
    removeListener(l: ChangeListener): void {
      listeners.delete(l);
    },
  };

  return {
    chrome: { storage: { local, onChanged } },
    store,
    listenerCount: (): number => listeners.size,
  };
}
