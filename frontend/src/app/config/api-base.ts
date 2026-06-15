import { InjectionToken } from '@angular/core';

/**
 * Base URL for the merge-search / download-proxy REST + SSE API.
 *
 * BUG-5 (search-flow-audit-20260615): the dashboard may be served from a
 * different origin than the API (a remote/standalone API instance). A
 * relative base (`''`) makes every HTTP request AND the EventSource stream
 * hit the *page* origin instead of the configured API, so the dashboard
 * silently talks to the wrong host. Per CLAUDE.md (no hardcoded
 * localhost/127.0.0.1), the base MUST be configurable and derive from the
 * request/runtime context.
 *
 * Resolution order (first non-empty wins):
 *   1. a build/deploy-time global `window.__BOBA_API_BASE__` (set by an
 *      index.html snippet or a config.js served alongside the dashboard);
 *   2. a `<meta name="boba-api-base" content="https://host:7187">` tag;
 *   3. empty string '' — same-origin relative behaviour (back-compat: a
 *      dashboard co-served with the API keeps working unchanged).
 *
 * A trailing slash is always stripped so callers can safely concatenate
 * `${base}/api/v1/...`.
 */
export const API_BASE_URL = new InjectionToken<string>('API_BASE_URL', {
  providedIn: 'root',
  factory: resolveApiBase,
});

/** Strip a single trailing slash so `${base}/api/...` never doubles up. */
export function normalizeApiBase(raw: string | null | undefined): string {
  if (!raw) return '';
  return raw.replace(/\/+$/, '');
}

/**
 * Discover the configured API base from the runtime environment. Returns
 * '' (same-origin) when nothing is configured.
 */
export function resolveApiBase(): string {
  if (typeof window === 'undefined') return '';

  const win = window as unknown as { __BOBA_API_BASE__?: string };
  if (win.__BOBA_API_BASE__) {
    return normalizeApiBase(win.__BOBA_API_BASE__);
  }

  if (typeof document !== 'undefined') {
    const meta = document.querySelector('meta[name="boba-api-base"]');
    const content = meta?.getAttribute('content');
    if (content) return normalizeApiBase(content);
  }

  return '';
}
