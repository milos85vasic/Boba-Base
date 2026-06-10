/**
 * @fileoverview Scanner orchestrator for BobaLink (Phase 2 port).
 *
 * Coordinates multiple scanners (the committed {@link LinkScanner} +
 * {@link TextScanner}) to detect torrent content on a single web page. It runs
 * every registered scanner over a root, AGGREGATES their results, and DEDUPS the
 * combined `DetectedTorrent[]` by the scanner-supplied stable `id` — so a magnet
 * detected by BOTH the link scanner (as an `<a href>`) AND the text scanner (as
 * bare text) appears EXACTLY ONCE in the detected set. It also drives a
 * MutationObserver-debounced re-scan for dynamic content. The combined set is
 * exposed via {@link getDetectedTorrents} and changes are announced through the
 * `torrent-detected` / `scan-completed` events on the shared TypedEventEmitter.
 *
 * Ported into the BobaLink extension (REFACTOR per F-adopt-vs-rewrite) from the
 * reference guide source. The reference's public API + behaviour are preserved.
 * Two committed-dependency deltas vs the reference:
 *   1. The reference imported a `getMutationDebounceForUrl(url)` helper from
 *      `scanner/site-db`. The committed site-db (which is the single source of
 *      truth, REFACTORed away from the reference's duplicate tables) does NOT
 *      expose per-site mutation debounce — so this port resolves the debounce
 *      purely from the option / `DEBOUNCE_DELAYS.MUTATION`, with no ghost import.
 *   2. Cross-scanner dedup is keyed on the STABLE id from the committed
 *      {@link BaseScanner} (`computeStableId`: infohash → magnet URI → file URL →
 *      display name). Because both scanners derive the same id for the same
 *      torrent, the orchestrator's id-keyed `Map` collapses a magnet seen by both
 *      scanners into one entry. (The reference's `Date.now()`-salted id could not
 *      have deduped across scanners — that defect was fixed in `base.ts`.)
 *
 * Tab-group batching is a LATER phase; this orchestrator handles single-page
 * orchestration only.
 *
 * @module scanner/orchestrator
 */

import { createLogger } from "../shared/logger";
import { TypedEventEmitter } from "../shared/events";
import { debounce, yieldToBrowser } from "../shared/utils";
import { DEBOUNCE_DELAYS } from "../shared/constants";
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

  /** Debounce delay (ms) for mutation-triggered re-scans */
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
 * Coordinates multiple torrent scanners and manages the single-page scanning
 * lifecycle.
 *
 * The orchestrator:
 * 1. Registers and manages individual scanners (link + text by default).
 * 2. Runs scans on demand and when the DOM changes (debounced).
 * 3. Aggregates results from all scanners and DEDUPS by stable id.
 * 4. Emits events when the detected set changes.
 * 5. Cleans up its MutationObserver on {@link stop}.
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
   * @param events - Event emitter for publishing scan events (created if omitted)
   * @param options - Partial configuration; merged over the defaults
   */
  constructor(
    events?: TypedEventEmitter,
    options: Partial<OrchestratorOptions> = {},
  ) {
    this.events = events ?? new TypedEventEmitter();
    this.options = { ...DEFAULT_ORCHESTRATOR_OPTIONS, ...options };

    // Create debounced scan function for mutation-driven re-scans.
    this.debouncedScan = debounce(() => {
      this.performScan().catch((err) => {
        log.error("Debounced scan failed", err);
      });
    }, this.options.mutationDebounceMs);

    // Register default scanners (the committed Link + Text scanners).
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
   * Performs an initial scan and sets up the mutation observer.
   */
  start(): void {
    log.info("Starting scanner orchestrator");

    // Perform initial scan.
    this.performScan().catch((err) => {
      log.error("Initial scan failed", err);
    });

    // Set up mutation observer for dynamic content.
    if (this.options.observeMutations) {
      this.setupMutationObserver();
    }
  }

  /**
   * Stop the orchestrator.
   * Disconnects the mutation observer and cancels pending debounced scans.
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
   * Get all currently detected torrents (deduped across scanners).
   *
   * @returns Array of detected torrent items
   */
  getDetectedTorrents(): readonly DetectedTorrent[] {
    return Array.from(this.detectedMap.values());
  }

  /**
   * Get the count of detected torrents.
   *
   * @returns Number of distinct detected torrents
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
   * Perform the actual scan across all registered scanners, then merge + dedup.
   *
   * @param root - Optional root element to scan
   * @returns Aggregated, deduped scan result
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

      // Run each scanner that is not already mid-scan, aggregating results.
      for (let i = 0; i < this.scanners.length; i++) {
        const scanner = this.scanners[i];
        if (!scanner || scanner.isActive()) {
          continue;
        }

        try {
          const results = await scanner.scan(root);
          allResults.push(...results);

          // Yield to the browser between scanners (not after the last one).
          if (i < this.scanners.length - 1) {
            await yieldToBrowser();
          }
        } catch (err) {
          log.error(`Scanner ${scanner.getScannerId()} failed`, err);
        }
      }

      // Merge new results with the existing detected set, deduping by stable id.
      const newTorrents = this.mergeResults(allResults);

      this.hasScanned = true;

      const result = this.createScanResult(newTorrents);

      // Emit scan-completed event.
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
   * Merge new scan results into the detected set, deduping by the stable `id`.
   *
   * The `id` is the deterministic identity hash from {@link BaseScanner}
   * (infohash-first). Because the LinkScanner and the TextScanner both derive the
   * SAME id for the same torrent, a magnet found by BOTH scanners is added ONCE —
   * the second scanner's duplicate is dropped here. Only genuinely-new torrents
   * are added and announced via `torrent-detected`.
   *
   * @param newResults - Newly detected torrents from this scan pass
   * @returns The subset of `newResults` that were not previously seen
   */
  private mergeResults(
    newResults: readonly DetectedTorrent[],
  ): readonly DetectedTorrent[] {
    const newlyAdded: DetectedTorrent[] = [];

    for (const result of newResults) {
      if (!this.detectedMap.has(result.id)) {
        this.detectedMap.set(result.id, result);
        newlyAdded.push(result);

        // Announce the individual torrent detection.
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
   * Build a PageScanResult snapshot from the current detected set.
   *
   * @param _newItems - Items newly detected in this scan (for symmetry with the
   *   reference API; the snapshot always reports the full deduped set)
   * @returns Page scan result over the full deduped detected set
   */
  private createScanResult(
    _newItems: readonly DetectedTorrent[],
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
   * Set up a MutationObserver to watch for DOM changes and trigger debounced
   * re-scans when torrent-relevant content is added/changed.
   */
  private setupMutationObserver(): void {
    this.mutationObserver = new MutationObserver((mutations) => {
      const hasRelevantChanges = mutations.some((mutation) => {
        // Check added nodes for anchors or magnet-bearing text.
        for (const node of mutation.addedNodes) {
          if (node instanceof Element) {
            if (
              node.tagName === "A" ||
              node.querySelector("a[href^='magnet:'], a[href$='.torrent']")
            ) {
              return true;
            }
          } else if (
            node instanceof Text &&
            node.textContent?.includes("magnet:")
          ) {
            return true;
          }
        }

        // Check href attribute changes on anchor elements.
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
