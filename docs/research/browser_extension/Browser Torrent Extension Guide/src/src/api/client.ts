/**
 * @fileoverview Boba API client for BobaLink.
 *
 * Provides typed methods for communicating with qBitTorrent and Boba Project
 * backends. Handles request serialization, error handling, retries with
 * exponential backoff, and rate limiting.
 *
 * @module api/client
 */

import { createLogger } from "../shared/logger";
import { retryWithBackoff, TokenBucket, sleep } from "../shared/utils";
import {
  REQUEST_TIMEOUTS,
  RETRY_CONFIG,
  RATE_LIMIT,
  QBITTORRENT_ENDPOINTS,
} from "../shared/constants";
import {
  NetworkError,
  ServerError,
  RateLimitError,
  normalizeError,
} from "../shared/errors";
import type {
  QBittorrentVersion,
  QBittorrentAddTorrentParams,
  QBittorrentTorrentInfo,
} from "../types/api";

const log = createLogger("BobaAPIClient");

/**
 * HTTP methods supported by the client.
 */
type HttpMethod = "GET" | "POST" | "DELETE";

/**
 * Request options for API calls.
 */
interface RequestOptions {
  /** Request timeout in milliseconds */
  timeout?: number;

  /** Whether to retry on failure */
  retry?: boolean;

  /** Custom headers to include */
  headers?: Record<string, string>;

  /** Request body (for POST) */
  body?: FormData | string;

  /** Number of retry attempts */
  maxRetries?: number;
}

/**
 * BobaAPIClient handles all HTTP communication with qBitTorrent/Boba servers.
 *
 * Features:
 * - Automatic retries with exponential backoff and jitter
 * - Token bucket rate limiting
 * - Request timeout handling via AbortController
 * - FormData support for file uploads
 * - Consistent error handling with typed errors
 */
export class BobaAPIClient {
  private readonly baseUrl: string;
  private readonly requestTimeout: number;
  private readonly rateLimiter: TokenBucket;
  private authCookie: string | null = null;
  private customHeaders: Record<string, string> = {};

  /**
   * Create a new API client.
   *
   * @param baseUrl - Base URL of the qBitTorrent/Boba server
   * @param requestTimeout - Default request timeout in ms
   */
  constructor(baseUrl: string, requestTimeout: number = REQUEST_TIMEOUTS.DEFAULT) {
    // Normalize URL (remove trailing slash)
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.requestTimeout = requestTimeout;
    this.rateLimiter = new TokenBucket(
      RATE_LIMIT.MAX_REQUESTS,
      RATE_LIMIT.MAX_REQUESTS / (RATE_LIMIT.WINDOW_MS / 1000),
    );

    log.debug(`Created API client for ${this.baseUrl}`);
  }

  /**
   * Set the authentication cookie (SID) for subsequent requests.
   *
   * @param cookie - The SID cookie value
   */
  setAuthCookie(cookie: string | null): void {
    this.authCookie = cookie;
    log.debug(`Auth cookie ${cookie ? "set" : "cleared"}`);
  }

  /**
   * Set custom headers for all requests.
   *
   * @param headers - Headers to include
   */
  setHeaders(headers: Record<string, string>): void {
    this.customHeaders = { ...headers };
  }

  /**
   * Get the base URL of this client.
   *
   * @returns Base URL string
   */
  getBaseUrl(): string {
    return this.baseUrl;
  }

