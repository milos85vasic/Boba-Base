/**
 * @fileoverview UI/UX render-correctness + state-rendering tests for the REAL
 * options module (the 13-type-matrix UI/UX cells — §11.4 anti-bluff).
 *
 * Sibling to `options.test.ts` (which covers populate-all-fields, save-persists,
 * invalid-URL-rejects, basic tab show/hide, token encryption, and the §11.4.10
 * source grep). This file ADDS the UX-specific render + state cases that file
 * does NOT cover:
 *
 *   - tab switching shows the right panel AND hides the others (panel-by-panel,
 *     all seven), via the real click wiring from `initOptions`;
 *   - keyboard tab navigation (ArrowRight / ArrowLeft / Home / End) moves the
 *     activation + roving tabindex (WAI-ARIA automatic-activation pattern);
 *   - form fields populate into the CORRECT per-tab panels from a distinct config;
 *   - an invalid server URL surfaces a validation error in the save-status region
 *     (the user-visible UX surface) and does NOT persist;
 *   - the save-status announces success text + the success class after a valid save;
 *   - numeric-field behaviour: this build performs NO numeric validation — the
 *     test asserts the ACTUAL behaviour (negative accepted, non-numeric falls
 *     back) and the gap is reported as a finding (NOT a non-existent rejection).
 *
 * Every assertion inspects user-observable DOM (visibility / textContent /
 * classes / value / tabindex) and fails if the UX behaviour broke. The real
 * `src/entrypoints/options/index.html` body + the real options module are used.
 *
 * @module tests/unit/options-ux.test
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

/** Assert a value is present, returning it narrowed (stronger than `!`). */
function mustExist<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`expected ${what} to exist`);
  }
  return value;
}

