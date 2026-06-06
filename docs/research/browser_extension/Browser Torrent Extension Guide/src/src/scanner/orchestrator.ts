/**
 * @fileoverview Scanner orchestrator for BobaLink.
 *
 * Coordinates multiple scanners (link scanner, text scanner) to detect
 * torrent content on web pages. Handles MutationObserver for dynamic content,
 * debounced re-scans, and result aggregation.
 *
 * @module scanner/orchestrator
 */

import { createLogger } from "../shared/logger";
import { TypedEventEmitter } from "../shared/events";
import { debounce, yieldToBrowser } from "../shared/utils";
import { DEBOUNCE_DELAYS } from "../shared/constants";
import { getMutationDebounceForUrl } from "./site-db";
import { LinkScanner } from "./link-scanner";
import { TextScanner } from "./text-scanner";
import type { BaseScanner } from "./base";
import type { DetectedTorrent, PageScanResult } from "../types/torrent";

const log = createLogger("ScannerOrchestrator");

/**
 * Options for the scanner orchestrator.
 */
export interface OrchestratorOptions {
  /** Whether to enable the link scanner */
  readonly enableLinkScanner: boolean;

  /** Whether to enable the text scanner */
  readonly enableTextScanner: boolean;

  /** Debounce delay for mutation-triggered re-scans */
  readonly mutationDebounceMs: number;

  /** Whether to observe DOM mutations for dynamic content */
  readonly observeMutations: boolean;
}

/**
 * Default orchestrator options.
 */
export const DEFAULT_ORCHESTRATOR_OPTIONS: Readonly<OrchestratorOptions> = {
  enableLinkScanner: true,
  enableTextScanner: true,
  mutationDebounceMs: DEBOUNCE_DELAYS.MUTATION,
  observeMutations: true,
};

/**
 * Coordinates multiple torrent scanners and manages the scanning lifecycle.
 *
 * The orchestrator:
 * 1. Registers and manages individual scanners
 * 2. Runs scans on page load and when DOM changes
 * 3. Aggregates results from all scanners
 * 4. Emits events for detected torrents
 * 5. Handles cleanup on page unload
 */
export class ScannerOrchestrator {
  private readonly scanners: BaseScanner[] = [];
  private readonly events: TypedEventEmitter;
  private readonly options: Readonly<OrchestratorOptions>;
  private readonly debouncedScan: ReturnType<typeof debounce>;
  private mutationObserver: MutationObserver | null = null;
  private isScanning = false;
  private hasScanned = false;
  private readonly detectedMap = new Map<string, DetectedTorrent>();
  private scanStartTime = 0;

  /**
   * Create a new scanner orchestrator.
   *
   * @param events - Event emitter for publishing scan events
   * @param options - Configuration options
   */
  constructor(
    events?: TypedEventEmitter,
    options: Partial<OrchestratorOptions> = {},
  ) {
    this.events = events ?? new TypedEventEmitter();
    this.options = { ...DEFAULT_ORCHESTRATOR_OPTIONS, ...options };

    // Adjust mutation debounce based on site
    const siteDebounce = getMutationDebounceForUrl(window.location.href);
    if (siteDebounce !== this.options.mutationDebounceMs) {
      this.options = { ...this.options, mutationDebounceMs: siteDebounce };
    }

    // Create debounced scan function
    this.debouncedScan = debounce(() => {
      this.performScan().catch((err) => {
        log.error("Debounced scan failed", err);
      });
    }, this.options.mutationDebounceMs);

    // Register default scanners
    this.registerDefaultScanners();
  }

  /**
   * Get the event emitter for this orchestrator.
   *
   * @returns The event emitter
   */
  getEvents(): TypedEventEmitter {
    return this.events;
  }

  /**
   * Register the default set of scanners based on options.
   */
  private registerDefaultScanners(): void {
    if (this.options.enableLinkScanner) {
      this.registerScanner(new LinkScanner(this.events));
    }

    if (this.options.enableTextScanner) {
      this.registerScanner(new TextScanner(this.events));
    }
  }

  /**
   * Register a scanner with the orchestrator.
   *
   * @param scanner - Scanner instance to register
   */
  registerScanner(scanner: BaseScanner): void {
    this.scanners.push(scanner);
    log.debug(`Registered scanner: ${scanner.getScannerId()}`);
  }

  /**
   * Start the orchestrator.
   * Performs an initial scan and sets up mutation observers.
   */
  start(): void {
    log.info("Starting scanner orchestrator");

    // Perform initial scan
    this.performScan().catch((err) => {
      log.error("Initial scan failed", err);
    });

    // Set up mutation observer for dynamic content
    if (this.options.observeMutations) {
      this.setupMutationObserver();
    }
  }

  /**
   * Stop the orchestrator.
   * Disconnects mutation observers and cancels pending scans.
   */
  stop(): void {
    log.info("Stopping scanner orchestrator");

    this.debouncedScan.cancel();

    if (this.mutationObserver) {
      this.mutationObserver.disconnect();
      this.mutationObserver = null;
    }
  }

  /**
   * Perform a manual scan immediately.
   *
   * @param root - Optional root element to scan
   * @returns Page scan result with all detected torrents
   */
  async scanNow(root?: Element): Promise<PageScanResult> {
    return this.performScan(root);
  }

  /**
   * Get all currently detected torrents.
   *
   * @returns Array of detected torrent items
   */
  getDetectedTorrents(): readonly DetectedTorrent[] {
    return Array.from(this.detectedMap.values());
  }

