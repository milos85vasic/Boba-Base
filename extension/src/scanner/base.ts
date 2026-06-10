/**
 * @fileoverview Abstract base scanner class for BobaLink.
 *
 * Defines the common interface and shared functionality for all torrent scanners.
 * Scanners are responsible for finding torrent-related content (magnet links,
 * .torrent files) within the DOM.
 *
 * Ported into the BobaLink extension (Phase 2) from the reference guide source.
 * REFACTOR (disposition F-adopt-vs-rewrite): the reference derived each detection
 * id by appending `Date.now()` to the content hash (`base.ts:272` in the reference),
 * making ids UNSTABLE across runs and across pages. That broke deduplication: the
 * orchestrator's dedup `Map` is keyed on this id, so the same torrent detected twice
 * (rescan, second page, navigation) produced a different id each time and was treated
 * as a new item. This port derives a STABLE, deterministic id purely from the
 * torrent's identity (infohash if present, else a stable hash of the normalized
 * magnet URI / torrent-file URL / display name). The same torrent now always yields
 * the same id, so dedup works.
 *
 * @module scanner/base
 */

import { createLogger, type Logger } from "../shared/logger";
import type { TypedEventEmitter } from "../shared/events";
import type { DetectedTorrent } from "../types/torrent";

/**
 * Configuration options for scanners.
 */
export interface ScannerOptions {
  /** Whether to scan within shadow DOM */
  readonly scanShadowDom: boolean;

  /** Maximum number of elements to scan (safety limit) */
  readonly maxElements: number;

  /** Whether to include hidden elements */
  readonly includeHidden: boolean;

  /** CSS selector for elements to skip */
  readonly excludeSelector: string;
}

/**
 * Default scanner options.
 */
export const DEFAULT_SCANNER_OPTIONS: Readonly<ScannerOptions> = {
  scanShadowDom: true,
  maxElements: 10000,
  includeHidden: false,
  excludeSelector: "script,style,noscript,template,textarea",
};

/**
 * Abstract base class for all torrent scanners.
 *
 * Subclasses must implement the `scan()` method to perform their specific
 * detection logic. The base class provides common utilities for DOM traversal,
 * element filtering, and result management.
 */
export abstract class BaseScanner {
  /** Logger instance for this scanner */
  protected readonly log: Logger;

  /** Scanner configuration options */
  protected readonly options: Readonly<ScannerOptions>;

  /** Whether a scan is currently in progress */
  private isScanning = false;

  /**
   * Create a new scanner instance.
   *
   * @param name - Scanner name for logging
   * @param events - Event emitter for publishing results
   * @param options - Scanner configuration options
   */
  constructor(
    name: string,
    protected readonly events: TypedEventEmitter,
    options: Partial<ScannerOptions> = {},
  ) {
    this.log = createLogger(name);
    this.options = { ...DEFAULT_SCANNER_OPTIONS, ...options };
  }

  /**
   * Perform a scan of the document for torrent content.
   *
   * Subclasses must implement this method with their specific detection logic.
   *
   * @param root - Root element to scan (defaults to document.body)
   * @returns Array of detected torrent items
   */
  abstract scan(root?: Element): Promise<readonly DetectedTorrent[]>;

  /**
   * Get a unique identifier for this scanner type.
   */
  abstract getScannerId(): string;

  /**
   * Check if a scan is currently in progress.
   *
   * @returns True if scanning
   */
  isActive(): boolean {
    return this.isScanning;
  }

  /**
   * Execute a scan with proper state management.
   * Subclasses should call this from their scan() implementation.
   *
   * @param scanFn - Actual scan implementation
   * @returns Scan results
   */
  protected async executeScan(
    scanFn: () =>
      | readonly DetectedTorrent[]
      | Promise<readonly DetectedTorrent[]>,
  ): Promise<readonly DetectedTorrent[]> {
    if (this.isScanning) {
      this.log.warn("Scan already in progress, skipping");
      return [];
    }

    this.isScanning = true;
    const endTimer = this.log.timed("scan");

    try {
      const results = await scanFn();
      this.log.info(`Scan complete: found ${results.length} torrents`);
      return results;
    } catch (err) {
      this.log.error("Scan failed", err);
      return [];
    } finally {
      this.isScanning = false;
      endTimer();
    }
  }

  /**
   * Check if an element should be included in scanning.
   * Filters out hidden elements and excluded selectors.
   *
   * @param element - Element to check
   * @returns True if the element should be scanned
   */
  protected shouldIncludeElement(element: Element): boolean {
    // Skip excluded element types
    if (element.matches(this.options.excludeSelector)) {
      return false;
    }

    // Skip hidden elements unless configured otherwise
    if (!this.options.includeHidden) {
      const style = window.getComputedStyle(element);
      if (style.display === "none" || style.visibility === "hidden") {
        return false;
      }
    }

    return true;
  }