  /**
   * Authenticate with qBitTorrent using cookie-based auth.
   *
   * @param username - qBitTorrent username
   * @param password - qBitTorrent password
   * @returns True if authentication succeeded
   */
  async login(username: string, password: string): Promise<boolean> {
    try {
      const formData = new FormData();
      formData.append("username", username);
      formData.append("password", password);

      const response = await this.requestRaw(
        "POST",
        QBITTORRENT_ENDPOINTS.AUTH_LOGIN,
        { body: formData as unknown as FormData, timeout: REQUEST_TIMEOUTS.AUTH },
      );

      if (response.status === 200) {
        // Extract SID cookie from response
        const setCookie = response.headers.get("set-cookie");
        if (setCookie) {
          const sidMatch = setCookie.match(/SID=([^;]+)/);
          if (sidMatch?.[1]) {
            this.authCookie = sidMatch[1];
            log.info("Authentication successful");
            return true;
          }
        }

        // Check for OK text response
        const text = await response.text();
        if (text.toLowerCase().includes("ok")) {
          log.info("Authentication successful (OK response)");
          return true;
        }
      }

      log.warn(`Authentication failed: HTTP ${response.status}`);
      return false;
    } catch (err) {
      log.error("Authentication request failed", err);
      return false;
    }
  }

  /**
   * Logout from qBitTorrent.
   */
  async logout(): Promise<void> {
    try {
      await this.post(QBITTORRENT_ENDPOINTS.AUTH_LOGOUT, undefined, { retry: false });
      this.authCookie = null;
      log.info("Logged out");
    } catch (err) {
      log.error("Logout failed", err);
    }
  }

  /**
   * Get qBitTorrent application version.
   *
   * @returns Version string (e.g., "v4.6.0")
   */
  async getVersion(): Promise<string> {
    const response = await this.get<QBittorrentVersion>(
      QBITTORRENT_ENDPOINTS.APP_VERSION,
      { timeout: REQUEST_TIMEOUTS.HEALTH_CHECK },
    );
    return response.version;
  }

  /**
   * Add a torrent via magnet URI.
   *
   * @param magnetUri - The magnet URI to add
   * @param options - Additional add options
   * @returns True if the torrent was added successfully
   */
  async addTorrentFromMagnet(
    magnetUri: string,
    options: Partial<QBittorrentAddTorrentParams> = {},
  ): Promise<boolean> {
    const formData = new FormData();
    formData.append("urls", magnetUri);
    this.applyAddOptions(formData, options);

    const response = await this.requestRaw(
      "POST",
      QBITTORRENT_ENDPOINTS.TORRENTS_ADD,
      {
        body: formData as unknown as FormData,
        timeout: REQUEST_TIMEOUTS.ADD_TORRENT,
      },
    );

    // qBitTorrent returns 200 with "Ok." or "Fails." on failure
    const text = await response.text();
    const success = response.status === 200 && !text.toLowerCase().includes("fail");

    if (!success) {
      throw new ServerError(
        `Failed to add torrent: ${text || `HTTP ${response.status}`}`,
        response.status,
      );
    }

    return true;
  }

  /**
   * Add a torrent from a .torrent file.
   *
   * @param file - The .torrent file to upload
   * @param options - Additional add options
   * @returns True if the torrent was added successfully
   */
  async addTorrentFromFile(
    file: File,
    options: Partial<QBittorrentAddTorrentParams> = {},
  ): Promise<boolean> {
    const formData = new FormData();
    formData.append("torrents", file);
    this.applyAddOptions(formData, options);

    const response = await this.requestRaw(
      "POST",
      QBITTORRENT_ENDPOINTS.TORRENTS_ADD,
      {
        body: formData as unknown as FormData,
        timeout: REQUEST_TIMEOUTS.ADD_TORRENT,
      },
    );

    const text = await response.text();
    const success = response.status === 200 && !text.toLowerCase().includes("fail");

    if (!success) {
      throw new ServerError(
        `Failed to add torrent file: ${text || `HTTP ${response.status}`}`,
        response.status,
      );
    }

    return true;
  }

  /**
   * Get list of torrents from qBitTorrent.
   *
   * @param filter - Optional filter (all, downloading, seeding, completed, paused, active, inactive)
   * @returns Array of torrent info objects
   */
  async getTorrents(
    filter?: string,
  ): Promise<readonly QBittorrentTorrentInfo[]> {
    const params = filter ? `?filter=${filter}` : "";
    return this.get<readonly QBittorrentTorrentInfo[]>(
      `${QBITTORRENT_ENDPOINTS.TORRENTS_INFO}${params}`,
    );
  }

