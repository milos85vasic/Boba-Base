/**
 * @fileoverview Background service worker (MV3) for BobaLink — the message hub.
 *
 * This is the central hub of the extension. It:
 * - routes messages between content scripts, popup, and options page
 *   (`chrome.runtime.onMessage`),
 * - manages `chrome.contextMenus` for right-click actions and dispatches them,
 * - handles keyboard shortcuts (`chrome.commands`) — including sending the
 *   typed `scan-now` / `highlight-toggle` directives to the active tab's
 *   content script,
 * - runs a keep-alive alarm + a periodic health-check alarm (`chrome.alarms`),
 * - reflects the detected-torrent count on the action badge
 *   (`chrome.action.setBadgeText`) and raises `chrome.notifications`,
 * - on a send request reads config, builds the committed {@link BobaClient}
 *   (`POST /api/v1/download` on the Boba merge service :7187), and ENQUEUES
 *   into the committed {@link OfflineQueue} on failure.
 *
 * ## MV3 correctness
 * Top-level event listeners are registered SYNCHRONOUSLY from
 * {@link initBackground} (called once at module load when a real `chrome`
 * surface is present). Under unit test the module does NOT auto-register —
 * the test calls `initBackground()` explicitly against an installed fake — so
 * importing this module never touches a missing global.
 *
 * ## §11.4.10 — credentials
 * The configured Boba token (if any) is read from the active server's config
 * and passed to {@link BobaClient}, which sends it as a bearer header. The
 * token VALUE is NEVER logged here (only its presence is implied by behaviour);
 * the secure session-passphrase DECRYPT path is Phase 7. For now we read
 * whatever plaintext token the config exposes (`encryptedBobaApiToken`) or
 * `undefined` (→ default-open). No key is ever hard-coded.
 *
 * @module background/index
 */

import { BobaClient } from "../api/boba-client";
import { probeHealth, type HealthProbeResult } from "../api/health";
import { OfflineQueue, type OfflineQueueItem } from "../api/queue";
import {
  BADGE_COLORS,
  EXT,
  STORAGE_KEYS,
} from "../shared/constants";
import { createLogger, initLogger } from "../shared/logger";
import { storageGet, storageSet } from "../shared/storage";
import type { ExtensionMessage, ExtensionMessageResponse } from "../types/api";
import {
  DEFAULT_CONFIG,
  type ExtensionConfig,
  type ServerConfig,
} from "../types/config";
import type { DetectedTorrent, PageScanResult } from "../types/torrent";

const log = createLogger("Background");

// ─────────────────────────────────────────────────────────────────────────────
// Alarm + keep-alive intervals (minutes — chrome.alarms granularity)
// ─────────────────────────────────────────────────────────────────────────────

/** Keep-alive alarm name (touches storage to keep the SW from being torn down). */
const ALARM_KEEPALIVE = "keepalive";

/** Periodic health-check alarm name. */
const ALARM_HEALTH = "health-check";

/** Keep-alive period: ~20s (0.33 min) is the conventional MV3 keep-alive cadence. */
const KEEPALIVE_PERIOD_MIN = 0.33;

/** Health-check period (minutes); overridden per-config when available. */
const DEFAULT_HEALTH_PERIOD_MIN = 5;

// ─────────────────────────────────────────────────────────────────────────────
// In-memory state (per service-worker lifetime)
// ─────────────────────────────────────────────────────────────────────────────

/** Detected scan result keyed by tab id (the popup's `get-detected` source). */
const tabResults = new Map<number, PageScanResult>();

/** The offline retry queue (committed module; SEND injected at process time). */
const offlineQueue = new OfflineQueue();

/** Guards against double registration if `initBackground` is called twice. */
let registered = false;

// ─────────────────────────────────────────────────────────────────────────────
// Config helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Load the extension configuration from storage, falling back to defaults.
 *
 * @returns The persisted {@link ExtensionConfig} or a copy of the defaults.
 */
async function loadConfig(): Promise<ExtensionConfig> {
  try {
    const data = await storageGet<ExtensionConfig>(STORAGE_KEYS.CONFIG);
    return data ?? { ...DEFAULT_CONFIG };
  } catch {
    return { ...DEFAULT_CONFIG };
  }
}

/**
 * Resolve the currently-active server from a config (or null when none).
 *
 * @param config - The extension configuration.
 * @returns The active {@link ServerConfig}, or null.
 */
