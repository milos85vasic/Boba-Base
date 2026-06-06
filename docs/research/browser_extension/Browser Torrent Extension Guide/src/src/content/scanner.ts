/**
 * @fileoverview Content script scanner bridge for BobaLink.
 *
 * Bridges the ScannerOrchestrator with the content script environment.
 * Handles result communication and manages the scanning lifecycle
 * within the content script context.
 *
 * @module content/scanner
 */

import { createLogger } from "../shared/logger";
import { ScannerOrchestrator } from "../scanner/orchestrator";

const log = createLogger("ContentScanner");

/**
 * Bridges the scanner orchestrator with the content script environment.
 *
 * Manages scan lifecycle, result aggregation, and communication
 * with the background service worker.
 */
export class ContentScanner {
  private orchestrator: ScannerOrchestrator;
  private isScanning = false;

  /**
   * Create a new content scanner bridge.
   *
   * @param orchestrator - The scanner orchestrator instance
   */
  constructor(orchestrator: ScannerOrchestrator) {
    this.orchestrator = orchestrator;
    this.setupEventListeners();
  }

  /**
   * Setup listeners for scanner events.
   */
  private setupEventListeners(): void {
    const events = this.orchestrator.getEvents();

    events.on("scan-started", () => {
      this.isScanning = true;
      log.debug("Scan started");
    });

    events.on("scan-completed", (data) => {
      this.isScanning = false;
      log.info(
        `Scan completed: ${data.magnetCount} magnets, ${data.torrentFileCount} files (${data.durationMs}ms)`,
      );
    });

    events.on("scan-error", (data) => {
      this.isScanning = false;
      log.error(`Scan error on ${data.url}: ${data.error}`);
    });

    events.on("torrent-detected", (data) => {
      log.debug(`Detected: ${data.displayName}`);
    });
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
   * Get the number of detected torrents.
   *
   * @returns Number of detected torrents
   */
  getDetectedCount(): number {
    return this.orchestrator.getDetectedCount();
  }

  /**
   * Get detected torrents.
   *
   * @returns Array of detected torrents
   */
  getDetectedTorrents() {
    return this.orchestrator.getDetectedTorrents();
  }
}