  /**
   * Get the count of detected torrents.
   *
   * @returns Number of detected torrents
   */
  getDetectedCount(): number {
    return this.detectedMap.size;
  }

  /**
   * Clear all detected torrents.
   */
  clearDetected(): void {
    this.detectedMap.clear();
    this.hasScanned = false;
  }

  /**
   * Check if the initial scan has completed.
   *
   * @returns True if at least one scan has run
   */
  hasInitialScanCompleted(): boolean {
    return this.hasScanned;
  }

  /**
   * Check if a scan is currently in progress.
   *
   * @returns True if scanning
   */
  isCurrentlyScanning(): boolean {
    return this.isScanning;
  }

  /**
   * Perform the actual scan across all registered scanners.
   *
   * @param root - Optional root element to scan
   * @returns Aggregated scan result
   */
  private async performScan(root?: Element): Promise<PageScanResult> {
    if (this.isScanning) {
      log.debug("Scan already in progress, skipping");
      return this.createScanResult([]);
    }

    this.isScanning = true;
    this.scanStartTime = performance.now();
    log.info("Starting page scan");

    this.events.emit("scan-started", {
      url: window.location.href,
      timestamp: Date.now(),
    });

    try {
      const allResults: DetectedTorrent[] = [];

      // Run each scanner
      for (const scanner of this.scanners) {
        if (!scanner.isActive()) {
          try {
            const results = await scanner.scan(root);
            allResults.push(...results);

            // Yield to browser between scanners
            if (this.scanners.indexOf(scanner) < this.scanners.length - 1) {
              await yieldToBrowser();
            }
          } catch (err) {
            log.error(`Scanner ${scanner.getScannerId()} failed`, err);
          }
        }
      }

      // Merge new results with existing, avoiding duplicates
      const newTorrents = this.mergeResults(allResults);

      this.hasScanned = true;

      const result = this.createScanResult(newTorrents);

      // Emit scan completed event
      const duration = Math.round(performance.now() - this.scanStartTime);
      this.events.emit("scan-completed", {
        url: window.location.href,
        magnetCount: result.magnetCount,
        torrentFileCount: result.torrentFileCount,
        durationMs: duration,
      });

      log.info(
        `Scan complete: ${result.magnetCount} magnets, ${result.torrentFileCount} torrent files (${duration}ms)`,
      );

      return result;
    } catch (err) {
      log.error("Scan failed", err);

      this.events.emit("scan-error", {
        url: window.location.href,
        error: err instanceof Error ? err.message : String(err),
      });

      return this.createScanResult([]);
    } finally {
      this.isScanning = false;
    }
  }

  /**
   * Merge new scan results with existing detected torrents.
   * Avoids duplicates based on the torrent ID.
   *
   * @param newResults - Newly detected torrents
   * @returns Array of newly added torrents (not previously seen)
   */
  private mergeResults(
    newResults: readonly DetectedTorrent[],
  ): readonly DetectedTorrent[] {
    const newlyAdded: DetectedTorrent[] = [];

    for (const result of newResults) {
      if (!this.detectedMap.has(result.id)) {
        this.detectedMap.set(result.id, result);
        newlyAdded.push(result);

        // Emit individual torrent detection event
        this.events.emit("torrent-detected", {
          id: result.id,
          type: result.type,
          displayName: result.displayName,
          url: result.magnet?.uri ?? result.torrentFile?.url ?? "",
        });
      }
    }

    return newlyAdded;
  }

  /**
   * Create a PageScanResult from the current state.
   *
   * @param newItems - Items newly detected in this scan
   * @returns Page scan result
   */
  private createScanResult(
    newItems: readonly DetectedTorrent[],
  ): PageScanResult {
    const allItems = this.getDetectedTorrents();
    const magnets = allItems.filter((i) => i.type === "magnet");
    const torrentFiles = allItems.filter((i) => i.type === "torrent-file");

    return {
      pageUrl: window.location.href,
      pageTitle: document.title,
      items: allItems,
      magnetCount: magnets.length,
      torrentFileCount: torrentFiles.length,
      scannedAt: Date.now(),
      scanDurationMs: Math.round(performance.now() - this.scanStartTime),
    };
  }

  /**
   * Set up a MutationObserver to watch for DOM changes.
   * Triggers debounced re-scans when content changes.
   */
  private setupMutationObserver(): void {
    this.mutationObserver = new MutationObserver((mutations) => {
      // Check if mutations are relevant (added nodes contain potential links)
      const hasRelevantChanges = mutations.some((mutation) => {
        // Check added nodes
        for (const node of mutation.addedNodes) {
          if (node instanceof Element) {
            if (
              node.tagName === "A" ||
              node.querySelector("a[href^='magnet:'], a[href$='.torrent']")
            ) {
              return true;
            }
          } else if (node instanceof Text && node.textContent?.includes("magnet:")) {
            return true;
          }
        }

        // Check attribute changes on anchor elements
        if (
          mutation.type === "attributes" &&
          mutation.target instanceof HTMLAnchorElement &&
          mutation.attributeName === "href"
        ) {
          const href = mutation.target.getAttribute("href");
          if (href?.startsWith("magnet:") || href?.endsWith(".torrent")) {
            return true;
          }
        }

        return false;
      });

      if (hasRelevantChanges) {
        this.debouncedScan();
      }
    });

    this.mutationObserver.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["href"],
    });

    log.debug("Mutation observer active");
  }
}