  /**
   * Delete torrents from qBitTorrent.
   *
   * @param hashes - Torrent hashes to delete
   * @param deleteFiles - Whether to also delete downloaded files
   */
  async deleteTorrents(
    hashes: readonly string[],
    deleteFiles: boolean = false,
  ): Promise<void> {
    const formData = new FormData();
    formData.append("hashes", hashes.join("|"));
    formData.append("deleteFiles", deleteFiles ? "true" : "false");

    await this.post(QBITTORRENT_ENDPOINTS.TORRENTS_DELETE, formData as unknown as FormData);
  }

  /**
   * Pause torrents.
   *
   * @param hashes - Torrent hashes to pause
   */
  async pauseTorrents(hashes: readonly string[]): Promise<void> {
    const formData = new FormData();
    formData.append("hashes", hashes.join("|"));
    await this.post(QBITTORRENT_ENDPOINTS.TORRENTS_PAUSE, formData as unknown as FormData);
  }

  /**
   * Resume torrents.
   *
   * @param hashes - Torrent hashes to resume
   */
  async resumeTorrents(hashes: readonly string[]): Promise<void> {
    const formData = new FormData();
    formData.append("hashes", hashes.join("|"));
    await this.post(QBITTORRENT_ENDPOINTS.TORRENTS_RESUME, formData as unknown as FormData);
  }

