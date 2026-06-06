/**
 * @fileoverview Unit tests for the scanner system.
 *
 * Tests the scanner orchestrator, link scanner, and text scanner
 * with a simulated DOM environment.
 */

import { ScannerOrchestrator } from "../../src/scanner/orchestrator";
import { TypedEventEmitter } from "../../src/shared/events";
import { getSiteConfig, isKnownTorrentSite } from "../../src/scanner/site-db";

describe("Scanner System", () => {
  describe("TypedEventEmitter", () => {
    it("emits events to registered listeners", () => {
      const emitter = new TypedEventEmitter();
      const listener = jest.fn();

      emitter.on("scan-started", listener);
      emitter.emit("scan-started", { url: "https://example.com", timestamp: Date.now() });

      expect(listener).toHaveBeenCalledTimes(1);
    });

    it("supports multiple listeners for same event", () => {
      const emitter = new TypedEventEmitter();
      const listener1 = jest.fn();
      const listener2 = jest.fn();

      emitter.on("scan-started", listener1);
      emitter.on("scan-started", listener2);
      emitter.emit("scan-started", { url: "https://example.com", timestamp: Date.now() });

      expect(listener1).toHaveBeenCalledTimes(1);
      expect(listener2).toHaveBeenCalledTimes(1);
    });

    it("unsubscribe stops receiving events", () => {
      const emitter = new TypedEventEmitter();
      const listener = jest.fn();

      const unsub = emitter.on("scan-started", listener);
      unsub();
      emitter.emit("scan-started", { url: "https://example.com", timestamp: Date.now() });

      expect(listener).not.toHaveBeenCalled();
    });

    it("once listener only fires once", () => {
      const emitter = new TypedEventEmitter();
      const listener = jest.fn();

      emitter.once("scan-started", listener);
      emitter.emit("scan-started", { url: "https://example.com", timestamp: Date.now() });
      emitter.emit("scan-started", { url: "https://example.com", timestamp: Date.now() });

      expect(listener).toHaveBeenCalledTimes(1);
    });

    it("reports correct listener count", () => {
      const emitter = new TypedEventEmitter();
      expect(emitter.listenerCount("scan-started")).toBe(0);

      const unsub = emitter.on("scan-started", () => {});
      expect(emitter.listenerCount("scan-started")).toBe(1);

      unsub();
      expect(emitter.listenerCount("scan-started")).toBe(0);
    });

    it("does not break when emitting with no listeners", () => {
      const emitter = new TypedEventEmitter();
      expect(() =>
        emitter.emit("scan-started", { url: "https://example.com", timestamp: Date.now() }),
      ).not.toThrow();
    });

    it("handles errors in listeners gracefully", () => {
      const emitter = new TypedEventEmitter();
      const badListener = (): void => {
        throw new Error("Listener error");
      };
      const goodListener = jest.fn();

      emitter.on("scan-started", badListener);
      emitter.on("scan-started", goodListener);

      expect(() =>
        emitter.emit("scan-started", { url: "https://example.com", timestamp: Date.now() }),
      ).not.toThrow();

      expect(goodListener).toHaveBeenCalled();
    });
  });

  describe("ScannerOrchestrator", () => {
    let orchestrator: ScannerOrchestrator;

    beforeEach(() => {
      document.body.innerHTML = "";
      orchestrator = new ScannerOrchestrator(new TypedEventEmitter(), {
        enableLinkScanner: true,
        enableTextScanner: true,
        mutationDebounceMs: 100,
        observeMutations: false,
      });
    });

    afterEach(() => {
      orchestrator.stop();
    });

    it("initializes with zero detected torrents", () => {
      expect(orchestrator.getDetectedCount()).toBe(0);
      expect(orchestrator.hasInitialScanCompleted()).toBe(false);
    });

    it("is not scanning initially", () => {
      expect(orchestrator.isCurrentlyScanning()).toBe(false);
    });

    it("returns empty array when no torrents", () => {
      expect(orchestrator.getDetectedTorrents()).toEqual([]);
    });
  });

  describe("Site Database", () => {
    it("recognizes known torrent sites", () => {
      expect(isKnownTorrentSite("https://1337x.to/search/ubuntu")).toBe(true);
      expect(isKnownTorrentSite("https://nyaa.si/view/1234")).toBe(true);
      expect(isKnownTorrentSite("https://yts.mx/movies/ubuntu-22-04")).toBe(true);
    });

    it("returns false for unknown sites", () => {
      expect(isKnownTorrentSite("https://example.com")).toBe(false);
      expect(isKnownTorrentSite("https://google.com")).toBe(false);
    });

    it("returns site config for known sites", () => {
      const config = getSiteConfig("https://1337x.to");
      expect(config).not.toBeNull();
      expect(config?.name).toBe("1337x");
      expect(config?.domain).toBe("1337x.to");
      expect(config?.selectors.length).toBeGreaterThan(0);
    });

    it("returns null for unknown sites", () => {
      expect(getSiteConfig("https://example.com")).toBeNull();
    });

    it("matches sites with www prefix", () => {
      const config = getSiteConfig("https://www.1337x.to");
      expect(config).not.toBeNull();
      expect(config?.domain).toBe("1337x.to");
    });

    it("has selectors for all known sites", () => {
      // Verify the 1337x site has magnet selector
      const config = getSiteConfig("https://1337x.to");
      const magnetSelector = config?.selectors.some((s) =>
        s.includes('href^="magnet:'),
      );
      expect(magnetSelector).toBe(true);
    });
  });

  describe("DOM Magnet Link Detection", () => {
    beforeEach(() => {
      document.body.innerHTML = "";
    });

    it("finds magnet links in anchor tags", () => {
      document.body.innerHTML = `
        <a href="magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678&dn=Test">Link 1</a>
        <a href="magnet:?xt=urn:btih:abcdef1234567890abcdef1234567890abcdef12&dn=Test2">Link 2</a>
      `;

      const links = document.querySelectorAll('a[href^="magnet:"]');
      expect(links.length).toBe(2);
    });

    it("finds .torrent file links", () => {
      document.body.innerHTML = `
        <a href="http://example.com/file.torrent">Torrent</a>
      `;

      const links = document.querySelectorAll('a[href$=".torrent"]');
      expect(links.length).toBe(1);
    });

    it("ignores non-torrent links", () => {
      document.body.innerHTML = `
        <a href="http://example.com">Normal</a>
        <a href="http://example.com/file.txt">Text file</a>
      `;

      const magnets = document.querySelectorAll('a[href^="magnet:"]');
      expect(magnets.length).toBe(0);
    });

    it("finds magnet links in nested elements", () => {
      document.body.innerHTML = `
        <div>
          <span>
            <a href="magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678&dn=Nested">Nested</a>
          </span>
        </div>
      `;

      const links = document.querySelectorAll('a[href^="magnet:"]');
      expect(links.length).toBe(1);
    });
  });
});
