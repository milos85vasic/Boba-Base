/**
 * @fileoverview SECURITY — Content-Security-Policy audit (Plan E §3.2).
 *
 * Imports the REAL wxt.config and parses the
 * `manifest.content_security_policy.extension_pages` CSP string into a
 * directive → source-list map, then asserts the security-relevant directives.
 *
 * Anti-bluff (§11.4): the CSP is parsed from the actual shipped string. If a
 * regression added `'unsafe-inline'` / `'unsafe-eval'` to `script-src`, loosened
 * `object-src`, or widened `connect-src` past the merge service, the matching
 * assertion FAILs.
 *
 * @module tests/security/csp.test
 */

import { describe, it, expect, vi } from "vitest";

// See manifest-least-privilege.test.ts: stub `wxt`'s `defineConfig` to identity
// so importing wxt.config.ts does not pull in esbuild (which breaks under the
// jsdom TextEncoder). The real manifest object is returned unchanged.
vi.mock("wxt", () => ({
  defineConfig: <T>(config: T): T => config,
}));

const wxtConfig = (await import("../../wxt.config")).default;

const manifest = wxtConfig.manifest as {
  content_security_policy?:
    | { extension_pages?: string; sandbox?: string }
    | string;
};
const cspObject = manifest.content_security_policy;

/** The extension_pages CSP string as it ships in the manifest. */
const extensionPagesCsp =
  typeof cspObject === "object" && cspObject
    ? (cspObject.extension_pages ?? "")
    : "";

/**
 * Parse a CSP string into a Map of directive → array of sources.
 * e.g. "script-src 'self'; object-src 'self'" →
 *   { "script-src": ["'self'"], "object-src": ["'self'"] }
 */
function parseCsp(csp: string): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const segment of csp.split(";")) {
    const parts = segment.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) continue;
    const directive = (parts[0] as string).toLowerCase();
    map.set(directive, parts.slice(1));
  }
  return map;
}

const directives = parseCsp(extensionPagesCsp);

describe("CSP — extension_pages is present and parseable", () => {
  it("ships a non-empty extension_pages CSP string", () => {
    // Guard: an empty CSP would make every 'unsafe-*' negative check a tautology.
    expect(typeof extensionPagesCsp).toBe("string");
    expect(extensionPagesCsp.length).toBeGreaterThan(0);
    expect(directives.size).toBeGreaterThan(0);
  });
});

describe("CSP — script-src is locked to 'self' (no inline / eval)", () => {
  it("declares a script-src directive", () => {
    expect(directives.has("script-src")).toBe(true);
  });

  it("script-src contains 'self'", () => {
    expect(directives.get("script-src")).toContain("'self'");
  });

  it("script-src does NOT allow 'unsafe-inline'", () => {
    // Catches: re-introducing inline scripts (XSS surface). FAILs if present.
    expect(directives.get("script-src")).not.toContain("'unsafe-inline'");
  });

  it("script-src does NOT allow 'unsafe-eval'", () => {
    expect(directives.get("script-src")).not.toContain("'unsafe-eval'");
  });

  it("script-src does NOT allow 'wasm-unsafe-eval' or remote http(s) origins", () => {
    const sources = directives.get("script-src") ?? [];
    expect(sources).not.toContain("'wasm-unsafe-eval'");
    for (const src of sources) {
      // Only 'self' / keyword sources allowed; no remote script origin.
      expect(src).not.toMatch(/^https?:\/\//);
      expect(src).not.toBe("*");
    }
  });
});

describe("CSP — object-src is locked to 'self'", () => {
  it("object-src is exactly 'self' (no plugins / data: objects)", () => {
    expect(directives.get("object-src")).toEqual(["'self'"]);
  });
});

describe("CSP — connect-src is scoped to the Boba merge service only", () => {
  it("declares a connect-src directive", () => {
    expect(directives.has("connect-src")).toBe(true);
  });

  it("connect-src allows the merge service origin (localhost:7187)", () => {
    expect(directives.get("connect-src")).toContain("http://localhost:7187");
  });

  it("connect-src does NOT allow a wildcard or arbitrary remote origin", () => {
    // Catches: exfiltration channel widening. The extension must only be able to
    // talk to localhost:7187 (+ 'self'); '*' or any other host FAILs.
    const sources = directives.get("connect-src") ?? [];
    expect(sources).not.toContain("*");
    expect(sources).not.toContain("'unsafe-inline'");
    for (const src of sources) {
      const allowed = src === "'self'" || src === "http://localhost:7187";
      expect(allowed).toBe(true);
    }
  });
});

describe("CSP — hardening directives", () => {
  it("default-src is 'self' (deny-by-default base policy)", () => {
    expect(directives.get("default-src")).toEqual(["'self'"]);
  });

  it("base-uri is locked to 'none' (no <base> hijack)", () => {
    expect(directives.get("base-uri")).toEqual(["'none'"]);
  });

  it("frame-ancestors is 'none' (no clickjacking embedding)", () => {
    expect(directives.get("frame-ancestors")).toEqual(["'none'"]);
  });
});
