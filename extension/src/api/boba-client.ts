/**
 * @fileoverview Real Boba merge-service (:7187) API client for BobaLink.
 *
 * This is the ONE network client the extension uses to drive the Boba backend.
 * It speaks to Boba's **merge service on :7187** (FastAPI), NOT to qBittorrent
 * directly (no :8080, no `/api/v2/torrents`, no JWT). qBittorrent auth
 * (admin/admin) and private-tracker cookies are handled server-side by Boba —
 * the extension never sends them. See
 * `docs/browser_extension/_plan/A-backend-contract.md`.
 *
 * Endpoints (base `http://<host>:7187`):
 *   - POST /api/v1/download   body {result_id, download_urls:[...]}  → add torrents/magnets
 *   - GET  /health                                                   → liveness
 *   - GET  /api/v1/auth/status                                       → auth gate state
 *
 * ## Optional shared-secret token (§ Plan E / §11.4.10)
 * The backend's download-write gate (`require_api_token`) is OPEN by default and
 * only enforced when the operator sets `BOBA_API_TOKEN`. When the client is
 * constructed with a (decrypted, plaintext) token, EVERY request carries it as
 * `Authorization: Bearer <token>` AND `X-Boba-Token: <token>` (the backend
 * accepts either). When no token is set, NO auth header is sent — preserving the
 * default-open contract.
 *
 * **The token value is NEVER logged (§11.4.10).** Logs only record
 * `[token: set]` / `[token: none]`. The client does no crypto itself — the
 * caller decrypts `encryptedBobaApiToken` (via `shared/crypto.ts`) and passes
 * the plaintext in.
 *
 * @module api/boba-client
 */

import {
  BOBA_TOKEN_HEADERS,
  DEFAULT_URLS,
  RATE_LIMIT,
  REQUEST_TIMEOUTS,
  RETRY_CONFIG,
} from "../shared/constants";
import { NetworkError, ServerError } from "../shared/errors";
import { createLogger, type Logger } from "../shared/logger";
import { sleep, TokenBucket } from "../shared/utils";

/**
 * Result of an add-torrent / add-magnet call.
 */
export interface AddResult {
  /** Whether the backend reported the request was accepted (2xx). */
  readonly accepted: boolean;

  /** The backend-assigned download id, when present in the response. */
  readonly downloadId?: string;

  /** Number of URLs the backend reported it added, when present. */
  readonly addedCount?: number;

  /** The raw parsed response body (unknown shape — caller may inspect). */
  readonly raw: unknown;
}

/**
 * Construction options for {@link BobaClient}.
 */
export interface BobaClientOptions {
  /** Base URL of the Boba merge service. Defaults to {@link DEFAULT_URLS.FAST_API}. */
  readonly baseUrl?: string;

  /**
   * Optional plaintext bearer token (already decrypted by the caller). When
   * set, sent on every request. NEVER logged.
   */
  readonly token?: string;

  /** Per-request timeout in ms. Defaults to {@link REQUEST_TIMEOUTS.ADD_TORRENT}. */
  readonly timeoutMs?: number;

  /** Max retries on 5xx/network. Defaults to {@link RETRY_CONFIG.MAX_RETRIES}. */
  readonly maxRetries?: number;

  /** Injectable fetch implementation (defaults to global `fetch`). For tests. */
  readonly fetchImpl?: typeof fetch;

  /** Disable the client-side token-bucket rate limiter (default: enabled). */
  readonly disableRateLimit?: boolean;
}

/** Default `result_id` label when the caller does not supply one. */
const DEFAULT_RESULT_ID = "bobalink";

/**
 * Real client for Boba's merge service (:7187).
 */
export class BobaClient {
  private readonly baseUrl: string;
  private readonly token: string | null;
  private readonly timeoutMs: number;
  private readonly maxRetries: number;
  private readonly fetchImpl: typeof fetch;
  private readonly bucket: TokenBucket | null;
  private readonly log: Logger;

