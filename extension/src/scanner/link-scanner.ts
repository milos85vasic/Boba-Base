/**
 * @fileoverview Link scanner for detecting torrent-related anchor tags (BobaLink Phase 2 port).
 *
 * Scans the DOM for <a> elements with href attributes pointing to:
 * - Magnet links (href^="magnet:")
 * - .torrent files (href$=".torrent")
 * - Known torrent download URLs (via the site-db CSS selectors)
 *
 * Ported into the BobaLink extension (ADOPT per F-adopt-vs-rewrite) from the
 * reference guide source. Two committed-dependency integrations replace the
 * reference's inlined logic:
 *   1. Site-selector resolution is delegated to the committed
 *      {@link getSiteSelectors} (scanner/site-db) — the SINGLE source of truth
 *      over `SITE_SELECTORS`, with `www.` stripping + base-domain fallback +
 *      generic fallback. The reference reimplemented that lookup inline.
 *   2. Detection `id`s come from the committed {@link BaseScanner.createDetectedTorrent}
 *      / `computeStableId`, which derive a STABLE, time-independent id from the
 *      torrent's identity (infohash → magnet URI → torrent-file URL → display
 *      name). This is what makes the same torrent dedup across rescans / pages
 *      (the reference's `Date.now()`-salted id could not).
 *
 * Magnet URIs are parsed via the committed {@link parseMagnetUri} (parser/magnet),
 * which also XSS-sanitizes the `dn` display name.
 *
 * @module scanner/link-scanner
 */

import { BaseScanner } from "./base";
import { getSiteSelectors } from "./site-db";
import { parseMagnetUri } from "../parser/magnet";
import { TORRENT_FILE_VALIDATION_REGEX } from "../shared/constants";
import type { TypedEventEmitter } from "../shared/events";
import type {
  DetectedTorrent,
  MagnetInfo,
  TorrentFile,
} from "../types/torrent";

/**
 * Scanner that finds torrent content in anchor (<a>) elements.
 */
export class LinkScanner extends BaseScanner {
  constructor(events: TypedEventEmitter) {
    super("LinkScanner", events);
  }

  getScannerId(): string {
    return "link";
  }

  /**
   * Scan the document for torrent links in anchor elements.
   *
   * Runs two passes:
   *   1. Site-specific: the CSS selectors resolved for the current host via the
   *      committed {@link getSiteSelectors}.
   *   2. Generic fallback: every `a[href]` not yet seen.
   * Magnet hrefs and `.torrent` (suffix) hrefs are detected; everything else is
   * ignored. Duplicate hrefs (case-insensitive, trimmed) are scanned once.
   *
   * @param root - Root element to scan (defaults to document.body)
   * @returns Array of detected torrent items with STABLE ids
   */
  async scan(root?: Element): Promise<readonly DetectedTorrent[]> {
    return this.executeScan(() => {
      const scanRoot = root ?? document.body;
      const results: DetectedTorrent[] = [];
      const seen = new Set<string>();

      const consider = (el: Element): void => {
        if (!this.shouldIncludeElement(el)) return;

        const href = el.getAttribute("href");
        if (!href) return;

        const normalized = href.toLowerCase().trim();
        if (seen.has(normalized)) return;

        if (normalized.startsWith("magnet:")) {
          seen.add(normalized);
          const torrent = this.processMagnetLink(el, href);
          if (torrent) results.push(torrent);
        } else if (this.isTorrentFileUrl(href)) {
          seen.add(normalized);
          const torrent = this.processTorrentLink(el, href);
          if (torrent) results.push(torrent);
        }
      };

      // 1. Site-specific pass: selectors for the current host (shadow-DOM aware).
      for (const selector of this.getSiteSelectors()) {
        for (const el of this.querySelectorAllDeep(scanRoot, selector)) {
          consider(el);
        }
      }

      // 2. Generic fallback: scan all remaining anchor elements.
      for (const el of scanRoot.querySelectorAll("a[href]")) {
        consider(el);
      }

      return results;
    });
  }

  /**
   * Get site-specific CSS selectors for the current host.
   *
   * Delegates to the committed {@link getSiteSelectors} (scanner/site-db), the
   * single source of truth — exact-host match → base-domain fallback → generic.
   *
   * @returns Array of CSS selectors to use
   */
  private getSiteSelectors(): readonly string[] {
    return getSiteSelectors(window.location.href);
  }

  /**
   * Check if a URL points to a .torrent file.
   *
   * @param url - URL to check
   * @returns True if it looks like a torrent file URL
   */
  private isTorrentFileUrl(url: string): boolean {
    return TORRENT_FILE_VALIDATION_REGEX.test(url);
  }

  /**
   * Process a magnet link element into a DetectedTorrent.
   *
   * @param element - The anchor element
   * @param href - The magnet URI
   * @returns DetectedTorrent or null if invalid
   */
  private processMagnetLink(
    element: Element,
    href: string,
  ): DetectedTorrent | null {
    try {
      const magnetInfo: MagnetInfo = parseMagnetUri(href, element);

      const displayName =
        magnetInfo.displayName ??
        (element.textContent?.trim() || null) ??
        `Magnet ${magnetInfo.infohash.slice(0, 12)}...`;

      return this.createDetectedTorrent("magnet", displayName, magnetInfo, null);
    } catch {
      // Invalid magnet link, skip
      return null;
    }
  }

  /**
   * Process a .torrent file link into a DetectedTorrent.
   *
   * @param element - The anchor element
   * @param href - The .torrent URL
   * @returns DetectedTorrent or null if the URL cannot be resolved
   */
  private processTorrentLink(
    element: Element,
    href: string,
  ): DetectedTorrent | null {
    const absoluteUrl = this.resolveUrl(href);
    if (!absoluteUrl) return null;

    const filename = this.extractFilename(absoluteUrl);

    const torrentFile: TorrentFile = {
      url: absoluteUrl,
      filename,
      size: null,
      sameOrigin: this.isSameOrigin(absoluteUrl),
      detectedAt: Date.now(),
      sourceElement: element,
    };

    const displayName =
      element.textContent?.trim() || filename || "Unknown torrent file";

    return this.createDetectedTorrent(
      "torrent-file",
      displayName,
      null,
      torrentFile,
    );
  }

  /**
   * Resolve a potentially relative URL to absolute.
   *
   * @param url - URL to resolve
   * @returns Absolute URL, or null if invalid
   */
  private resolveUrl(url: string): string | null {
    try {
      return new URL(url, window.location.href).href;
    } catch {
      return null;
    }
  }

  /**
   * Extract a filename from a URL's path.
   *
   * @param url - URL to extract from
   * @returns Filename string
   */
  private extractFilename(url: string): string {
    try {
      const pathname = new URL(url).pathname;
      const segments = pathname.split("/");
      const lastSegment = segments[segments.length - 1] ?? "";
      return decodeURIComponent(lastSegment) || "unknown.torrent";
    } catch {
      return "unknown.torrent";
    }
  }

  /**
   * Check if a URL is from the same origin as the current page.
   *
   * @param url - URL to check
   * @returns True if same origin
   */
  private isSameOrigin(url: string): boolean {
    try {
      return new URL(url).origin === window.location.origin;
    } catch {
      return false;
    }
  }
}
