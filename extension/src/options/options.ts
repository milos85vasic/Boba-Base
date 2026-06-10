/**
 * @fileoverview Options page logic for BobaLink (7-tab settings UI).
 *
 * REFACTOR of the reference `src/options/options.ts` (disposition F = REFACTOR).
 * Loads the persisted {@link ExtensionConfig} from the committed storage layer,
 * populates the form fields across the seven tabs (Server / Download Prefs /
 * Queue / Notifications / Detection / UI / Security), and on save validates and
 * writes the updated config back to storage.
 *
 * SECURITY (§11.4.10): the reference encrypted credentials with a HARD-CODED
 * fixed passphrase literal (reference options.ts:327). That defect is
 * NOT ported. The BobaLink security model is delegate-by-default — the extension
 * stores no decryptable secret by default. The only optional secret is the Boba
 * API token (`encryptedBobaApiToken`). When the user supplies a token, it is
 * encrypted under a USER-ENTERED session passphrase (never a literal/empty one);
 * if the user does not also enter a passphrase, the token is left untouched and a
 * non-blocking notice is shown (full encryption wiring lands in Phase 7). No
 * literal key, no empty-string key, exists anywhere in this module.
 *
 * Usage / Inputs / Outputs / Side-effects:
 *   - Inputs:  the seven tabs' form controls (read by id from the active Document)
 *              + the persisted ExtensionConfig (chrome.storage.local).
 *   - Outputs: the populated form on load; the persisted ExtensionConfig on save.
 *   - Side-effects: writes STORAGE_KEYS.CONFIG via the committed storage module.
 *   - Dependencies: src/shared/storage, src/types/config, src/shared/constants,
 *                   src/shared/utils, src/shared/crypto, src/shared/logger.
 *
 * @module options/options
 */

import { createLogger } from "../shared/logger";
import { storageGet, storageSet } from "../shared/storage";
import { STORAGE_KEYS, DEFAULT_URLS } from "../shared/constants";
import { generateId, isValidHttpUrl } from "../shared/utils";
import { encrypt } from "../shared/crypto";
import {
  DEFAULT_CONFIG,
  type ExtensionConfig,
  type ServerConfig,
} from "../types/config";

const log = createLogger("Options");

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Default Boba server URL for the Server tab. The Boba foundation endpoint is
 * the merge service on :7187 (see constants port retarget), NOT the reference
 * qBittorrent :8080.
 */
export const DEFAULT_SERVER_URL: string = DEFAULT_URLS.FAST_API;

/** Element ids for the seven option tabs (panels) and their nav buttons. */
export const TAB_IDS = [
  "server",
  "download",
  "queue",
  "notifications",
  "detection",
  "ui",
  "security",
] as const;

export type TabId = (typeof TAB_IDS)[number];

// ─────────────────────────────────────────────────────────────────────────────
// Small typed DOM helpers (operate on an explicit Document so tests can pass a
// jsdom-loaded document; default to the ambient `document`).
// ─────────────────────────────────────────────────────────────────────────────

function input(doc: Document, id: string): HTMLInputElement | null {
  return doc.getElementById(id) as HTMLInputElement | null;
}

function setValue(doc: Document, id: string, value: string): void {
  const el = doc.getElementById(id) as
    | HTMLInputElement
    | HTMLSelectElement
    | null;
  if (el) el.value = value;
}

function setChecked(doc: Document, id: string, checked: boolean): void {
  const el = input(doc, id);
  if (el) el.checked = checked;
}

function readValue(doc: Document, id: string, fallback: string): string {
  const el = doc.getElementById(id) as
    | HTMLInputElement
    | HTMLSelectElement
    | null;
  return el ? el.value : fallback;
}

function readChecked(doc: Document, id: string, fallback: boolean): boolean {
  const el = input(doc, id);
  return el ? el.checked : fallback;
}

function readInt(doc: Document, id: string, fallback: number): number {
  const raw = readValue(doc, id, String(fallback)).trim();
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) ? n : fallback;
}

// ─────────────────────────────────────────────────────────────────────────────
// Config <-> single-server model
//
// The Server tab edits the FIRST (active) server in the config's servers list.
// We keep a stable id across save cycles so persistence round-trips cleanly.
// ─────────────────────────────────────────────────────────────────────────────

