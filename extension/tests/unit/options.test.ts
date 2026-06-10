/**
 * @fileoverview Anti-bluff unit tests for the REAL options module (§11.4 / §11.4.69).
 *
 * Imports the production `src/options/options.ts` and drives it against:
 *   - the real `src/options/index.html` parsed into a jsdom document, and
 *   - the in-memory chrome.storage fake (tests/unit/chrome-fake.ts) installed on
 *     globalThis so the committed storage module persists for real.
 *
 * Asserts USER-OBSERVABLE outcomes — not status codes:
 *   - load populates the seven tabs' inputs from a persisted ExtensionConfig;
 *   - the default Server URL is :7187 when no config is stored;
 *   - changing a field + save writes the new config to storage (read back);
 *   - tab navigation shows/hides the right panels (real DOM state);
 *   - §11.4.10 guard: the BUILT options source contains NO hard-coded passphrase
 *     (`"bobalink-extension"`) and no literal/empty encryption key.
 *
 * Each assertion fails against a no-op stub (see the RED/anti-bluff notes).
 *
 * @module tests/unit/options.test
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

// Vitest runs with cwd = the extension/ project root (where vitest.config.ts is).
const OPTIONS_HTML_PATH = resolve(process.cwd(), "src/options/index.html");
const OPTIONS_TS_PATH = resolve(process.cwd(), "src/options/options.ts");

/**
 * Assert a value is present, returning it narrowed. A real assertion — if the
 * element is missing the test fails here (stronger than `!`, which would
 * silently pass a `null` to the next access).
 */
function mustExist<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`expected ${what} to exist`);
  }
  return value;
}

let fake: ReturnType<typeof createChromeStorageFake>;

/** Parse the real options markup into the jsdom document. */
function loadOptionsMarkup(): void {
  const html = readFileSync(OPTIONS_HTML_PATH, "utf8");
  const bodyMatch = /<body[^>]*>([\s\S]*?)<\/body>/i.exec(html);
  document.body.innerHTML = bodyMatch ? (bodyMatch[1] ?? "") : html;
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

/** A fully-populated server config distinct from defaults, for round-trips. */
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
    autoScan: false,
    autoScanDelay: 5000,
    highlightTorrents: false,
    highlightStyle: "glow",
    showNotifications: false,
    notificationSound: true,
    autoSend: true,
    maxHistoryItems: 42,
    debugMode: true,
    healthCheckInterval: 9,
    offlineQueue: false,
    maxOfflineQueueSize: 7,
    showContextMenu: false,
    keyboardShortcuts: false,
    ...overrides,
  };
}

const val = (id: string): string =>
  (document.getElementById(id) as HTMLInputElement | HTMLSelectElement).value;
const checked = (id: string): boolean =>
  (document.getElementById(id) as HTMLInputElement).checked;

// ─────────────────────────────────────────────────────────────────────────────
// Default server URL
// ─────────────────────────────────────────────────────────────────────────────

