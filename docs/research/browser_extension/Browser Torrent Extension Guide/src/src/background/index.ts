/**
 * @fileoverview Background service worker for BobaLink.
 *
 * The service worker is the central hub of the extension. It:
 * - Routes messages between content scripts, popup, and options page
 * - Manages chrome.contextMenus for right-click actions
 * - Handles keyboard shortcuts (commands)
 * - Runs periodic health checks via chrome.alarms
 * - Keeps itself alive using alarm-based keepalive
 * - Manages the badge state and chrome.notifications
 * - Processes the offline send queue
 *
 * @module background/index
 */

import { createLogger, initLogger } from "../shared/logger";
import { TypedEventEmitter } from "../shared/events";
import { BobaAPIClient } from "../api/client";
import { AuthHandler } from "../api/auth";
import { HealthChecker } from "../api/health";
import { OfflineQueue } from "../api/queue";
import { qBitTorrentAdapter } from "../api/qbittorrent";
import { storageGet, storageSet, onStorageChange } from "../shared/storage";
import { initStorage } from "../shared/storage";
import { generateId, isValidHttpUrl } from "../shared/utils";
import {
  STORAGE_KEYS,
  BADGE_COLORS,
  DEFAULT_CONFIG,
  EXT,
  DEBOUNCE_DELAYS,
} from "../shared/constants";
import type {
  ExtensionConfig,
  ServerConfig,
  ConnectionTestResult,
} from "../types/config";
import type {
  DetectedTorrent,
  PageScanResult,
  SendResult,
} from "../types/torrent";
import type { ExtensionMessage, ExtensionMessageResponse } from "../types/api";

const log = createLogger("Background");

// ─────────────────────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────────────────────

/** Event emitter for background-internal communication. */
const events = new TypedEventEmitter();

/** Active API client (created when server is configured). */
let apiClient: BobaAPIClient | null = null;

/** Auth handler for the active client. */
let authHandler: AuthHandler | null = null;

/** Health checker instance. */
const healthChecker = new HealthChecker();

/** Offline queue for failed sends. */
const offlineQueue = new OfflineQueue();

/** Detected torrents keyed by tab ID. */
const tabTorrents = new Map<number, PageScanResult>();

/** Whether the service worker is initialized. */
let initialized = false;

// ─────────────────────────────────────────────────────────────────────────────
// Lifecycle
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Initialize the service worker.
 * Called on startup and install.
 */
async function initialize(): Promise<void> {
  if (initialized) return;

  log.info(`${EXT.NAME} background service worker initializing`);

  try {
    // Load configuration
    const config = await loadConfig();
    initLogger(config.debugMode);

    // Initialize offline queue
    await offlineQueue.init();

    // Setup context menus
    setupContextMenus();

    // Setup keyboard shortcuts
    setupCommandListeners();

    // Setup message routing
    setupMessageRouting();

    // Setup storage change listeners
    setupStorageListeners();

    // Setup alarms for keepalive and health checks
    setupAlarms();

    // Initialize API client if server is configured
    await initializeApiClient(config);

    initialized = true;
    log.info(`${EXT.NAME} background service worker initialized`);

    // Show startup notification
    if (config.showNotifications) {
      showNotification(
        `${EXT.NAME} Active`,
        "Extension is ready. Browse torrent sites to detect magnet links and .torrent files.",
        "info",
      );
    }
  } catch (err) {
    log.error("Initialization failed", err);
  }
}

/**
 * Initialize the API client from configuration.
 *
 * @param config - Extension configuration
 */
