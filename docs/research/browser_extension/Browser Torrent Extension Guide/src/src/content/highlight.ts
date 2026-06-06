/**
 * @fileoverview Visual highlight manager for detected torrents.
 *
 * Adds overlay badges and visual indicators to DOM elements that contain
 * torrent links (magnet URIs or .torrent files). Provides configurable
 * highlight styles: badge, border, and glow.
 *
 * The highlight manager listens to scan events and applies/removes
 * visual indicators as torrents are detected.
 *
 * @module content/highlight
 */

import { createLogger } from "../shared/logger";
import type { TypedEventEmitter } from "../shared/events";
import { storageGet } from "../shared/storage";
import { STORAGE_KEYS, DEFAULT_CONFIG } from "../shared/constants";
import type { ExtensionConfig } from "../types/config";

const log = createLogger("HighlightManager");

/**
 * CSS class names used for highlighting.
 */
const CLASSES = {
  /** Container for the highlight badge */
  BADGE: "bobalink-badge",

  /** Applied to elements with a border highlight */
  BORDER: "bobalink-border",

  /** Applied to elements with a glow highlight */
  GLOW: "bobalink-glow",

  /** The badge text/content */
  BADGE_TEXT: "bobalink-badge-text",

  /** Icon inside the badge */
  BADGE_ICON: "bobalink-badge-icon",
} as const;

/**
 * Manages visual highlighting of detected torrent elements on the page.
 *
 * Listens for scan events and applies visual indicators to elements
 * containing torrent links. Supports multiple highlight styles.
 */
export class HighlightManager {
  private readonly events: TypedEventEmitter;
  private readonly highlightedElements = new Set<Element>();
  private highlightStyle: "badge" | "border" | "glow" = "badge";
  private enabled = true;
  private unsubscribers: Array<() => void> = [];

  /**
   * Create a new highlight manager.
   *
   * @param events - Event emitter for scan events
   */
  constructor(events: TypedEventEmitter) {
    this.events = events;
    this.loadConfig();
    this.setupEventListeners();
  }

  /**
   * Load highlight configuration from storage.
   */
  private async loadConfig(): Promise<void> {
    try {
      const config = await storageGet<ExtensionConfig>(STORAGE_KEYS.CONFIG);
      this.highlightStyle = config?.highlightStyle ?? "badge";
      this.enabled = config?.highlightTorrents ?? true;
    } catch {
      this.highlightStyle = "badge";
      this.enabled = true;
    }
  }

  /**
   * Setup event listeners for scan events.
   */
  private setupEventListeners(): void {
    // Listen for individual torrent detections
    const unsub1 = this.events.on("torrent-detected", (data) => {
      if (this.enabled) {
        this.highlightTorrentElement(data.url, data.type);
      }
    });

    // Listen for scan completions to batch-apply highlights
    const unsub2 = this.events.on("scan-completed", () => {
      log.debug(`Highlighting complete. ${this.highlightedElements.size} elements marked.`);
    });

    this.unsubscribers.push(unsub1, unsub2);
  }

  /**
   * Highlight a DOM element containing a torrent link.
   *
   * @param url - The magnet URI or .torrent URL
   * @param type - Type of torrent content
   */
  private highlightTorrentElement(url: string, type: "magnet" | "torrent-file"): void {
    try {
      // Find the element with this URL
      const elements = this.findElementsByUrl(url);

      for (const element of elements) {
        if (this.highlightedElements.has(element)) continue;

        this.highlightedElements.add(element);

        switch (this.highlightStyle) {
          case "badge":
            this.addBadge(element, type);
            break;
          case "border":
            this.addBorder(element);
            break;
          case "glow":
            this.addGlow(element);
            break;
        }
      }
    } catch (err) {
      log.debug(`Failed to highlight element for ${url}`, err);
    }
  }

  /**
   * Find DOM elements that contain a specific URL.
   *
   * @param url - URL to search for
   * @returns Array of matching elements
   */
  private findElementsByUrl(url: string): Element[] {
    const results: Element[] = [];

    // Search for anchor elements with matching href
    if (url.startsWith("magnet:")) {
      // For magnet links, normalize case for comparison
      const magnetLinks = document.querySelectorAll('a[href^="magnet:"]');
      for (const el of magnetLinks) {
        const href = el.getAttribute("href");
        if (href && href.toLowerCase() === url.toLowerCase()) {
          results.push(el);
        }
      }
    } else {
      // For .torrent files, match the full URL
      const links = document.querySelectorAll(`a[href="${CSS.escape(url)}"]`);
      results.push(...links);

      // Also try partial match
      if (results.length === 0) {
        const allLinks = document.querySelectorAll("a[href]");
        for (const el of allLinks) {
          const href = el.getAttribute("href");
          if (href && (href === url || href.endsWith(url))) {
            results.push(el);
          }
        }
      }
    }

    return results;
  }

  /**
   * Add a badge overlay to an element.
   *
   * @param element - Element to badge
   * @param type - Torrent type for badge icon
   */
  private addBadge(element: Element, type: "magnet" | "torrent-file"): void {
    // Ensure the element can be positioned
    const htmlEl = element as HTMLElement;
    const computedStyle = window.getComputedStyle(htmlEl);
    if (computedStyle.position === "static") {
      htmlEl.style.position = "relative";
    }

    const badge = document.createElement("span");
    badge.className = CLASSES.BADGE;
    badge.title = `BobaLink: ${type === "magnet" ? "Magnet Link" : ".torrent File"}`;
    badge.innerHTML = `
      <span class="${CLASSES.BADGE_ICON}">${type === "magnet" ? "&#127759;" : "&#128190;"}</span>
      <span class="${CLASSES.BADGE_TEXT}">${type === "magnet" ? "MAGNET" : "TORRENT"}</span>
    `;

    htmlEl.appendChild(badge);
  }

  /**
   * Add a border highlight to an element.
   *
   * @param element - Element to highlight
   */
  private addBorder(element: Element): void {
    element.classList.add(CLASSES.BORDER);
  }

  /**
   * Add a glow highlight to an element.
   *
   * @param element - Element to highlight
   */
  private addGlow(element: Element): void {
    element.classList.add(CLASSES.GLOW);
  }

  /**
   * Remove all highlights from the page.
   */
  clearAllHighlights(): void {
    // Remove badges
    const badges = document.querySelectorAll(`.${CLASSES.BADGE}`);
    for (const badge of badges) {
      badge.remove();
    }

    // Remove border class
    const bordered = document.querySelectorAll(`.${CLASSES.BORDER}`);
    for (const el of bordered) {
      el.classList.remove(CLASSES.BORDER);
    }

    // Remove glow class
    const glowing = document.querySelectorAll(`.${CLASSES.GLOW}`);
    for (const el of glowing) {
      el.classList.remove(CLASSES.GLOW);
    }

    this.highlightedElements.clear();
    log.debug("All highlights cleared");
  }

  /**
   * Destroy the highlight manager and clean up.
   */
  destroy(): void {
    this.clearAllHighlights();

    // Unsubscribe from events
    for (const unsub of this.unsubscribers) {
      unsub();
    }
    this.unsubscribers = [];
  }
}
