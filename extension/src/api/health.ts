/**
 * @fileoverview Health-probe helper for the Boba merge service (:7187).
 *
 * Probes `GET <base>/health` on the Boba merge service and reports
 * reachability + round-trip latency. Used by the popup/options to show
 * a connection indicator and by auto-discovery to confirm a base URL
 * actually answers.
 *
 * Contract (docs/browser_extension/_plan/A-backend-contract.md):
 *   GET http://<base>:7187/health → {status:"healthy",service,version}
 *
 * This module is a thin, dependency-light wrapper around `fetch` with an
 * `AbortController` timeout. It NEVER throws — an unreachable server is a
 * value (`reachable:false`), not an exception — so callers can render it
 * directly. It deliberately holds no auth: `/health` is unauthenticated by
 * the backend contract, so no token is ever sent here (and thus never
 * logged — §11.4.10).
 *
 * @module api/health
 */

import { REQUEST_TIMEOUTS } from "../shared/constants";

/**
 * Outcome of a single health probe.
 */
export interface HealthProbeResult {
  /** Whether the server answered with a 2xx response. */
  readonly reachable: boolean;

  /** HTTP status code of the response, or null if the request never completed. */
  readonly statusCode: number | null;

  /** Round-trip latency in milliseconds (measured even on failure). */
  readonly latencyMs: number;

  /** Parsed `status` field from the body (e.g. "healthy"), or null. */
  readonly status: string | null;

  /** Parsed `service`/`version` fields from the body, when present. */
  readonly service: string | null;
  readonly version: string | null;

  /** Error message if the probe failed (timeout / network / non-2xx). */
  readonly error: string | null;
}

/**
 * Build the `/health` URL from a base URL, tolerating a trailing slash.
 *
 * @param baseUrl - Base URL of the Boba merge service (e.g. http://localhost:7187)
 * @returns The fully-qualified `/health` URL.
 */
export function healthUrl(baseUrl: string): string {
  return `${baseUrl.replace(/\/+$/, "")}/health`;
}

/**
 * Probe the Boba merge service `/health` endpoint.
 *
 * Never throws: a timeout, network failure, or non-2xx status is reported as
 * `reachable:false` with the measured latency and an error message.
 *
 * @param baseUrl - Base URL of the Boba merge service.
 * @param opts - Optional `timeoutMs` (defaults to the health-check timeout) and
 *   `fetchImpl` (defaults to the global `fetch`; injectable for tests).
 * @returns A {@link HealthProbeResult} describing the outcome.
 */
export async function probeHealth(
  baseUrl: string,
  opts: { timeoutMs?: number; fetchImpl?: typeof fetch } = {},
): Promise<HealthProbeResult> {
  const timeoutMs = opts.timeoutMs ?? REQUEST_TIMEOUTS.HEALTH_CHECK;
  const fetchImpl = opts.fetchImpl ?? fetch;
  const url = healthUrl(baseUrl);
  const started = Date.now();

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetchImpl(url, {
      method: "GET",
      signal: controller.signal,
      headers: { Accept: "application/json" },
    });
    const latencyMs = Date.now() - started;

    let status: string | null = null;
    let service: string | null = null;
    let version: string | null = null;
    try {
      const body = (await res.json()) as Record<string, unknown>;
      status = typeof body.status === "string" ? body.status : null;
      service = typeof body.service === "string" ? body.service : null;
      version = typeof body.version === "string" ? body.version : null;
    } catch {
      // Body was not JSON; reachability is still determined by res.ok.
    }

    return {
      reachable: res.ok,
      statusCode: res.status,
      latencyMs,
      status,
      service,
      version,
      error: res.ok ? null : `HTTP ${String(res.status)}`,
    };
  } catch (err) {
    const latencyMs = Date.now() - started;
    const aborted =
      err instanceof Error && err.name === "AbortError";
    return {
      reachable: false,
      statusCode: null,
      latencyMs,
      status: null,
      service: null,
      version: null,
      error: aborted
        ? `timeout after ${String(timeoutMs)}ms`
        : err instanceof Error
          ? err.message
          : String(err),
    };
  } finally {
    clearTimeout(timer);
  }
}