async function initializeApiClient(
  config: ExtensionConfig,
): Promise<void> {
  const activeServer = config.servers.find(
    (s) => s.id === config.activeServerId,
  );

  if (!activeServer) {
    log.info("No active server configured");
    updateBadge(0, BADGE_COLORS.DEFAULT);
    return;
  }

  try {
    apiClient = new BobaAPIClient(
      activeServer.url,
      activeServer.requestTimeout,
    );
    authHandler = new AuthHandler(apiClient, activeServer.authMethod);

    log.info(`API client initialized for ${activeServer.url}`);

    // Start auto queue processing if enabled
    if (config.offlineQueue) {
      offlineQueue.startAutoProcessing(
        activeServer,
        config.healthCheckInterval * 60000,
      );
    }
  } catch (err) {
    log.error("Failed to initialize API client", err);
    updateBadge(0, BADGE_COLORS.ERROR);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Load extension configuration from storage.
 * Returns defaults if no config exists.
 *
 * @returns Extension configuration
 */
async function loadConfig(): Promise<ExtensionConfig> {
  try {
    const data = await storageGet<ExtensionConfig>(STORAGE_KEYS.CONFIG);
    return data ?? { ...DEFAULT_CONFIG };
  } catch {
    return { ...DEFAULT_CONFIG };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Message Routing
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Setup chrome.runtime.onMessage listener for routing messages
 * between content scripts, popup, and options page.
 */
function setupMessageRouting(): void {
  chrome.runtime.onMessage.addListener(
    (
      message: ExtensionMessage,
      sender: chrome.runtime.MessageSender,
      sendResponse: (response: ExtensionMessageResponse) => void,
    ): boolean => {
      // Handle the message asynchronously
      handleMessage(message, sender)
        .then((response) => sendResponse(response))
        .catch((err) =>
          sendResponse({
            success: false,
            error: err instanceof Error ? err.message : String(err),
          }),
        );

      // Return true to indicate async response
      return true;
    },
  );
}

/**
 * Handle incoming messages from other extension contexts.
 *
 * @param message - The message to handle
 * @param sender - Message sender info
 * @returns Response data
 */
async function handleMessage(
  message: ExtensionMessage,
  sender: chrome.runtime.MessageSender,
): Promise<ExtensionMessageResponse> {
  log.debug(`Received message: ${message.type}`, { payload: message.payload });

  try {
    switch (message.type) {
      case "scan-result": {
        // Store scan results from content script
        const tabId = sender.tab?.id;
        const result = message.payload?.result as PageScanResult | undefined;
        if (tabId && result) {
          tabTorrents.set(tabId, result);
          updateBadge(result.items.length, BADGE_COLORS.DETECTED);
        }
        return { success: true };
      }

      case "get-detected": {
        // Return detected torrents for a specific tab
        const tabId = (message.payload?.tabId as number) || sender.tab?.id;
        const result = tabId ? tabTorrents.get(tabId) ?? null : null;
        return { success: true, data: { result } };
      }

      case "send-torrent": {
        // Send torrent(s) to qBitTorrent
        const ids = message.payload?.ids as string[] | undefined;
        const tabId = (message.payload?.tabId as number) || sender.tab?.id;
        if (!tabId || !ids) {
          return { success: false, error: "Missing tabId or ids" };
        }

        const results = await sendTorrents(tabId, ids);
        return { success: true, data: { results } };
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
        // Reinitialize API client with new config
        await initializeApiClient(config);
        return { success: true };
      }

      case "health-check": {
        const config = await loadConfig();
        const results = await healthChecker.checkAllServers(config.servers);
        return { success: true, data: { results } };
      }

      case "test-connection": {
        const url = message.payload?.url as string | undefined;
        if (!url) {
          return { success: false, error: "Missing URL" };
        }
        const result = await healthChecker.testConnection(url);
        return { success: true, data: { result } };
      }

      case "auto-discover": {
        const results = await healthChecker.autoDiscover();
        return { success: true, data: { results } };
      }

      case "authenticate": {
        const serverId = message.payload?.serverId as string | undefined;
        const config = await loadConfig();
        const server = config.servers.find((s) => s.id === serverId);
        if (!server) {
          return { success: false, error: "Server not found" };
        }

        // Reinitialize client for this server
        apiClient = new BobaAPIClient(server.url, server.requestTimeout);
        authHandler = new AuthHandler(apiClient, server.authMethod);

        // For cookie auth, we need the passphrase to decrypt credentials
        // This would come from a secure prompt in the options page
        const passphrase = (message.payload?.passphrase as string) || "";
        const { AuthHandler } = await import("../api/auth");
        const credentials = await AuthHandler.createCredentialsFromConfig(
          server,
          passphrase,
        );

        const success = await authHandler.authenticate(credentials);
        return { success, data: { authenticated: success } };
      }

      case "scan-page": {
        // Trigger a scan on the specified tab
        const tabId = (message.payload?.tabId as number) || sender.tab?.id;
        if (!tabId) {
          return { success: false, error: "No tab specified" };
        }

        await chrome.tabs.sendMessage(tabId, { type: "scan-now" });
        return { success: true };
      }

      case "open-dashboard": {
        const config = await loadConfig();
        const activeServer = config.servers.find(
          (s) => s.id === config.activeServerId,
        );
        if (activeServer) {
          await chrome.tabs.create({ url: activeServer.url });
        } else {
          // Fallback to common qBitTorrent WebUI URL
          await chrome.tabs.create({ url: "http://localhost:8080" });
        }
        return { success: true };
      }

      case "queue-status": {
        return {
          success: true,
          data: { size: offlineQueue.getSize(), items: offlineQueue.getItems() },
        };
      }

      case "queue-process": {
        const config = await loadConfig();
        const activeServer = config.servers.find(
          (s) => s.id === config.activeServerId,
        );
        if (!activeServer) {
          return { success: false, error: "No active server" };
        }
        const result = await offlineQueue.processQueue(activeServer);
        return { success: true, data: { result } };
      }

      default:
        return { success: false, error: `Unknown message type: ${message.type}` };
    }
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    log.error(`Message handler error: ${message.type}`, err);
    return { success: false, error };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Torrent Sending
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Send selected torrents from a tab to qBitTorrent.
 *
 * @param tabId - Tab ID containing the torrents
 * @param ids - IDs of torrents to send
 * @returns Array of send results
 */
async function sendTorrents(
  tabId: number,
  ids: readonly string[],
): Promise<readonly SendResult[]> {
  const config = await loadConfig();
  const activeServer = config.servers.find(
    (s) => s.id === config.activeServerId,
  );

  if (!activeServer) {
    throw new Error("No active server configured");
  }

  if (!apiClient || !authHandler) {
    throw new Error("API client not initialized");
  }

  // Ensure we're authenticated
  const { AuthHandler } = await import("../api/auth");
  const credentials = await AuthHandler.createCredentialsFromConfig(
    activeServer,
    "", // Passphrase would be provided via secure prompt
  );
  await authHandler.refreshIfNeeded(credentials);

  // Get torrents for this tab
  const scanResult = tabTorrents.get(tabId);
  if (!scanResult) {
    throw new Error("No torrents detected for this tab");
  }

  const toSend = scanResult.items.filter((item) => ids.includes(item.id));
  if (toSend.length === 0) {
    throw new Error("No matching torrents found");
  }

  log.info(`Sending ${toSend.length} torrents from tab ${tabId}`);

  const adapter = new qBitTorrentAdapter(apiClient);
  const results = await adapter.sendTorrents(toSend, activeServer);

  // Queue failed items for retry if offline queue is enabled
  for (const result of results) {
    if (!result.success && config.offlineQueue) {
      const torrent = result.torrent;
      await offlineQueue.enqueue(
        torrent.magnet?.infohash ?? torrent.id,
        torrent.magnet?.uri ?? null,
        torrent.torrentFile?.url ?? null,
        torrent.displayName,
        activeServer.id,
        "normal",
      );
    }
  }

  // Update sent status
  for (const result of results) {
    if (result.success) {
      const item = scanResult.items.find((i) => i.id === result.torrent.id);
      if (item) {
        (item as DetectedTorrent).sent = true;
        (item as DetectedTorrent).sendStatus = "success";
      }
    }
  }

  // Update badge
  const unsentCount = scanResult.items.filter((i) => !i.sent).length;
  updateBadge(unsentCount, unsentCount > 0 ? BADGE_COLORS.DETECTED : BADGE_COLORS.HEALTHY);

  // Notify
  if (config.showNotifications) {
    const succeeded = results.filter((r) => r.success).length;
    if (succeeded > 0) {
      showNotification(
        "Torrents Sent",
        `${succeeded}/${results.length} torrents sent to qBitTorrent successfully.`,
        "success",
      );
    }
  }

  return results;
}

// ─────────────────────────────────────────────────────────────────────────────
// Context Menus
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Setup right-click context menus.
 */
function setupContextMenus(): void {
  chrome.contextMenus.create({
    id: "bobalink-send",
    title: "Send to Boba",
    contexts: ["link"],
    targetUrlPatterns: [
      "magnet:*",
      "*://*/*.torrent",
      "*://*/*.torrent?*",
    ],
  });

  chrome.contextMenus.create({
    id: "bobalink-scan",
    title: "Scan Page for Torrents",
    contexts: ["page", "action"],
  });

  chrome.contextMenus.create({
    id: "bobalink-dashboard",
    title: "Open Boba Dashboard",
    contexts: ["action", "page"],
  });

  chrome.contextMenus.onClicked.addListener(async (info, tab) => {
    switch (info.menuItemId) {
      case "bobalink-send": {
        if (info.linkUrl) {
          await handleContextSend(info.linkUrl, tab);
        }
        break;
      }
      case "bobalink-scan": {
        if (tab?.id) {
          await chrome.tabs.sendMessage(tab.id, { type: "scan-now" });
        }
        break;
      }
      case "bobalink-dashboard": {
        const config = await loadConfig();
        const url = config.servers.find((s) => s.id === config.activeServerId)?.url
          ?? "http://localhost:8080";
        await chrome.tabs.create({ url });
        break;
      }
    }
  });

  log.debug("Context menus registered");
}

/**
 * Handle "Send to Boba" context menu click on a link.
 *
 * @param linkUrl - URL of the clicked link
 * @param tab - Tab where the click occurred
 */
async function handleContextSend(
  linkUrl: string,
  tab: chrome.tabs.Tab | undefined,
): Promise<void> {
  try {
    const config = await loadConfig();
    const activeServer = config.servers.find(
      (s) => s.id === config.activeServerId,
    );

    if (!activeServer) {
      showNotification("Not Configured", "Please configure a server in extension options.", "warning");
      return;
    }

    if (!apiClient) {
      apiClient = new BobaAPIClient(activeServer.url, activeServer.requestTimeout);
      authHandler = new AuthHandler(apiClient, activeServer.authMethod);
    }

    // Send the link directly
    if (linkUrl.startsWith("magnet:")) {
      await apiClient.addTorrentFromMagnet(linkUrl, {
        category: activeServer.defaultCategory ?? undefined,
      });
    } else if (linkUrl.endsWith(".torrent")) {
      // Download and send .torrent file
      const response = await fetch(linkUrl);
      const blob = await response.blob();
      const filename = linkUrl.split("/").pop() || "download.torrent";
      const file = new File([blob], decodeURIComponent(filename), {
        type: "application/x-bittorrent",
      });
      await apiClient.addTorrentFromFile(file, {
        category: activeServer.defaultCategory ?? undefined,
      });
    }

    showNotification("Sent!", "Torrent sent to qBitTorrent successfully.", "success");
  } catch (err) {
    log.error("Context send failed", err);
    showNotification(
      "Send Failed",
      err instanceof Error ? err.message : "Failed to send torrent",
      "error",
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Keyboard Shortcuts
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Setup keyboard shortcut command listeners.
 */
function setupCommandListeners(): void {
  chrome.commands.onCommand.addListener(async (command, tab) => {
    log.debug(`Command received: ${command}`);

    switch (command) {
      case "send-to-boba": {
        if (tab?.id) {
          const result = tabTorrents.get(tab.id);
          if (result && result.items.length > 0) {
            const unsent = result.items.filter((i) => !i.sent).map((i) => i.id);
            if (unsent.length > 0) {
              await sendTorrents(tab.id, unsent);
            }
          }
        }
        break;
      }
      case "scan-page": {
        if (tab?.id) {
          await chrome.tabs.sendMessage(tab.id, { type: "scan-now" });
        }
        break;
      }
      case "open-dashboard": {
        const config = await loadConfig();
        const url = config.servers.find((s) => s.id === config.activeServerId)?.url
          ?? "http://localhost:8080";
        await chrome.tabs.create({ url });
        break;
      }
    }
  });

  log.debug("Command listeners registered");
}

// ─────────────────────────────────────────────────────────────────────────────
// Alarms
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Setup chrome.alarms for keepalive and health checks.
 */
function setupAlarms(): void {
  // Keepalive alarm (every 20 seconds to prevent service worker termination)
  chrome.alarms.create("keepalive", { periodInMinutes: 0.33 }); // ~20 seconds

  // Health check alarm
  chrome.alarms.create("health-check", { periodInMinutes: 5 });

  chrome.alarms.onAlarm.addListener(async (alarm) => {
    switch (alarm.name) {
      case "keepalive": {
        // Just accessing storage keeps the service worker alive
        try {
          await chrome.storage.local.get("bobalink_keepalive");
        } catch {
          // Ignore
        }
        break;
      }
      case "health-check": {
        try {
          const config = await loadConfig();
          if (config.servers.length > 0) {
            await healthChecker.checkAllServers(config.servers);
          }
        } catch (err) {
          log.error("Health check alarm failed", err);
        }
        break;
      }
    }
  });

  log.debug("Alarms registered");
}

// ─────────────────────────────────────────────────────────────────────────────
// Badge & Notifications
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Update the extension badge with count and color.
 *
 * @param count - Number to display
 * @param color - Badge background color
 */
function updateBadge(count: number, color: string): void {
  const text = count > 0 ? String(Math.min(count, 99)) : "";
  chrome.action.setBadgeText({ text });
  chrome.action.setBadgeBackgroundColor({ color });
}

/**
 * Show a chrome notification.
 *
 * @param title - Notification title
 * @param message - Notification body
 * @param type - Notification type (affects icon)
 */
function showNotification(
  title: string,
  message: string,
  type: "info" | "success" | "warning" | "error",
): void {
  const iconUrl = `/icon-128.png`;

  chrome.notifications.create({
    type: "basic",
    iconUrl,
    title,
    message,
    priority: type === "error" ? 2 : 1,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Storage Listeners
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Listen for storage changes to react to configuration updates.
 */
function setupStorageListeners(): void {
  onStorageChange([STORAGE_KEYS.CONFIG], (changes) => {
    const change = changes.get(STORAGE_KEYS.CONFIG);
    if (change?.newValue) {
      log.info("Configuration changed, reinitializing");
      initializeApiClient(change.newValue as ExtensionConfig).catch((err) => {
        log.error("Reinitialization after config change failed", err);
      });
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Event Listeners
// ─────────────────────────────────────────────────────────────────────────────

// Initialize on install/update
chrome.runtime.onInstalled.addListener((details) => {
  log.info(`Extension ${details.reason}`);

  if (details.reason === "install") {
    // Set default configuration
    storageSet(STORAGE_KEYS.CONFIG, { ...DEFAULT_CONFIG }).catch((err) => {
      log.error("Failed to set default config", err);
    });
  }

  initialize();
});

// Initialize on startup
chrome.runtime.onStartup.addListener(() => {
  initialize();
});

// Keep service worker alive on message
chrome.runtime.onMessage.addListener(() => {
  // Just receiving a message keeps the service worker alive
});

// Initialize immediately
initialize();