function activeServer(config: ExtensionConfig): ServerConfig | null {
  return (
    config.servers.find((s) => s.id === config.activeServerId) ??
    config.servers.find((s) => s.active) ??
    null
  );
}

/**
 * Build a {@link BobaClient} for a server, forwarding its plaintext token when
 * present. §11.4.10: the token value is never logged here.
 *
 * Phase 7: `encryptedBobaApiToken` will be decrypted with the session
 * passphrase via `shared/crypto.ts` before being passed here. For now the
 * field is read as-is (plaintext or undefined → default-open). No key is
 * hard-coded.
 *
 * @param server - The target server config.
 * @returns A configured {@link BobaClient}.
 */
function clientFor(server: ServerConfig): BobaClient {
  // Phase 7: decrypt `server.encryptedBobaApiToken` here before use.
  const token = server.encryptedBobaApiToken ?? undefined;
  return new BobaClient(
    token !== undefined && token !== null
      ? { baseUrl: server.url, token }
      : { baseUrl: server.url },
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Badge + notifications
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Reflect a count on the action badge (capped at 99) with a background color.
 *
 * @param count - Number to display (0 clears the badge).
 * @param color - Badge background color.
 */
function updateBadge(count: number, color: string): void {
  const text = count > 0 ? String(Math.min(count, 99)) : "";
  void chrome.action.setBadgeText({ text });
  void chrome.action.setBadgeBackgroundColor({ color });
}

/**
 * Raise a chrome notification.
 *
 * @param title - Notification title.
 * @param message - Notification body.
 * @param type - Severity (affects priority; error → 2).
 */
function notify(
  title: string,
  message: string,
  type: "info" | "success" | "warning" | "error",
): void {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "/icon-128.png",
    title,
    message,
    priority: type === "error" ? 2 : 1,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Torrent sending (real BobaClient → enqueue on failure)
// ─────────────────────────────────────────────────────────────────────────────

/** The structured result of one send attempt, reported back to the popup. */
interface SendOutcome {
  readonly id: string;
  readonly success: boolean;
  readonly displayName: string;
  readonly error: string | null;
}

/**
 * Extract the magnet URI (or `.torrent` URL) the backend should be handed for a
 * detected torrent.
 *
 * @param item - The detected torrent.
 * @returns The download URL, or null if the item carries neither.
 */
function downloadUrlOf(item: DetectedTorrent): string | null {
  return item.magnet?.uri ?? item.torrentFile?.url ?? null;
}

/**
 * Send the requested torrents from a tab's stored set to the active Boba
 * server via the committed {@link BobaClient}. Each FAILURE is enqueued into
 * the persisted {@link OfflineQueue} (the queue's SEND is the boba-client call).
 *
 * @param tabId - Tab whose detected set the ids refer to.
 * @param ids - Detected-torrent ids to send.
 * @returns Per-id {@link SendOutcome}s.
 */
async function sendTorrents(
  tabId: number,
  ids: readonly string[],
): Promise<readonly SendOutcome[]> {
  const config = await loadConfig();
  const server = activeServer(config);
  if (!server) {
    throw new Error("No active server configured");
  }

  const result = tabResults.get(tabId);
  if (!result) {
    throw new Error("No torrents detected for this tab");
  }

  const toSend = result.items.filter((i) => ids.includes(i.id));
  if (toSend.length === 0) {
    throw new Error("No matching torrents found");
  }

  const client = clientFor(server);
  const outcomes: SendOutcome[] = [];

  for (const item of toSend) {
    const url = downloadUrlOf(item);
    if (url === null) {
      outcomes.push({
        id: item.id,
        success: false,
        displayName: item.displayName,
        error: "torrent has no magnet or .torrent URL",
      });
      continue;
    }

    try {
      const add = await client.addMagnet(url);
      if (add.accepted) {
        outcomes.push({
          id: item.id,
          success: true,
          displayName: item.displayName,
          error: null,
        });
      } else {
        outcomes.push({
          id: item.id,
          success: false,
          displayName: item.displayName,
          error: "backend rejected the download",
        });
        await enqueueFailed(item, url, server.id, config);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      log.warn(`send failed for ${item.displayName}, queuing for retry`);
      outcomes.push({
        id: item.id,
        success: false,
        displayName: item.displayName,
        error: message,
      });
      await enqueueFailed(item, url, server.id, config);
    }
  }

  const succeeded = outcomes.filter((o) => o.success).length;
  const failed = outcomes.length - succeeded;

  if (config.showNotifications) {
    if (succeeded > 0) {
      notify(
        "Torrents sent",
        `${String(succeeded)}/${String(outcomes.length)} sent to Boba.`,
        "success",
      );
    }
    if (failed > 0) {
      notify(
        "Some sends failed",
        `${String(failed)} torrent(s) queued for retry.`,
        "warning",
      );
    }
  }

  return outcomes;
}

/**
 * Enqueue a failed send into the offline queue when offline-queueing is on.
 *
 * @param item - The detected torrent that failed.
 * @param url - The resolved download URL.
 * @param serverId - Active server id.
 * @param config - The current config (gates on `offlineQueue`).
 */
async function enqueueFailed(
  item: DetectedTorrent,
  url: string,
  serverId: string,
  config: ExtensionConfig,
): Promise<void> {
  if (!config.offlineQueue) return;
  await offlineQueue.enqueue(
    item.magnet?.infohash ?? item.id,
    item.magnet?.uri ?? null,
    item.torrentFile?.url ?? url,
    item.displayName,
    serverId,
    "normal",
  );
}

/**
 * The injected queue SEND: re-attempt a queued item through a fresh
 * {@link BobaClient} for its target server. Resolves true on accept.
 *
 * @param queueItem - The persisted queue item.
 * @returns Whether the re-send was accepted.
 */
async function processQueueItem(queueItem: OfflineQueueItem): Promise<boolean> {
  const config = await loadConfig();
  const server =
    config.servers.find((s) => s.id === queueItem.serverId) ??
    activeServer(config);
  if (!server) return false;

  const url = queueItem.torrent.magnetUri ?? queueItem.torrent.torrentUrl;
  if (url === null) return false;

  const client = clientFor(server);
  const add = await client.addMagnet(url);
  return add.accepted;
}

// ─────────────────────────────────────────────────────────────────────────────
// Message router
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Handle a single incoming extension message. Pure async — the listener
 * adapter wires the reply + returns `true` for the async channel.
 *
 * @param message - The incoming message.
 * @param sender - The chrome message sender (tab id source).
 * @returns The response payload.
 */
async function handleMessage(
  message: ExtensionMessage,
  sender: chrome.runtime.MessageSender,
): Promise<ExtensionMessageResponse> {
  switch (message.type) {
    case "scan-result": {
      const tabId = sender.tab?.id;
      const result = message.payload?.result as PageScanResult | undefined;
      if (typeof tabId === "number" && result) {
        tabResults.set(tabId, result);
        updateBadge(result.items.length, BADGE_COLORS.DETECTED);
      }
      return { success: true };
    }

    case "get-detected": {
      const tabId =
        (message.payload?.tabId as number | undefined) ?? sender.tab?.id;
      const result =
        typeof tabId === "number" ? tabResults.get(tabId) ?? null : null;
      return { success: true, data: { result } };
    }

    case "send-torrent": {
      const ids = message.payload?.ids as string[] | undefined;
      const tabId =
        (message.payload?.tabId as number | undefined) ?? sender.tab?.id;
      if (typeof tabId !== "number" || !ids) {
        return { success: false, error: "Missing tabId or ids" };
      }
      const results = await sendTorrents(tabId, ids);
      return { success: true, data: { results } };
    }

    case "health-check": {
      const config = await loadConfig();
      const results = await Promise.all(
        config.servers.map(async (s) => {
          const probe: HealthProbeResult = await probeHealth(s.url);
          return {
            serverId: s.id,
            url: s.url,
            reachable: probe.reachable,
            status: probe.status ?? (probe.reachable ? "healthy" : "unhealthy"),
            latencyMs: probe.latencyMs,
            version: probe.version,
            error: probe.error,
          };
        }),
      );
      return { success: true, data: { results } };
    }

    case "queue-status": {
      return {
        success: true,
        data: { size: offlineQueue.getSize(), items: offlineQueue.getItems() },
      };
    }

    case "queue-process": {
      const result = await offlineQueue.processQueue(processQueueItem);
      return { success: true, data: { result } };
    }

    case "get-config": {
      const config = await loadConfig();
      return { success: true, data: { config } };
    }

    case "set-config": {
      const config = message.payload?.config as ExtensionConfig | undefined;
      if (!config) {
        return { success: false, error: "Missing config" };
      }
      await storageSet(STORAGE_KEYS.CONFIG, config);
      initLogger(config.debugMode);
      return { success: true };
    }

    case "scan-page": {
      const tabId =
        (message.payload?.tabId as number | undefined) ?? sender.tab?.id;
      if (typeof tabId !== "number") {
        return { success: false, error: "No tab specified" };
      }
      await chrome.tabs.sendMessage(tabId, { type: "scan-now" });
      return { success: true };
    }

    case "open-dashboard": {
      const config = await loadConfig();
      const server = activeServer(config);
      await chrome.tabs.create({ url: server?.url ?? config.servers[0]?.url ?? EXT.NAME });
      return { success: true };
    }

    default:
      return {
        success: false,
        error: `Unknown message type: ${message.type}`,
      };
  }
}

/**
 * Register the `chrome.runtime.onMessage` router. Async handlers return `true`
 * synchronously to keep the message channel open for the deferred reply.
 */
function registerMessageRouter(): void {
  chrome.runtime.onMessage.addListener(
    (
      message: ExtensionMessage,
      sender: chrome.runtime.MessageSender,
      sendResponse: (response: ExtensionMessageResponse) => void,
    ): boolean => {
      handleMessage(message, sender)
        .then(sendResponse)
        .catch((err: unknown) => {
          sendResponse({
            success: false,
            error: err instanceof Error ? err.message : String(err),
          });
        });
      return true;
    },
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Context menus
// ─────────────────────────────────────────────────────────────────────────────

/** Context-menu item ids. */
const MENU_SEND = "bobalink-send";
const MENU_SEND_ALL = "bobalink-send-all";
const MENU_SEND_GROUP = "bobalink-send-group";

/**
 * (Re)create the right-click context menus.
 */
function createContextMenus(): void {
  chrome.contextMenus.create({
    id: MENU_SEND,
    title: "Send magnet to Boba",
    contexts: ["link"],
    targetUrlPatterns: ["magnet:*", "*://*/*.torrent", "*://*/*.torrent?*"],
  });
  chrome.contextMenus.create({
    id: MENU_SEND_ALL,
    title: "Send all on page",
    contexts: ["page", "action"],
  });
  chrome.contextMenus.create({
    id: MENU_SEND_GROUP,
    // Placeholder (tab-group send is a later phase).
    title: "Send tab group",
    contexts: ["action"],
  });
}

/**
 * Register the context-menu click dispatcher.
 */
function registerContextMenuClicks(): void {
  chrome.contextMenus.onClicked.addListener((info, tab) => {
    void (async (): Promise<void> => {
      try {
        switch (info.menuItemId) {
          case MENU_SEND: {
            const url = info.linkUrl;
            const config = await loadConfig();
            const server = activeServer(config);
            if (url && server) {
              const client = clientFor(server);
              const add = await client.addMagnet(url);
              if (config.showNotifications) {
                notify(
                  add.accepted ? "Sent!" : "Send failed",
                  add.accepted
                    ? "Magnet sent to Boba."
                    : "The backend rejected the magnet.",
                  add.accepted ? "success" : "error",
                );
              }
            }
            break;
          }
          case MENU_SEND_ALL: {
            if (typeof tab?.id === "number") {
              const result = tabResults.get(tab.id);
              if (result && result.items.length > 0) {
                await sendTorrents(
                  tab.id,
                  result.items.map((i) => i.id),
                );
              }
            }
            break;
          }
          case MENU_SEND_GROUP:
            // Placeholder — tab-group send lands in a later phase.
            break;
          default:
            break;
        }
      } catch (err) {
        log.error("context-menu action failed", err);
      }
    })();
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Keyboard commands
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Register the keyboard-shortcut command listener. Drives the typed
 * `scan-now` / `highlight-toggle` directives to the active tab's content
 * script, sends the detected set, or opens the popup.
 */
function registerCommands(): void {
  chrome.commands.onCommand.addListener((command, tab) => {
    void (async (): Promise<void> => {
      try {
        const tabId = tab?.id ?? (await activeTabId());
        switch (command) {
          case "send-all": {
            if (typeof tabId === "number") {
              const result = tabResults.get(tabId);
              if (result) {
                const unsent = result.items
                  .filter((i) => !i.sent)
                  .map((i) => i.id);
                if (unsent.length > 0) await sendTorrents(tabId, unsent);
              }
            }
            break;
          }
          case "scan-page": {
            if (typeof tabId === "number") {
              await chrome.tabs.sendMessage(tabId, { type: "scan-now" });
            }
            break;
          }
          case "toggle-highlight": {
            if (typeof tabId === "number") {
              await chrome.tabs.sendMessage(tabId, { type: "highlight-toggle" });
            }
            break;
          }
          case "open-popup": {
            // chrome.action.openPopup is not universally available; opening the
            // options page is the portable fallback the popup also uses.
            if (typeof chrome.action.openPopup === "function") {
              await chrome.action.openPopup();
            }
            break;
          }
          default:
            break;
        }
      } catch (err) {
        log.error(`command "${command}" failed`, err);
      }
    })();
  });
}

/**
 * Resolve the active tab id (used when a command does not carry a tab).
 *
 * @returns The active tab id, or undefined.
 */
async function activeTabId(): Promise<number | undefined> {
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs[0]?.id;
  } catch {
    return undefined;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Alarms (keep-alive + periodic health check)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Create the keep-alive + health-check alarms and register their handler.
 *
 * @param healthPeriodMin - Health-check period (minutes).
 */
function registerAlarms(healthPeriodMin: number): void {
  void chrome.alarms.create(ALARM_KEEPALIVE, {
    periodInMinutes: KEEPALIVE_PERIOD_MIN,
  });
  void chrome.alarms.create(ALARM_HEALTH, {
    periodInMinutes: Math.max(0.5, healthPeriodMin),
  });

  chrome.alarms.onAlarm.addListener((alarm) => {
    void (async (): Promise<void> => {
      try {
        if (alarm.name === ALARM_KEEPALIVE) {
          // Touching storage keeps the MV3 service worker from being torn down.
          await chrome.storage.local.get("bobalink_keepalive");
        } else if (alarm.name === ALARM_HEALTH) {
          const config = await loadConfig();
          await Promise.all(config.servers.map((s) => probeHealth(s.url)));
        }
      } catch (err) {
        log.error(`alarm "${alarm.name}" failed`, err);
      }
    })();
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Lifecycle
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Seed the default config into storage when it is absent (first install).
 */
async function seedDefaultConfigIfAbsent(): Promise<void> {
  const existing = await storageGet<ExtensionConfig>(STORAGE_KEYS.CONFIG);
  if (existing === null) {
    await storageSet(STORAGE_KEYS.CONFIG, { ...DEFAULT_CONFIG });
  }
}

/**
 * Register lifecycle listeners (`onInstalled` / `onStartup`): seed config,
 * (re)create the context menus, and load the offline queue.
 */
function registerLifecycle(): void {
  chrome.runtime.onInstalled.addListener((details) => {
    void (async (): Promise<void> => {
      log.info(`extension ${details.reason}`);
      try {
        await seedDefaultConfigIfAbsent();
        createContextMenus();
        await offlineQueue.init();
      } catch (err) {
        log.error("onInstalled handler failed", err);
      }
    })();
  });

  chrome.runtime.onStartup.addListener(() => {
    void (async (): Promise<void> => {
      try {
        await offlineQueue.init();
        createContextMenus();
      } catch (err) {
        log.error("onStartup handler failed", err);
      }
    })();
  });
}

/**
 * Register every background listener (MV3-correct: synchronous top-level
 * registration). Idempotent. Called once at module load when a real `chrome`
 * surface is present, and explicitly by unit tests against an installed fake.
 */
export function initBackground(): void {
  if (registered) return;
  registered = true;

  registerMessageRouter();
  registerLifecycle();
  registerContextMenuClicks();
  registerCommands();
  registerAlarms(DEFAULT_HEALTH_PERIOD_MIN);

  log.info(`${EXT.NAME} background service worker listeners registered`);
}

// Auto-register only inside the actual MV3 service worker, NOT under unit test.
// The discriminator is the Node `process` global: the Vitest/jsdom runner
// always defines it, the browser service-worker never does. Under test the
// `chrome` fake is installed BEFORE the test calls `initBackground()` itself,
// so this guard keeps a bare import side-effect-free in that environment.
if (
  typeof process === "undefined" &&
  typeof chrome !== "undefined" &&
  chrome.runtime !== undefined &&
  typeof chrome.runtime.onMessage?.addListener === "function"
) {
  initBackground();
}