describe("default server URL", () => {
  it("exposes :7187 as the default Boba server URL", async () => {
    const { DEFAULT_SERVER_URL } = await loadModule();
    expect(DEFAULT_SERVER_URL).toBe("http://localhost:7187");
  });

  it("populates the Server URL field with :7187 when no config is stored", async () => {
    loadOptionsMarkup();
    const { populateForm } = await loadModule();
    await populateForm(document);
    expect(val("opt-server-url")).toBe("http://localhost:7187");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Load populates the form
// ─────────────────────────────────────────────────────────────────────────────

describe("populateForm — load populates the seven tabs from a persisted config", () => {
  it("reflects every persisted value into its input", async () => {
    const config = makeConfig();
    await fake.chrome.storage.local.set({ [STORAGE_KEYS.CONFIG]: config });

    loadOptionsMarkup();
    const { populateForm } = await loadModule();
    await populateForm(document);

    // Server tab
    expect(val("opt-server-name")).toBe("My Boba");
    expect(val("opt-server-url")).toBe("https://boba.example.test:9999");
    expect(val("opt-server-auth")).toBe("api_key");
    expect(val("opt-request-timeout")).toBe("45"); // 45000ms -> 45s
    expect(val("opt-health-interval")).toBe("9");
    expect(checked("opt-verify-ssl")).toBe(false);

    // Download Prefs tab
    expect(val("opt-default-category")).toBe("movies");
    expect(val("opt-default-savepath")).toBe("/data/dl");
    expect(val("opt-content-layout")).toBe("subfolder");
    expect(checked("opt-start-paused")).toBe(true);
    expect(checked("opt-skip-hashcheck")).toBe(true);
    expect(checked("opt-auto-tmm")).toBe(true);

    // Queue tab
    expect(val("opt-max-queue")).toBe("7");
    expect(val("opt-max-history")).toBe("42");
    expect(checked("opt-offline-queue")).toBe(false);

    // Notifications tab
    expect(checked("opt-show-notifications")).toBe(false);
    expect(checked("opt-notification-sound")).toBe(true);
    expect(checked("opt-auto-send")).toBe(true);

    // Detection tab
    expect(checked("opt-auto-scan")).toBe(false);
    expect(val("opt-auto-scan-delay")).toBe("5000");
    expect(checked("opt-highlight")).toBe(false);
    expect(val("opt-highlight-style")).toBe("glow");

    // UI tab
    expect(checked("opt-show-context-menu")).toBe(false);
    expect(checked("opt-keyboard-shortcuts")).toBe(false);

    // Security tab
    expect(checked("opt-debug-mode")).toBe(true);
  });

  it("never seeds the token or passphrase fields with any value", async () => {
    const config = makeConfig({
      servers: [makeServer({ encryptedBobaApiToken: '{"some":"blob"}' })],
    });
    await fake.chrome.storage.local.set({ [STORAGE_KEYS.CONFIG]: config });

    loadOptionsMarkup();
    const { populateForm } = await loadModule();
    await populateForm(document);

    // The encrypted blob is NEVER round-tripped into a visible value.
    expect(val("opt-boba-api-token")).toBe("");
    expect(val("opt-token-passphrase")).toBe("");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Save persists the change (read it back)
// ─────────────────────────────────────────────────────────────────────────────

describe("saveOptions — changing a field then saving persists to storage", () => {
  it("persists a changed Server URL and a changed checkbox", async () => {
    await fake.chrome.storage.local.set({
      [STORAGE_KEYS.CONFIG]: makeConfig(),
    });
    loadOptionsMarkup();
    const { populateForm, saveOptions } = await loadModule();
    await populateForm(document);

    // User edits two fields across two tabs.
    (document.getElementById("opt-server-url") as HTMLInputElement).value =
      "http://localhost:7187";
    (document.getElementById("opt-auto-send") as HTMLInputElement).checked =
      false;
    (document.getElementById("opt-max-queue") as HTMLInputElement).value =
      "1000";

    const returned = await saveOptions(document);

    // Returned config reflects the edits.
    expect(returned.servers[0]?.url).toBe("http://localhost:7187");
    expect(returned.autoSend).toBe(false);
    expect(returned.maxOfflineQueueSize).toBe(1000);

    // Read back from storage independently — the change actually persisted.
    const stored = (await fake.chrome.storage.local.get(STORAGE_KEYS.CONFIG))[
      STORAGE_KEYS.CONFIG
    ] as ExtensionConfig;
    expect(stored.servers[0]?.url).toBe("http://localhost:7187");
    expect(stored.autoSend).toBe(false);
    expect(stored.maxOfflineQueueSize).toBe(1000);
    expect(stored.lastUpdated).toBeGreaterThan(0);
  });

  it("creates a server from the form when none exists, with the default URL", async () => {
    // No config stored at all.
    loadOptionsMarkup();
    const { populateForm, saveOptions } = await loadModule();
    await populateForm(document);

    (document.getElementById("opt-server-name") as HTMLInputElement).value =
      "Fresh";
    const returned = await saveOptions(document);

    expect(returned.servers).toHaveLength(1);
    expect(returned.servers[0]?.name).toBe("Fresh");
    expect(returned.servers[0]?.url).toBe("http://localhost:7187");

    const stored = (await fake.chrome.storage.local.get(STORAGE_KEYS.CONFIG))[
      STORAGE_KEYS.CONFIG
    ] as ExtensionConfig;
    expect(stored.servers[0]?.name).toBe("Fresh");
  });

  it("rejects an invalid (non-http) server URL", async () => {
    loadOptionsMarkup();
    const { populateForm, saveOptions } = await loadModule();
    await populateForm(document);

    (document.getElementById("opt-server-url") as HTMLInputElement).value =
      "ftp://nope";
    await expect(saveOptions(document)).rejects.toThrow(/invalid server url/i);

    // Nothing was persisted.
    const stored = await fake.chrome.storage.local.get(STORAGE_KEYS.CONFIG);
    expect(stored[STORAGE_KEYS.CONFIG]).toBeUndefined();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Boba API token (§11.4.10 — user-supplied passphrase only)
// ─────────────────────────────────────────────────────────────────────────────

describe("Boba API token encryption uses a user-supplied passphrase", () => {
  it("encrypts the token under the entered passphrase and persists a non-plaintext blob", async () => {
    loadOptionsMarkup();
    const { populateForm, saveOptions } = await loadModule();
    await populateForm(document);

    (document.getElementById("opt-boba-api-token") as HTMLInputElement).value =
      "super-secret-token-value";
    (
      document.getElementById("opt-token-passphrase") as HTMLInputElement
    ).value = "my-session-pass";

    const returned = await saveOptions(document);
    const blob = returned.servers[0]?.encryptedBobaApiToken;
    expect(typeof blob).toBe("string");
    // Stored value is an encrypted bundle, NOT the plaintext token.
    expect(blob).not.toContain("super-secret-token-value");
    expect(blob).toMatch(/"ciphertext"/);
  });

  it("does NOT store the token when no passphrase is supplied (anti-fixed-key)", async () => {
    loadOptionsMarkup();
    const { populateForm, saveOptions } = await loadModule();
    await populateForm(document);

    (document.getElementById("opt-boba-api-token") as HTMLInputElement).value =
      "token-without-pass";
    // passphrase left blank
    const returned = await saveOptions(document);
    expect(returned.servers[0]?.encryptedBobaApiToken ?? null).toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Tab navigation (real DOM state)
// ─────────────────────────────────────────────────────────────────────────────

describe("tab navigation", () => {
  it("shows only the activated panel and marks its tab selected", async () => {
    loadOptionsMarkup();
    const { setupTabs, activateTab } = await loadModule();
    setupTabs(document);

    activateTab(document, "security");

    const securityPanel = mustExist(document.getElementById("panel-security"), "#panel-security");
    const serverPanel = mustExist(document.getElementById("panel-server"), "#panel-server");
    expect(securityPanel.hidden).toBe(false);
    expect(serverPanel.hidden).toBe(true);
    expect(
      mustExist(document.getElementById("tab-security"), "#tab-security").getAttribute("aria-selected"),
    ).toBe("true");
    expect(
      mustExist(document.getElementById("tab-server"), "#tab-server").getAttribute("aria-selected"),
    ).toBe("false");
  });

  it("clicking a tab button activates its panel", async () => {
    loadOptionsMarkup();
    const { setupTabs, activateTab } = await loadModule();
    setupTabs(document);
    activateTab(document, "server");

    (document.getElementById("tab-queue") as HTMLButtonElement).click();

    expect(mustExist(document.getElementById("panel-queue"), "#panel-queue").hidden).toBe(false);
    expect(mustExist(document.getElementById("panel-server"), "#panel-server").hidden).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// §11.4.10 — NO hard-coded passphrase / literal encryption key in the source
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.10 — no hard-coded passphrase / literal key", () => {
  const source = readFileSync(OPTIONS_TS_PATH, "utf8");

  it("does NOT contain the reference's fixed passphrase 'bobalink-extension'", () => {
    expect(source).not.toContain("bobalink-extension");
  });

  it("does NOT call encrypt() with a string/empty literal as the passphrase", () => {
    // encrypt(<plaintext>, <passphrase>) — the 2nd argument must never be a
    // string literal (a hard-coded key) or an empty string.
    const literalPassphrase =
      /encrypt\s*\(\s*[^,]+,\s*(?:""|''|`[^`]*`|"[^"]*"|'[^']*')\s*\)/;
    expect(literalPassphrase.test(source)).toBe(false);
  });

  it("encrypts only under the user-entered passphrase variable", () => {
    // The single encrypt() call passes the tokenPassphrase variable (read from
    // the form), proving the key is user-supplied, not a constant.
    expect(source).toMatch(/encrypt\s*\(\s*tokenPlain\s*,\s*tokenPassphrase\s*\)/);
  });
});
