/**
 * @fileoverview Abstract base scanner class for BobaLink.
 *
 * Defines the common interface and shared functionality for all torrent scanners.
 * Scanners are responsible for finding torrent-related content (magnet links,
 * .torrent files) within the DOM.
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
    scanFn: () => Promise<readonly DetectedTorrent[]>,
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
    root: Element | Document,
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
    // Generate a stable ID from the magnet URI or torrent URL
    const idSource =
      magnet?.infohash ?? torrentFile?.url ?? displayName;
    const id = this.hashString(idSource);

    return {
      id,
      type,
      magnet,
      torrentFile,
      displayName: displayName.length > 80 ? displayName.slice(0, 80) + "..." : displayName,
      selected: false,
      sent: false,
      sendStatus: null,
      detectedAt: Date.now(),
    };
  }

  /**
   * Simple string hash for generating IDs.
   *
   * @param str - String to hash
   * @returns Numeric hash
   */
  private hashString(str: string): string {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = (hash << 5) - hash + char;
      hash |= 0;
    }
    return Math.abs(hash).toString(36) + Date.now().toString(36);
  }
}
