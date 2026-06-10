/**
 * i18n locale-parity guard (Phase 6 — locales `ru`, `de`, `fr`, `es`, `it`,
 * `pt`, `ja`).
 *
 * The user-observable property: every non-default locale renders the SAME
 * set of UI strings the default locale (en) renders — no key the en catalog
 * defines is missing from a translation (which would fall back to the literal
 * token / empty string for that locale's user), and no stray key exists in a
 * translation that en lacks (a dead translation pointing at nothing). Chrome
 * resolves each `__MSG_foo__` / `i18n.getMessage("foo")` against the active
 * locale's catalog; if a locale drops `foo`, that locale's user sees a broken
 * label even though the en test stays green.
 *
 * This test loads BOTH real parsed catalogs (en source-of-truth + each
 * translation) from disk and asserts PARITY, for EACH locale in LOCALES:
 *   1. the locale has EXACTLY the same key set as en (no missing, no extra).
 *   2. every locale `message` is a non-empty string.
 *   3. every substitution token present in an en message (Chrome `$NAME$` /
 *      positional `$1`..`$9`, or a leftover `__MSG_*__`) is also present in
 *      the corresponding locale message — so a translation can't silently drop
 *      a placeholder and break interpolation for that locale's users.
 *
 * The key set is diffed from the REAL parsed catalogs, not hard-coded, so
 * adding a key to en (or dropping one from a translation) turns this test red.
 */
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const EXT_ROOT = resolve(__dirname, "..", "..");
const LOCALES_DIR = join(EXT_ROOT, "src", "public", "_locales");

/** Every non-default locale catalog that must stay in parity with en. */
const LOCALES = ["ru", "de", "fr", "es", "it", "pt", "ja"] as const;

const EN_PATH = join(LOCALES_DIR, "en", "messages.json");
const localePath = (locale: string): string =>
  join(LOCALES_DIR, locale, "messages.json");

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

describe("i18n locale parity (en ⇄ {ru, de, fr, es, it, pt, ja})", () => {
  it("the en source-of-truth catalog is valid JSON with at least one key", () => {
    const en = loadCatalog(EN_PATH);
    expect(Object.keys(en).length).toBeGreaterThan(0);
  });

  it.each(LOCALES)(
    "%s catalog is valid JSON with at least one key",
    (locale) => {
      const cat = loadCatalog(localePath(locale));
      expect(Object.keys(cat).length).toBeGreaterThan(0);
    },
  );

  it.each(LOCALES)(
    "%s has EXACTLY the same key set as en (no missing, no extra)",
    (locale) => {
      const enKeys = new Set(Object.keys(loadCatalog(EN_PATH)));
      const localeKeys = new Set(Object.keys(loadCatalog(localePath(locale))));

      const missing = [...enKeys].filter((k) => !localeKeys.has(k)).sort();
      const extra = [...localeKeys].filter((k) => !enKeys.has(k)).sort();

      expect(
        missing,
        `${locale} is missing keys present in en: ${missing.join(", ")}`,
      ).toEqual([]);
      expect(
        extra,
        `${locale} has keys not present in en: ${extra.join(", ")}`,
      ).toEqual([]);
      // Same cardinality is implied by the two empty-diff assertions above, but
      // assert it explicitly so the parity claim is unambiguous.
      expect(localeKeys.size).toBe(enKeys.size);
    },
  );

  it.each(LOCALES)("every %s message is a non-empty string", (locale) => {
    const cat = loadCatalog(localePath(locale));
    for (const [name, entry] of Object.entries(cat)) {
      expect(entry, `${locale} entry "${name}" must be an object`).toBeTypeOf(
        "object",
      );
      expect(
        typeof entry.message,
        `${locale} entry "${name}" must have a "message" string`,
      ).toBe("string");
      expect(
        entry.message.trim().length,
        `${locale} entry "${name}" must have a non-empty message`,
      ).toBeGreaterThan(0);
    }
  });

  it.each(LOCALES)(
    "every placeholder token in an en message is preserved in %s",
    (locale) => {
      const en = loadCatalog(EN_PATH);
      const cat = loadCatalog(localePath(locale));

      const violations: string[] = [];
      for (const [name, enEntry] of Object.entries(en)) {
        const localeEntry = cat[name];
        if (!localeEntry || typeof localeEntry.message !== "string") continue; // covered by the key-parity test
        const enTokens = extractPlaceholders(enEntry.message);
        if (enTokens.length === 0) continue;
        const localeTokens = new Set(extractPlaceholders(localeEntry.message));
        const dropped = enTokens.filter((t) => !localeTokens.has(t));
        if (dropped.length > 0) {
          violations.push(`${name}: dropped ${dropped.join(", ")}`);
        }
      }

      expect(
        violations,
        `${locale} translations dropped placeholder tokens present in en: ${violations.join("; ")}`,
      ).toEqual([]);
    },
  );
});