  /**
   * @param options - See {@link BobaClientOptions}. A bare string is also
   *   accepted as the base URL for convenience.
   */
  constructor(options: BobaClientOptions | string = {}) {
    const opts: BobaClientOptions =
      typeof options === "string" ? { baseUrl: options } : options;

    this.baseUrl = (opts.baseUrl ?? DEFAULT_URLS.FAST_API).replace(/\/+$/, "");
    this.token =
      typeof opts.token === "string" && opts.token.length > 0
        ? opts.token
        : null;
    this.timeoutMs = opts.timeoutMs ?? REQUEST_TIMEOUTS.ADD_TORRENT;
    this.maxRetries = opts.maxRetries ?? RETRY_CONFIG.MAX_RETRIES;
    this.fetchImpl = opts.fetchImpl ?? fetch;
    this.bucket = opts.disableRateLimit
      ? null
      : new TokenBucket(RATE_LIMIT.MAX_REQUESTS, RATE_LIMIT.MAX_REQUESTS);
    this.log = createLogger("BobaClient");

    // §11.4.10: log the PRESENCE of a token, never its value.
    this.log.info(
      `client created base=${this.baseUrl} [token: ${this.token ? "set" : "none"}]`,
    );
  }

  /**
   * Build request headers, including auth headers only when a token is set.
   *
   * NOTE: returns a plain object; callers/loggers MUST NOT serialize it —
   * the token value lives here and must never be logged (§11.4.10).
   *
   * @param json - Whether to set a JSON content-type (for bodied requests).
   * @returns Header map for `fetch`.
   */
  private buildHeaders(json: boolean): Record<string, string> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (json) {
      headers["Content-Type"] = "application/json";
    }
    if (this.token !== null) {
      headers[BOBA_TOKEN_HEADERS.AUTHORIZATION] = `Bearer ${this.token}`;
      headers[BOBA_TOKEN_HEADERS.X_BOBA_TOKEN] = this.token;
    }
    return headers;
  }

  /**
   * Issue a single fetch with an AbortController timeout. Maps transport
   * failures to {@link NetworkError} and non-2xx to {@link ServerError}.
   *
   * @param path - Path appended to the base URL (must start with `/`).
   * @param init - Method + optional body.
   * @returns The parsed JSON body (or `null` when the body is empty/non-JSON).
   */
  private async requestOnce(
    path: string,
    init: { method: string; body?: string },
  ): Promise<{ status: number; body: unknown }> {
    const url = `${this.baseUrl}${path}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    const hasBody = typeof init.body === "string";

    let res: Response;
    try {
      res = await this.fetchImpl(url, {
        method: init.method,
        headers: this.buildHeaders(hasBody),
        ...(hasBody ? { body: init.body } : {}),
        signal: controller.signal,
      });
    } catch (err) {
      const aborted = err instanceof Error && err.name === "AbortError";
      throw new NetworkError(
        aborted
          ? `request to ${path} timed out after ${String(this.timeoutMs)}ms`
          : `request to ${path} failed`,
        {
          ...(err instanceof Error ? { cause: err } : {}),
          context: { path, aborted },
        },
      );
    } finally {
      clearTimeout(timer);
    }

    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = null;
    }

    if (!res.ok) {
      throw new ServerError(
        `${init.method} ${path} returned ${String(res.status)}`,
        res.status,
        { context: { path, body } },
      );
    }

    return { status: res.status, body };
  }

  /**
   * Run a request with exponential-backoff + jitter retry on 5xx/network.
   * 4xx (client) errors are NOT retried — they will not change on retry.
   *
   * @param path - Request path.
   * @param init - Method + optional body.
   * @returns The successful response body.
   */
  private async requestWithRetry(
    path: string,
    init: { method: string; body?: string },
  ): Promise<{ status: number; body: unknown }> {
    if (this.bucket && !this.bucket.consume()) {
      // Soft wait one window for a token rather than failing hard.
      await sleep(RATE_LIMIT.WINDOW_MS);
      this.bucket.consume();
    }

    let lastErr: Error | null = null;
    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      try {
        return await this.requestOnce(path, init);
      } catch (err) {
        lastErr = err instanceof Error ? err : new Error(String(err));

        const retriable =
          err instanceof NetworkError ||
          (err instanceof ServerError &&
            err.statusCode !== null &&
            err.statusCode >= 500);

        if (!retriable || attempt === this.maxRetries) {
          break;
        }

        const expo = RETRY_CONFIG.BASE_DELAY_MS * Math.pow(2, attempt);
        const clamped = Math.min(expo, RETRY_CONFIG.MAX_DELAY_MS);
        const jitter = Math.random() * RETRY_CONFIG.JITTER_FACTOR * clamped;
        this.log.warn(
          `retry ${String(attempt + 1)}/${String(this.maxRetries)} for ${path} after error`,
        );
        await sleep(clamped + jitter);
      }
    }
    throw lastErr ?? new NetworkError(`request to ${path} failed`);
  }

  /**
   * Normalize a `/api/v1/download` response body into an {@link AddResult}.
   *
   * @param status - HTTP status of the response.
   * @param body - Parsed response body.
   * @returns A structured add result.
   */
  private static toAddResult(status: number, body: unknown): AddResult {
    const rec =
      body !== null && typeof body === "object"
        ? (body as Record<string, unknown>)
        : {};
    const downloadId =
      typeof rec.download_id === "string" ? rec.download_id : undefined;
    const addedCount =
      typeof rec.added_count === "number" ? rec.added_count : undefined;
    // Backend reports {status:"initiated"|"failed", added_count, ...}.
    // "accepted" means the HTTP request succeeded AND the backend did not
    // report a wholesale failure.
    const backendOk = rec.status !== "failed";
    const result: { accepted: boolean; raw: unknown; downloadId?: string; addedCount?: number } = {
      accepted: status >= 200 && status < 300 && backendOk,
      raw: body,
    };
    if (downloadId !== undefined) result.downloadId = downloadId;
    if (addedCount !== undefined) result.addedCount = addedCount;
    return result;
  }

  /**
   * Add a single magnet (or direct `.torrent`/tracker URL) via the Boba
   * merge service. POSTs to `/api/v1/download`.
   *
   * @param magnetUri - The magnet URI or download URL.
   * @param opts - Optional `resultId` label (default `"bobalink"`).
   * @returns The {@link AddResult}.
   */
  async addMagnet(
    magnetUri: string,
    opts: { resultId?: string } = {},
  ): Promise<AddResult> {
    return this.addMagnets([magnetUri], opts);
  }

  /**
   * Add multiple magnets/URLs in one request (batch). POSTs to
   * `/api/v1/download` with `download_urls` as the array.
   *
   * @param magnetUris - Magnet URIs / download URLs.
   * @param opts - Optional `resultId` label.
   * @returns The {@link AddResult}.
   */
  async addMagnets(
    magnetUris: readonly string[],
    opts: { resultId?: string } = {},
  ): Promise<AddResult> {
    const payload = {
      result_id: opts.resultId ?? DEFAULT_RESULT_ID,
      download_urls: [...magnetUris],
    };
    this.log.info(
      `POST /api/v1/download urls=${String(magnetUris.length)} [token: ${this.token ? "set" : "none"}]`,
    );
    const { status, body } = await this.requestWithRetry("/api/v1/download", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return BobaClient.toAddResult(status, body);
  }

  /**
   * Probe `/health`. Returns `{ok, raw}` rather than throwing on a non-2xx,
   * so callers can render the result directly.
   *
   * @returns `{ok, status?, raw}`.
   */
  async health(): Promise<{ ok: boolean; status: string | null; raw: unknown }> {
    try {
      const { body } = await this.requestWithRetry("/health", {
        method: "GET",
      });
      const rec =
        body !== null && typeof body === "object"
          ? (body as Record<string, unknown>)
          : {};
      const status = typeof rec.status === "string" ? rec.status : null;
      return { ok: status === "healthy" || status === null, status, raw: body };
    } catch (err) {
      this.log.warn("health probe failed");
      return {
        ok: false,
        status: null,
        raw: err instanceof Error ? { error: err.message } : { error: String(err) },
      };
    }
  }

  /**
   * Fetch the backend auth-gate status (`/api/v1/auth/status`).
   *
   * @returns The raw parsed body.
   */
  async authStatus(): Promise<unknown> {
    const { body } = await this.requestWithRetry("/api/v1/auth/status", {
      method: "GET",
    });
    return body;
  }
}
