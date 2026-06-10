/**
 * @fileoverview SECURITY — least-privilege manifest audit (§11.4.10 + Plan E §3.1).
 *
 * Imports the REAL wxt.config (the config object `defineConfig` returns) and
 * asserts on its `manifest.permissions` + `manifest.host_permissions` arrays —
 * the exact values that ship into the generated MV3 manifest the browser reads.
 *
 * Anti-bluff (§11.4): every assertion inspects the actual parsed manifest array.
 * If someone added a broad/dangerous permission (`scripting`, `tabs`,
 * `webRequest`, `cookies`, `<all_urls>`) the matching test FAILS — i.e. the
 * test catches an over-privileged manifest, not "the file exists".
 *
 * @module tests/security/manifest-least-privilege.test
 */

import { describe, it, expect, vi } from "vitest";

// `wxt.config.ts` does `import { defineConfig } from "wxt"`, and the real `wxt`
// package eagerly loads `esbuild`, which throws under the jsdom TextEncoder.
// We only need the manifest LITERAL, so stub `defineConfig` to identity — the
// config object (and thus the real manifest) is returned unchanged, exactly as
// the real `defineConfig` does (verified: it returns its argument as-is).
vi.mock("wxt", () => ({
  defineConfig: <T>(config: T): T => config,
}));

const wxtConfig = (await import("../../wxt.config")).default;

/**
 * Resolve the manifest object the same way WXT will at build time.
 * `defineConfig` returns the config object unchanged, so `manifest` is the
 * literal object declared in wxt.config.ts.
 */
const manifest = wxtConfig.manifest as {
  manifest_version: number;
  permissions: string[];
  host_permissions: string[];
  optional_permissions?: string[];
  optional_host_permissions?: string[];
};

/** Permissions a browser surfaces as "scary"/broad — none may be requested. */
const FORBIDDEN_PERMISSIONS = [
  "scripting",
  "tabs",
  "webRequest",
  "webRequestBlocking",
  "cookies",
  "<all_urls>",
  "history",
  "bookmarks",
  "downloads",
  "management",
  "proxy",
  "privacy",
  "debugger",
  "declarativeNetRequest",
] as const;

/** Host-permission wildcards that would grant access to every site. */
const FORBIDDEN_HOST_WILDCARDS = [
  "<all_urls>",
  "*://*/*",
  "http://*/*",
  "https://*/*",
  "*://*/",
  "<all_urls>/*",
] as const;

describe("manifest least-privilege — permissions array", () => {
  it("is a real Manifest V3 manifest object", () => {
    // Guards the rest of the suite: if the import shape changes (manifest moved
    // / not parseable), this fails loudly instead of silently passing on an
    // undefined array (which would make every `not.toContain` a tautology).
    expect(manifest.manifest_version).toBe(3);
    expect(Array.isArray(manifest.permissions)).toBe(true);
    expect(Array.isArray(manifest.host_permissions)).toBe(true);
  });

  it("requests ONLY the five least-privilege permissions (exact set)", () => {
    // Catches: any NEW permission added to the array (the array is sorted-compared,
    // so adding `scripting` or `tabs` changes the set and FAILs).
    expect([...manifest.permissions].sort()).toEqual(
      ["activeTab", "alarms", "contextMenus", "notifications", "storage"].sort(),
    );
  });

  it.each(FORBIDDEN_PERMISSIONS)(
    "does NOT request the broad/dangerous permission %s",
    (perm) => {
      // Catches: a regression that adds this exact permission. Flip the
      // expectation mentally — if `scripting` were present, this FAILs.
      expect(manifest.permissions).not.toContain(perm);
    },
  );

  it("does not declare optional_permissions escalation hooks for broad perms", () => {
    // optional_permissions are user-grantable at runtime — they must also stay
    // free of the broad set. Absent is fine; present-with-broad is a violation.
    const optional = manifest.optional_permissions ?? [];
    for (const perm of FORBIDDEN_PERMISSIONS) {
      expect(optional).not.toContain(perm);
    }
  });
});

describe("manifest least-privilege — host_permissions scoping", () => {
  it("is scoped to ONLY the Boba merge service on localhost:7187", () => {
    // Catches: widening host access. The exact-array compare FAILs the moment
    // any extra origin (or a wildcard) is added.
    expect(manifest.host_permissions).toEqual(["http://localhost:7187/*"]);
  });

  it.each(FORBIDDEN_HOST_WILDCARDS)(
    "does NOT grant the all-sites host wildcard %s",
    (wildcard) => {
      expect(manifest.host_permissions).not.toContain(wildcard);
    },
  );

  it("every host_permission entry targets localhost:7187 (no cross-origin reach)", () => {
    // Substring + scheme assertion so even a non-listed-wildcard new origin
    // (e.g. "https://evil.example/*") is rejected.
    for (const origin of manifest.host_permissions) {
      expect(origin).toMatch(/^http:\/\/localhost:7187\//);
      expect(origin).not.toContain("*://");
      expect(origin).not.toContain("/*/*");
    }
  });

  it("optional_host_permissions (if present) never widen beyond localhost:7187", () => {
    const optionalHosts = manifest.optional_host_permissions ?? [];
    for (const origin of optionalHosts) {
      expect(origin).toMatch(/^http:\/\/localhost:7187\//);
    }
    for (const wildcard of FORBIDDEN_HOST_WILDCARDS) {
      expect(optionalHosts).not.toContain(wildcard);
    }
  });
});
