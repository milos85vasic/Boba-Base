/**
 * @fileoverview Content script entry point for BobaLink (Phase 3).
 *
 * Runs on every web page (at document_idle in the real extension). It:
 *   1. Instantiates the committed {@link ScannerOrchestrator} and runs an initial
 *      page scan (link + text scanners, cross-scanner deduped).
 *   2. SENDS the detected torrent set up to the background service worker over
 *      `chrome.runtime.sendMessage` using the typed `scan-result` {@link MessageType}
 *      envelope — every time a scan completes.
 *   3. Drives a {@link HighlightManager} that visually marks detected links in the
 *      page DOM, toggleable at runtime.
 *   4. Listens for background → content messages over `chrome.runtime.onMessage`
 *      (`scan-now` rescan, `get-detected`, `toggle-selection`, `get-scan-status`,
 *      `highlight-toggle`) and answers them.
 *
 * Ported into the BobaLink extension (REFACTOR per F-adopt-vs-rewrite) from the
 * reference guide source. Deltas vs the reference, all behaviour-preserving:
 *   1. The reference's thin `content/scanner.ts` bridge (an event-logging wrapper
 *      around the orchestrator) is FOLDED into this entry — it added no behaviour
 *      the orchestrator + entry do not already provide.
 *   2. The init logic is exposed as {@link initContentScript}, which returns a
 *      {@link ContentScriptController} (orchestrator + highlight manager +
 *      cleanup) so it is deterministically drivable from tests and from the
 *      eventual entrypoint wrapper, while module-load auto-run is preserved for
 *      the real extension (guarded so importing the module has no side effect
 *      outside a content-script context).
 *   3. The scan-result envelope uses the typed `MessageType` ("scan-result") and
 *      `ExtensionMessage` shape from `types/api.ts` — no untyped string literals.
 *
 * Boba constraint: NO credential crypto here (Phase 7); the content script runs
 * in the page world and only detects + reports + highlights.
 *
 * @module content/index
 */

import { ScannerOrchestrator } from "../scanner/orchestrator";
import { HighlightManager } from "./highlight";
import { createLogger, initLogger } from "../shared/logger";
import { storageGet } from "../shared/storage";
import { STORAGE_KEYS } from "../shared/constants";
import { DEFAULT_CONFIG, type ExtensionConfig } from "../types/config";
import type { ExtensionMessage } from "../types/api";
import type { PageScanResult } from "../types/torrent";

const log = createLogger("ContentScript");

// ─────────────────────────────────────────────────────────────────────────────
// Public init API
// ─────────────────────────────────────────────────────────────────────────────

/** Options controlling content-script initialization. */
export interface ContentInitOptions {
  /**
   * Whether to run the initial scan synchronously during init (resolved before the
   * returned promise settles). When false, no scan is run during init — the page
   * is scanned only on an explicit `scan-now` message. Defaults to the loaded
   * config's `autoScan`.
   */
  readonly autoScan?: boolean;
  /** Pre-resolved config (skips the storage read; used by tests + callers). */
  readonly config?: ExtensionConfig;
}

/**
 * Handle returned by {@link initContentScript} so the orchestrator, highlight
 * manager, and teardown are addressable by tests and the entrypoint wrapper.
 */
export interface ContentScriptController {
  /** The committed scanner orchestrator driving detection. */
  readonly orchestrator: ScannerOrchestrator;
  /** The DOM highlight manager. */
  readonly highlightManager: HighlightManager;
  /** Run a scan now and report the result to the background. */
  readonly rescan: () => Promise<PageScanResult>;
  /** Tear down: stop the orchestrator, remove highlights + listeners. */
  readonly cleanup: () => void;
}

/**
 * Initialize the content-script layer: orchestrator + highlight manager + message
 * routing, and run the initial scan (when auto-scan is enabled).
 *
 * @param options - Optional init overrides (auto-scan flag, pre-resolved config)
 * @returns A controller handle over the live content-script state
 */
export async function initContentScript(
  options: ContentInitOptions = {},
): Promise<ContentScriptController> {
  const config = options.config ?? (await loadConfig());
  initLogger(config.debugMode);

  const orchestrator = new ScannerOrchestrator();
  const highlightManager = new HighlightManager(orchestrator.getEvents(), {
    style: config.highlightStyle,
    enabled: config.highlightTorrents,
  });

  // Report every completed scan up to the background.
  const unsubScan = orchestrator.getEvents().on("scan-completed", (data) => {
    const items = orchestrator.getDetectedTorrents();
    sendScanResultToBackground({
      url: data.url,
      items,
      magnetCount: data.magnetCount,
      torrentFileCount: data.torrentFileCount,
      durationMs: data.durationMs,
    }).catch((err) => log.error("Failed to send scan result", err));
  });

  const rescan = async (): Promise<PageScanResult> => {
    return orchestrator.scanNow();
  };

  // Wire the background → content message listener.
  const messageListener = makeMessageListener({
    orchestrator,
    highlightManager,
    rescan,
  });
  getRuntime()?.onMessage.addListener(messageListener);

  const cleanup = (): void => {
    unsubScan();
    getRuntime()?.onMessage.removeListener(messageListener);
    orchestrator.stop();
    highlightManager.destroy();
  };

  // Initial scan (auto-scan).
  const autoScan = options.autoScan ?? config.autoScan;
  if (autoScan) {
    await orchestrator.scanNow();
  }

  log.info("Content script initialized");
  return { orchestrator, highlightManager, rescan, cleanup };
}