function firstServer(config: ExtensionConfig): ServerConfig | null {
  return config.servers.length > 0 ? (config.servers[0] ?? null) : null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Public API
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Read the persisted configuration, falling back to {@link DEFAULT_CONFIG}.
 *
 * @returns The stored ExtensionConfig, or DEFAULT_CONFIG when none is stored.
 */
export async function loadConfig(): Promise<ExtensionConfig> {
  try {
    const data = await storageGet<ExtensionConfig>(STORAGE_KEYS.CONFIG);
    if (data) return data;
  } catch (err) {
    log.error("Failed to load config", err);
  }
  return DEFAULT_CONFIG;
}

/**
 * Populate every tab's form controls from the given (or persisted) config.
 *
 * @param doc - Document hosting the options form.
 * @param preloaded - Optional already-loaded config (skips a storage read).
 * @returns The config that was used to populate the form.
 */
export async function populateForm(
  doc: Document = document,
  preloaded?: ExtensionConfig,
): Promise<ExtensionConfig> {
  const config = preloaded ?? (await loadConfig());
  const server = firstServer(config);

  // ── Server tab ────────────────────────────────────────────────────────────
  setValue(doc, "opt-server-name", server?.name ?? "Boba");
  setValue(doc, "opt-server-url", server?.url ?? DEFAULT_SERVER_URL);
  setValue(doc, "opt-server-auth", server?.authMethod ?? "none");
  setValue(
    doc,
    "opt-request-timeout",
    String(Math.round((server?.requestTimeout ?? 30000) / 1000)),
  );
  setValue(
    doc,
    "opt-health-interval",
    String(config.healthCheckInterval),
  );
  setChecked(doc, "opt-verify-ssl", server?.verifySsl ?? true);
  // Boba API token: never round-trip the encrypted blob into a visible input.
  // Show a placeholder-only field; presence is indicated, value is not exposed.
  const tokenEl = input(doc, "opt-boba-api-token");
  if (tokenEl) {
    tokenEl.value = "";
    tokenEl.placeholder = server?.encryptedBobaApiToken
      ? "•••••• (token set — leave blank to keep)"
      : "Optional Boba API token";
  }
  // Passphrase field is ALWAYS blank on load — never seeded with any literal.
  setValue(doc, "opt-token-passphrase", "");

  // ── Download Prefs tab ──────────────────────────────────────────────────────
  setValue(doc, "opt-default-category", server?.defaultCategory ?? "");
  setValue(doc, "opt-default-savepath", server?.defaultSavePath ?? "");
  setChecked(doc, "opt-start-paused", server?.startPaused ?? false);
  setChecked(doc, "opt-skip-hashcheck", server?.skipHashCheck ?? false);
  setValue(doc, "opt-content-layout", server?.contentLayout ?? "original");
  setChecked(doc, "opt-auto-tmm", server?.autoTMM ?? false);

  // ── Queue tab ───────────────────────────────────────────────────────────────
  setValue(doc, "opt-max-queue", String(config.maxOfflineQueueSize));
  setValue(doc, "opt-max-history", String(config.maxHistoryItems));
  setChecked(doc, "opt-offline-queue", config.offlineQueue);

  // ── Notifications tab ───────────────────────────────────────────────────────
  setChecked(doc, "opt-show-notifications", config.showNotifications);
  setChecked(doc, "opt-notification-sound", config.notificationSound);
  setChecked(doc, "opt-auto-send", config.autoSend);

  // ── Detection tab ───────────────────────────────────────────────────────────
  setChecked(doc, "opt-auto-scan", config.autoScan);
  setValue(doc, "opt-auto-scan-delay", String(config.autoScanDelay));
  setChecked(doc, "opt-highlight", config.highlightTorrents);
  setValue(doc, "opt-highlight-style", config.highlightStyle);

  // ── UI tab ──────────────────────────────────────────────────────────────────
  setChecked(doc, "opt-show-context-menu", config.showContextMenu);
  setChecked(doc, "opt-keyboard-shortcuts", config.keyboardShortcuts);

  // ── Security tab ────────────────────────────────────────────────────────────
  setChecked(doc, "opt-debug-mode", config.debugMode);

  return config;
}

/**
 * Read the seven tabs' controls, merge onto the persisted config, validate, and
 * persist the result. The Server tab edits the first/active server (creating one
 * if none exists).
 *
 * @param doc - Document hosting the options form.
 * @returns The persisted ExtensionConfig.
 * @throws Error when the server URL is not a valid http(s) URL.
 */
export async function saveOptions(
  doc: Document = document,
): Promise<ExtensionConfig> {
  const current = await loadConfig();
  const existing = firstServer(current);

  // ── Server tab ────────────────────────────────────────────────────────────
  const url = readValue(doc, "opt-server-url", DEFAULT_SERVER_URL).trim();
  if (!isValidHttpUrl(url)) {
    throw new Error(`Invalid server URL: "${url}" (must be http:// or https://)`);
  }
  const name = readValue(doc, "opt-server-name", "Boba").trim() || "Boba";
  const authMethod = readValue(
    doc,
    "opt-server-auth",
    "none",
  ) as ServerConfig["authMethod"];
  const requestTimeout =
    readInt(doc, "opt-request-timeout", 30) * 1000 || 30000;
  const verifySsl = readChecked(doc, "opt-verify-ssl", true);

  // ── Boba API token (the ONLY optional secret) ───────────────────────────────
  // §11.4.10: encrypt the token ONLY under a USER-SUPPLIED session passphrase.
  // No literal/empty passphrase is ever used. If the user enters a token but no
  // passphrase, the token is NOT stored (we keep the prior value) and a notice
  // is surfaced — the forbidden thing is auto-encrypting with a fixed key.
  let encryptedBobaApiToken: string | null =
    existing?.encryptedBobaApiToken ?? null;
  const tokenPlain = readValue(doc, "opt-boba-api-token", "");
  const tokenPassphrase = readValue(doc, "opt-token-passphrase", "");
  if (tokenPlain.length > 0) {
    if (tokenPassphrase.length > 0) {
      try {
        const bundle = await encrypt(tokenPlain, tokenPassphrase);
        encryptedBobaApiToken = JSON.stringify(bundle);
      } catch (err) {
        log.error("Failed to encrypt Boba API token", err);
        throw new Error("Failed to encrypt Boba API token");
      }
    } else {
      // No passphrase supplied — refuse to auto-encrypt (anti-§11.4.10).
      // TODO(Phase 7): wire a session-passphrase prompt + unlock flow.
      showNotice(
        doc,
        "Enter a session passphrase to store the Boba API token. Token not saved.",
        "warn",
      );
      log.warn("Boba API token entered without a passphrase — not stored");
    }
  }

  // ── Download Prefs tab ──────────────────────────────────────────────────────
  const defaultCategory =
    readValue(doc, "opt-default-category", "").trim() || null;
  const defaultSavePath =
    readValue(doc, "opt-default-savepath", "").trim() || null;
  const startPaused = readChecked(doc, "opt-start-paused", false);
  const skipHashCheck = readChecked(doc, "opt-skip-hashcheck", false);
  const contentLayout = readValue(
    doc,
    "opt-content-layout",
    "original",
  ) as ServerConfig["contentLayout"];
  const autoTMM = readChecked(doc, "opt-auto-tmm", false);

  const serverId = existing?.id ?? generateId();
  const server: ServerConfig = {
    id: serverId,
    name,
    url,
    active: true,
    authMethod,
    username: existing?.username ?? null,
    encryptedPassword: existing?.encryptedPassword ?? null,
    encryptedApiKey: existing?.encryptedApiKey ?? null,
    encryptedBobaApiToken,
    requestTimeout,
    verifySsl,
    defaultCategory,
    defaultSavePath,
    startPaused,
    skipHashCheck,
    contentLayout,
    autoTMM,
    uploadLimit: existing?.uploadLimit ?? 0,
    downloadLimit: existing?.downloadLimit ?? 0,
  };

  const servers: readonly ServerConfig[] =
    current.servers.length > 0
      ? current.servers.map((s, i) => (i === 0 ? server : s))
      : [server];

  // ── Remaining tabs merged onto the extension-level config ───────────────────
  const next: ExtensionConfig = {
    ...current,
    servers,
    activeServerId: serverId,

    // Queue
    maxOfflineQueueSize: readInt(
      doc,
      "opt-max-queue",
      current.maxOfflineQueueSize,
    ),
    maxHistoryItems: readInt(doc, "opt-max-history", current.maxHistoryItems),
    offlineQueue: readChecked(doc, "opt-offline-queue", current.offlineQueue),

    // Server tab (extension-level)
    healthCheckInterval: readInt(
      doc,
      "opt-health-interval",
      current.healthCheckInterval,
    ),

    // Notifications
    showNotifications: readChecked(
      doc,
      "opt-show-notifications",
      current.showNotifications,
    ),
    notificationSound: readChecked(
      doc,
      "opt-notification-sound",
      current.notificationSound,
    ),
    autoSend: readChecked(doc, "opt-auto-send", current.autoSend),

    // Detection
    autoScan: readChecked(doc, "opt-auto-scan", current.autoScan),
    autoScanDelay: readInt(doc, "opt-auto-scan-delay", current.autoScanDelay),
    highlightTorrents: readChecked(
      doc,
      "opt-highlight",
      current.highlightTorrents,
    ),
    highlightStyle: readValue(
      doc,
      "opt-highlight-style",
      current.highlightStyle,
    ) as ExtensionConfig["highlightStyle"],

    // UI
    showContextMenu: readChecked(
      doc,
      "opt-show-context-menu",
      current.showContextMenu,
    ),
    keyboardShortcuts: readChecked(
      doc,
      "opt-keyboard-shortcuts",
      current.keyboardShortcuts,
    ),

    // Security
    debugMode: readChecked(doc, "opt-debug-mode", current.debugMode),

    lastUpdated: Date.now(),
  };

  await storageSet(STORAGE_KEYS.CONFIG, next);
  showNotice(doc, "Settings saved", "success");
  log.info("Options saved");
  return next;
}

// ─────────────────────────────────────────────────────────────────────────────
// Navigation + wiring
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Wire the tab navigation: clicking a nav button shows its panel and marks it
 * selected (ARIA `aria-selected` + the `.active` class).
 *
 * @param doc - Document hosting the options form.
 */
export function setupTabs(doc: Document = document): void {
  const tabs = doc.querySelectorAll<HTMLElement>("[role='tab'][data-tab]");
  for (const tab of Array.from(tabs)) {
    tab.addEventListener("click", () => {
      const target = tab.getAttribute("data-tab");
      if (!target) return;
      activateTab(doc, target);
    });
  }
}

/**
 * Activate a single tab by id (panel + nav state).
 *
 * @param doc - Document hosting the options form.
 * @param tabId - Tab id to activate (one of {@link TAB_IDS}).
 */
export function activateTab(doc: Document, tabId: string): void {
  for (const tab of Array.from(
    doc.querySelectorAll<HTMLElement>("[role='tab'][data-tab]"),
  )) {
    const selected = tab.getAttribute("data-tab") === tabId;
    tab.classList.toggle("active", selected);
    tab.setAttribute("aria-selected", selected ? "true" : "false");
    tab.tabIndex = selected ? 0 : -1;
  }
  for (const panel of Array.from(
    doc.querySelectorAll<HTMLElement>("[role='tabpanel']"),
  )) {
    const show = panel.id === `panel-${tabId}`;
    panel.classList.toggle("active", show);
    panel.hidden = !show;
  }
}

/**
 * Show a transient notice in the save-status region (`aria-live`).
 *
 * @param doc - Document hosting the options form.
 * @param message - Message text.
 * @param kind - Visual kind.
 */
function showNotice(
  doc: Document,
  message: string,
  kind: "success" | "warn" | "error",
): void {
  const el = doc.getElementById("opt-save-status");
  if (!el) return;
  el.textContent = message;
  el.className = `save-status save-status--${kind}`;
}

/**
 * Initialize the options page: wire tabs, the save button, and populate the
 * form from the persisted config.
 *
 * @param doc - Document hosting the options form.
 * @returns The config used to populate the form.
 */
export async function initOptions(
  doc: Document = document,
): Promise<ExtensionConfig> {
  setupTabs(doc);
  activateTab(doc, TAB_IDS[0]);

  doc.getElementById("opt-save")?.addEventListener("click", () => {
    saveOptions(doc).catch((err) => {
      log.error("Save failed", err);
      showNotice(
        doc,
        err instanceof Error ? err.message : "Failed to save settings",
        "error",
      );
    });
  });

  return populateForm(doc);
}

// ─────────────────────────────────────────────────────────────────────────────
// Entry point (skipped under test, where the module is imported, not auto-run)
// ─────────────────────────────────────────────────────────────────────────────

/* c8 ignore start -- browser-only auto-bootstrap, exercised via initOptions in tests */
if (typeof document !== "undefined" && typeof process === "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      void initOptions();
    });
  } else {
    void initOptions();
  }
}
/* c8 ignore stop */
