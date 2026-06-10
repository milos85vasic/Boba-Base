/**
 * @fileoverview Visual highlight manager for detected torrents (Phase 3).
 *
 * Adds an overlay marker (badge by default) onto the DOM elements that contain
 * detected torrent links (magnet URIs or `.torrent` files), so the user SEES on
 * the page itself which links BobaLink recognised. Three styles are supported:
 * `badge` (an absolutely-positioned chip appended inside the anchor), `border`
 * (an outline class), and `glow` (a box-shadow class). The manager listens to the
 * orchestrator's `torrent-detected` events and applies markers as torrents are
 * found; it can be toggled on/off at runtime and cleans up every marker it added.
 *
 * Ported into the BobaLink extension (REFACTOR per F-adopt-vs-rewrite) from the
 * reference guide source. Deltas vs the reference, all behaviour-preserving:
 *   1. Config is INJECTABLE via the constructor `options` (style + enabled) so the
 *      manager is deterministically testable and the popup/options UI can drive it
 *      directly; when omitted it still falls back to `chrome.storage` config
 *      (and finally to the committed `DEFAULT_CONFIG`), exactly like the reference.
 *   2. {@link setEnabled} is a real runtime toggle: turning highlighting OFF
 *      removes every marker currently on the page; turning it back ON re-marks the
 *      already-detected set. This is the "highlight-toggle" surface the content
 *      entry exposes to background messages.
 *   3. The badge is built with safe DOM APIs (`createElement` + `textContent`)
 *      rather than `innerHTML`, so no page string is ever parsed as markup.
 *
 * @module content/highlight
 */

import { createLogger } from "../shared/logger";
import type { TypedEventEmitter } from "../shared/events";
import { storageGet } from "../shared/storage";
import { STORAGE_KEYS } from "../shared/constants";
import { DEFAULT_CONFIG, type ExtensionConfig } from "../types/config";
import type { TorrentContentType } from "../types/torrent";

const log = createLogger("HighlightManager");

/** Highlight visual style. */
export type HighlightStyle = "badge" | "border" | "glow";

/**
 * CSS class names used for highlighting (kept in sync with `styles.css`).
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

/** Globe emoji for magnet markers / floppy-disk emoji for `.torrent` markers. */
const ICON = {
  magnet: "\u{1F30F}",
  "torrent-file": "\u{1F4BE}",
} as const;

/**
 * Options for the highlight manager. When a field is omitted the manager resolves
 * it from `chrome.storage` config, falling back to {@link DEFAULT_CONFIG}.
 */
export interface HighlightOptions {
  /** Marker style (badge / border / glow). */
  readonly style?: HighlightStyle;
  /** Whether highlighting is enabled. */
  readonly enabled?: boolean;
}

/**
 * Manages visual highlighting of detected torrent elements on the page.
 *
 * Listens for `torrent-detected` events and applies visual markers to the
 * elements containing the detected links. Supports multiple highlight styles and
 * a runtime on/off toggle, and removes every marker it added on
 * {@link clearAllHighlights} / {@link destroy}.
 */
export class HighlightManager {
  private readonly events: TypedEventEmitter;
  /** Elements currently carrying a marker, mapped to their detected type. */
  private readonly highlighted = new Map<Element, TorrentContentType>();
  /** URLs detected so far (so a re-enable can re-apply markers). */
  private readonly detectedUrls = new Map<string, TorrentContentType>();
  private highlightStyle: HighlightStyle = "badge";
  private enabled = true;
  private unsubscribers: Array<() => void> = [];

  /**
   * Create a new highlight manager.
   *
   * @param events - Event emitter for scan events
   * @param options - Optional explicit style/enabled; storage config when omitted
   */
  constructor(events: TypedEventEmitter, options: HighlightOptions = {}) {
    this.events = events;

    if (options.style !== undefined) {
      this.highlightStyle = options.style;
    }
    if (options.enabled !== undefined) {
      this.enabled = options.enabled;
    }

    // Only consult storage for the fields the caller did NOT pin explicitly.
    if (options.style === undefined || options.enabled === undefined) {
      void this.loadConfig(options);
    }

    this.setupEventListeners();
  }

  /**
   * Load highlight configuration from storage for any unset option, falling back
   * to the committed {@link DEFAULT_CONFIG}.
   *
   * @param options - The explicit options (already-set fields are not overwritten)
   */
  private async loadConfig(options: HighlightOptions): Promise<void> {
    try {
      const config = await storageGet<ExtensionConfig>(STORAGE_KEYS.CONFIG);
      if (options.style === undefined) {
        this.highlightStyle =
          config?.highlightStyle ?? DEFAULT_CONFIG.highlightStyle;
      }
      if (options.enabled === undefined) {
        this.enabled = config?.highlightTorrents ?? DEFAULT_CONFIG.highlightTorrents;
      }
    } catch {
      if (options.style === undefined) {
        this.highlightStyle = DEFAULT_CONFIG.highlightStyle;
      }
      if (options.enabled === undefined) {
        this.enabled = DEFAULT_CONFIG.highlightTorrents;
      }
    }
  }