// ─────────────────────────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Load extension configuration from storage, falling back to {@link DEFAULT_CONFIG}.
 *
 * @returns Resolved extension configuration
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
// Message handling
// ─────────────────────────────────────────────────────────────────────────────

/** Dependencies the message router needs from the live content state. */
interface MessageDeps {
  readonly orchestrator: ScannerOrchestrator;
  readonly highlightManager: HighlightManager;
  readonly rescan: () => Promise<PageScanResult>;
}

type RuntimeMessageListener = (
  message: unknown,
  sender: unknown,
  sendResponse: (response?: unknown) => void,
) => boolean | undefined;

/**
 * Build the `chrome.runtime.onMessage` listener. The listener answers
 * asynchronously and returns `true` so the channel stays open for the reply.
 *
 * @param deps - Live content-script dependencies
 * @returns A runtime message listener
 */
function makeMessageListener(deps: MessageDeps): RuntimeMessageListener {
  return (message, _sender, sendResponse): boolean => {
    handleMessage(message as { type?: string; payload?: Record<string, unknown> }, deps)
      .then((response) => sendResponse(response))
      .catch((err) =>
        sendResponse({ success: false, error: String(err) }),
      );
    // Keep the message channel open for the async response.
    return true;
  };
}

/**
 * Handle an incoming background → content message.
 *
 * @param message - The message envelope (`{type, payload?}`)
 * @param deps - Live content-script dependencies
 * @returns Response object
 */
async function handleMessage(
  message: { type?: string; payload?: Record<string, unknown> },
  deps: MessageDeps,
): Promise<Record<string, unknown>> {
  const type = message.type ?? "";
  log.debug(`Received message: ${type}`);

  switch (type) {
    case "scan-now": {
      await deps.rescan();
      return { success: true };
    }

    case "get-detected": {
      const torrents = deps.orchestrator.getDetectedTorrents();
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
      const id = message.payload?.["id"] as string | undefined;
      if (id) {
        const torrent = deps.orchestrator
          .getDetectedTorrents()
          .find((t) => t.id === id);
        if (torrent) {
          torrent.selected = !torrent.selected;
        }
      }
      return { success: true };
    }

    case "get-scan-status": {
      return {
        success: true,
        isScanning: deps.orchestrator.isCurrentlyScanning(),
        hasScanned: deps.orchestrator.hasInitialScanCompleted(),
        torrentCount: deps.orchestrator.getDetectedCount(),
      };
    }

    case "highlight-toggle": {
      const enabledRaw = message.payload?.["enabled"];
      const enabled =
        typeof enabledRaw === "boolean"
          ? enabledRaw
          : !deps.highlightManager.isEnabled();
      deps.highlightManager.setEnabled(enabled);
      return { success: true, enabled: deps.highlightManager.isEnabled() };
    }

    default:
      return { success: false, error: `Unknown message type: ${type}` };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Background communication
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Send the detected torrent set to the background service worker as a typed
 * `scan-result` {@link ExtensionMessage}.
 *
 * @param result - The scan result to report
 */
async function sendScanResultToBackground(result: {
  url: string;
  items: PageScanResult["items"];
  magnetCount: number;
  torrentFileCount: number;
  durationMs: number;
}): Promise<void> {
  const runtime = getRuntime();
  if (!runtime) {
    log.debug("chrome.runtime unavailable; skipping scan-result send");
    return;
  }

  const message: ExtensionMessage = {
    type: "scan-result",
    payload: {
      result: {
        pageUrl: result.url,
        pageTitle: typeof document !== "undefined" ? document.title : "",
        items: result.items,
        magnetCount: result.magnetCount,
        torrentFileCount: result.torrentFileCount,
        scannedAt: Date.now(),
        scanDurationMs: result.durationMs,
      },
    },
  };

  try {
    await runtime.sendMessage(message);
    log.debug(`Sent scan result: ${result.items.length} torrents`);
  } catch (err) {
    log.error("Failed to send scan result to background", err);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// chrome.runtime access (test/SSR-safe)
// ─────────────────────────────────────────────────────────────────────────────

/** Minimal `chrome.runtime` surface this module uses. */
interface RuntimeLike {
  sendMessage: (message: unknown) => Promise<unknown> | undefined;
  onMessage: {
    addListener: (l: RuntimeMessageListener) => void;
    removeListener: (l: RuntimeMessageListener) => void;
  };
}

/**
 * Resolve `chrome.runtime` if present, else `null` (jsdom / SSR have no chrome.*).
 *
 * @returns The runtime surface or null
 */
function getRuntime(): RuntimeLike | null {
  const c = (globalThis as unknown as { chrome?: { runtime?: RuntimeLike } })
    .chrome;
  return c?.runtime ?? null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Lifecycle ownership
// ─────────────────────────────────────────────────────────────────────────────
//
// This module deliberately does NOT self-init. The WXT content-script
// entrypoint (`src/entrypoints/content.ts`) is the single driver: it declares
// the manifest `matches` and calls `initContentScript()` from its `main()`,
// honouring `run_at: document_idle`. A former module-load auto-run block was
// removed because running it in addition to the entrypoint's `main()` would
// double-register the `chrome.runtime.onMessage` listener (`initContentScript`
// is not idempotent). Unit tests call `initContentScript()` explicitly, so this
// change is invisible to them.
