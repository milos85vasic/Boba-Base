/**
 * @fileoverview Authentication handlers for BobaLink.
 *
 * Manages all authentication methods for connecting to qBitTorrent:
 * - Cookie-based: POST /api/v2/auth/login → SID cookie
 * - API key: X-API-Key header
 * - Basic auth: Authorization header with base64 credentials
 * - None: No authentication required
 *
 * @module api/auth
 */

import { createLogger } from "../shared/logger";
import { AuthError, ConfigError, normalizeError } from "../shared/errors";
import type {
  AuthMethod,
  AuthCredentials,
  AuthState,
  ServerConfig,
} from "../types/config";
import { BobaAPIClient } from "./client";

const log = createLogger("AuthHandler");

/**
 * Maximum number of consecutive auth failures before giving up.
 */
const MAX_CONSECUTIVE_FAILURES = 3;

/**
 * AuthHandler manages authentication state and performs login/logout
 * operations for qBitTorrent connections.
 */
export class AuthHandler {
  private state: AuthState;
  private client: BobaAPIClient;

  /**
   * Create an auth handler for a server.
   *
   * @param client - API client instance
   * @param initialMethod - Initial auth method
   */
  constructor(client: BobaAPIClient, initialMethod: AuthMethod = "none") {
    this.client = client;
    this.state = this.createInitialState(initialMethod);
  }

  /**
   * Get the current authentication state.
   *
   * @returns Current auth state (read-only copy)
   */
  getState(): AuthState {
    return { ...this.state };
  }

  /**
   * Check if currently authenticated.
   *
   * @returns True if authenticated
   */
  isAuthenticated(): boolean {
    return this.state.isAuthenticated;
  }

  /**
   * Authenticate with the server using the provided credentials.
   *
   * @param credentials - Auth credentials based on method
   * @returns True if authentication succeeded
   */
  async authenticate(credentials: AuthCredentials): Promise<boolean> {
    log.info(`Authenticating with method: ${credentials.method}`);

    try {
      let success = false;

      switch (credentials.method) {
        case "cookie":
          success = await this.authenticateCookie(
            credentials.username,
            credentials.password,
          );
          break;
        case "api_key":
          success = this.authenticateApiKey(credentials.apiKey);
          break;
        case "basic":
          success = this.authenticateBasic(
            credentials.username,
            credentials.password,
          );
          break;
        case "none":
          success = await this.authenticateNone();
          break;
      }

      if (success) {
        this.state = {
          ...this.state,
          isAuthenticated: true,
          lastRefreshedAt: Date.now(),
          consecutiveFailures: 0,
        };
        log.info("Authentication successful");
      } else {
        this.recordFailure("Authentication rejected by server");
      }

      return success;
    } catch (err) {
      this.recordFailure(err instanceof Error ? err.message : String(err));
      throw normalizeError(err, { context: { method: credentials.method } });
    }
  }

  /**
   * Logout from the server and clear auth state.
   */
  async logout(): Promise<void> {
    try {
      await this.client.logout();
    } catch (err) {
      log.warn("Logout request failed", err);
    } finally {
      this.state = this.createInitialState(this.state.method);
      this.client.setAuthCookie(null);
      this.client.setHeaders({});
      log.info("Auth state cleared");
    }
  }

  /**
   * Refresh the current authentication if needed.
   * For cookie auth, this re-authenticates. For API key/basic, no-op.
   *
   * @param credentials - Credentials for re-auth if needed
   * @returns True if auth is valid (either refreshed or still valid)
   */
  async refreshIfNeeded(credentials: AuthCredentials): Promise<boolean> {
    // API key and basic auth don't expire
    if (this.state.method === "api_key" || this.state.method === "basic" || this.state.method === "none") {
      return this.state.isAuthenticated;
    }

    // Check if cookie is still valid (qBitTorrent cookies typically last 1 hour)
    const COOKIE_LIFETIME_MS = 3600 * 1000;
    const needsRefresh =
      !this.state.isAuthenticated ||
      !this.state.lastRefreshedAt ||
      Date.now() - this.state.lastRefreshedAt > COOKIE_LIFETIME_MS;

    if (needsRefresh) {
      log.debug("Auth refresh needed, re-authenticating");
      return this.authenticate(credentials);
    }

    return true;
  }

