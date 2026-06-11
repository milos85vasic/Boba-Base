/**
 * @fileoverview Anti-bluff unit tests for the theme (light/dark/auto) feature.
 *
 * Phase 6 ships a minimal theme system: an explicit user preference
 * ("light" / "dark") wins over the OS preference, and "auto" follows
 * `prefers-color-scheme`. The applied preference is expressed as
 * `document.documentElement.dataset.theme`, which the stylesheets'
 * `[data-theme="..."]` override blocks key off — so this attribute is the
 * USER-OBSERVABLE state that drives the rendered colours (§11.4 / §11.4.69).
 *
 * Both the popup and the options module expose the SAME `applyTheme(doc, theme)`
 * surface; these tests drive the REAL exported functions from both production
 * modules and assert the resulting DOM attribute — not a return code, not
 * "no error". Each assertion fails against the pre-change code, which exports
 * no `applyTheme` and never sets `data-theme` (RED).
 *
 * Determinism: the matrix is run identically for both modules and is free of
 * timers / randomness, so repeated `vitest run` invocations are byte-identical.
 *
 * @module tests/unit/theme.test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { applyTheme as applyThemePopup } from "../../src/popup/popup";
import { applyTheme as applyThemeOptions } from "../../src/options/options";

/**
 * Install a deterministic `window.matchMedia` stub that reports the given
 * `prefers-color-scheme: dark` match state. Returns the original so it can be
 * restored. jsdom ships no `matchMedia`, so the stub is also what makes the
 * "auto" branch reachable at all.
 */
function stubMatchMedia(prefersDark: boolean): void {
  vi.stubGlobal(
    "matchMedia",
    (query: string): Pick<MediaQueryList, "matches" | "media"> => ({
      matches: query.includes("dark") ? prefersDark : !prefersDark,
      media: query,
    }),
  );
}

beforeEach(() => {
  // Start from a clean root each test — no stale attribute leaks across cases.
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-theme");
});

describe.each([
  ["popup", applyThemePopup],
  ["options", applyThemeOptions],
])("applyTheme — %s module", (_label, applyTheme) => {
  it('theme "dark" sets documentElement.dataset.theme = "dark"', () => {
    applyTheme(document, "dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it('theme "light" sets documentElement.dataset.theme = "light"', () => {
    applyTheme(document, "light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it('theme "auto" follows prefers-color-scheme: dark → "dark"', () => {
    stubMatchMedia(true);
    applyTheme(document, "auto");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it('theme "auto" follows prefers-color-scheme: light → "light"', () => {
    stubMatchMedia(false);
    applyTheme(document, "auto");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it('switching dark → light updates the attribute (no stale value)', () => {
    applyTheme(document, "dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    applyTheme(document, "light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("an undefined preference resolves to auto (matchMedia)", () => {
    stubMatchMedia(true);
    // `undefined` exercises the param default — the path that fires when a
    // stored config has no `theme` field yet (the deferred-control state).
    applyTheme(document, undefined);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
