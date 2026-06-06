/**
 * @fileoverview qBitTorrent API adapter for BobaLink.
 *
 * Provides a high-level interface to qBitTorrent operations, abstracting
 * the underlying API calls. Handles torrent addition, management, and
 * status queries with proper error handling.
 *
 * @module api/qbittorrent
 */

import { createLogger } from "../shared/logger";
import { TorrentError, normalizeError } from "../shared/errors";
import { BobaAPIClient } from "./client";
import type { DetectedTorrent, SendResult } from "../types/torrent";
import type { ServerConfig } from "../types/config";

const log = createLogger("qBitTorrentAdapter");

/**
 * High-level adapter for qBitTorrent operations.
 *
 * Wraps the BobaAPIClient with domain-specific methods for torrent management.
 */
export class qBitTorrentAdapter {
  private client: BobaAPIClient;

  /**
   * Create a new qBitTorrent adapter.
   *
   * @param client - Configured API client
   */
  constructor(client: BobaAPIClient) {
    this.client = client;
  }

  /**
   * Send a detected torrent to qBitTorrent.
   *
   * Handles both magnet links and .torrent files, with proper error handling
   * and result tracking.
   *
   * @param torrent - The detected torrent to send
   * @param config - Server configuration for add options
   * @returns Send result with success status
   */
  async sendTorrent(
    torrent: DetectedTorrent,
    config: ServerConfig,
  ): Promise<SendResult> {
    const startTime = Date.now();
    log.info(`Sending torrent: ${torrent.displayName}`);

    try {
      let success: boolean;

      if (torrent.type === "magnet" && torrent.magnet) {
        success = await this.addMagnet(torrent.magnet.uri, config);
      } else if (torrent.type === "torrent-file" && torrent.torrentFile) {
        success = await this.addTorrentFile(torrent.torrentFile.url, config);
      } else {
        throw new TorrentError("Invalid torrent: missing magnet URI or file URL");
      }

      const result: SendResult = {
        success,
        torrent,
        error: null,
        response: null,
        completedAt: Date.now(),
      };

      log.info(`Torrent sent: ${success ? "success" : "failed"}`);
      return result;
    } catch (err) {
      const error = normalizeError(err);
      log.error(`Failed to send torrent: ${error.message}`);

      return {
        success: false,
        torrent,
        error: error.getUserMessage(),
        response: null,
        completedAt: Date.now(),
      };
    }
  }

  /**
   * Send multiple torrents to qBitTorrent.
   *
   * @param torrents - Array of detected torrents
   * @param config - Server configuration
   * @returns Array of send results
   */
  async sendTorrents(
    torrents: readonly DetectedTorrent[],
    config: ServerConfig,
  ): Promise<readonly SendResult[]> {
    log.info(`Sending ${torrents.length} torrents`);
    const results: SendResult[] = [];

    for (const torrent of torrents) {
      try {
        const result = await this.sendTorrent(torrent, config);
        results.push(result);

        // Small delay between sends to avoid overwhelming the server
        if (torrents.indexOf(torrent) < torrents.length - 1) {
          await new Promise((resolve) => setTimeout(resolve, 250));
        }
      } catch (err) {
        const error = normalizeError(err);
        results.push({
          success: false,
          torrent,
          error: error.getUserMessage(),
          response: null,
          completedAt: Date.now(),
        });
      }
    }

    const succeeded = results.filter((r) => r.success).length;
    log.info(`Batch send complete: ${succeeded}/${torrents.length} succeeded`);

    return results;
  }

  /**
   * Add a magnet URI to qBitTorrent.
   *
   * @param magnetUri - The magnet URI
   * @param config - Server configuration for options
   * @returns True if added successfully
   */
  private async addMagnet(
    magnetUri: string,
    config: ServerConfig,
  ): Promise<boolean> {
    const options = this.buildAddOptions(config);
    return this.client.addTorrentFromMagnet(magnetUri, options);
  }

  /**
   * Add a .torrent file to qBitTorrent.
   *
   * @param url - URL of the .torrent file
   * @param config - Server configuration for options
   * @returns True if added successfully
   */
  private async addTorrentFile(
    url: string,
    config: ServerConfig,
  ): Promise<boolean> {
    try {
      // Download the .torrent file
      log.debug(`Downloading .torrent file from ${url}`);
      const response = await fetch(url, {
        credentials: "same-origin",
      });

      if (!response.ok) {
        throw new TorrentError(
          `Failed to download .torrent file: HTTP ${response.status}`,
        );
      }

      const blob = await response.blob();
      const filename = this.extractFilename(url);
      const file = new File([blob], filename, {
        type: "application/x-bittorrent",
      });

      const options = this.buildAddOptions(config);
      return this.client.addTorrentFromFile(file, options);
    } catch (err) {
      if (err instanceof TorrentError) throw err;
      throw new TorrentError(`Failed to add torrent file: ${String(err)}`, {
        cause: err instanceof Error ? err : undefined,
      });
    }
  }

  /**
   * Build qBitTorrent add options from server configuration.
   *
   * @param config - Server configuration
   * @returns Add options for the qBitTorrent API
   */
  private buildAddOptions(config: ServerConfig) {
    return {
      savepath: config.defaultSavePath ?? undefined,
      category: config.defaultCategory ?? undefined,
      skip_checking: config.skipHashCheck ? "true" : "false",
      paused: config.startPaused ? "true" : "false",
      autoTMM: config.autoTMM ? "true" : "false",
      contentLayout: this.mapContentLayout(config.contentLayout),
      upLimit: config.uploadLimit > 0 ? config.uploadLimit * 1024 : undefined,
      dlLimit: config.downloadLimit > 0 ? config.downloadLimit * 1024 : undefined,
    };
  }

  /**
   * Map our content layout enum to qBitTorrent values.
   *
   * @param layout - Our content layout value
   * @returns qBitTorrent content layout string
   */
  private mapContentLayout(
    layout: "original" | "subfolder" | "no_subfolder",
  ): "Original" | "Subfolder" | "NoSubfolder" {
    switch (layout) {
      case "subfolder":
        return "Subfolder";
      case "no_subfolder":
        return "NoSubfolder";
      default:
        return "Original";
    }
  }

  /**
   * Extract filename from URL.
   *
   * @param url - URL to extract from
   * @returns Filename
   */
  private extractFilename(url: string): string {
    try {
      const pathname = new URL(url).pathname;
      const segments = pathname.split("/");
      const lastSegment = segments[segments.length - 1];
      return decodeURIComponent(lastSegment) || "download.torrent";
    } catch {
      return "download.torrent";
    }
  }

  /**
   * Get the underlying API client.
   *
   * @returns The BobaAPIClient instance
   */
  getClient(): BobaAPIClient {
    return this.client;
  }
}