  /**
   * Create auth credentials from a server configuration.
   *
   * @param config - Server configuration
   * @param passphrase - Passphrase for decrypting credentials
   * @returns Auth credentials
   */
  static async createCredentialsFromConfig(
    config: ServerConfig,
    passphrase: string,
  ): Promise<AuthCredentials> {
    const { decrypt } = await import("../shared/crypto");

    switch (config.authMethod) {
      case "cookie": {
        if (!config.username || !config.encryptedPassword) {
          throw new ConfigError("Cookie auth requires username and password");
        }
        const password = await decrypt(
          JSON.parse(config.encryptedPassword) as Parameters<typeof decrypt>[0],
          passphrase,
        );
        return {
          method: "cookie",
          username: config.username,
          password,
        };
      }
      case "api_key": {
        if (!config.encryptedApiKey) {
          throw new ConfigError("API key auth requires an API key");
        }
        const apiKey = await decrypt(
          JSON.parse(config.encryptedApiKey) as Parameters<typeof decrypt>[0],
          passphrase,
        );
        return { method: "api_key", apiKey };
      }
      case "basic": {
        if (!config.username || !config.encryptedPassword) {
          throw new ConfigError("Basic auth requires username and password");
        }
        const password = await decrypt(
          JSON.parse(config.encryptedPassword) as Parameters<typeof decrypt>[0],
          passphrase,
        );
        return {
          method: "basic",
          username: config.username,
          password,
        };
      }
      case "none":
        return { method: "none" };
      default:
        throw new ConfigError(`Unknown auth method: ${config.authMethod}`);
    }
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Authentication method implementations
  // ───────────────────────────────────────────────────────────────────────────

  /**
   * Cookie-based authentication with qBitTorrent.
   *
   * @param username - qBitTorrent username
   * @param password - qBitTorrent password
   * @returns True if authenticated
   */
  private async authenticateCookie(
    username: string,
    password: string,
  ): Promise<boolean> {
    if (!username || !password) {
      throw new ConfigError("Username and password required for cookie auth");
    }

    const success = await this.client.login(username, password);

    if (success) {
      this.state = {
        ...this.state,
        method: "cookie",
        sidCookie: this.client["authCookie"] ?? null,
        sidExpiresAt: Date.now() + 3600 * 1000,
      };
    }

    return success;
  }

  /**
   * API key authentication (X-API-Key header).
   *
   * @param apiKey - The API key
   * @returns True (always succeeds for API key setup)
   */
  private authenticateApiKey(apiKey: string): boolean {
    if (!apiKey) {
      throw new ConfigError("API key required");
    }

    this.client.setHeaders({ "X-API-Key": apiKey });
    this.state = {
      ...this.state,
      method: "api_key",
      apiKeyHeader: `X-API-Key ${apiKey.slice(0, 4)}...`,
    };

    // API key auth is validated on first request
    return true;
  }

  /**
   * Basic HTTP authentication (Authorization header).
   *
   * @param username - Username
   * @param password - Password
   * @returns True (always succeeds for basic auth setup)
   */
  private authenticateBasic(username: string, password: string): boolean {
    if (!username || !password) {
      throw new ConfigError("Username and password required for basic auth");
    }

    // Base64 encode credentials
    const encoded = btoa(`${username}:${password}`);
    this.client.setHeaders({ Authorization: `Basic ${encoded}` });

    this.state = {
      ...this.state,
      method: "basic",
      basicAuthHeader: `Basic ${encoded.slice(0, 8)}...`,
    };

    return true;
  }

  /**
   * No authentication - just verify the server is accessible.
   *
   * @returns True if server responds
   */
  private async authenticateNone(): Promise<boolean> {
    try {
      await this.client.getVersion();
      this.state = { ...this.state, method: "none" };
      return true;
    } catch (err) {
      log.error("No-auth connection test failed", err);
      return false;
    }
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Helpers
  // ───────────────────────────────────────────────────────────────────────────

  /**
   * Record an authentication failure.
   *
   * @param message - Error message
   */
  private recordFailure(message: string): void {
    const failures = this.state.consecutiveFailures + 1;
    this.state = {
      ...this.state,
      isAuthenticated: false,
      consecutiveFailures: failures,
    };

    log.warn(`Auth failure #${failures}: ${message}`);

    if (failures >= MAX_CONSECUTIVE_FAILURES) {
      log.error(`Max auth failures (${MAX_CONSECUTIVE_FAILURES}) reached`);
      throw new AuthError(
        `${MAX_CONSECUTIVE_FAILURES} consecutive authentication failures. Please check your credentials.`,
        { context: { failures } },
      );
    }
  }

  /**
   * Create initial auth state.
   *
   * @param method - Auth method
   * @returns Initial state
   */
  private createInitialState(method: AuthMethod): AuthState {
    return {
      method,
      isAuthenticated: false,
      sidCookie: null,
      sidExpiresAt: null,
      basicAuthHeader: null,
      apiKeyHeader: null,
      lastRefreshedAt: null,
      consecutiveFailures: 0,
    };
  }
}
