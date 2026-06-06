/**
 * @fileoverview Content script entry point for BobaLink.
 *
 * This script runs on all web pages (at document_idle) and is responsible for:
 * 1. Initializing the torrent scanner orchestrator
 * 2. Listening for messages from the background service worker
 * 3. Communicating scan results back to the background
 * 4. Managing the highlight overlay on detected torrents
 *
 * The content script uses the ScannerOrchestrator to detect torrents,
 * and the HighlightManager to visually mark detected elements on the page.
 *
 * @module content/index
 */

import { ScannerOrchestrator } from "../scanner/orchestrator";
import { ContentScanner } from "./scanner";
import { HighlightManager } from "./highlight";
import { createLogger, initLogger } from "../shared/logger";
import { storageGet } from "../shared/storage";
import { STORAGE_KEYS, DEFAULT_CONFIG } from "../shared/constants";
import type { ExtensionConfig } from "../types/config";

const log = createLogger("ContentScript");

// ─────────────────────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────────────────────

/** Whether the content script is active on this page. */
let isActive = false;

/** The scanner orchestrator instance. */
let orchestrator: ScannerOrchestrator | null = null;

/** The highlight manager instance. */
let highlightManager: HighlightManager | null = null;

/** The content scanner bridge. */
let contentScanner: ContentScanner | null = null;

// ─────────────────────────────────────────────────────────────────────────────
// Initialization
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Initialize the content script.
 * Loads configuration and starts scanning if auto-scan is enabled.
 */
async function initialize(): Promise<void> {
  if (isActive) return;

  try {
    log.debug("Content script initializing");

    // Load extension configuration
    const config = await loadConfig();
    initLogger(config.debugMode);

    // Initialize the scanner orchestrator
    orchestrator = new ScannerOrchestrator();

    // Initialize the highlight manager
    highlightManager = new HighlightManager(orchestrator.getEvents());

    // Initialize the content scanner bridge
    contentScanner = new ContentScanner(orchestrator);

    // Listen for scan results and send to background
    orchestrator.getEvents().on("scan-completed", async (data) => {
      try {
        const scanResult = orchestrator?.getDetectedTorrents();
        if (scanResult) {
          await sendScanResultToBackground({
            url: data.url,
            items: scanResult,
            magnetCount: data.magnetCount,
            torrentFileCount: data.torrentFileCount,
            durationMs: data.durationMs,
          });
        }
      } catch (err) {
        log.error("Failed to send scan result", err);
      }
    });

    // Listen for individual torrent detections
    orchestrator.getEvents().on("torrent-detected", (data) => {
      log.debug(`Torrent detected: ${data.displayName}`);
    });

    // Start auto-scan if enabled
    if (config.autoScan) {
      log.debug(`Auto-scan enabled, starting in ${config.autoScanDelay}ms`);
      setTimeout(() => {
        startScanning();
      }, config.autoScanDelay);
    }

    // Setup message listener for manual scan commands
    setupMessageListener();

    isActive = true;
    log.info("Content script initialized");
  } catch (err) {
    log.error("Content script initialization failed", err);
  }
}

/**
 * Load extension configuration from storage.
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
// Scanning
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Start the torrent scanner.
 */
function startScanning(): void {
  if (!orchestrator) {
    log.error("Cannot start scanning: orchestrator not initialized");
    return;
  }

  log.info("Starting torrent scanner");
  orchestrator.start();
}

/**
 * Perform a manual scan now.
 */
async function manualScan(): Promise<void> {
  if (!orchestrator) {
    log.error("Cannot scan: orchestrator not initialized");
    return;
  }

  log.info("Manual scan triggered");
  await orchestrator.scanNow();
}

// ─────────────────────────────────────────────────────────────────────────────
// Message Handling
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Setup listener for messages from background script and popup.
 */
function setupMessageListener(): void {
  chrome.runtime.onMessage.addListener(
    (message: { type: string; payload?: Record<string, unknown> }, _sender, sendResponse) => {
      // Handle message asynchronously
      handleMessage(message)
        .then((response) => sendResponse(response))
        .catch((err) =>
          sendResponse({ success: false, error: String(err) }),
        );

      // Return true to indicate async response
      return true;
    },
  );
}

/**
 * Handle incoming messages.
 *
 * @param message - Message from background/popup
 * @returns Response object
 */
async function handleMessage(message: {
  type: string;
  payload?: Record<string, unknown>;
}): Promise<Record<string, unknown>> {
  log.debug(`Received message: ${message.type}`);

  switch (message.type) {
    case "scan-now":
      await manualScan();
      return { success: true };

    case "get-detected": {
      const torrents = orchestrator?.getDetectedTorrents() ?? [];
      return {
        success: true,
        torrents: torrents.map((t) => ({
          id: t.id,
          type: t.type,
          displayName: t.displayName,
          selected: t.selected,
          sent: t.sent,
        })),
      };
    }

    case "toggle-selection": {
      const id = message.payload?.id as string | undefined;
      if (id && orchestrator) {
        const torrents = orchestrator.getDetectedTorrents();
        const torrent = torrents.find((t) => t.id === id);
        if (torrent) {
          (torrent as { selected: boolean }).selected = !torrent.selected;
        }
      }
      return { success: true };
    }

    case "get-scan-status": {
      return {
        success: true,
        isScanning: orchestrator?.isCurrentlyScanning() ?? false,
        hasScanned: orchestrator?.hasInitialScanCompleted() ?? false,
        torrentCount: orchestrator?.getDetectedCount() ?? 0,
      };
    }

    default:
      return { success: false, error: `Unknown message type: ${message.type}` };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Background Communication
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Send scan results to the background service worker.
 *
 * @param result - Scan result to send
 */
async function sendScanResultToBackground(result: {
  url: string;
  items: readonly import("../types/torrent").DetectedTorrent[];
  magnetCount: number;
  torrentFileCount: number;
  durationMs: number;
}): Promise<void> {
  try {
    await chrome.runtime.sendMessage({
      type: "scan-result",
      payload: {
        result: {
          pageUrl: result.url,
          pageTitle: document.title,
          items: result.items,
          magnetCount: result.magnetCount,
          torrentFileCount: result.torrentFileCount,
          scannedAt: Date.now(),
          scanDurationMs: result.durationMs,
        },
      },
    });
    log.debug(`Sent scan result: ${result.items.length} torrents`);
  } catch (err) {
    log.error("Failed to send scan result to background", err);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Cleanup
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Clean up resources when the content script is unloaded.
 */
function cleanup(): void {
  log.debug("Content script cleaning up");

  if (orchestrator) {
    orchestrator.stop();
    orchestrator = null;
  }

  if (highlightManager) {
    highlightManager.destroy();
    highlightManager = null;
  }

  isActive = false;
}

// Cleanup on page unload
window.addEventListener("beforeunload", cleanup);

// ─────────────────────────────────────────────────────────────────────────────
// Entry Point
// ─────────────────────────────────────────────────────────────────────────────

// Initialize when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => initialize());
} else {
  initialize();
}