  /**
   * Make a GET request.
   *
   * @param path - API path (without base URL)
   * @param options - Request options
   * @returns Parsed JSON response
   */
  async get<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const response = await this.requestWithRetry("GET", path, options);
    return this.parseResponse<T>(response);
  }

  /**
   * Make a POST request.
   *
   * @param path - API path (without base URL)
   * @param body - Request body (FormData or JSON string)
   * @param options - Request options
   * @returns Parsed JSON response
   */
  async post<T>(
    path: string,
    body?: FormData | string,
    options: RequestOptions = {},
  ): Promise<T> {
    const response = await this.requestWithRetry("POST", path, {
      ...options,
      body,
    });
    return this.parseResponse<T>(response);
  }

  /**
   * Make a DELETE request.
   *
   * @param path - API path (without base URL)
   * @param options - Request options
   * @returns Parsed JSON response
   */
  async delete<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const response = await this.requestWithRetry("DELETE", path, options);
    return this.parseResponse<T>(response);
  }

  /**
   * Apply torrent add options to a FormData object.
   *
   * @param formData - FormData to populate
   * @param options - Add options
   */
  private applyAddOptions(
    formData: FormData,
    options: Partial<QBittorrentAddTorrentParams>,
  ): void {
    if (options.savepath) formData.append("savepath", options.savepath);
    if (options.category) formData.append("category", options.category);
    if (options.tags) formData.append("tags", options.tags);
    if (options.skip_checking) formData.append("skip_checking", options.skip_checking);
    if (options.paused) formData.append("paused", options.paused);
    if (options.root_folder) formData.append("root_folder", options.root_folder);
    if (options.rename) formData.append("rename", options.rename);
    if (options.upLimit !== undefined) formData.append("upLimit", String(options.upLimit));
    if (options.dlLimit !== undefined) formData.append("dlLimit", String(options.dlLimit));
    if (options.autoTMM) formData.append("autoTMM", options.autoTMM);
    if (options.contentLayout) formData.append("contentLayout", options.contentLayout);
    if (options.sequentialDownload)
      formData.append("sequentialDownload", options.sequentialDownload);
    if (options.firstLastPiecePrio)
      formData.append("firstLastPiecePrio", options.firstLastPiecePrio);
  }

  /**
   * Make an HTTP request with automatic retries.
   *
   * @param method - HTTP method
   * @param path - API path
   * @param options - Request options
   * @returns Response object
   */
  private async requestWithRetry(
    method: HttpMethod,
    path: string,
    options: RequestOptions,
  ): Promise<Response> {
    const shouldRetry = options.retry ?? true;
    const maxRetries = options.maxRetries ?? RETRY_CONFIG.MAX_RETRIES;

    if (!shouldRetry) {
      return this.requestRaw(method, path, options);
    }

    return retryWithBackoff(
      () => this.requestRaw(method, path, options),
      maxRetries,
      RETRY_CONFIG.BASE_DELAY_MS,
      RETRY_CONFIG.MAX_DELAY_MS,
    );
  }

  /**
   * Make a raw HTTP request.
   *
   * @param method - HTTP method
   * @param path - API path
   * @param options - Request options
   * @returns Response object
   */
  private async requestRaw(
    method: HttpMethod,
    path: string,
    options: RequestOptions = {},
  ): Promise<Response> {
    // Rate limiting
    if (!this.rateLimiter.consume()) {
      const waitTime = 1000 / this.rateLimiter.getAvailableTokens();
      log.debug(`Rate limited, waiting ${Math.round(waitTime)}ms`);
      await sleep(waitTime);
    }

    const url = `${this.baseUrl}${path}`;
    const timeout = options.timeout ?? this.requestTimeout;

    // Build headers
    const headers = new Headers();

    // Add auth cookie if available
    if (this.authCookie) {
      headers.set("Cookie", `SID=${this.authCookie}`);
    }

    // Add custom headers
    for (const [key, value] of Object.entries(this.customHeaders)) {
      headers.set(key, value);
    }

    // Add request-specific headers
    if (options.headers) {
      for (const [key, value] of Object.entries(options.headers)) {
        headers.set(key, value);
      }
    }

    // Don't set Content-Type for FormData (browser sets it with boundary)
    if (!(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/x-www-form-urlencoded");
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(url, {
        method,
        headers,
        body: options.body,
        signal: controller.signal,
        credentials: "include",
      });

      clearTimeout(timeoutId);

      // Handle error status codes
      if (!response.ok) {
        await this.handleErrorResponse(response);
      }

      return response;
    } catch (err) {
      clearTimeout(timeoutId);

      if (err instanceof Error && err.name === "AbortError") {
        throw new NetworkError(`Request timeout after ${timeout}ms`, {
          context: { url, method, timeout },
        });
      }

      throw new NetworkError(`Request failed: ${err instanceof Error ? err.message : String(err)}`, {
        cause: err instanceof Error ? err : undefined,
        context: { url, method },
      });
    }
  }

  /**
   * Parse the response body as JSON.
   *
   * @param response - Fetch response
   * @returns Parsed JSON
   */
  private async parseResponse<T>(response: Response): Promise<T> {
    // Handle empty responses
    if (response.status === 204 || response.headers.get("content-length") === "0") {
      return undefined as T;
    }

    const contentType = response.headers.get("content-type");

    // Handle text responses (qBitTorrent sometimes returns plain text)
    if (contentType?.includes("text/plain")) {
      const text = await response.text();
      return text as T;
    }

    // Handle JSON responses
    try {
      return (await response.json()) as T;
    } catch {
      // Fallback to text
      const text = await response.text();
      return text as T;
    }
  }

  /**
   * Handle error responses from the server.
   *
   * @param response - Error response
   * @throws ServerError or RateLimitError
   */
  private async handleErrorResponse(response: Response): Promise<never> {
    const status = response.status;

    // Handle rate limiting
    if (status === 429) {
      const retryAfter = response.headers.get("retry-after");
      const retryMs = retryAfter ? parseInt(retryAfter, 10) * 1000 : 60000;
      throw new RateLimitError("Rate limited by server", retryMs);
    }

    // Try to get error details from response body
    let message = `HTTP ${status} ${response.statusText}`;
    try {
      const body = await response.text();
      if (body) {
        message = body;
      }
    } catch {
      // Ignore parse errors
    }

    throw new ServerError(message, status);
  }
}
