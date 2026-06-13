/**
 * @fileoverview Anti-bluff unit tests for the REAL options SAVE/CONFIG
 * persistence-round-trip integrity (§11.4 / §11.4.69) — the gaps NOT covered by
 * the sibling `options.test.ts` / `options-ux.test.ts`.
 *
 * Those two files cover: populate-all-fields, save-persists-a-changed-field,
 * invalid-URL-rejects, token-encrypted-not-plaintext, token-without-passphrase,
 * save-status success/error/warn, basic + keyboard tab navigation, and the
 * numeric no-validation behaviour. This file ADDS the persistence-integrity
 * cases none of them assert:
 *
 *   1. requestTimeout SAVE direction — the field is seconds, persisted as ms
 *      (sibling files only assert the LOAD direction ms→seconds);
 *   2. existing server SECRET + LIMIT fields (username, encryptedPassword,
 *      encryptedApiKey, uploadLimit, downloadLimit) are PRESERVED across a save
 *      of unrelated fields — a save that silently drops a stored credential is a
 *      serious persistence defect;
 *   3. a multi-server config: editing the Server tab replaces ONLY servers[0]
 *      and PRESERVES servers[1+] (both files use single-server configs);
 *   4. loadConfig falls back to DEFAULT_CONFIG when chrome.storage.get throws.
 *
 * Drives the production `src/options/options.ts` over the real options markup in
 * jsdom + the in-memory chrome.storage fake (a legitimate boundary stub — the
 * storage module under it is the REAL committed module; the unit under test is
 * NOT stubbed). Every assertion inspects a user-observable outcome read back
 * from storage. Each test would FAIL against a no-op stub of saveOptions /
 * loadConfig (see per-test RED notes).
 *
 * @module tests/unit/options-save-flow.test
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { createChromeStorageFake } from "./chrome-fake";
import {
  DEFAULT_CONFIG,
  type ExtensionConfig,
  type ServerConfig,
} from "../../src/types/config";
import { STORAGE_KEYS } from "../../src/shared/constants";

const OPTIONS_HTML_PATH = resolve(
  process.cwd(),
  "src/entrypoints/options/index.html",
);

function mustExist<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`expected ${what} to exist`);
  }
  return value;
}

let fake: ReturnType<typeof createChromeStorageFake>;

/** Parse the real options markup into the jsdom document body. */
function loadOptionsMarkup(): void {
  const html = readFileSync(OPTIONS_HTML_PATH, "utf8");
  const bodyMatch = /<body[^>]*>([\s\S]*?)<\/body>/i.exec(html);
  document.body.innerHTML = bodyMatch ? (bodyMatch[1] ?? "") : html;
  for (const s of Array.from(document.querySelectorAll("script"))) s.remove();
}

beforeEach(() => {
  fake = createChromeStorageFake();
  (globalThis as unknown as { chrome: unknown }).chrome = fake.chrome;
  document.body.innerHTML = "";
  vi.resetModules();
});

async function loadModule() {
  return import("../../src/options/options");
}

function makeServer(overrides: Partial<ServerConfig> = {}): ServerConfig {
  return {
    id: "srv-test-1",
    name: "My Boba",
    url: "https://boba.example.test:9999",
    active: true,
    authMethod: "api_key",
    username: null,
    encryptedPassword: null,
    encryptedApiKey: null,
    encryptedBobaApiToken: null,
    requestTimeout: 45000,
    verifySsl: false,
    defaultCategory: "movies",
    defaultSavePath: "/data/dl",
    startPaused: true,
    skipHashCheck: true,
    contentLayout: "subfolder",
    autoTMM: true,
    uploadLimit: 0,
    downloadLimit: 0,
    ...overrides,
  };
}

function makeConfig(overrides: Partial<ExtensionConfig> = {}): ExtensionConfig {
  return {
    ...DEFAULT_CONFIG,
    servers: [makeServer()],
    activeServerId: "srv-test-1",
    ...overrides,
  };
}

