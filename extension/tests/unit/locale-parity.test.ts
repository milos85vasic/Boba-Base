/**
 * i18n locale-parity guard (Phase 6 — second locale `ru`).
 *
 * The user-observable property: a non-default locale (ru) renders the SAME
 * set of UI strings the default locale (en) renders — no key the en catalog
 * defines is missing from ru (which would fall back to the literal token /
 * empty string for a Russian-locale user), and no stray key exists in ru that
 * en lacks (a dead translation pointing at nothing). Chrome resolves each
 * `__MSG_foo__` / `i18n.getMessage("foo")` against the active locale's
 * catalog; if ru drops `foo`, a ru user sees a broken label even though the
 * en test stays green.
 *
 * This test loads BOTH real parsed catalogs (en source-of-truth + ru) from
 * disk and asserts PARITY:
 *   1. ru has EXACTLY the same key set as en (no missing key, no extra key).
 *   2. every ru `message` is a non-empty string.
 *   3. every substitution token present in an en message (Chrome `$NAME$` /
 *      positional `$1`..`$9`, or a leftover `__MSG_*__`) is also present in
 *      the corresponding ru message — so a translation can't silently drop a
 *      placeholder and break interpolation for ru users.
 *
 * The key set is diffed from the two REAL parsed catalogs, not hard-coded, so
 * adding a key to en (or dropping one from ru) turns this test red.
 */
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const EXT_ROOT = resolve(__dirname, "..", "..");
const LOCALES_DIR = join(EXT_ROOT, "src", "public", "_locales");
const EN_PATH = join(LOCALES_DIR, "en", "messages.json");
const RU_PATH = join(LOCALES_DIR, "ru", "messages.json");

interface CatalogEntry {
  message: string;
  description?: string;
}

function loadCatalog(path: string): Record<string, CatalogEntry> {
  return JSON.parse(readFileSync(path, "utf8")) as Record<string, CatalogEntry>;
}

/**
 * Extract substitution / interpolation tokens from a message string:
 *   - Chrome named placeholders `$NAME$` (e.g. `$COUNT$`)
 *   - positional placeholders `$1` .. `$9`
 *   - leftover `__MSG_name__` references
 * Returned sorted + de-duplicated so two messages are token-comparable.
 */
function extractPlaceholders(message: string): string[] {
  const tokens = new Set<string>();
  for (const m of message.matchAll(/\$[A-Za-z0-9_@]+\$/g)) tokens.add(m[0]);
  for (const m of message.matchAll(/\$[1-9]/g)) tokens.add(m[0]);
  for (const m of message.matchAll(/__MSG_[A-Za-z0-9_@]+__/g)) tokens.add(m[0]);
  return [...tokens].sort();
}

describe("i18n locale parity (en ⇄ ru)", () => {
  it("both catalogs are valid JSON with at least one key", () => {
    const en = loadCatalog(EN_PATH);
    const ru = loadCatalog(RU_PATH);
    expect(Object.keys(en).length).toBeGreaterThan(0);
    expect(Object.keys(ru).length).toBeGreaterThan(0);
  });

  it("ru has EXACTLY the same key set as en (no missing, no extra)", () => {
    const enKeys = new Set(Object.keys(loadCatalog(EN_PATH)));
    const ruKeys = new Set(Object.keys(loadCatalog(RU_PATH)));

    const missingInRu = [...enKeys].filter((k) => !ruKeys.has(k)).sort();
    const extraInRu = [...ruKeys].filter((k) => !enKeys.has(k)).sort();

    expect(
      missingInRu,
      `ru is missing keys present in en: ${missingInRu.join(", ")}`,
    ).toEqual([]);
    expect(
      extraInRu,
      `ru has keys not present in en: ${extraInRu.join(", ")}`,
    ).toEqual([]);
    // Same cardinality is implied by the two empty-diff assertions above, but
    // assert it explicitly so the parity claim is unambiguous.
    expect(ruKeys.size).toBe(enKeys.size);
  });

  it("every ru message is a non-empty string", () => {
    const ru = loadCatalog(RU_PATH);
    for (const [name, entry] of Object.entries(ru)) {
      expect(entry, `ru entry "${name}" must be an object`).toBeTypeOf(
        "object",
      );
      expect(
        typeof entry.message,
        `ru entry "${name}" must have a "message" string`,
      ).toBe("string");
      expect(
        entry.message.trim().length,
        `ru entry "${name}" must have a non-empty message`,
      ).toBeGreaterThan(0);
    }
  });

  it("every placeholder token in an en message is preserved in ru", () => {
    const en = loadCatalog(EN_PATH);
    const ru = loadCatalog(RU_PATH);

    const violations: string[] = [];
    for (const [name, enEntry] of Object.entries(en)) {
      const ruEntry = ru[name];
      if (!ruEntry || typeof ruEntry.message !== "string") continue; // covered by the key-parity test
      const enTokens = extractPlaceholders(enEntry.message);
      if (enTokens.length === 0) continue;
      const ruTokens = new Set(extractPlaceholders(ruEntry.message));
      const dropped = enTokens.filter((t) => !ruTokens.has(t));
      if (dropped.length > 0) {
        violations.push(`${name}: dropped ${dropped.join(", ")}`);
      }
    }

    expect(
      violations,
      `ru translations dropped placeholder tokens present in en: ${violations.join("; ")}`,
    ).toEqual([]);
  });
});
