/**
 * @fileoverview Anti-bluff unit tests for the REAL storage module.
 *
 * Imports the production `src/shared/storage.ts` and drives it against an
 * in-memory chrome.storage fake (tests/unit/chrome-fake.ts) installed on
 * globalThis. Asserts user-observable outcomes: a value written is read back
 * byte-for-byte; remove deletes it; clearAll only touches bobalink_ keys;
 * NamespacedStorage prefixes correctly; onStorageChange fires with the change;
 * a backing failure is wrapped as StorageError.
 *
 * @module tests/unit/storage.test
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { createChromeStorageFake } from "./chrome-fake";

// Install a fresh fake before importing the module under test in each test.
let fake: ReturnType<typeof createChromeStorageFake>;

beforeEach(() => {
  fake = createChromeStorageFake();
  (globalThis as unknown as { chrome: unknown }).chrome = fake.chrome;
  vi.resetModules();
});

async function loadStorage() {
  return import("../../src/shared/storage");
}

describe("storageGet / storageSet / storageRemove", () => {
  it("reads back exactly what was written", async () => {
    const { storageGet, storageSet } = await loadStorage();
    await storageSet("bobalink_x", { hello: "world", n: 7 });
    expect(await storageGet("bobalink_x")).toEqual({ hello: "world", n: 7 });
  });

  it("returns null for a missing key", async () => {
    const { storageGet } = await loadStorage();
    expect(await storageGet("bobalink_missing")).toBeNull();
  });

  it("remove deletes the value", async () => {
    const { storageGet, storageSet, storageRemove } = await loadStorage();
    await storageSet("bobalink_y", 1);
    await storageRemove("bobalink_y");
    expect(await storageGet("bobalink_y")).toBeNull();
  });

  it("storageGetMultiple maps each key to value-or-null", async () => {
    const { storageSet, storageGetMultiple } = await loadStorage();
    await storageSet("bobalink_a", "A");
    const map = await storageGetMultiple(["bobalink_a", "bobalink_b"]);
    expect(map.get("bobalink_a")).toBe("A");
    expect(map.get("bobalink_b")).toBeNull();
  });
});

describe("storageClearAll", () => {
  it("removes only bobalink_-prefixed keys", async () => {
    const { storageSet, storageClearAll, storageGet } = await loadStorage();
    await storageSet("bobalink_one", 1);
    fake.store.set("foreign_key", "keep-me");
    await storageClearAll();
    expect(await storageGet("bobalink_one")).toBeNull();
    expect(fake.store.get("foreign_key")).toBe("keep-me");
  });
});

describe("NamespacedStorage", () => {
  it("prefixes keys with bobalink_<namespace>_ and round-trips", async () => {
    const { NamespacedStorage } = await loadStorage();
    const ns = new NamespacedStorage("config");
    await ns.set("theme", "dark");
    expect(await ns.get("theme")).toBe("dark");
    expect(fake.store.has("bobalink_config_theme")).toBe(true);
  });

  it("getAllKeys returns only this namespace's keys; clear wipes them", async () => {
    const { NamespacedStorage } = await loadStorage();
    const ns = new NamespacedStorage("cache");
    await ns.set("k1", 1);
    await ns.set("k2", 2);
    fake.store.set("bobalink_config_other", 99);
    const keys = await ns.getAllKeys();
    expect(keys.sort()).toEqual(["bobalink_cache_k1", "bobalink_cache_k2"]);
    await ns.clear();
    expect(await ns.get("k1")).toBeNull();
    expect(fake.store.get("bobalink_config_other")).toBe(99);
  });
});

describe("onStorageChange", () => {
  it("invokes the callback with old/new values for watched keys", async () => {
    const { onStorageChange, storageSet } = await loadStorage();
    const seen: Array<{ oldValue: unknown; newValue: unknown }> = [];
    const unsub = onStorageChange(["bobalink_watched"], (changes) => {
      const c = changes.get("bobalink_watched");
      if (c) seen.push(c);
    });
    await storageSet("bobalink_watched", "v1");
    await storageSet("bobalink_watched", "v2");
    expect(seen).toEqual([
      { oldValue: null, newValue: "v1" },
      { oldValue: "v1", newValue: "v2" },
    ]);
    unsub();
    expect(fake.listenerCount()).toBe(0);
  });
});

describe("error wrapping", () => {
  it("wraps a backing-store failure as StorageError", async () => {
    const { storageGet } = await loadStorage();
    const { StorageError } = await import("../../src/shared/errors");
    fake.chrome.storage.local.get = (): Promise<never> =>
      Promise.reject(new Error("quota exceeded"));
    await expect(storageGet("bobalink_x")).rejects.toBeInstanceOf(StorageError);
  });
});
