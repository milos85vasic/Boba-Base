/**
 * i18n message-key completeness guard (Phase 6).
 *
 * The user-observable property: no `__MSG_missing__` / unresolved i18n key
 * is ever rendered to the user. Chrome resolves `__MSG_foo__` tokens (in the
 * manifest) and `i18n.getMessage("foo")` lookups (in code) against the
 * default-locale catalog at `_locales/en/messages.json`. A referenced key
 * with no catalog entry renders as the literal token / an empty string — a
 * broken UI label.
 *
 * This test re-derives the *referenced* key set from the real source files
 * (wxt.config.ts + every popup/options HTML + every TS source file) at test
 * time, then asserts every referenced key resolves to a non-empty message in
 * the catalog. The expected key list is NOT hard-coded — it is extracted from
 * source — so the guard stays honest as the code evolves (a new
 * `__MSG_whatever__` token with no catalog entry turns this test red).
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const EXT_ROOT = resolve(__dirname, "..", "..");
const SRC_DIR = join(EXT_ROOT, "src");
const CATALOG_PATH = join(SRC_DIR, "public", "_locales", "en", "messages.json");

/** Recursively collect files under `dir` matching one of `exts`. */
function collectFiles(dir: string, exts: string[]): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === "_locales") continue;
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      out.push(...collectFiles(full, exts));
    } else if (exts.some((e) => entry.endsWith(e))) {
      out.push(full);
    }
  }
  return out;
}

/**
 * Derive the set of referenced i18n keys from the real source tree:
 *   - `__MSG_<name>__` tokens (manifest in wxt.config.ts + any HTML)
 *   - `i18n.getMessage("name")` / `browser.i18n.getMessage("name")` /
 *     `chrome.i18n.getMessage("name")` / bare `getMessage("name")` in TS.
 */
function deriveReferencedKeys(): Set<string> {
  const keys = new Set<string>();

  const sources: string[] = [
    join(EXT_ROOT, "wxt.config.ts"),
    ...collectFiles(SRC_DIR, [".html", ".ts", ".tsx"]),
  ];

  const msgToken = /__MSG_([A-Za-z0-9_@]+)__/g;
  // getMessage("name", ...) with optional i18n / browser.i18n / chrome.i18n prefix.
  const getMessageCall =
    /(?:(?:browser|chrome)\.)?(?:i18n\.)?getMessage\(\s*["'`]([A-Za-z0-9_@]+)["'`]/g;

  for (const file of sources) {
    let text: string;
    try {
      text = readFileSync(file, "utf8");
    } catch {
      continue; // wxt.config.ts is the only optional path; HTML/TS always exist
    }
    for (const m of text.matchAll(msgToken)) {
      if (m[1] !== undefined) keys.add(m[1]);
    }
    for (const m of text.matchAll(getMessageCall)) {
      if (m[1] !== undefined) keys.add(m[1]);
    }
  }

  return keys;
}

interface CatalogEntry {
  message: string;
  description?: string;
}

function loadCatalogRaw(): string {
  return readFileSync(CATALOG_PATH, "utf8");
}

function loadCatalog(): Record<string, CatalogEntry> {
  return JSON.parse(loadCatalogRaw()) as Record<string, CatalogEntry>;
}

describe("i18n locale catalog (en) completeness", () => {
  it("is valid JSON and every entry has a non-empty string message", () => {
    const catalog = loadCatalog();
    const names = Object.keys(catalog);
    expect(names.length).toBeGreaterThan(0);

    for (const [name, entry] of Object.entries(catalog)) {
      expect(entry, `entry "${name}" must be an object`).toBeTypeOf("object");
      expect(
        typeof entry.message,
        `entry "${name}" must have a "message" string`,
      ).toBe("string");
      expect(
        entry.message.trim().length,
        `entry "${name}" must have a non-empty message`,
      ).toBeGreaterThan(0);
    }
  });

  it("has no duplicate keys in the raw catalog JSON", () => {
    const raw = loadCatalogRaw();
    // Top-level keys live at two-space indent in the formatted catalog.
    const keyLine = /^ {2}"([A-Za-z0-9_@]+)":/gm;
    const seen = new Set<string>();
    const dups: string[] = [];
    for (const m of raw.matchAll(keyLine)) {
      const key = m[1];
      if (key === undefined) continue;
      if (seen.has(key)) dups.push(key);
      seen.add(key);
    }
    expect(dups, `duplicate catalog keys: ${dups.join(", ")}`).toEqual([]);
  });

  it("derives at least the known manifest keys from real source", () => {
    // Sanity: the derivation actually finds tokens (guards against a regex
    // that silently matches nothing, which would make completeness vacuous).
    const referenced = deriveReferencedKeys();
    expect(referenced.size).toBeGreaterThan(0);
    // extName / extDescription / the three command descriptions live in
    // wxt.config.ts as __MSG_*__ tokens and must be discoverable.
    for (const k of [
      "extName",
      "extDescription",
      "cmdSendToBoba",
      "cmdScanPage",
      "cmdOpenDashboard",
    ]) {
      expect(referenced.has(k), `expected to derive "${k}" from source`).toBe(
        true,
      );
    }
  });

  it("every referenced i18n key resolves to a non-empty catalog message", () => {
    const catalog = loadCatalog();
    const referenced = deriveReferencedKeys();

    const missing: string[] = [];
    for (const key of referenced) {
      const entry = catalog[key];
      if (!entry || typeof entry.message !== "string" || entry.message.trim() === "") {
        missing.push(key);
      }
    }

    expect(
      missing,
      `referenced i18n keys missing a non-empty catalog message: ${missing.join(", ")}`,
    ).toEqual([]);
  });
});