  /**
   * Subscribe to the orchestrator's detection events.
   */
  private setupEventListeners(): void {
    const unsub1 = this.events.on("torrent-detected", (data) => {
      this.detectedUrls.set(data.url, data.type);
      if (this.enabled) {
        this.highlightTorrentElement(data.url, data.type);
      }
    });

    const unsub2 = this.events.on("scan-completed", () => {
      log.debug(`Highlighting complete. ${this.highlighted.size} elements marked.`);
    });

    this.unsubscribers.push(unsub1, unsub2);
  }

  /**
   * Whether highlighting is currently enabled.
   *
   * @returns True if markers are being applied
   */
  isEnabled(): boolean {
    return this.enabled;
  }

  /**
   * Get the marker style in use.
   *
   * @returns The current highlight style
   */
  getStyle(): HighlightStyle {
    return this.highlightStyle;
  }

  /**
   * Toggle highlighting on/off at runtime.
   *
   * Turning OFF removes every marker currently on the page. Turning ON re-applies
   * markers to every torrent detected so far. This is the surface the content
   * entry drives from a background `highlight-toggle` message.
   *
   * @param enabled - Desired enabled state
   */
  setEnabled(enabled: boolean): void {
    if (this.enabled === enabled) return;
    this.enabled = enabled;

    if (enabled) {
      // Re-mark everything detected so far.
      for (const [url, type] of this.detectedUrls) {
        this.highlightTorrentElement(url, type);
      }
      log.debug("Highlighting enabled");
    } else {
      this.clearAllHighlights();
      log.debug("Highlighting disabled");
    }
  }

  /**
   * Highlight the DOM element(s) containing a torrent link.
   *
   * @param url - The magnet URI or `.torrent` URL
   * @param type - Type of torrent content
   */
  private highlightTorrentElement(url: string, type: TorrentContentType): void {
    try {
      const elements = this.findElementsByUrl(url);
      for (const element of elements) {
        if (this.highlighted.has(element)) continue;
        this.highlighted.set(element, type);

        switch (this.highlightStyle) {
          case "badge":
            this.addBadge(element, type);
            break;
          case "border":
            element.classList.add(CLASSES.BORDER);
            break;
          case "glow":
            element.classList.add(CLASSES.GLOW);
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

    if (url.startsWith("magnet:")) {
      // Magnet hrefs compared case-insensitively (hex hash case is not significant).
      const magnetLinks = document.querySelectorAll('a[href^="magnet:"]');
      for (const el of magnetLinks) {
        const href = el.getAttribute("href");
        if (href && href.toLowerCase() === url.toLowerCase()) {
          results.push(el);
        }
      }
    } else {
      const links = document.querySelectorAll(`a[href="${CSS.escape(url)}"]`);
      results.push(...links);

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
   * Append a badge marker inside an element (built with safe DOM APIs).
   *
   * @param element - Element to badge
   * @param type - Torrent type for the badge icon + label
   */
  private addBadge(element: Element, type: TorrentContentType): void {
    const htmlEl = element as HTMLElement;
    // Ensure the absolutely-positioned badge anchors to this element.
    const computedStyle = window.getComputedStyle(htmlEl);
    if (computedStyle.position === "static") {
      htmlEl.style.position = "relative";
    }

    const badge = document.createElement("span");
    badge.className = CLASSES.BADGE;
    badge.title = `BobaLink: ${type === "magnet" ? "Magnet Link" : ".torrent File"}`;

    const iconEl = document.createElement("span");
    iconEl.className = CLASSES.BADGE_ICON;
    iconEl.textContent = ICON[type];

    const textEl = document.createElement("span");
    textEl.className = CLASSES.BADGE_TEXT;
    textEl.textContent = type === "magnet" ? "MAGNET" : "TORRENT";

    badge.appendChild(iconEl);
    badge.appendChild(textEl);
    htmlEl.appendChild(badge);
  }

  /**
   * Remove every marker this manager applied from the page.
   */
  clearAllHighlights(): void {
    for (const badge of document.querySelectorAll(`.${CLASSES.BADGE}`)) {
      badge.remove();
    }
    for (const el of document.querySelectorAll(`.${CLASSES.BORDER}`)) {
      el.classList.remove(CLASSES.BORDER);
    }
    for (const el of document.querySelectorAll(`.${CLASSES.GLOW}`)) {
      el.classList.remove(CLASSES.GLOW);
    }

    this.highlighted.clear();
    log.debug("All highlights cleared");
  }

  /**
   * Destroy the highlight manager: clear markers and unsubscribe from events.
   */
  destroy(): void {
    this.clearAllHighlights();
    this.detectedUrls.clear();
    for (const unsub of this.unsubscribers) {
      unsub();
    }
    this.unsubscribers = [];
  }
}
