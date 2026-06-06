/**
 * @fileoverview Text node scanner for detecting magnet links in plain text.
 *
 * Uses a TreeWalker to traverse text nodes in the DOM and find magnet links
 * that appear as plain text (not in anchor tags). Common on forums, comments,
 * and sites where magnet links are pasted as text.
 *
 * @module scanner/text-scanner
 */

import { BaseScanner } from "./base";
import { parseMagnetUri } from "../parser/magnet";
import { findMagnetUris } from "../parser/magnet";
import type { TypedEventEmitter } from "../shared/events";
import type { DetectedTorrent, MagnetInfo } from "../types/torrent";

/**
 * Scanner that finds magnet links embedded in plain text content.
 * Uses TreeWalker for efficient text node traversal.
 */
export class TextScanner extends BaseScanner {
  constructor(events: TypedEventEmitter) {
    super("TextScanner", events);
  }

  getScannerId(): string {
    return "text";
  }

  /**
   * Scan text nodes in the document for magnet links.
   *
   * Uses TreeWalker for efficient traversal of only text nodes,
   * skipping script/style elements and other non-content areas.
   *
   * @param root - Root element to scan (defaults to document.body)
   * @returns Array of detected torrent items
   */
  async scan(root?: Element): Promise<readonly DetectedTorrent[]> {
    return this.executeScan(async () => {
      const scanRoot = root ?? document.body;
      const results: DetectedTorrent[] = [];
      const seen = new Set<string>();
      let scannedNodes = 0;

      // Use TreeWalker to efficiently iterate only text nodes
      const treeWalker = document.createTreeWalker(
        scanRoot,
        NodeFilter.SHOW_TEXT,
        {
          acceptNode: (node: Text): number => {
            // Skip text inside script, style, and other non-content elements
            const parent = node.parentElement;
            if (!parent) return NodeFilter.FILTER_SKIP;

            if (
              parent.closest("script, style, noscript, template, textarea, code")
            ) {
              return NodeFilter.FILTER_SKIP;
            }

            // Skip very short text nodes (optimization)
            if (node.textContent && node.textContent.length < 20) {
              return NodeFilter.FILTER_SKIP;
            }

            return NodeFilter.FILTER_ACCEPT;
          },
        },
      );

      let textNode: Text | null;
      while ((textNode = treeWalker.nextNode() as Text | null)) {
        if (scannedNodes >= this.options.maxElements) {
          this.log.warn(`Reached max text nodes limit (${this.options.maxElements})`);
          break;
        }
        scannedNodes++;

        const text = textNode.textContent;
        if (!text) continue;

        // Fast check: does text contain "magnet:?"
        if (!text.includes("magnet:?")) continue;

        // Find all magnet URIs in this text node
        const magnetUris = findMagnetUris(text);

        for (const uri of magnetUris) {
          // Skip duplicates
          if (seen.has(uri)) continue;
          seen.add(uri);

          const torrent = this.processMagnetText(textNode, uri);
          if (torrent) results.push(torrent);
        }
      }

      this.log.debug(`Scanned ${scannedNodes} text nodes, found ${results.length} magnets`);
      return results;
    });
  }

  /**
   * Process a magnet URI found in a text node.
   *
   * @param textNode - The text node containing the magnet
   * @param uri - The full magnet URI
   * @returns DetectedTorrent or null if parsing fails
   */
  private processMagnetText(
    textNode: Text,
    uri: string,
  ): DetectedTorrent | null {
    try {
      // Find the closest element container for the source element
      const container = textNode.parentElement;

      const magnetInfo: MagnetInfo = parseMagnetUri(uri, container);

      // Try to find a contextual name from surrounding text or parent element
      const displayName =
        magnetInfo.displayName ??
        container?.getAttribute("title") ??
        container?.textContent?.trim() ??
        `Magnet ${magnetInfo.infohash.slice(0, 12)}...`;

      return this.createDetectedTorrent("magnet", displayName, magnetInfo, null);
    } catch {
      // Invalid magnet, skip
      return null;
    }
  }
}
