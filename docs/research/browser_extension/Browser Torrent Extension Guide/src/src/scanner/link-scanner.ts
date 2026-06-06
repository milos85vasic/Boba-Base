/**
 * @fileoverview Link scanner for detecting torrent-related anchor tags.
 *
 * Scans the DOM for <a> elements with href attributes pointing to:
 * - Magnet links (href^="magnet:")
 * - .torrent files (href$=".torrent")
 * - Known torrent download URLs
 *
 * @module scanner/link-scanner
 */

import { BaseScanner } from "./base";
import { parseMagnetUri } from "../parser/magnet";
import {
  TORRENT_FILE_REGEX,
  TORRENT_FILE_VALIDATION_REGEX,
  SITE_SELECTORS,
} from "../shared/constants";
import { getDomain } from "../shared/utils";
import type { TypedEventEmitter } from "../shared/events";
import type { DetectedTorrent, MagnetInfo, TorrentFile } from "../types/torrent";

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
   * @param root - Root element to scan (defaults to document.body)
   * @returns Array of detected torrent items
   */
  async scan(root?: Element): Promise<readonly DetectedTorrent[]> {
    return this.executeScan(async () => {
      const scanRoot = root ?? document.body;
      const results: DetectedTorrent[] = [];
      const seen = new Set<string>();

      // 1. Use site-specific selectors for known torrent sites
      const siteSelectors = this.getSiteSelectors();
      for (const selector of siteSelectors) {
        const elements = this.querySelectorAllDeep(scanRoot, selector);
        for (const el of elements) {
          if (!this.shouldIncludeElement(el)) continue;

          const href = el.getAttribute("href");
          if (!href) continue;

          const normalized = href.toLowerCase().trim();

          // Skip duplicates
          if (seen.has(normalized)) continue;
          seen.add(normalized);

          // Handle magnet links
          if (normalized.startsWith("magnet:")) {
            const torrent = this.processMagnetLink(el, href);
            if (torrent) results.push(torrent);
          }
          // Handle .torrent files
          else if (this.isTorrentFileUrl(href)) {
            const torrent = this.processTorrentLink(el, href);
            if (torrent) results.push(torrent);
          }
        }
      }

      // 2. Generic fallback: scan all anchor elements
      const allAnchors = scanRoot.querySelectorAll("a[href]");
      for (const el of allAnchors) {
        if (!this.shouldIncludeElement(el)) continue;

        const href = el.getAttribute("href");
        if (!href) continue;

        const normalized = href.toLowerCase().trim();

        // Skip already processed
        if (seen.has(normalized)) continue;

        // Check for magnet links
        if (normalized.startsWith("magnet:")) {
          seen.add(normalized);
          const torrent = this.processMagnetLink(el, href);
          if (torrent) results.push(torrent);
        }
        // Check for .torrent files
        else if (this.isTorrentFileUrl(href)) {
          seen.add(normalized);
          const torrent = this.processTorrentLink(el, href);
          if (torrent) results.push(torrent);
        }
      }

      return results;
    });
  }

  /**
   * Get site-specific CSS selectors based on the current domain.
   *
   * @returns Array of CSS selectors to use
   */
  private getSiteSelectors(): readonly string[] {
    const domain = getDomain(window.location.href);

    // Try exact domain match
    if (domain in SITE_SELECTORS) {
      return SITE_SELECTORS[domain];
    }

    // Try without subdomains
    const parts = domain.split(".");
    if (parts.length > 2) {
      const baseDomain = parts.slice(-2).join(".");
      if (baseDomain in SITE_SELECTORS) {
        return SITE_SELECTORS[baseDomain];
      }
    }

    // Return generic selectors
    return SITE_SELECTORS["generic"];
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
        element.textContent?.trim() ??
        `Magnet ${magnetInfo.infohash.slice(0, 12)}...`;

      return this.createDetectedTorrent(
        "magnet",
        displayName,
        magnetInfo,
        null,
      );
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
   * @returns DetectedTorrent
   */
  private processTorrentLink(
    element: Element,
    href: string,
  ): DetectedTorrent | null {
    // Resolve relative URLs
    const absoluteUrl = this.resolveUrl(href);
    if (!absoluteUrl) return null;

    // Extract filename from URL
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
      element.textContent?.trim() ||
      filename ||
      "Unknown torrent file";

    return this.createDetectedTorrent("torrent-file", displayName, null, torrentFile);
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
   * Extract filename from a URL.
   *
   * @param url - URL to extract from
   * @returns Filename string
   */
  private extractFilename(url: string): string {
    try {
      const pathname = new URL(url).pathname;
      const segments = pathname.split("/");
      const lastSegment = segments[segments.length - 1];
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