  /**
   * Get all elements matching a selector, including shadow DOM.
   *
   * @param root - Root element to search from
   * @param selector - CSS selector
   * @returns Array of matching elements
   */
  protected querySelectorAllDeep(
    root: Element | Document,
    selector: string,
  ): Element[] {
    const results: Element[] = [];
    const seen = new Set<Element>();

    // Query from the root document
    const addElements = (container: Element | Document): void => {
      try {
        const elements = container.querySelectorAll(selector);
        for (const el of elements) {
          if (!seen.has(el)) {
            seen.add(el);
            results.push(el);
          }
        }
      } catch {
        // Invalid selector, skip
      }
    };

    addElements(root);

    // Scan shadow DOM if enabled
    if (this.options.scanShadowDom) {
      this.scanShadowDOM(root, (shadowEl) => {
        addElements(shadowEl);
      });
    }

    return results;
  }

  /**
   * Recursively scan shadow DOM trees.
   *
   * @param root - Root element to search from
   * @param callback - Called for each shadow root found
   */
  private scanShadowDOM(
    root: Element | Document | ShadowRoot,
    callback: (shadowHost: Element) => void,
  ): void {
    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_ELEMENT,
      null,
    );

    let count = 0;
    let node: Element | null = walker.currentNode as Element;

    while (node && count < this.options.maxElements) {
      if (node.shadowRoot) {
        // Use shadow root's host element for querying
        callback(node);
        // Recursively scan inside the shadow root
        this.scanShadowDOM(node.shadowRoot, callback);
      }
      node = walker.nextNode() as Element | null;
      count++;
    }
  }

  /**
   * Create a detected torrent item from raw data.
   *
   * The detection `id` is STABLE and deterministic: it is derived purely from the
   * torrent's identity (infohash if present, else the normalized magnet URI /
   * torrent-file URL, else the display name) via {@link stableId}. It contains NO
   * wall-clock component, so the SAME torrent detected on two scans / two pages
   * always produces the SAME id — which is what makes the orchestrator's id-keyed
   * deduplication actually work. `detectedAt` (not the id) carries the timestamp.
   *
   * @param type - Type of torrent content
   * @param displayName - Display name for the UI
   * @param magnet - Magnet info if applicable
   * @param torrentFile - Torrent file info if applicable
   * @returns Detected torrent item
   */
  protected createDetectedTorrent(
    type: "magnet" | "torrent-file",
    displayName: string,
    magnet: DetectedTorrent["magnet"],
    torrentFile: DetectedTorrent["torrentFile"],
  ): DetectedTorrent {
    return {
      id: this.computeStableId(magnet, torrentFile, displayName),
      type,
      magnet,
      torrentFile,
      displayName:
        displayName.length > 80 ? displayName.slice(0, 80) + "..." : displayName,
      selected: false,
      sent: false,
      sendStatus: null,
      detectedAt: Date.now(),
    };
  }

  /**
   * Derive the STABLE, deterministic identity source string for a detected item.
   *
   * Priority: infohash (the canonical BitTorrent identity) → normalized magnet URI
   * → normalized torrent-file URL → display name. Magnet URIs and URLs are
   * normalized (lower-cased, whitespace-trimmed) so trivially-different spellings
   * of the same resource collapse to the same id.
   *
   * Exposed as a `protected` method (rather than inlined) so subclasses and the
   * orchestrator can compute the same id from a known-normalized infohash/magnet
   * the caller already holds.
   *
   * @param magnet - Magnet info if applicable
   * @param torrentFile - Torrent file info if applicable
   * @param displayName - Fallback display name
   * @returns A stable, time-independent id string
   */
  protected computeStableId(
    magnet: DetectedTorrent["magnet"],
    torrentFile: DetectedTorrent["torrentFile"],
    displayName: string,
  ): string {
    const identity =
      this.normalizeIdentity(magnet?.infohash) ??
      this.normalizeIdentity(magnet?.uri) ??
      this.normalizeIdentity(torrentFile?.url) ??
      this.normalizeIdentity(displayName) ??
      "unknown";
    return BaseScanner.stableHash(identity);
  }

  /**
   * Normalize an identity candidate to a canonical comparable form.
   * Returns null for null/undefined/blank input so the `??` priority chain
   * falls through to the next candidate.
   *
   * @param value - Raw identity candidate
   * @returns Normalized lowercase trimmed string, or null if blank
   */
  private normalizeIdentity(value: string | null | undefined): string | null {
    if (value == null) {
      return null;
    }
    const normalized = value.trim().toLowerCase();
    return normalized.length > 0 ? normalized : null;
  }

  /**
   * Deterministic djb2-style string hash, base-36 encoded.
   *
   * CRITICAL: this is a PURE function of its input — no `Date.now()`, no random,
   * no other ambient state. The reference implementation appended
   * `Date.now().toString(36)` here, which is exactly the defect this port removes:
   * a time-salted "id" can never deduplicate the same torrent across scans.
   *
   * @param str - String to hash
   * @returns Stable base-36 hash string
   */
  protected static stableHash(str: string): string {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = (hash << 5) - hash + char;
      hash |= 0;
    }
    return Math.abs(hash).toString(36);
  }
}
