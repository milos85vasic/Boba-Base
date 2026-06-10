/**
 * @fileoverview chrome.storage.local wrapper for BobaLink.
 *
 * Provides typed, promise-based access to chrome.storage.local with
 * built-in JSON serialization, change event support, and namespacing.
 * All storage operations are asynchronous and include error handling.
 *
 * @module shared/storage
 */

import { STORAGE_KEYS } from "./constants";
import { StorageError } from "./errors";
import { createLogger } from "./logger";

const log = createLogger("Storage");

/**
 * Read a value from chrome.storage.local.
 *
 * @param key - Storage key to read
 * @returns Parsed value, or null if not found
 */
export async function storageGet<T>(key: string): Promise<T | null> {
  try {
    const result = await chrome.storage.local.get(key);
    if (key in result) {
      return result[key] as T;
    }
    return null;
  } catch (cause) {
    throw new StorageError(`Failed to read "${key}" from storage`, {
      cause: cause instanceof Error ? cause : new Error(String(cause)),
      context: { key },
    });
  }
}

/**
 * Write a value to chrome.storage.local.
 *
 * @param key - Storage key to write
 * @param value - Value to store (must be JSON-serializable)
 */
export async function storageSet<T>(key: string, value: T): Promise<void> {
  try {
    await chrome.storage.local.set({ [key]: value });
    log.debug(`Stored value for "${key}"`);
  } catch (cause) {
    throw new StorageError(`Failed to write "${key}" to storage`, {
      cause: cause instanceof Error ? cause : new Error(String(cause)),
      context: { key },
    });
  }
}

/**
 * Remove a value from chrome.storage.local.
 *
 * @param key - Storage key to remove
 */
export async function storageRemove(key: string): Promise<void> {
  try {
    await chrome.storage.local.remove(key);
    log.debug(`Removed "${key}" from storage`);
  } catch (cause) {
    throw new StorageError(`Failed to remove "${key}" from storage`, {
      cause: cause instanceof Error ? cause : new Error(String(cause)),
      context: { key },
    });
  }
}

/**
 * Read multiple values from chrome.storage.local.
 *
 * @param keys - Array of keys to read
 * @returns Map of key to value (null if not found)
 */
export async function storageGetMultiple<T>(
  keys: readonly string[],
): Promise<ReadonlyMap<string, T | null>> {
  try {
    const result = await chrome.storage.local.get(keys as string[]);
    const map = new Map<string, T | null>();

    for (const key of keys) {
      map.set(key, key in result ? (result[key] as T) : null);
    }

    return map;
  } catch (cause) {
    throw new StorageError("Failed to read multiple keys from storage", {
      cause: cause instanceof Error ? cause : new Error(String(cause)),
      context: { keys: keys.join(", ") },
    });
  }
}

/**
 * Clear all BobaLink data from storage.
 * Only removes keys with the bobalink_ prefix.
 */
export async function storageClearAll(): Promise<void> {
  try {
    const allData = await chrome.storage.local.get(null);
    const keysToRemove = Object.keys(allData).filter((k) =>
      k.startsWith("bobalink_"),
    );

    if (keysToRemove.length > 0) {
      await chrome.storage.local.remove(keysToRemove);
      log.info(`Cleared ${keysToRemove.length} storage entries`);
    }
  } catch (cause) {
    throw new StorageError("Failed to clear storage", {
      cause: cause instanceof Error ? cause : new Error(String(cause)),
    });
  }
}

/**
 * Get all storage keys used by BobaLink.
 *
 * @returns Array of all storage keys
 */
export function getStorageKeys(): typeof STORAGE_KEYS {
  return STORAGE_KEYS;
}

/**
 * Listen for changes to specific storage keys.
 *
 * @param keys - Keys to watch for changes
 * @param callback - Called when any watched key changes
 * @returns Unsubscribe function
 */
export function onStorageChange<T>(
  keys: readonly string[],
  callback: (changes: ReadonlyMap<string, { oldValue: T | null; newValue: T | null }>) => void,
): () => void {
  const listener = (
    changes: Record<string, chrome.storage.StorageChange>,
    areaName: string,
  ): void => {
    if (areaName !== "local") return;

    const relevantChanges = new Map<
      string,
      { oldValue: T | null; newValue: T | null }
    >();

    for (const key of keys) {
      const change = changes[key];
      if (change) {
        relevantChanges.set(key, {
          oldValue: (change.oldValue as T | undefined) ?? null,
          newValue: (change.newValue as T | undefined) ?? null,
        });
      }
    }

    if (relevantChanges.size > 0) {
      callback(relevantChanges);
    }
  };

  chrome.storage.onChanged.addListener(listener);

  // Return unsubscribe function
  return (): void => {
    chrome.storage.onChanged.removeListener(listener);
  };
}

/**
 * Namespaced storage accessor for a specific domain.
 * All keys are automatically prefixed.
 */
export class NamespacedStorage {
  private readonly prefix: string;

  /**
   * Create a namespaced storage instance.
   *
   * @param namespace - The namespace prefix (e.g., "config", "cache")
   */
  constructor(namespace: string) {
    this.prefix = `bobalink_${namespace}_`;
  }

  /**
   * Get the full prefixed key.
   *
   * @param key - Short key name
   * @returns Full prefixed key
   */
  private key(key: string): string {
    return `${this.prefix}${key}`;
  }

  /**
   * Read a value.
   *
   * @param key - Short key name
   * @returns Parsed value, or null if not found
   */
  async get<T>(key: string): Promise<T | null> {
    return storageGet<T>(this.key(key));
  }

  /**
   * Write a value.
   *
   * @param key - Short key name
   * @param value - Value to store
   */
  async set<T>(key: string, value: T): Promise<void> {
    return storageSet(this.key(key), value);
  }

  /**
   * Remove a value.
   *
   * @param key - Short key name
   */
  async remove(key: string): Promise<void> {
    return storageRemove(this.key(key));
  }

  /**
   * Get all keys in this namespace.
   *
   * @returns Array of full prefixed keys
   */
  async getAllKeys(): Promise<string[]> {
    const allData = await chrome.storage.local.get(null);
    return Object.keys(allData).filter((k) => k.startsWith(this.prefix));
  }

  /**
   * Clear all values in this namespace.
   */
  async clear(): Promise<void> {
    const keys = await this.getAllKeys();
    if (keys.length > 0) {
      await chrome.storage.local.remove(keys);
    }
  }
}
