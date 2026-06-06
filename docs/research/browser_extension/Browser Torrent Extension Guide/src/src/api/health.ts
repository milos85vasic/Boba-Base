/**
 * @fileoverview Health checker for BobaLink.
 *
 * Periodically checks the connectivity and health of configured qBitTorrent/Boba
 * servers. Uses chrome.alarms for periodic checks and maintains health status
 * in storage for use by popup and options pages.
 *
 * @module api/health
 */

import { createLogger } from "../shared/logger";
import { BobaAPIClient } from "./client";
import { AuthHandler } from "./auth";
import { storageSet, storageGet } from "../shared/storage";
import { STORAGE_KEYS, REQUEST_TIMEOUTS } from "../shared/constants";
import type {
  HealthCheckResult,
  HealthStatus,
  ServerConfig,
} from "../types/api";
import type { ConnectionTestResult } from "../types/config";

const log = createLogger("HealthChecker");

/**
 * Thresholds for determining health status.
 */
const HEALTH_THRESHOLDS = {
  /** Response time below this is considered healthy (ms) */
  HEALTHY_LATENCY_MS: 2000,

  /** Response time above this is considered degraded (ms) */
  DEGRADED_LATENCY_MS: 5000,

  /** Number of consecutive failures before marking as unhealthy */
  MAX_FAILURES: 2,
} as const;

/**
 * Health checker that monitors server connectivity.
 */
export class HealthChecker {
  private readonly results: Map<string, HealthCheckResult> = new Map();
  private checkInProgress = false;

  /**
   * Perform a health check on a single server.
   *
   * @param config - Server configuration
   * @returns Health check result
   */
  async checkServer(config: ServerConfig): Promise<HealthCheckResult> {
    const startTime = performance.now();
    log.debug(`Checking health for ${config.url}`);

    try {
      const client = new BobaAPIClient(config.url, config.requestTimeout);

      // Test basic connectivity by getting version
      const version = await client.getVersion();
      const responseTimeMs = Math.round(performance.now() - startTime);

      // Determine health status based on response time
      const status = this.determineStatus(responseTimeMs, true, 0);

      const result: HealthCheckResult = {
        serverId: config.id,
        url: config.url,
        status,
        version,
        responseTimeMs,
        authValid: true,
        error: null,
        checkedAt: Date.now(),
      };

      this.results.set(config.id, result);
      log.info(`Health check OK: ${config.url} (${responseTimeMs}ms, ${status})`);

      return result;
    } catch (err) {
      const responseTimeMs = Math.round(performance.now() - startTime);
      const error = err instanceof Error ? err.message : String(err);

      // Count consecutive failures
      const previous = this.results.get(config.id);
      const failures = previous ? (previous.status !== "healthy" ? 2 : 1) : 1;

      const result: HealthCheckResult = {
        serverId: config.id,
        url: config.url,
        status: failures >= HEALTH_THRESHOLDS.MAX_FAILURES ? "unhealthy" : "degraded",
        version: null,
        responseTimeMs,
        authValid: false,
        error,
        checkedAt: Date.now(),
      };

      this.results.set(config.id, result);
      log.warn(`Health check failed: ${config.url} - ${error}`);

      return result;
    }
  }

  /**
   * Check all servers in a list.
   *
   * @param configs - Array of server configurations
   * @returns Array of health check results
   */
  async checkAllServers(
    configs: readonly ServerConfig[],
  ): Promise<readonly HealthCheckResult[]> {
    if (this.checkInProgress) {
      log.debug("Health check already in progress");
      return Array.from(this.results.values());
    }

    this.checkInProgress = true;
    log.info(`Checking ${configs.length} servers`);

    try {
      const results: HealthCheckResult[] = [];

      for (const config of configs) {
        try {
          const result = await this.checkServer(config);
          results.push(result);
        } catch (err) {
          log.error(`Health check error for ${config.url}`, err);
          results.push({
            serverId: config.id,
            url: config.url,
            status: "unhealthy",
            version: null,
            responseTimeMs: 0,
            authValid: false,
            error: err instanceof Error ? err.message : String(err),
            checkedAt: Date.now(),
          });
        }
      }

      // Persist results to storage
      await this.persistResults(results);

      return results;
    } finally {
      this.checkInProgress = false;
    }
  }

  /**
   * Test a connection to a server without authentication.
   * Used for testing server configuration in options page.
   *
   * @param url - Server URL to test
   * @returns Connection test result
   */
  async testConnection(url: string): Promise<ConnectionTestResult> {
    const startTime = performance.now();
    log.debug(`Testing connection to ${url}`);

    try {
      const client = new BobaAPIClient(url, REQUEST_TIMEOUTS.HEALTH_CHECK);
      const version = await client.getVersion();
      const responseTimeMs = Math.round(performance.now() - startTime);

      return {
        success: true,
        url,
        version,
        error: null,
        responseTimeMs,
        testedAt: Date.now(),
      };
    } catch (err) {
      const responseTimeMs = Math.round(performance.now() - startTime);
      const error = err instanceof Error ? err.message : String(err);

      return {
        success: false,
        url,
        version: null,
        error,
        responseTimeMs,
        testedAt: Date.now(),
      };
    }
  }

  /**
   * Auto-discover Boba/qBitTorrent servers on common ports.
   * Scans localhost on the default Boba Project ports.
   *
   * @returns Array of connection test results for discovered servers
   */
  async autoDiscover(): Promise<readonly ConnectionTestResult[]> {
    const ports = [8080, 7187, 7189];
    const results: ConnectionTestResult[] = [];

    log.info(`Auto-discovering servers on ports: ${ports.join(", ")}`);

    for (const port of ports) {
      const url = `http://localhost:${port}`;
      const result = await this.testConnection(url);
      results.push(result);

      if (result.success) {
        log.info(`Discovered server at ${url} (v${result.version})`);
      }
    }

    return results;
  }

  /**
   * Get the last health check result for a server.
   *
   * @param serverId - Server ID
   * @returns Last result, or null if not checked
   */
  getLastResult(serverId: string): HealthCheckResult | null {
    return this.results.get(serverId) ?? null;
  }

  /**
   * Get all cached health results.
   *
   * @returns Array of all results
   */
  getAllResults(): readonly HealthCheckResult[] {
    return Array.from(this.results.values());
  }

  /**
   * Determine health status based on response time and failures.
   *
   * @param latency - Response time in ms
   * @param success - Whether the request succeeded
   * @param consecutiveFailures - Number of consecutive failures
   * @returns Health status
   */
  private determineStatus(
    latency: number,
    success: boolean,
    consecutiveFailures: number,
  ): HealthStatus {
    if (!success || consecutiveFailures >= HEALTH_THRESHOLDS.MAX_FAILURES) {
      return "unhealthy";
    }

    if (latency < HEALTH_THRESHOLDS.HEALTHY_LATENCY_MS) {
      return "healthy";
    }

    if (latency < HEALTH_THRESHOLDS.DEGRADED_LATENCY_MS) {
      return "degraded";
    }

    return "unhealthy";
  }

  /**
   * Persist health results to storage.
   *
   * @param results - Results to persist
   */
  private async persistResults(
    results: readonly HealthCheckResult[],
  ): Promise<void> {
    try {
      const data = results.reduce(
        (map, r) => {
          map[r.serverId] = r;
          return map;
        },
        {} as Record<string, HealthCheckResult>,
      );

      await storageSet(STORAGE_KEYS.HEALTH, data);
    } catch (err) {
      log.error("Failed to persist health results", err);
    }
  }
}