const input = (id: string): HTMLInputElement =>
  mustExist(document.getElementById(id), `#${id}`) as HTMLInputElement;

async function readStored(): Promise<ExtensionConfig> {
  const stored = (await fake.chrome.storage.local.get(STORAGE_KEYS.CONFIG))[
    STORAGE_KEYS.CONFIG
  ] as ExtensionConfig;
  return mustExist(stored, "persisted config");
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. requestTimeout SAVE direction — seconds field persisted as milliseconds.
//
// The sibling files assert only the LOAD direction (ms→seconds, "45000"→"45").
// The SAVE conversion (read seconds, persist `*1000` ms) is its own code path
// (options.ts:281) and is untested. A regression that dropped the `* 1000`
// (storing 30 instead of 30000) would silently break every server connection
// timeout while the load-direction test stayed green.
// ─────────────────────────────────────────────────────────────────────────────

describe("options save-flow — requestTimeout seconds field persists as milliseconds", () => {
  it("converts the seconds input to milliseconds on save (read back from storage)", async () => {
    await fake.chrome.storage.local.set({ [STORAGE_KEYS.CONFIG]: makeConfig() });
    loadOptionsMarkup();
    const { populateForm, saveOptions } = await loadModule();
    await populateForm(document);

    input("opt-server-url").value = "http://localhost:7187";
    input("opt-request-timeout").value = "12"; // 12 seconds
    await saveOptions(document);

    const stored = await readStored();
    // PROPERTY: the persisted requestTimeout is the entered seconds * 1000 (ms).
    // RED: a no-op/stub save, or a regression dropping the `* 1000`, persists 12
    // (or the unchanged 45000) — this assertion catches both.
    expect(stored.servers[0]?.requestTimeout).toBe(12000);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. Existing server SECRET + LIMIT fields are PRESERVED across a save.
//
// saveOptions rebuilds the server object (options.ts:329-349) carrying forward
// username / encryptedPassword / encryptedApiKey / uploadLimit / downloadLimit
// from the EXISTING stored server (the form has no controls for them). Neither
// sibling file asserts this — a regression that forgot to carry one forward
// would WIPE a stored credential on the next unrelated save (a save of the
// theme/notification toggle silently logging the user out). High-severity.
// ─────────────────────────────────────────────────────────────────────────────

describe("options save-flow — saving preserves stored secrets + rate limits the form cannot edit", () => {
  it("keeps username/encryptedPassword/encryptedApiKey/uploadLimit/downloadLimit after an unrelated save", async () => {
    const st:ServerConfig = makeServer({
      username: "alice",
      encryptedPassword: '{"ciphertext":"pw-blob"}',
      encryptedApiKey: '{"ciphertext":"key-blob"}',
      uploadLimit: 512,
      downloadLimit: 2048,
    });
    await fake.chrome.storage.local.set({
      [STORAGE_KEYS.CONFIG]: makeConfig({ servers: [st] }),
    });
    loadOptionsMarkup();
    const { populateForm, saveOptions } = await loadModule();
    await populateForm(document);

    // User edits ONLY an unrelated toggle and saves — no secret/limit control
    // exists in the form, so these MUST survive untouched.
    input("opt-server-url").value = "http://localhost:7187";
    input("opt-debug-mode").checked = true;
    await saveOptions(document);

    const persisted = (await readStored()).servers[0];
    // PROPERTY: secrets + limits the form cannot edit round-trip unchanged.
    // RED: a stub save (or a regression that rebuilds the server without
    // carrying these forward) drops them to null/0 — caught here field-by-field.
    expect(persisted?.username).toBe("alice");
    expect(persisted?.encryptedPassword).toBe('{"ciphertext":"pw-blob"}');
    expect(persisted?.encryptedApiKey).toBe('{"ciphertext":"key-blob"}');
    expect(persisted?.uploadLimit).toBe(512);
    expect(persisted?.downloadLimit).toBe(2048);
    // The id is also stable across the save (no churn that would orphan refs).
    expect(persisted?.id).toBe("srv-test-1");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. Multi-server config: editing the Server tab replaces ONLY servers[0]
//    and PRESERVES the remaining servers.
//
// saveOptions maps over current.servers replacing index 0 only (options.ts:
// 351-354). Both sibling files use a single-server config, so the
// preserve-the-rest branch is unexercised. A regression collapsing the list to
// `[server]` would DELETE every additional configured backend on the next save.
// ─────────────────────────────────────────────────────────────────────────────

describe("options save-flow — a multi-server config keeps the non-active servers", () => {
  it("replaces only servers[0] and preserves servers[1..] verbatim", async () => {
    const active = makeServer({ id: "srv-active", name: "Active" });
    const secondary = makeServer({
      id: "srv-secondary",
      name: "Secondary",
      url: "https://second.example.test:1234",
      username: "bob",
    });
    await fake.chrome.storage.local.set({
      [STORAGE_KEYS.CONFIG]: makeConfig({
        servers: [active, secondary],
        activeServerId: "srv-active",
      }),
    });
    loadOptionsMarkup();
    const { populateForm, saveOptions } = await loadModule();
    await populateForm(document);

    input("opt-server-name").value = "Active Renamed";
    input("opt-server-url").value = "http://localhost:7187";
    await saveOptions(document);

    const persisted = await readStored();
    // PROPERTY: the list keeps both servers; servers[0] reflects the edit,
    // servers[1] is byte-for-byte the stored secondary.
    // RED: a stub save (or a regression collapsing to `[server]`) loses the
    // secondary entirely — length + the servers[1] field checks catch it.
    expect(persisted.servers).toHaveLength(2);
    expect(persisted.servers[0]?.id).toBe("srv-active");
    expect(persisted.servers[0]?.name).toBe("Active Renamed");
    expect(persisted.servers[0]?.url).toBe("http://localhost:7187");
    expect(persisted.servers[1]?.id).toBe("srv-secondary");
    expect(persisted.servers[1]?.name).toBe("Secondary");
    expect(persisted.servers[1]?.url).toBe("https://second.example.test:1234");
    expect(persisted.servers[1]?.username).toBe("bob");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. loadConfig falls back to DEFAULT_CONFIG when storage read throws.
//
// loadConfig wraps storageGet in try/catch and returns DEFAULT_CONFIG on error
// (options.ts:169-177). Neither sibling file exercises the error path — they
// only test the happy read + the no-config (undefined) path. A regression that
// rethrew (or returned undefined) here would crash the options page on a
// transient storage error instead of degrading gracefully to defaults.
// ─────────────────────────────────────────────────────────────────────────────

describe("options save-flow — loadConfig degrades to DEFAULT_CONFIG on a storage error", () => {
  it("returns DEFAULT_CONFIG (not a throw) when chrome.storage.get rejects", async () => {
    // Make the storage boundary throw — a legitimate boundary stub, not a stub
    // of the unit under test (loadConfig itself runs for real).
    fake.chrome.storage.local.get = vi
      .fn()
      .mockRejectedValue(new Error("storage unavailable"));

    const { loadConfig } = await loadModule();
    const cfg = await loadConfig();

    // PROPERTY: a storage failure yields the DEFAULT_CONFIG, never a throw.
    // RED: a no-op/stub returning undefined, or a regression rethrowing, fails
    // the resolves + identity assertions below.
    await expect(loadConfig()).resolves.toBeDefined();
    // Identity with DEFAULT_CONFIG proves the fallback object — not a partial or
    // an undefined — was returned. DEFAULT_CONFIG ships an empty servers list,
    // so assert that exact shape (no masking `?? fallback`, which would be a
    // self-satisfying bluff regardless of what loadConfig returned).
    expect(cfg).toEqual(DEFAULT_CONFIG);
    expect(cfg.servers).toEqual([]);
  });
});