/** Flush microtasks so the async save click handler settles. */
async function flush(): Promise<void> {
  for (let i = 0; i < 4; i++) await Promise.resolve();
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

const el = (id: string): HTMLElement =>
  mustExist(document.getElementById(id), `#${id}`);
const input = (id: string): HTMLInputElement => el(id) as HTMLInputElement;

const PANEL_IDS = [
  "panel-server",
  "panel-download",
  "panel-queue",
  "panel-notifications",
  "panel-detection",
  "panel-ui",
  "panel-security",
] as const;

/** Assert exactly one panel is visible and it is `expectedPanelId`. */
function expectOnlyPanelVisible(expectedPanelId: string): void {
  for (const pid of PANEL_IDS) {
    const panel = el(pid);
    if (pid === expectedPanelId) {
      expect(panel.hidden, `${pid} should be visible`).toBe(false);
    } else {
      expect(panel.hidden, `${pid} should be hidden`).toBe(true);
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab switching shows the right panel + hides the others (all seven)
// ─────────────────────────────────────────────────────────────────────────────

describe("options UX — tab switching shows exactly one panel", () => {
  it("starts on the Server tab with only its panel visible after init", async () => {
    loadOptionsMarkup();
    const { initOptions } = await loadModule();
    await initOptions(document);

    expectOnlyPanelVisible("panel-server");
    expect(el("tab-server").getAttribute("aria-selected")).toBe("true");
  });

  it("clicking each tab reveals only that tab's panel and selects it", async () => {
    loadOptionsMarkup();
    const { initOptions } = await loadModule();
    await initOptions(document);

    const cases: Array<[string, string]> = [
      ["tab-download", "panel-download"],
      ["tab-queue", "panel-queue"],
      ["tab-notifications", "panel-notifications"],
      ["tab-detection", "panel-detection"],
      ["tab-ui", "panel-ui"],
      ["tab-security", "panel-security"],
      ["tab-server", "panel-server"],
    ];
    for (const [tabId, panelId] of cases) {
      (el(tabId) as HTMLButtonElement).click();
      expectOnlyPanelVisible(panelId);
      expect(el(tabId).getAttribute("aria-selected"), `${tabId} selected`).toBe(
        "true",
      );
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Keyboard tab navigation (WAI-ARIA automatic activation)
// ─────────────────────────────────────────────────────────────────────────────

describe("options UX — keyboard tab navigation", () => {
  function press(tabId: string, key: string): void {
    el(tabId).dispatchEvent(
      new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }),
    );
  }

  it("ArrowRight moves activation + roving tabindex to the next tab", async () => {
    loadOptionsMarkup();
    const { initOptions } = await loadModule();
    await initOptions(document);

    // Start on server (index 0); ArrowRight → download.
    press("tab-server", "ArrowRight");

    expectOnlyPanelVisible("panel-download");
    expect(el("tab-download").getAttribute("aria-selected")).toBe("true");
    // Roving tabindex: active tab is focusable (0), previous is removed (-1).
    expect((el("tab-download") as HTMLButtonElement).tabIndex).toBe(0);
    expect((el("tab-server") as HTMLButtonElement).tabIndex).toBe(-1);
  });

  it("ArrowLeft wraps from the first tab to the last", async () => {
    loadOptionsMarkup();
    const { initOptions } = await loadModule();
    await initOptions(document);

    press("tab-server", "ArrowLeft");

    expectOnlyPanelVisible("panel-security");
    expect(el("tab-security").getAttribute("aria-selected")).toBe("true");
  });

  it("Home / End jump to the first / last tab", async () => {
    loadOptionsMarkup();
    const { initOptions } = await loadModule();
    await initOptions(document);

    press("tab-server", "End");
    expectOnlyPanelVisible("panel-security");

    press("tab-security", "Home");
    expectOnlyPanelVisible("panel-server");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Fields populate into the CORRECT per-tab panels
// ─────────────────────────────────────────────────────────────────────────────

describe("options UX — fields populate into their owning panels", () => {
  it("each populated field lives inside the panel for its tab", async () => {
    await fake.chrome.storage.local.set({
      [STORAGE_KEYS.CONFIG]: makeConfig(),
    });
    loadOptionsMarkup();
    const { initOptions } = await loadModule();
    await initOptions(document);

    // A representative field per panel carries the loaded value AND is a
    // descendant of the correct panel (so switching to that tab shows it).
    const checks: Array<[string, string, string]> = [
      ["opt-server-url", "panel-server", "https://boba.example.test:9999"],
      ["opt-default-category", "panel-download", "movies"],
      ["opt-max-history", "panel-queue", "42"],
      ["opt-auto-scan-delay", "panel-detection", "5000"],
    ];
    for (const [fieldId, panelId, value] of checks) {
      const field = input(fieldId);
      expect(field.value, `${fieldId} value`).toBe(value);
      expect(
        el(panelId).contains(field),
        `${fieldId} should live inside ${panelId}`,
      ).toBe(true);
    }

    // A boolean reaches the right checkbox in the Security panel.
    expect(input("opt-debug-mode").checked).toBe(true);
    expect(el("panel-security").contains(input("opt-debug-mode"))).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Save-status UX surface — error on invalid URL, success on valid save
// ─────────────────────────────────────────────────────────────────────────────

describe("options UX — save-status announces validation + success", () => {
  it("surfaces an error in the save-status region for an invalid URL (no persist)", async () => {
    loadOptionsMarkup();
    const { initOptions } = await loadModule();
    await initOptions(document);

    input("opt-server-url").value = "ftp://nope";
    // Drive the REAL user path: click the save button (wired by initOptions),
    // which catches the validation throw and renders it into save-status.
    (el("opt-save") as HTMLButtonElement).click();
    await flush();

    const status = el("opt-save-status");
    expect(status.textContent ?? "").toMatch(/invalid server url/i);
    expect(status.className).toContain("save-status--error");
    expect(status.className).not.toContain("save-status--success");

    // Nothing persisted.
    const stored = await fake.chrome.storage.local.get(STORAGE_KEYS.CONFIG);
    expect(stored[STORAGE_KEYS.CONFIG]).toBeUndefined();
  });

  it("announces success in the save-status region after a valid save", async () => {
    loadOptionsMarkup();
    const { initOptions } = await loadModule();
    await initOptions(document);

    input("opt-server-url").value = "http://localhost:7187";
    (el("opt-save") as HTMLButtonElement).click();
    await flush();

    const status = el("opt-save-status");
    expect(status.textContent ?? "").toMatch(/saved/i);
    expect(status.className).toContain("save-status--success");

    // The config actually persisted (the success message is not a bluff).
    const stored = (await fake.chrome.storage.local.get(STORAGE_KEYS.CONFIG))[
      STORAGE_KEYS.CONFIG
    ] as ExtensionConfig;
    expect(stored?.servers[0]?.url).toBe("http://localhost:7187");
  });

  it("shows a non-blocking warning when a token is entered without a passphrase", async () => {
    loadOptionsMarkup();
    const { initOptions } = await loadModule();
    await initOptions(document);

    input("opt-server-url").value = "http://localhost:7187";
    input("opt-boba-api-token").value = "tok-without-pass";
    // passphrase left blank
    (el("opt-save") as HTMLButtonElement).click();
    await flush();

    // The save-status surfaces the warning UX (token NOT saved).
    const status = el("opt-save-status");
    expect(status.textContent ?? "").toMatch(/passphrase/i);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Numeric-field behaviour — documents the ACTUAL (no-validation) behaviour
//
// FINDING: this build performs NO numeric validation/clamping. `saveOptions`
// reads numeric fields via `readInt` (Number.parseInt + finite-fallback), so:
//   - a NEGATIVE value is parsed and persisted as-is (NOT rejected/clamped);
//   - a NON-NUMERIC value silently falls back to the prior persisted value
//     (NO error is surfaced).
// These tests assert the real behaviour (anti-bluff: they would fail if the
// behaviour silently changed) rather than a rejection the code does not do.
// ─────────────────────────────────────────────────────────────────────────────

describe("options UX — numeric fields (current no-validation behaviour)", () => {
  it("persists a negative numeric value as-is (no clamping — see FINDING)", async () => {
    await fake.chrome.storage.local.set({
      [STORAGE_KEYS.CONFIG]: makeConfig({ maxOfflineQueueSize: 50 }),
    });
    loadOptionsMarkup();
    const { initOptions } = await loadModule();
    await initOptions(document);

    input("opt-server-url").value = "http://localhost:7187";
    input("opt-max-queue").value = "-5";
    (el("opt-save") as HTMLButtonElement).click();
    await flush();

    const stored = (await fake.chrome.storage.local.get(STORAGE_KEYS.CONFIG))[
      STORAGE_KEYS.CONFIG
    ] as ExtensionConfig;
    // Documents that NO validation rejects/clamps the negative value.
    expect(stored.maxOfflineQueueSize).toBe(-5);
    // No error was surfaced — the save reported success.
    expect(el("opt-save-status").className).toContain("save-status--success");
  });

  it("falls back to the prior value for a non-numeric entry (silently)", async () => {
    await fake.chrome.storage.local.set({
      [STORAGE_KEYS.CONFIG]: makeConfig({ maxHistoryItems: 123 }),
    });
    loadOptionsMarkup();
    const { initOptions } = await loadModule();
    await initOptions(document);

    input("opt-server-url").value = "http://localhost:7187";
    input("opt-max-history").value = "not-a-number";
    (el("opt-save") as HTMLButtonElement).click();
    await flush();

    const stored = (await fake.chrome.storage.local.get(STORAGE_KEYS.CONFIG))[
      STORAGE_KEYS.CONFIG
    ] as ExtensionConfig;
    // Non-numeric → readInt fallback to the loaded value (123), not NaN/0.
    expect(stored.maxHistoryItems).toBe(123);
    expect(el("opt-save-status").className).toContain("save-status--success");
  });
});
